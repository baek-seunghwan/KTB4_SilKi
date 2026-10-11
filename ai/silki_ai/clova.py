"""Async CLOVA Speech streaming adapter.

The adapter depends only on the protobuf modules generated from NAVER Cloud's
published ``nest.proto`` contract.  Imports are delayed until ``start()`` so
unit tests and non-speech application processes do not require grpcio or
generated modules at import time.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import math
import re
import sys
import unicodedata
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

CLOVA_MAX_KEYWORD_WEIGHT = 5.0
CLOVA_MAX_BOOSTING_KEYWORDS = 1_000
# NCP documents a 1,000-word hard limit but recommends staying at or below 500
# words because recognition quality degrades beyond that.
CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS = 500
DEFAULT_CLOVA_KEYWORD_PATH = Path(__file__).resolve().parent / "resources" / "clova_keywords.txt"

# A keyword-file section header such as ``# weight: 4`` starts a new boosting
# group; every other ``#`` line is a comment.
_WEIGHT_HEADER_PATTERN = re.compile(
    r"^#\s*weight\s*:\s*(?P<weight>\d+(?:\.\d+)?)\s*$", re.IGNORECASE
)


class ClovaEventKind(StrEnum):
    PARTIAL = "partial"
    FLUSHED = "flushed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ClovaEvent:
    kind: ClovaEventKind
    text: str = ""
    position: int = 0
    confidence: float | None = None
    seq_id: int = 0
    endpoint: bool = False
    is_final: bool = False
    epd_type: str | None = None
    response_type: tuple[str, ...] = ()
    error: str | None = None
    raw: Mapping[str, Any] | None = None
    generation: int = 0

    @property
    def ep_flag(self) -> bool:
        return self.endpoint


class ClovaError(RuntimeError):
    pass


class ClovaNotStarted(ClovaError):
    pass


class ClovaAudioFormatError(ClovaError, ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClovaKeywordGroup:
    """One entry of CLOVA's ``keywordBoosting.boostings`` array.

    ``weight=None`` means "no explicit weight": the caller's default weight
    (``settings.clova_keyword_weight`` in the application) is applied when the
    boosting configuration is built.
    """

    keywords: tuple[str, ...]
    weight: float | None = None


def _validate_keyword_weight(weight: float) -> float:
    normalized_weight = float(weight)
    valid_weight = (
        math.isfinite(normalized_weight) and 0 <= normalized_weight <= CLOVA_MAX_KEYWORD_WEIGHT
    )
    if not valid_weight:
        raise ValueError(f"CLOVA keyword weight must be between 0 and {CLOVA_MAX_KEYWORD_WEIGHT:g}")
    return normalized_weight


def normalize_clova_keywords(keywords: Iterable[str]) -> tuple[str, ...]:
    """Normalize and deduplicate direct CLOVA boosting words, preserving order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_keyword in keywords:
        keyword = unicodedata.normalize("NFC", " ".join(str(raw_keyword).split()))
        if not keyword or keyword in seen:
            continue
        if "," in keyword:
            raise ValueError(f"CLOVA boosting keyword cannot contain a comma: {keyword!r}")
        seen.add(keyword)
        normalized.append(keyword)
    if len(normalized) > CLOVA_MAX_BOOSTING_KEYWORDS:
        raise ValueError(
            f"CLOVA direct keyword boosting supports at most {CLOVA_MAX_BOOSTING_KEYWORDS} keywords"
        )
    if len(normalized) > CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS:
        logger.warning(
            "CLOVA keyword boosting uses %d keywords; NCP recommends at most %d "
            "because recognition quality degrades beyond that",
            len(normalized),
            CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS,
        )
    return tuple(normalized)


def parse_clova_keyword_groups(lines: Iterable[str]) -> tuple[ClovaKeywordGroup, ...]:
    """Split keyword-file lines into boosting groups on ``# weight: N`` headers.

    Lines before the first header form a group without an explicit weight,
    empty lines are skipped, and any other ``#`` line is a comment.
    """

    groups: list[ClovaKeywordGroup] = []
    current_weight: float | None = None
    current_keywords: list[str] = []

    def _flush() -> None:
        nonlocal current_keywords
        if current_keywords:
            groups.append(
                ClovaKeywordGroup(keywords=tuple(current_keywords), weight=current_weight)
            )
        current_keywords = []

    for raw_line in lines:
        line = raw_line.strip()
        if header := _WEIGHT_HEADER_PATTERN.match(line):
            _flush()
            current_weight = _validate_keyword_weight(float(header.group("weight")))
            continue
        if not line or line.startswith("#"):
            continue
        current_keywords.append(line)
    _flush()
    return tuple(groups)


def load_clova_keyword_groups(path: str | Path | None = None) -> tuple[ClovaKeywordGroup, ...]:
    """Load weighted boosting groups from the packaged or configured keyword file."""

    keyword_path = Path(path) if path is not None else DEFAULT_CLOVA_KEYWORD_PATH
    try:
        lines = keyword_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ClovaError(f"unable to load CLOVA keyword file: {keyword_path}") from exc
    return parse_clova_keyword_groups(lines)


def load_clova_keywords(path: str | Path | None = None) -> tuple[str, ...]:
    """Load the flat normalized keyword list, ignoring group headers and comments."""

    groups = load_clova_keyword_groups(path)
    return normalize_clova_keywords(
        keyword for group in groups for keyword in group.keywords
    )


BoostingKeywords = Iterable[str] | Iterable[ClovaKeywordGroup]


def _coerce_keyword_groups(keywords: BoostingKeywords) -> tuple[ClovaKeywordGroup, ...]:
    items = tuple(keywords)
    if not items:
        return ()
    if all(isinstance(item, ClovaKeywordGroup) for item in items):
        return items  # type: ignore[return-value]
    if any(isinstance(item, ClovaKeywordGroup) for item in items):
        raise TypeError("boosting keywords cannot mix plain strings with ClovaKeywordGroup")
    return (ClovaKeywordGroup(keywords=tuple(str(item) for item in items)),)


def build_keyword_boosting_config(
    keywords: BoostingKeywords, *, weight: float = CLOVA_MAX_KEYWORD_WEIGHT
) -> dict[str, Any]:
    """Build CLOVA's direct request-level keyword boosting configuration.

    ``keywords`` is either a flat iterable of words (one boosting group) or an
    iterable of :class:`ClovaKeywordGroup`, each serialized as one entry of the
    ``boostings`` array. A group without an explicit weight uses ``weight``.
    """

    default_weight = _validate_keyword_weight(weight)
    boostings: list[dict[str, Any]] = []
    combined_keywords: list[str] = []
    seen: set[str] = set()
    for group in _coerce_keyword_groups(keywords):
        group_weight = (
            default_weight if group.weight is None else _validate_keyword_weight(group.weight)
        )
        # Deduplicate across groups as well: the first group that mentions a
        # keyword owns it, so CLOVA never receives conflicting weights.
        words = tuple(
            keyword for keyword in normalize_clova_keywords(group.keywords) if keyword not in seen
        )
        if not words:
            continue
        seen.update(words)
        combined_keywords.extend(words)
        boostings.append({"words": ",".join(words), "weight": group_weight})
    # Enforce the provider's total keyword limit (and the recommended-limit
    # warning) across all groups combined, not only per group.
    normalize_clova_keywords(combined_keywords)
    if not boostings:
        return {}
    return {
        # Direct boostings and console/domain boostings cannot be used together.
        "useDomainBoostings": False,
        "keywordBoosting": {"boostings": boostings},
    }


class TranscriptAssembler:
    """Apply CLOVA text payloads, whether they arrive as fragments or restatements.

    NAVER documents ``position`` as an offset into the "full text" but does not
    pin down whether a payload carries only the newest fragment or restates the
    utterance so far, nor whether the offset resets after ``epFlag``. Rather
    than betting on one reading, each payload is joined at the seam its offset
    points to and any already-emitted prefix it repeats is dropped, so both
    server behaviors converge on the same transcript.
    """

    def __init__(self) -> None:
        self.text = ""
        self._position_origin: int | None = None

    def apply(self, text: str, position: int) -> str:
        if position < 0:
            raise ValueError("transcript position cannot be negative")
        # The first offset after each flush is this turn's origin, so a server
        # that keeps counting across turns still yields turn-local text.
        if self._position_origin is None:
            self._position_origin = position
        if not text:
            return self.text

        relative_position = max(0, position - self._position_origin)
        # Never invent characters the provider did not send: an offset past the
        # text held so far means "append here", not "pad the gap with spaces".
        seam = min(relative_position, len(self.text))
        head = self.text[:seam]

        if text.startswith(head):
            # The payload restates everything up to the seam, so it already is
            # the transcript. Replacing it also lets a corrected, shorter
            # hypothesis shrink the text instead of stranding a stale tail.
            self.text = text
            return self.text

        # Otherwise treat it as a fragment, minus any leading characters that
        # were already emitted at the seam.
        repeated = 0
        for size in range(min(len(head), len(text)), 0, -1):
            if head.endswith(text[:size]):
                repeated = size
                break
        # Dropping the old tail is deliberate: the provider's newest payload
        # defines everything from the seam onward.
        self.text = head + text[repeated:]
        return self.text

    def reset(self) -> None:
        self.text = ""
        self._position_origin = None


def _status_error(payload: Mapping[str, Any], section_name: str) -> str | None:
    section = payload.get(section_name)
    if not isinstance(section, Mapping):
        return None
    statuses: list[tuple[str, object]] = []
    if "status" in section:
        statuses.append((section_name, section["status"]))
    for name, value in section.items():
        if isinstance(value, Mapping) and "status" in value:
            statuses.append((f"{section_name}.{name}", value["status"]))
    for name, status in statuses:
        normalized = str(status).strip()
        if normalized and normalized.casefold() not in {"ok", "success"}:
            return f"{name}: {normalized}"
    return None


def parse_clova_response(response: Any) -> ClovaEvent | None:
    """Parse a generated ``NestResponse``, JSON string/bytes, or mapping."""

    contents = getattr(response, "contents", response)
    if isinstance(contents, bytes):
        contents = contents.decode("utf-8")
    if isinstance(contents, str):
        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as exc:
            return ClovaEvent(kind=ClovaEventKind.ERROR, error=f"invalid response JSON: {exc}")
    elif isinstance(contents, Mapping):
        payload = dict(contents)
    else:
        return ClovaEvent(
            kind=ClovaEventKind.ERROR,
            error=f"unsupported response type: {type(contents).__name__}",
        )

    response_types_value = payload.get("responseType", ())
    if isinstance(response_types_value, str):
        response_types = (response_types_value,)
    else:
        response_types = tuple(str(value) for value in response_types_value or ())

    for section_name in ("config", "recognize"):
        if status_error := _status_error(payload, section_name):
            return ClovaEvent(
                kind=ClovaEventKind.ERROR,
                response_type=response_types,
                error=status_error,
                raw=payload,
            )

    result: Mapping[str, Any] | None = None
    # Transcription is preferred when a response contains several result
    # types. semanticEpd is a result-generation hint with the same text shape.
    for key in ("transcription", "semanticEpd"):
        candidate = payload.get(key)
        if isinstance(candidate, Mapping):
            result = candidate
            break
    if result is None:
        return None

    try:
        position = int(result.get("position", 0) or 0)
        seq_id = int(result.get("seqId", 0) or 0)
        confidence_value = result.get("confidence")
        confidence = float(confidence_value) if confidence_value is not None else None
    except (TypeError, ValueError) as exc:
        return ClovaEvent(
            kind=ClovaEventKind.ERROR,
            response_type=response_types,
            error=f"invalid transcription fields: {exc}",
            raw=payload,
        )

    endpoint = bool(result.get("epFlag", False))
    is_final = endpoint and seq_id != 0
    return ClovaEvent(
        kind=ClovaEventKind.FLUSHED if is_final else ClovaEventKind.PARTIAL,
        text=str(result.get("text", "")),
        position=position,
        confidence=confidence,
        seq_id=seq_id,
        endpoint=endpoint,
        is_final=is_final,
        epd_type=str(result["epdType"]) if result.get("epdType") is not None else None,
        response_type=response_types,
        raw=payload,
    )


ChannelFactory = Callable[[str], Any]
StubFactory = Callable[[Any], Any]
_STOP = object()


class ClovaStreamingClient:
    """One long-lived bidirectional CLOVA stream for a WebSocket session."""

    def __init__(
        self,
        *,
        secret_key: str,
        target: str = "clovaspeech-gw.ncloud.com:50051",
        language: str = "ko",
        semantic_epd: Mapping[str, Any] | None = None,
        boosting_keywords: BoostingKeywords = (),
        keyword_boosting_weight: float = CLOVA_MAX_KEYWORD_WEIGHT,
        pb2_module: str | ModuleType | Any | None = None,
        pb2_grpc_module: str | ModuleType | Any | None = None,
        channel_factory: ChannelFactory | None = None,
        stub_factory: StubFactory | None = None,
        frame_bytes: int = 640,
        request_queue_maxsize: int = 256,
        event_queue_maxsize: int = 256,
    ) -> None:
        if not secret_key:
            raise ValueError("secret_key is required")
        if frame_bytes <= 0:
            raise ValueError("frame_bytes must be positive")
        if request_queue_maxsize <= 0 or event_queue_maxsize <= 0:
            raise ValueError("stream queue sizes must be positive")
        self.secret_key = secret_key
        self.target = target
        self.language = language
        self.semantic_epd = dict(
            {
                "skipEmptyText": True,
                "useWordEpd": True,
                "usePeriodEpd": True,
                "gapThreshold": 1500,
                "durationThreshold": 20000,
                "syllableThreshold": 0,
            }
            if semantic_epd is None
            else semantic_epd
        )
        # ``boosting_groups`` is the weighted form sent to CLOVA;
        # ``boosting_keywords`` stays a flat deduplicated word tuple so callers
        # and tests can inspect "which words are boosted" without unpacking.
        self.boosting_groups = _coerce_keyword_groups(boosting_keywords)
        self.boosting_keywords = normalize_clova_keywords(
            keyword for group in self.boosting_groups for keyword in group.keywords
        )
        # Validate the provider ranges at construction time instead of failing
        # only after a live gRPC stream has opened.
        build_keyword_boosting_config(
            self.boosting_groups,
            weight=keyword_boosting_weight,
        )
        self.keyword_boosting_weight = float(keyword_boosting_weight)
        self.frame_bytes = frame_bytes
        self._pb2_spec = pb2_module
        self._pb2_grpc_spec = pb2_grpc_module
        self._channel_factory = channel_factory
        self._stub_factory = stub_factory

        self._pb2: Any = None
        self._channel: Any = None
        # Apply backpressure when either peer is slow.  Unbounded queues would
        # otherwise let one session retain arbitrarily much PCM or transcript
        # data while the gRPC server or WebSocket client is unavailable.
        self._requests: asyncio.Queue[Any] = asyncio.Queue(maxsize=request_queue_maxsize)
        self._events: asyncio.Queue[ClovaEvent | object] = asyncio.Queue(
            maxsize=event_queue_maxsize
        )
        self._pending_flushes: dict[int, asyncio.Future[ClovaEvent]] = {}
        self._response_task: asyncio.Task[None] | None = None
        self._assembler = TranscriptAssembler()
        self._next_seq_id = 1
        self._generation = 0
        self._started = False
        self._closed = False

    @property
    def started(self) -> bool:
        return self._started and not self._closed

    @property
    def generation(self) -> int:
        """Current turn-local transcript generation within this stream."""

        return self._generation

    async def start(self) -> None:
        if self.started:
            return
        if self._closed:
            raise ClovaError("a closed client cannot be restarted")

        self._pb2 = self._resolve_module(
            self._pb2_spec,
            ("silki_ai.generated.nest_pb2", "silki_ai.nest_pb2", "nest_pb2"),
        )
        # grpc_tools generates ``import nest_pb2`` in the sibling grpc module
        # even when both files live in a Python package.
        if "." in getattr(self._pb2, "__name__", ""):
            sys.modules.setdefault("nest_pb2", self._pb2)
        pb2_grpc = self._resolve_module(
            self._pb2_grpc_spec,
            ("silki_ai.generated.nest_pb2_grpc", "silki_ai.nest_pb2_grpc", "nest_pb2_grpc"),
        )

        if self._channel_factory is None:
            grpc = importlib.import_module("grpc")
            self._channel = grpc.aio.secure_channel(self.target, grpc.ssl_channel_credentials())
        else:
            self._channel = self._channel_factory(self.target)

        stub = (
            self._stub_factory(self._channel)
            if self._stub_factory is not None
            else pb2_grpc.NestServiceStub(self._channel)
        )
        responses = stub.recognize(
            self._request_iterator(),
            metadata=(("authorization", f"Bearer {self.secret_key}"),),
        )
        if inspect.isawaitable(responses) and not hasattr(responses, "__aiter__"):
            responses = await responses
        self._started = True
        self._response_task = asyncio.create_task(self._consume_responses(responses))

    async def send_audio(self, pcm: bytes) -> None:
        self._require_started()
        if not pcm or len(pcm) % self.frame_bytes:
            raise ClovaAudioFormatError(
                f"audio must contain one or more {self.frame_bytes}-byte PCM frames"
            )
        await self._requests.put(self._data_request(pcm, seq_id=0, ep_flag=False))

    async def request_flush(
        self, seq_id: int | None = None
    ) -> tuple[int, asyncio.Future[ClovaEvent]]:
        """Send epFlag/seqId without closing the session-level gRPC stream."""

        self._require_started()
        if seq_id is None:
            seq_id = self._next_seq_id
            self._next_seq_id += 1
        if seq_id <= 0:
            raise ValueError("flush seq_id must be non-zero and positive")
        if seq_id in self._pending_flushes:
            raise ValueError(f"flush seq_id {seq_id} is already pending")
        future: asyncio.Future[ClovaEvent] = asyncio.get_running_loop().create_future()
        self._pending_flushes[seq_id] = future
        # A DATA request carrying epFlag is the documented CLOVA buffer flush.
        # Include one valid silence frame instead of an empty audio payload;
        # CLOVA rejects malformed PCM before evaluating extraContents.
        await self._requests.put(
            self._data_request(b"\x00" * self.frame_bytes, seq_id=seq_id, ep_flag=True)
        )
        return seq_id, future

    async def flush(
        self,
        seq_id: int | None = None,
        *,
        wait: bool = True,
        timeout_seconds: float | None = 5.0,
    ) -> ClovaEvent | int:
        actual_seq_id, future = await self.request_flush(seq_id)
        if not wait:
            return actual_seq_id
        try:
            if timeout_seconds is None:
                return await asyncio.shield(future)
            return await asyncio.wait_for(asyncio.shield(future), timeout_seconds)
        except BaseException:
            self._pending_flushes.pop(actual_seq_id, None)
            if not future.done():
                future.cancel()
            raise

    async def next_event(self) -> ClovaEvent:
        event = await self._events.get()
        if event is _STOP:
            raise StopAsyncIteration
        assert isinstance(event, ClovaEvent)
        return event

    async def events(self) -> AsyncIterator[ClovaEvent]:
        while True:
            event = await self._events.get()
            if event is _STOP:
                break
            assert isinstance(event, ClovaEvent)
            yield event

    def reset_transcript(self) -> None:
        """Reset assembled text after a turn has been fully flushed."""

        self._assembler.reset()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._replace_queue_with_stop(self._requests)
        if self._response_task is not None:
            try:
                await asyncio.wait_for(self._response_task, timeout=2.0)
            except TimeoutError:
                self._response_task.cancel()
                await asyncio.gather(self._response_task, return_exceptions=True)
        for future in self._pending_flushes.values():
            if not future.done():
                future.set_exception(ClovaError("stream closed before flush completed"))
        self._pending_flushes.clear()
        self._replace_queue_with_stop(self._events)
        if self._channel is not None:
            close_result = self._channel.close()
            if inspect.isawaitable(close_result):
                await close_result

    async def _request_iterator(self) -> AsyncIterator[Any]:
        config = {
            "transcription": {"language": self.language},
        }
        config.update(
            build_keyword_boosting_config(
                self.boosting_groups,
                weight=self.keyword_boosting_weight,
            )
        )
        if self.semantic_epd:
            config["semanticEpd"] = self.semantic_epd
        yield self._pb2.NestRequest(
            type=self._enum_value("CONFIG"),
            config=self._pb2.NestConfig(
                config=json.dumps(config, ensure_ascii=False, separators=(",", ":"))
            ),
        )
        while True:
            request = await self._requests.get()
            if request is _STOP:
                break
            yield request

    async def _consume_responses(self, responses: AsyncIterator[Any]) -> None:
        try:
            async for response in responses:
                event = parse_clova_response(response)
                if event is None:
                    continue
                if event.is_final and event.seq_id not in self._pending_flushes:
                    # A response for a timed-out/abandoned flush must not alter
                    # the next turn's assembler state.
                    continue
                if event.kind is not ClovaEventKind.ERROR:
                    full_text = self._assembler.apply(event.text, event.position)
                    event = replace(
                        event,
                        text=full_text,
                        generation=self._generation,
                    )
                if event.is_final:
                    # A flush result belongs exclusively to the caller that
                    # owns seqId. Publishing it as a generic partial can race
                    # with the next active turn and corrupt its transcript.
                    future = self._pending_flushes.pop(event.seq_id, None)
                    if future is not None and not future.done():
                        future.set_result(event)
                    self._assembler.reset()
                    self._generation += 1
                    continue
                await self._events.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._fail_stream(str(exc))
        else:
            if not self._closed:
                await self._fail_stream("CLOVA response stream ended unexpectedly")

    async def _fail_stream(self, message: str) -> None:
        self._started = False
        for future in self._pending_flushes.values():
            if not future.done():
                future.set_exception(ClovaError(message))
        self._pending_flushes.clear()
        await self._events.put(ClovaEvent(kind=ClovaEventKind.ERROR, error=message))

    @staticmethod
    def _replace_queue_with_stop(queue: asyncio.Queue[Any]) -> None:
        """Discard queued work during shutdown and wake its consumer immediately."""

        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        queue.put_nowait(_STOP)

    def _data_request(self, chunk: bytes, *, seq_id: int, ep_flag: bool) -> Any:
        return self._pb2.NestRequest(
            type=self._enum_value("DATA"),
            data=self._pb2.NestData(
                chunk=chunk,
                extra_contents=json.dumps(
                    {"seqId": seq_id, "epFlag": ep_flag}, separators=(",", ":")
                ),
            ),
        )

    def _enum_value(self, name: str) -> Any:
        request_type = getattr(self._pb2, "RequestType", None)
        if request_type is not None and hasattr(request_type, name):
            return getattr(request_type, name)
        return getattr(self._pb2, name)

    def _require_started(self) -> None:
        if not self.started:
            raise ClovaNotStarted("call start() before streaming audio")

    @staticmethod
    def _resolve_module(spec: Any, candidates: tuple[str, ...]) -> Any:
        if spec is not None and not isinstance(spec, str):
            return spec
        names = (spec,) if isinstance(spec, str) else candidates
        last_error: ModuleNotFoundError | None = None
        for name in names:
            try:
                return importlib.import_module(name)
            except ModuleNotFoundError as exc:
                # Only try a fallback when the candidate itself is absent;
                # surface missing dependencies inside a generated module.
                if exc.name != name:
                    raise
                last_error = exc
        raise ClovaError(
            "generated nest protobuf modules are unavailable; compile proto/nest.proto first"
        ) from last_error


# Explicit descriptive alias for callers that prefer the service name.
ClovaSpeechClient = ClovaStreamingClient
