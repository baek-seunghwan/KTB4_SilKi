"""Non-streaming TTS providers used by the voice-order WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any, Literal

import edge_tts
import httpx

FishAudioFormat = Literal["wav", "mp3", "opus"]

_MEDIA_TYPES: dict[FishAudioFormat, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
}


class TtsProviderError(RuntimeError):
    """Raised when a TTS provider cannot produce a safe, usable response."""


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    content: bytes
    media_type: str


class EdgeTtsClient:
    """Generate an MP3 in memory with the third-party ``edge-tts`` client.

    This adapter deliberately exposes the same ``synthesize`` contract as the
    private Fish service.  It is intended as a convenient local/demo provider;
    callers can switch providers without changing the WebSocket contract.
    """

    def __init__(
        self,
        *,
        voice: str = "ko-KR-SunHiNeural",
        rate: str = "-5%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        timeout_seconds: float = 5.0,
        max_audio_bytes: int = 5 * 1024 * 1024,
        communicator_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._pitch = pitch
        self._timeout_seconds = timeout_seconds
        self._max_audio_bytes = max_audio_bytes
        self._communicator_factory = communicator_factory or edge_tts.Communicate

    async def synthesize(self, text: str) -> SynthesizedAudio:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("TTS text must not be blank")

        chunks: list[bytes] = []
        received = 0
        try:
            async with asyncio.timeout(self._timeout_seconds):
                communicator = self._communicator_factory(
                    normalized_text,
                    self._voice,
                    rate=self._rate,
                    volume=self._volume,
                    pitch=self._pitch,
                )
                async with aclosing(communicator.stream()) as stream:
                    async for message in stream:
                        if message.get("type") != "audio":
                            continue
                        chunk = message.get("data")
                        if not isinstance(chunk, bytes) or not chunk:
                            raise TtsProviderError("Edge TTS returned an invalid audio chunk")
                        received += len(chunk)
                        if received > self._max_audio_bytes:
                            raise TtsProviderError("Edge TTS response exceeds the size limit")
                        chunks.append(chunk)
        except TtsProviderError:
            raise
        except TimeoutError as exc:
            raise TtsProviderError("Edge TTS request timed out") from exc
        except Exception as exc:
            raise TtsProviderError("Edge TTS request failed") from exc

        content = b"".join(chunks)
        if not content:
            raise TtsProviderError("Edge TTS returned empty audio")
        return SynthesizedAudio(content=content, media_type="audio/mpeg")

    async def aclose(self) -> None:
        """Match the long-lived Fish client lifecycle; edge-tts owns each session."""


class FishSpeechTtsClient:
    """Call Fish Speech's self-hosted ``POST /v1/tts`` endpoint.

    S2 Pro is selected when the remote Fish Speech process is started with the
    S2 Pro checkpoints. The request deliberately uses ``streaming=false`` and
    never contains the API key in its URL or payload.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        audio_format: FishAudioFormat = "mp3",
        reference_id: str | None = None,
        timeout_seconds: float = 20.0,
        max_audio_bytes: int = 5 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/v1/tts"
        self._api_key = api_key
        self._audio_format = audio_format
        self._reference_id = reference_id
        self._timeout_seconds = timeout_seconds
        self._max_audio_bytes = max_audio_bytes
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            # This client targets a private service and carries an API key.
            # Never inherit process-wide HTTP_PROXY/HTTPS_PROXY values.
            trust_env=False,
            transport=transport,
        )

    async def synthesize(self, text: str) -> SynthesizedAudio:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("TTS text must not be blank")

        payload: dict[str, object] = {
            "text": normalized_text,
            "references": [],
            "reference_id": self._reference_id,
            "format": self._audio_format,
            "streaming": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": _MEDIA_TYPES[self._audio_format],
        }

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._client.stream(
                    "POST",
                    self._endpoint,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code != httpx.codes.OK:
                        raise TtsProviderError(
                            f"Fish Audio returned HTTP {response.status_code}"
                        )

                    declared_length = response.headers.get("content-length")
                    if declared_length is not None:
                        try:
                            if int(declared_length) > self._max_audio_bytes:
                                raise TtsProviderError(
                                    "Fish Audio response exceeds the size limit"
                                )
                        except ValueError as exc:
                            raise TtsProviderError(
                                "Fish Audio returned an invalid Content-Length"
                            ) from exc

                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > self._max_audio_bytes:
                            raise TtsProviderError(
                                "Fish Audio response exceeds the size limit"
                            )
                        chunks.append(chunk)
        except TtsProviderError:
            raise
        except TimeoutError as exc:
            raise TtsProviderError("Fish Audio request timed out") from exc
        except httpx.HTTPError as exc:
            raise TtsProviderError("Fish Audio request failed") from exc

        content = b"".join(chunks)
        if not content:
            raise TtsProviderError("Fish Audio returned empty audio")

        response_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        expected_type = _MEDIA_TYPES[self._audio_format]
        if response_type in {expected_type, "application/octet-stream"}:
            media_type = expected_type
        else:
            raise TtsProviderError("Fish Audio returned an unexpected media type")
        return SynthesizedAudio(content=content, media_type=media_type)

    async def aclose(self) -> None:
        await self._client.aclose()
