from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from silki_ai.clova import (
    _STOP,
    CLOVA_MAX_KEYWORD_WEIGHT,
    CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS,
    ClovaAudioFormatError,
    ClovaEvent,
    ClovaEventKind,
    ClovaKeywordGroup,
    ClovaStreamingClient,
    TranscriptAssembler,
    build_keyword_boosting_config,
    load_clova_keyword_groups,
    load_clova_keywords,
    normalize_clova_keywords,
    parse_clova_keyword_groups,
    parse_clova_response,
)


@dataclass
class NestConfig:
    config: str


@dataclass
class NestData:
    chunk: bytes
    extra_contents: str


@dataclass
class NestRequest:
    type: int
    config: NestConfig | None = None
    data: NestData | None = None


class RequestType:
    CONFIG = 0
    DATA = 1


PB2 = SimpleNamespace(
    NestConfig=NestConfig,
    NestData=NestData,
    NestRequest=NestRequest,
    RequestType=RequestType,
)


class FakeChannel:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeStub:
    def __init__(self) -> None:
        self.requests: list[NestRequest] = []
        self.metadata = None

    def recognize(self, requests, *, metadata):
        self.metadata = metadata

        async def responses():
            async for request in requests:
                self.requests.append(request)
                if request.type != RequestType.DATA:
                    continue
                extra = json.loads(request.data.extra_contents)
                if extra["epFlag"]:
                    payload = {
                        "responseType": ["transcription"],
                        "transcription": {
                            "text": " 주세요",
                            "position": 5,
                            "confidence": 0.97,
                            "epFlag": True,
                            "seqId": extra["seqId"],
                            "epdType": "endPoint",
                        },
                    }
                else:
                    payload = {
                        "responseType": ["transcription"],
                        "transcription": {
                            "text": "커피 한잔",
                            "position": 0,
                            "confidence": 0.91,
                            "epFlag": False,
                            "seqId": 0,
                            "epdType": "period",
                        },
                    }
                yield SimpleNamespace(contents=json.dumps(payload, ensure_ascii=False))

        return responses()


def test_parser_exposes_turn_correlation_fields() -> None:
    event = parse_clova_response(
        {
            "responseType": ["transcription"],
            "transcription": {
                "text": "라떼",
                "position": 3,
                "confidence": 0.9,
                "epFlag": True,
                "seqId": 42,
                "epdType": "endPoint",
            },
        }
    )

    assert event is not None
    assert event.kind is ClovaEventKind.FLUSHED
    assert event.text == "라떼"
    assert event.position == 3
    assert event.confidence == pytest.approx(0.9)
    assert event.seq_id == 42
    assert event.endpoint is True
    assert event.ep_flag is True
    assert event.is_final is True


def test_semantic_epd_result_is_partial_not_application_final() -> None:
    event = parse_clova_response(
        {
            "responseType": ["semanticEpd"],
            "semanticEpd": {
                "text": "달달한 음료",
                "position": 0,
                "epFlag": False,
                "seqId": 0,
                "epdType": "gap",
            },
        }
    )
    assert event is not None
    assert event.kind is ClovaEventKind.PARTIAL
    assert event.is_final is False


def test_config_failure_is_exposed_as_provider_error() -> None:
    event = parse_clova_response(
        {
            "responseType": ["config"],
            "config": {
                "status": "Failure",
                "semanticEpd": {"status": "Unknown key"},
            },
        }
    )

    assert event is not None
    assert event.kind is ClovaEventKind.ERROR
    assert "Failure" in (event.error or "")


def test_transcript_assembler_honors_absolute_position() -> None:
    assembler = TranscriptAssembler()
    assert assembler.apply("커피", 0) == "커피"
    assert assembler.apply(" 한잔", 2) == "커피 한잔"
    assert assembler.apply("두잔", 3) == "커피 두잔"


def test_transcript_assembler_does_not_duplicate_pad_or_strand_text() -> None:
    duplicating = TranscriptAssembler()
    for text, position in (("아", 0), ("아이스 아메", 1), ("메리칸", 7)):
        duplicating.apply(text, position)
    # Repeated prefixes ("아아이스", "아메메리칸") and invented spaces are gone.
    assert duplicating.text == "아이스 아메리칸"

    correcting = TranscriptAssembler()
    correcting.apply("아이스 아메리카노 완전 좋은데 안 하나", 0)
    correcting.apply("아이스 아메리카노 한잔", 0)
    # A shorter corrected hypothesis replaces the stale tail instead of keeping it.
    assert correcting.text == "아이스 아메리카노 한잔"


def test_transcript_assembler_uses_new_origin_after_flush() -> None:
    assembler = TranscriptAssembler()
    assert assembler.apply("첫 번째", 12) == "첫 번째"
    assembler.reset()
    assert assembler.apply("두 번째", 19) == "두 번째"


def test_stream_client_requires_bounded_queues() -> None:
    client = ClovaStreamingClient(
        secret_key="test-secret",
        request_queue_maxsize=1,
        event_queue_maxsize=2,
    )

    assert client._requests.maxsize == 1
    assert client._events.maxsize == 2

    with pytest.raises(ValueError, match="queue sizes must be positive"):
        ClovaStreamingClient(secret_key="test-secret", request_queue_maxsize=0)


def test_keyword_boosting_normalizes_deduplicates_and_uses_max_weight() -> None:
    config = build_keyword_boosting_config(
        [" 아이스   아메리카노 ", "아이스 아메리카노", "아아"]
    )

    assert normalize_clova_keywords([" 라떼 ", "라떼", "카페 라떼"]) == (
        "라떼",
        "카페 라떼",
    )
    assert config == {
        "useDomainBoostings": False,
        "keywordBoosting": {
            "boostings": [
                {
                    "words": "아이스 아메리카노,아아",
                    "weight": CLOVA_MAX_KEYWORD_WEIGHT,
                }
            ]
        },
    }


def test_keyword_boosting_rejects_provider_invalid_values() -> None:
    with pytest.raises(ValueError, match="cannot contain a comma"):
        build_keyword_boosting_config(["라떼,아메리카노"])
    with pytest.raises(ValueError, match="between 0 and 5"):
        build_keyword_boosting_config(["라떼"], weight=5.1)


def test_packaged_keyword_list_stays_within_recommended_limit() -> None:
    keywords = load_clova_keywords()

    assert 0 < len(keywords) <= CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS
    assert len(set(keywords)) == len(keywords)
    assert "아이스 아메리카노" in keywords
    assert "아아" in keywords
    # Spacing-only duplicate variants were collapsed to a single form.
    assert not ({"두 개", "두개"} <= set(keywords))
    assert not ({"아이스 초코", "아이스초코"} <= set(keywords))
    # Generic high-frequency standard words are no longer boosted.
    assert "주세요" not in keywords
    assert "하나" not in keywords
    assert "빼고" not in keywords
    assert "그거" not in keywords


def test_packaged_keyword_file_defines_weighted_groups() -> None:
    groups = load_clova_keyword_groups()

    assert [group.weight for group in groups] == [5.0, 4.0, 3.0]
    weights_by_keyword = {
        keyword: group.weight for group in groups for keyword in group.keywords
    }
    assert weights_by_keyword["아메리카노"] == 5.0
    assert weights_by_keyword["아아"] == 4.0
    assert weights_by_keyword["샷 추가"] == 3.0


def test_parse_keyword_groups_honors_headers_comments_and_default_group() -> None:
    groups = parse_clova_keyword_groups(
        [
            "# 일반 주석은 무시된다",
            "기본 가중치 키워드",
            "# weight: 5",
            "유자차",
            "",
            "# WEIGHT: 3.5",
            "샷 추가",
        ]
    )

    assert groups == (
        ClovaKeywordGroup(keywords=("기본 가중치 키워드",), weight=None),
        ClovaKeywordGroup(keywords=("유자차",), weight=5.0),
        ClovaKeywordGroup(keywords=("샷 추가",), weight=3.5),
    )


def test_parse_keyword_groups_rejects_out_of_range_header_weight() -> None:
    with pytest.raises(ValueError, match="between 0 and 5"):
        parse_clova_keyword_groups(["# weight: 6", "유자차"])


def test_build_config_serializes_multiple_groups_with_default_fallback() -> None:
    config = build_keyword_boosting_config(
        [
            ClovaKeywordGroup(keywords=("유자차", "아메리카노"), weight=5),
            ClovaKeywordGroup(keywords=("아아", "유자차"), weight=4),
            ClovaKeywordGroup(keywords=("샷 추가",)),
        ],
        weight=2,
    )

    assert config == {
        "useDomainBoostings": False,
        "keywordBoosting": {
            "boostings": [
                {"words": "유자차,아메리카노", "weight": 5.0},
                # "유자차" already belongs to the first group, so it is not
                # repeated with a conflicting weight.
                {"words": "아아", "weight": 4.0},
                # The headerless group falls back to the caller default.
                {"words": "샷 추가", "weight": 2.0},
            ]
        },
    }


def test_build_config_rejects_mixed_strings_and_groups() -> None:
    with pytest.raises(TypeError, match="cannot mix"):
        build_keyword_boosting_config(["유자차", ClovaKeywordGroup(keywords=("아아",))])


def test_build_config_with_only_empty_groups_is_empty() -> None:
    assert build_keyword_boosting_config([ClovaKeywordGroup(keywords=("", "  "))]) == {}


def test_normalize_warns_above_recommended_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    over_limit = [f"키워드{index}" for index in range(CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS + 1)]

    with caplog.at_level("WARNING", logger="silki_ai.clova"):
        keywords = normalize_clova_keywords(over_limit)

    assert len(keywords) == CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS + 1
    assert any(
        "501" in record.getMessage() and "500" in record.getMessage()
        for record in caplog.records
    )


def test_normalize_does_not_warn_at_recommended_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    at_limit = [f"키워드{index}" for index in range(CLOVA_RECOMMENDED_MAX_BOOSTING_KEYWORDS)]

    with caplog.at_level("WARNING", logger="silki_ai.clova"):
        normalize_clova_keywords(at_limit)

    assert not caplog.records


@pytest.mark.asyncio
async def test_close_discards_full_queues_without_blocking() -> None:
    client = ClovaStreamingClient(
        secret_key="test-secret",
        request_queue_maxsize=1,
        event_queue_maxsize=1,
    )
    client._started = True
    client._requests.put_nowait(object())
    client._events.put_nowait(ClovaEvent(kind=ClovaEventKind.PARTIAL, text="대기 중"))

    await client.close()

    assert await client._requests.get() is _STOP
    with pytest.raises(StopAsyncIteration):
        await client.next_event()


@pytest.mark.asyncio
async def test_stream_stays_open_across_audio_and_flush() -> None:
    channel = FakeChannel()
    stub = FakeStub()
    client = ClovaStreamingClient(
        secret_key="test-secret",
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: channel,
        stub_factory=lambda _channel: stub,
    )

    await client.start()
    await client.send_audio(b"\x01\x00" * 320)
    partial = await client.next_event()
    assert partial.kind is ClovaEventKind.PARTIAL
    final = await client.flush(seq_id=7, timeout_seconds=1)

    assert final.kind is ClovaEventKind.FLUSHED
    assert final.seq_id == 7
    assert final.text == "커피 한잔 주세요"
    assert final.generation == 0
    assert client.generation == 1
    assert client.started is True
    assert stub.metadata == (("authorization", "Bearer test-secret"),)
    assert stub.requests[0].type == RequestType.CONFIG
    config = json.loads(stub.requests[0].config.config)
    assert config["transcription"]["language"] == "ko"
    assert "semanticEpd" in config
    flush_request = stub.requests[-1]
    assert json.loads(flush_request.data.extra_contents) == {"seqId": 7, "epFlag": True}
    assert flush_request.data.chunk == b"\x00" * 640

    await client.send_audio(b"\x01\x00" * 320)
    next_turn = await client.next_event()
    assert next_turn.generation == 1
    assert next_turn.text == "커피 한잔"

    # The correlated final is delivered only to flush(), never to the generic
    # partial stream where it could be attached to a later application turn.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client.next_event(), timeout=0.01)

    await client.close()
    assert channel.closed is True


@pytest.mark.asyncio
async def test_stream_config_sends_direct_keyword_boosting() -> None:
    channel = FakeChannel()
    stub = FakeStub()
    client = ClovaStreamingClient(
        secret_key="test-secret",
        boosting_keywords=["아이스 아메리카노", "아아"],
        keyword_boosting_weight=5,
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: channel,
        stub_factory=lambda _channel: stub,
    )

    await client.start()
    await client.send_audio(b"\x01\x00" * 320)
    await client.next_event()
    config = json.loads(stub.requests[0].config.config)

    assert config["useDomainBoostings"] is False
    assert config["keywordBoosting"]["boostings"] == [
        {"words": "아이스 아메리카노,아아", "weight": 5.0}
    ]
    await client.close()


def test_client_exposes_groups_and_flat_keywords() -> None:
    client = ClovaStreamingClient(
        secret_key="test-secret",
        boosting_keywords=[
            ClovaKeywordGroup(keywords=("아이스 아메리카노", "아아"), weight=5),
            ClovaKeywordGroup(keywords=("아아", "샷 추가"), weight=3),
        ],
    )

    assert client.boosting_groups[0].weight == 5.0
    # Flat view stays a deduplicated tuple of plain words for callers that only
    # need to know which words are boosted.
    assert client.boosting_keywords == ("아이스 아메리카노", "아아", "샷 추가")


def test_client_accepts_plain_string_keywords() -> None:
    client = ClovaStreamingClient(
        secret_key="test-secret",
        boosting_keywords=["아이스 아메리카노", "아아", "아아"],
    )

    assert client.boosting_keywords == ("아이스 아메리카노", "아아")
    assert client.boosting_groups == (
        ClovaKeywordGroup(keywords=("아이스 아메리카노", "아아", "아아"), weight=None),
    )


def test_disabled_boosting_sends_no_keyword_fields() -> None:
    client = ClovaStreamingClient(secret_key="test-secret", boosting_keywords=())

    assert client.boosting_groups == ()
    assert client.boosting_keywords == ()
    assert build_keyword_boosting_config(client.boosting_groups) == {}


@pytest.mark.asyncio
async def test_stream_config_omits_boosting_when_disabled() -> None:
    channel = FakeChannel()
    stub = FakeStub()
    client = ClovaStreamingClient(
        secret_key="test-secret",
        boosting_keywords=(),
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: channel,
        stub_factory=lambda _channel: stub,
    )

    await client.start()
    await client.send_audio(b"\x01\x00" * 320)
    await client.next_event()
    config = json.loads(stub.requests[0].config.config)

    # Neither direct boosting nor the domain-boosting flag is sent, so CLOVA
    # applies no keyword boosting at all.
    assert "keywordBoosting" not in config
    assert "useDomainBoostings" not in config
    await client.close()


@pytest.mark.asyncio
async def test_stream_config_sends_multi_group_keyword_boosting() -> None:
    channel = FakeChannel()
    stub = FakeStub()
    client = ClovaStreamingClient(
        secret_key="test-secret",
        boosting_keywords=[
            ClovaKeywordGroup(keywords=("아이스 아메리카노",), weight=5),
            ClovaKeywordGroup(keywords=("아아",), weight=4),
            ClovaKeywordGroup(keywords=("샷 추가",)),
        ],
        keyword_boosting_weight=3,
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: channel,
        stub_factory=lambda _channel: stub,
    )

    await client.start()
    await client.send_audio(b"\x01\x00" * 320)
    await client.next_event()
    config = json.loads(stub.requests[0].config.config)

    assert config["useDomainBoostings"] is False
    assert config["keywordBoosting"]["boostings"] == [
        {"words": "아이스 아메리카노", "weight": 5.0},
        {"words": "아아", "weight": 4.0},
        {"words": "샷 추가", "weight": 3.0},
    ]
    await client.close()


@pytest.mark.asyncio
async def test_semantic_epd_can_be_disabled() -> None:
    channel = FakeChannel()
    stub = FakeStub()
    client = ClovaStreamingClient(
        secret_key="test-secret",
        semantic_epd={},
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: channel,
        stub_factory=lambda _channel: stub,
    )

    await client.start()
    await client.send_audio(b"\x01\x00" * 320)
    await client.next_event()
    config = json.loads(stub.requests[0].config.config)

    assert "semanticEpd" not in config
    await client.close()


@pytest.mark.asyncio
async def test_audio_requires_complete_twenty_millisecond_frames() -> None:
    client = ClovaStreamingClient(
        secret_key="test-secret",
        pb2_module=PB2,
        pb2_grpc_module=SimpleNamespace(),
        channel_factory=lambda _target: FakeChannel(),
        stub_factory=lambda _channel: FakeStub(),
    )
    await client.start()
    with pytest.raises(ClovaAudioFormatError):
        await client.send_audio(b"odd")
    await client.close()
