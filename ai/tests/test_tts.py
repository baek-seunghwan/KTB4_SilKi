from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from silki_ai.tts import EdgeTtsClient, FishSpeechTtsClient, TtsProviderError


class FakeEdgeCommunicator:
    def __init__(
        self,
        text: str,
        voice: str,
        *,
        rate: str,
        volume: str,
        pitch: str,
        messages: list[dict[str, object]],
        delay: float = 0,
    ) -> None:
        self.arguments = {
            "text": text,
            "voice": voice,
            "rate": rate,
            "volume": volume,
            "pitch": pitch,
        }
        self._messages = messages
        self._delay = delay

    async def stream(self):
        for message in self._messages:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield message


@pytest.mark.asyncio
async def test_edge_tts_client_collects_mp3_in_memory_with_configured_voice() -> None:
    observed: dict[str, object] = {}

    def factory(text: str, voice: str, **kwargs: str) -> FakeEdgeCommunicator:
        communicator = FakeEdgeCommunicator(
            text,
            voice,
            messages=[
                {"type": "WordBoundary", "offset": 0},
                {"type": "audio", "data": b"ID3"},
                {"type": "audio", "data": b"audio"},
            ],
            **kwargs,
        )
        observed.update(communicator.arguments)
        return communicator

    client = EdgeTtsClient(
        voice="ko-KR-SunHiNeural",
        rate="-5%",
        communicator_factory=factory,
    )

    audio = await client.synthesize("  따뜻한 아메리카노인지 알려주세요.  ")

    assert observed == {
        "text": "따뜻한 아메리카노인지 알려주세요.",
        "voice": "ko-KR-SunHiNeural",
        "rate": "-5%",
        "volume": "+0%",
        "pitch": "+0Hz",
    }
    assert audio.content == b"ID3audio"
    assert audio.media_type == "audio/mpeg"


@pytest.mark.asyncio
async def test_edge_tts_client_rejects_oversized_or_empty_audio() -> None:
    def oversized_factory(text: str, voice: str, **kwargs: str) -> FakeEdgeCommunicator:
        return FakeEdgeCommunicator(
            text,
            voice,
            messages=[{"type": "audio", "data": b"x" * 17}],
            **kwargs,
        )

    oversized = EdgeTtsClient(max_audio_bytes=16, communicator_factory=oversized_factory)
    with pytest.raises(TtsProviderError, match="size limit"):
        await oversized.synthesize("안내 문장")

    def empty_factory(text: str, voice: str, **kwargs: str) -> FakeEdgeCommunicator:
        return FakeEdgeCommunicator(
            text,
            voice,
            messages=[{"type": "WordBoundary", "offset": 0}],
            **kwargs,
        )

    empty = EdgeTtsClient(communicator_factory=empty_factory)
    with pytest.raises(TtsProviderError, match="empty audio"):
        await empty.synthesize("안내 문장")


@pytest.mark.asyncio
async def test_edge_tts_client_enforces_a_whole_request_deadline() -> None:
    def factory(text: str, voice: str, **kwargs: str) -> FakeEdgeCommunicator:
        return FakeEdgeCommunicator(
            text,
            voice,
            messages=[{"type": "audio", "data": b"late"}],
            delay=0.05,
            **kwargs,
        )

    client = EdgeTtsClient(timeout_seconds=0.01, communicator_factory=factory)
    with pytest.raises(TtsProviderError, match="timed out"):
        await client.synthesize("시간 제한 테스트")


@pytest.mark.asyncio
async def test_fish_speech_client_uses_private_v1_contract_and_api_key() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=b"ID3audio")

    client = FishSpeechTtsClient(
        base_url="http://fish-audio.internal:8080",
        api_key="test-secret",
        audio_format="mp3",
        reference_id="silki-ko",
        transport=httpx.MockTransport(handler),
    )
    try:
        audio = await client.synthesize("제로 아이스티를 추천드려요.")
    finally:
        await client.aclose()

    assert observed == {
        "url": "http://fish-audio.internal:8080/v1/tts",
        "authorization": "Bearer test-secret",
        "payload": {
            "text": "제로 아이스티를 추천드려요.",
            "references": [],
            "reference_id": "silki-ko",
            "format": "mp3",
            "streaming": False,
        },
    }
    assert audio.content == b"ID3audio"
    assert audio.media_type == "audio/mpeg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"error": "busy"}),
        httpx.Response(200, headers={"content-type": "application/json"}, json={"x": 1}),
        httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=b""),
        httpx.Response(
            200,
            headers={"content-type": "audio/mpeg", "content-length": "100"},
            content=b"x" * 100,
        ),
    ],
)
async def test_fish_speech_client_rejects_failed_or_unsafe_responses(
    response: httpx.Response,
) -> None:
    client = FishSpeechTtsClient(
        base_url="http://fish-audio.internal:8080",
        api_key="test-secret",
        max_audio_bytes=16,
        transport=httpx.MockTransport(lambda _: response),
    )
    try:
        with pytest.raises(TtsProviderError):
            await client.synthesize("안내 문장")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_fish_speech_client_enforces_a_whole_request_deadline() -> None:
    async def slow_handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            headers={"content-type": "audio/mpeg"},
            content=b"late audio",
        )

    client = FishSpeechTtsClient(
        base_url="http://fish-audio.internal:8080",
        api_key="test-secret",
        timeout_seconds=0.01,
        transport=httpx.MockTransport(slow_handler),
    )
    try:
        with pytest.raises(TtsProviderError, match="timed out"):
            await client.synthesize("시간 제한 테스트")
    finally:
        await client.aclose()
