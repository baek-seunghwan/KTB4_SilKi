from __future__ import annotations

import asyncio
import base64
import struct
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from silki_ai.app import create_app
from silki_ai.clova import ClovaEvent, ClovaEventKind
from silki_ai.config import Settings
from silki_ai.contracts import (
    MenuCandidate,
    ReindexResponse,
    ReindexStatus,
    SearchAttributes,
)
from silki_ai.recommendation import RecommendationResult
from silki_ai.security import AccessTokenVerifier
from silki_ai.tts import SynthesizedAudio
from silki_ai.websocket_api import clova_public_error_message

SPEECH = struct.pack("<320h", *([2_000] * 320))
SILENCE = b"\x00" * 640
LOW_NOISE = struct.pack("<320h", *([100] * 320))


@pytest.mark.parametrize(
    ("provider_error", "expected"),
    [
        (
            "StatusCode.UNAUTHENTICATED: Invalid authentication token",
            "CLOVA Speech Secret Key가 올바르지 않거나 실시간 스트리밍 권한이 없습니다.",
        ),
        (
            "RESOURCE_EXHAUSTED: No more slot",
            "CLOVA Speech 동시 연결 한도가 찼습니다. 잠시 후 다시 시도해주세요.",
        ),
        ("connection reset", "CLOVA Speech 스트리밍 연결에 실패했습니다."),
    ],
)
def test_clova_public_error_message(provider_error: str, expected: str) -> None:
    assert clova_public_error_message(provider_error) == expected


class FakeVerifier:
    def verify(self, token: str) -> SimpleNamespace:
        if token != "valid-token":
            raise ValueError("invalid token")
        return SimpleNamespace(
            store_id="store-1",
            order_session_id="order-session-1",
        )


class FakeVad:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        assert sample_rate == 16_000
        return any(frame)


class FakeSpeech:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[ClovaEvent | None] = asyncio.Queue()
        self.partial_sent = False
        self.closed = False
        self.sent_frames: list[bytes] = []

    async def start(self) -> None:
        if self.closed:
            self.queue = asyncio.Queue()
            self.partial_sent = False
            self.closed = False
        return None

    async def send_audio(self, frame: bytes) -> None:
        self.sent_frames.append(frame)
        if any(frame) and not self.partial_sent:
            self.partial_sent = True
            await self.queue.put(
                ClovaEvent(
                    kind=ClovaEventKind.PARTIAL,
                    text="차갑고 안 단 음료",
                    position=0,
                    confidence=0.9,
                    epd_type="gap",
                )
            )

    async def flush(self, *, timeout_seconds: float) -> ClovaEvent:
        assert timeout_seconds == 0.2
        return ClovaEvent(
            kind=ClovaEventKind.FLUSHED,
            text="차갑고 안 단 음료",
            seq_id=1,
            endpoint=True,
            is_final=True,
        )

    async def events(self):
        while True:
            event = await self.queue.get()
            if event is None:
                return
            yield event

    def reset_transcript(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(None)


class MultiTurnFakeSpeech(FakeSpeech):
    def __init__(self) -> None:
        super().__init__()
        self.generation = 0

    def _text(self) -> str:
        return "첫 번째 음료" if self.generation == 0 else "두 번째 음료"

    async def send_audio(self, frame: bytes) -> None:
        if any(frame) and not self.partial_sent:
            self.partial_sent = True
            await self.queue.put(
                ClovaEvent(
                    kind=ClovaEventKind.PARTIAL,
                    text=self._text(),
                    position=0,
                    generation=self.generation,
                )
            )

    async def flush(self, *, timeout_seconds: float) -> ClovaEvent:
        current_generation = self.generation
        text = self._text()
        self.generation += 1
        self.partial_sent = False
        return ClovaEvent(
            kind=ClovaEventKind.FLUSHED,
            text=text,
            seq_id=current_generation + 1,
            endpoint=True,
            is_final=True,
            generation=current_generation,
        )


class FailingStartSpeech(FakeSpeech):
    async def start(self) -> None:
        raise RuntimeError("provider unavailable")


class FakeRecommendationService:
    async def recommend(self, *, store_id: str, transcript: str) -> RecommendationResult:
        assert store_id == "store-1"
        assert transcript == "차갑고 안 단 음료"
        return RecommendationResult(
            search_query="차갑고 당도가 낮은 음료",
            quantity=2,
            attributes=SearchAttributes(temperature="ice", sweetness="low"),
            degraded=False,
            candidates=(MenuCandidate(menu_id="menu-1", name="제로 아이스티", score=0.82),),
        )


class AmericanoSpeech(FakeSpeech):
    def __init__(self) -> None:
        super().__init__()
        self.text = "아메리카노"

    async def send_audio(self, frame: bytes) -> None:
        self.sent_frames.append(frame)
        if any(frame) and not self.partial_sent:
            self.partial_sent = True
            await self.queue.put(
                ClovaEvent(
                    kind=ClovaEventKind.PARTIAL,
                    text=self.text,
                    position=0,
                    confidence=0.9,
                    epd_type="gap",
                )
            )

    async def flush(self, *, timeout_seconds: float) -> ClovaEvent:
        assert timeout_seconds == 0.2
        return ClovaEvent(
            kind=ClovaEventKind.FLUSHED,
            text=self.text,
            seq_id=1,
            endpoint=True,
            is_final=True,
        )


class DialogRecommendationService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def recommend(self, *, store_id: str, transcript: str) -> RecommendationResult:
        assert store_id == "store-1"
        assert "아메리카노" in transcript
        self.calls.append(transcript)
        return RecommendationResult(
            search_query="아메리카노",
            quantity=1,
            attributes=SearchAttributes(category="coffee"),
            degraded=False,
            candidates=(
                MenuCandidate(menu_id="hot", name="따뜻한 아메리카노", score=0.86),
                MenuCandidate(menu_id="ice", name="아이스 아메리카노", score=0.85),
            ),
        )


class FakeTtsClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> SynthesizedAudio:
        self.texts.append(text)
        if self.fail:
            raise RuntimeError("GPU service unavailable")
        return SynthesizedAudio(content=b"ID3-fake-audio", media_type="audio/mpeg")


class ReorderingRecommendationService:
    async def recommend(self, *, store_id: str, transcript: str) -> RecommendationResult:
        if transcript.startswith("첫"):
            await asyncio.sleep(0.05)
            menu_id = "first-menu"
        else:
            menu_id = "second-menu"
        return RecommendationResult(
            search_query=transcript,
            quantity=1,
            attributes=SearchAttributes(),
            degraded=False,
            candidates=(MenuCandidate(menu_id=menu_id, name=transcript, score=0.9),),
        )


class FakeReindexService:
    async def reindex(self, store_id: str, request) -> ReindexResponse:
        return ReindexResponse(
            store_id=store_id,
            source_revision=request.source_revision,
            indexed_count=len(request.menu_ids),
            deleted_count=0,
            status=ReindexStatus.PROCESSED,
        )


class FakeContainer:
    def __init__(self) -> None:
        self.settings = Settings(
            environment="test",
            internal_api_key=SecretStr("internal-secret"),
            clova_flush_timeout_seconds=0.2,
        )
        self.speech = FakeSpeech()
        self.recommendation_service = FakeRecommendationService()
        self.reindex_service = FakeReindexService()
        self.tts_client = None
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.started = False

    async def readiness(self) -> dict[str, bool]:
        return {"test": self.started}

    def token_verifier(self) -> FakeVerifier:
        return FakeVerifier()

    def create_speech_client(self) -> FakeSpeech:
        return self.speech

    def create_vad(self) -> FakeVad:
        return FakeVad()


class DialogContainer(FakeContainer):
    def __init__(self) -> None:
        super().__init__()
        self.speech = AmericanoSpeech()
        self.recommendation_service = DialogRecommendationService()


def _signing_key_pair(*, elliptic_curve: bool = False) -> tuple[str, str]:
    private_key = (
        ec.generate_private_key(ec.SECP256R1())
        if elliptic_curve
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def _spring_access_token(
    private_key: str,
    *,
    algorithm: str = "RS256",
    **overrides: object,
) -> str:
    """Issue the same NumericDate/list-audience JWT shape as Spring Nimbus."""

    now = datetime.now(UTC).replace(microsecond=0)
    claims: dict[str, object] = {
        "iss": "silki-be",
        "sub": str(uuid4()),
        "aud": ["ai-ws"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=2)).timestamp()),
        "jti": str(uuid4()),
        "storeId": str(uuid4()),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm=algorithm, headers={"typ": "JWT"})


class SpringTokenContainer(FakeContainer):
    def __init__(self, public_key: str) -> None:
        super().__init__()
        self.settings = Settings(
            _env_file=None,
            environment="test",
            internal_api_key=SecretStr("internal-secret"),
            clova_flush_timeout_seconds=0.2,
            jwt_public_key=public_key,
        )
        self.speech_factory_calls = 0

    def token_verifier(self) -> AccessTokenVerifier:
        return AccessTokenVerifier(
            self.settings.jwt_public_key,
            audience=self.settings.jwt_audience,
            algorithms=self.settings.jwt_algorithms,
            issuer=self.settings.jwt_issuer,
            leeway_seconds=self.settings.jwt_leeway_seconds,
            max_ttl_seconds=self.settings.jwt_max_ttl_seconds,
        )

    def create_speech_client(self) -> FakeSpeech:
        self.speech_factory_calls += 1
        return self.speech


def _receive_until(websocket, event_type: str) -> tuple[dict, list[dict]]:
    seen: list[dict] = []
    while True:
        event = websocket.receive_json()
        seen.append(event)
        if event["type"] == event_type:
            return event, seen


def test_spring_compatible_rs256_token_opens_websocket_session() -> None:
    private_key, public_key = _signing_key_pair()
    order_session_id = str(uuid4())
    store_id = str(uuid4())
    container = SpringTokenContainer(public_key)
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": _spring_access_token(
                        private_key,
                        sub=order_session_id,
                        storeId=store_id,
                    ),
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_json(
                {
                    "type": "session.end",
                    "sessionId": ready["sessionId"],
                }
            )

    assert ready["type"] == "session.ready"
    assert ready["orderSessionId"] == order_session_id
    assert ready["storeId"] == store_id
    assert container.speech_factory_calls == 1


@pytest.mark.parametrize("failure", ["audience", "issuer", "expired", "signature", "algorithm"])
def test_invalid_spring_tokens_close_with_4401_before_speech_starts(failure: str) -> None:
    private_key, public_key = _signing_key_pair()
    now = datetime.now(UTC).replace(microsecond=0)
    overrides: dict[str, object] = {}
    signing_key = private_key
    algorithm = "RS256"
    if failure == "audience":
        overrides["aud"] = ["another-service"]
    elif failure == "issuer":
        overrides["iss"] = "another-issuer"
    elif failure == "expired":
        overrides.update(
            {
                "iat": int((now - timedelta(seconds=130)).timestamp()),
                # Stay beyond the configured five-second clock-skew allowance.
                "exp": int((now - timedelta(seconds=10)).timestamp()),
            }
        )
    elif failure == "signature":
        signing_key, _ = _signing_key_pair()
    else:
        signing_key, _ = _signing_key_pair(elliptic_curve=True)
        algorithm = "ES256"

    token = _spring_access_token(signing_key, algorithm=algorithm, **overrides)

    container = SpringTokenContainer(public_key)
    app = create_app(settings=container.settings, container=container)
    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": token,
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            error = websocket.receive_json()
            with pytest.raises(WebSocketDisconnect) as disconnect:
                websocket.receive_json()

    assert error["code"] == "authentication_failed"
    assert error["retryable"] is False
    assert disconnect.value.code == 4401
    assert container.speech_factory_calls == 0


def test_streaming_session_keeps_session_and_turn_correlation() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 7,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            assert ready["type"] == "session.ready"

            websocket.send_bytes(SPEECH)
            started, prelude = _receive_until(websocket, "turn.started")
            assert prelude[0]["type"] == "turn.started"
            assert started["sessionId"] == ready["sessionId"]
            assert started["basedOnCartVersion"] == 7

            # Complete transcript uses the 1.5 second silence path.
            websocket.send_bytes(SILENCE * 75)
            candidates, events = _receive_until(websocket, "menu.candidates")
            turn_events = [event for event in events if "turnId" in event]
            assert all(event["turnId"] == started["turnId"] for event in turn_events)
            assert candidates["sessionId"] == ready["sessionId"]
            assert candidates["basedOnCartVersion"] == 7
            assert candidates["candidates"][0]["menuId"] == "menu-1"
            assert candidates["degraded"] is False

            websocket.send_json(
                {
                    "type": "session.end",
                    "sessionId": ready["sessionId"],
                    "reason": "client_closed",
                }
            )

    assert container.speech.closed is True


def test_dialog_v1_clarifies_choice_rejects_and_completes_on_new_cart_version() -> None:
    container = DialogContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                    "capabilities": ["dialog.v1"],
                }
            )
            ready = websocket.receive_json()
            assert ready["capabilities"] == ["dialog.v1"]

            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            clarification, _ = _receive_until(websocket, "dialog.clarification")
            unavailable, _ = _receive_until(websocket, "tts.unavailable")

            assert clarification["missingSlot"] == "temperature"
            assert clarification["ttsExpected"] is False
            assert unavailable["conversationId"] == clarification["conversationId"]
            assert unavailable["dialogId"] == clarification["dialogId"]
            assert unavailable["revision"] == clarification["revision"]
            assert unavailable["purpose"] == "clarification"

            ice = next(choice for choice in clarification["choices"] if choice["value"] == "ice")
            # Audio received before dialog.listen must be dropped. If it opened a
            # turn, turn.started would appear before the following proposal.
            websocket.send_bytes(SPEECH)
            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": clarification["conversationId"],
                    "dialogId": clarification["dialogId"],
                    "revision": clarification["revision"],
                }
            )
            websocket.send_json(
                {
                    "type": "dialog.choice",
                    "sessionId": ready["sessionId"],
                    "conversationId": clarification["conversationId"],
                    "dialogId": clarification["dialogId"],
                    "revision": clarification["revision"],
                    "choiceId": ice["id"],
                    "value": ice["value"],
                    "label": ice["label"],
                }
            )
            proposal, seen = _receive_until(websocket, "dialog.proposal")
            assert "turn.started" not in {event["type"] for event in seen}
            assert proposal["menu"]["menuId"] == "ice"
            assert proposal["resolvedOptions"] == [{"groupCode": "TEMPERATURE", "valueCode": "ICE"}]
            _receive_until(websocket, "tts.unavailable")

            # If the visible reject button wins after voice input has already
            # started, the superseded CLOVA turn must be discarded without a
            # late turn.final leaking into the replayed clarification.
            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": proposal["conversationId"],
                    "dialogId": proposal["dialogId"],
                    "revision": proposal["revision"],
                }
            )
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_json(
                {
                    "type": "dialog.reject",
                    "sessionId": ready["sessionId"],
                    "conversationId": proposal["conversationId"],
                    "dialogId": proposal["dialogId"],
                    "revision": proposal["revision"],
                }
            )
            replay, seen = _receive_until(websocket, "dialog.clarification")
            assert "turn.final" not in {event["type"] for event in seen}
            assert replay["missingSlot"] == "temperature"
            assert replay["dialogId"] != clarification["dialogId"]
            _receive_until(websocket, "tts.unavailable")

            replay_ice = next(choice for choice in replay["choices"] if choice["value"] == "ice")
            websocket.send_json(
                {
                    "type": "dialog.choice",
                    "sessionId": ready["sessionId"],
                    "conversationId": replay["conversationId"],
                    "dialogId": replay["dialogId"],
                    "revision": replay["revision"],
                    "choiceId": replay_ice["id"],
                    "value": replay_ice["value"],
                    "label": replay_ice["label"],
                }
            )
            second_proposal, _ = _receive_until(websocket, "dialog.proposal")
            _receive_until(websocket, "tts.unavailable")

            # The same cart version is only context refresh, not confirmation.
            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            # The authoritative cart update may also win while confirmation
            # voice input is active. It completes the proposal and discards the
            # in-progress turn rather than finalizing it into a follow-up.
            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": second_proposal["conversationId"],
                    "dialogId": second_proposal["dialogId"],
                    "revision": second_proposal["revision"],
                }
            )
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 1,
                    "cartItems": [{"menuId": "ice", "quantity": 1, "optionIds": []}],
                }
            )
            completed, seen = _receive_until(websocket, "dialog.completed")
            assert "turn.final" not in {event["type"] for event in seen}
            assert completed["conversationId"] == second_proposal["conversationId"]
            assert completed["dialogId"] == second_proposal["dialogId"]
            assert completed["text"] == "장바구니에 담았어요. 더 주문하시겠어요?"
            assert completed["turnId"] == second_proposal["turnId"]
            assert completed["ttsExpected"] is False
            completion_unavailable, _ = _receive_until(websocket, "tts.unavailable")
            assert completion_unavailable["purpose"] == "completion"
            assert completion_unavailable["dialogId"] == completed["dialogId"]
            assert completion_unavailable["revision"] == completed["revision"]

            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})


def test_dialog_v1_tts_audio_keeps_prompt_correlation() -> None:
    container = DialogContainer()
    container.tts_client = FakeTtsClient()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                    "capabilities": ["dialog.v1"],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            clarification, _ = _receive_until(websocket, "dialog.clarification")
            tts, _ = _receive_until(websocket, "tts.audio")

            assert clarification["ttsExpected"] is True
            assert tts["conversationId"] == clarification["conversationId"]
            assert tts["dialogId"] == clarification["dialogId"]
            assert tts["revision"] == clarification["revision"]
            assert tts["purpose"] == "clarification"
            assert base64.b64decode(tts["audioBase64"]) == b"ID3-fake-audio"

            choice = clarification["choices"][0]
            websocket.send_json(
                {
                    "type": "dialog.choice",
                    "sessionId": ready["sessionId"],
                    "conversationId": clarification["conversationId"],
                    "dialogId": clarification["dialogId"],
                    "revision": clarification["revision"],
                    "choiceId": choice["id"],
                    "value": choice["value"],
                    "label": choice["label"],
                }
            )
            proposal, _ = _receive_until(websocket, "dialog.proposal")
            _receive_until(websocket, "tts.audio")
            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 1,
                    "cartItems": [
                        {
                            "menuId": proposal["menu"]["menuId"],
                            "quantity": proposal["quantity"],
                            "optionIds": [],
                        }
                    ],
                }
            )
            completed, _ = _receive_until(websocket, "dialog.completed")
            completion_tts, _ = _receive_until(websocket, "tts.audio")

            assert completed["ttsExpected"] is True
            assert completion_tts["purpose"] == "completion"
            assert completion_tts["text"] == "장바구니에 담았어요. 더 주문하시겠어요?"
            assert completion_tts["dialogId"] == completed["dialogId"]
            assert completion_tts["revision"] == completed["revision"]
            assert container.tts_client.texts[-1] == completion_tts["text"]

            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})


def test_dialog_v1_voice_temperature_confirmation_and_finish_actions() -> None:
    container = DialogContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                    "capabilities": ["dialog.v1"],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            clarification, _ = _receive_until(websocket, "dialog.clarification")
            _receive_until(websocket, "tts.unavailable")

            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": clarification["conversationId"],
                    "dialogId": clarification["dialogId"],
                    "revision": clarification["revision"],
                }
            )
            container.speech.text = "차갑게"
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            proposal, _ = _receive_until(websocket, "dialog.proposal")
            _receive_until(websocket, "tts.unavailable")

            assert proposal["menu"]["menuId"] == "ice"
            assert proposal["resolvedOptions"] == [{"groupCode": "TEMPERATURE", "valueCode": "ICE"}]
            assert container.recommendation_service.calls == ["아메리카노"]

            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": proposal["conversationId"],
                    "dialogId": proposal["dialogId"],
                    "revision": proposal["revision"],
                }
            )
            container.speech.text = "네"
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            accept, _ = _receive_until(websocket, "dialog.action")
            assert accept["action"] == "accept"
            assert accept["dialogId"] == proposal["dialogId"]

            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 1,
                    "cartItems": [{"menuId": "ice", "quantity": 1, "optionIds": []}],
                }
            )
            completed, _ = _receive_until(websocket, "dialog.completed")
            _receive_until(websocket, "tts.unavailable")

            websocket.send_json(
                {
                    "type": "dialog.listen",
                    "sessionId": ready["sessionId"],
                    "conversationId": completed["conversationId"],
                    "dialogId": completed["dialogId"],
                    "revision": completed["revision"],
                }
            )
            container.speech.text = "주문 마칠게"
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            finish, _ = _receive_until(websocket, "dialog.action")
            assert finish["action"] == "finish"
            assert finish["dialogId"] == completed["dialogId"]

            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})


def test_positive_webrtcvad_noise_below_dbfs_floor_does_not_start_a_turn() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()

            # FakeVad deliberately says both frames are speech. The dBFS floor
            # must reject the low-energy one, so only the loud frame starts the
            # turn -- but the quiet frame is still replayed as pre-roll, because
            # it is the onset of the very word being recognized.
            websocket.send_bytes(LOW_NOISE)
            websocket.send_bytes(SPEECH)
            started, _ = _receive_until(websocket, "turn.started")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert started["type"] == "turn.started"
    assert container.speech.sent_frames == [LOW_NOISE, SPEECH]


def test_preroll_replays_only_the_configured_window_before_the_turn() -> None:
    container = FakeContainer()
    container.settings = Settings(
        environment="test",
        internal_api_key=SecretStr("internal-secret"),
        clova_flush_timeout_seconds=0.2,
        audio_preroll_ms=40,
    )
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()

            # Five quiet frames precede the speech, but a 40 ms window keeps
            # only the two most recent ones.
            websocket.send_bytes(LOW_NOISE * 5)
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert container.speech.sent_frames == [LOW_NOISE, LOW_NOISE, SPEECH]


def test_zero_preroll_sends_only_gated_audio() -> None:
    container = FakeContainer()
    container.settings = Settings(
        environment="test",
        internal_api_key=SecretStr("internal-secret"),
        clova_flush_timeout_seconds=0.2,
        audio_preroll_ms=0,
    )
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(LOW_NOISE * 5)
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert container.speech.sent_frames == [SPEECH]


def test_continuous_voiced_audio_finalizes_at_configured_max_duration() -> None:
    container = FakeContainer()
    container.settings = Settings(
        environment="test",
        internal_api_key=SecretStr("internal-secret"),
        clova_flush_timeout_seconds=0.2,
        turn_silence_seconds=0.02,
        turn_incomplete_silence_seconds=0.04,
        turn_max_seconds=0.06,
    )
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(SPEECH * 3)
            final, _ = _receive_until(websocket, "turn.final")
            candidates, _ = _receive_until(websocket, "menu.candidates")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert final["reason"] == "max_duration"
    assert candidates["candidates"][0]["menuId"] == "menu-1"


def test_stable_partial_finalizes_even_when_vad_stays_positive() -> None:
    container = FakeContainer()
    container.settings = Settings(
        environment="test",
        internal_api_key=SecretStr("internal-secret"),
        clova_flush_timeout_seconds=0.2,
        turn_silence_seconds=0.02,
        turn_incomplete_silence_seconds=0.04,
        turn_max_seconds=1.0,
        turn_transcript_stable_seconds=0.06,
    )
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "stt.partial")

            # Persistent voiced input simulates steady room noise that fools
            # WebRTC VAD. The unchanged partial must end the turn before the
            # one-second absolute maximum.
            websocket.send_bytes(SPEECH * 3)
            final, _ = _receive_until(websocket, "turn.final")
            candidates, _ = _receive_until(websocket, "menu.candidates")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert final["reason"] == "transcript_stable_timeout"
    assert candidates["candidates"][0]["menuId"] == "menu-1"


def test_successful_recommendation_sends_non_streaming_tts_after_candidates() -> None:
    container = FakeContainer()
    tts_client = FakeTtsClient()
    container.tts_client = tts_client
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 7,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            assert ready["orderSessionId"] == "order-session-1"
            assert ready["storeId"] == "store-1"

            websocket.send_bytes(SPEECH)
            started, _ = _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            candidates, _ = _receive_until(websocket, "menu.candidates")
            tts, events = _receive_until(websocket, "tts.audio")

            assert candidates["turnId"] == started["turnId"]
            assert events[-1]["type"] == "tts.audio"
            assert tts["sessionId"] == ready["sessionId"]
            assert tts["turnId"] == started["turnId"]
            assert tts["mediaType"] == "audio/mpeg"
            assert base64.b64decode(tts["audioBase64"]) == b"ID3-fake-audio"
            assert tts_client.texts == ["제로 아이스티 2잔을 추천드려요. 주문에 담을까요?"]

            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})


def test_tts_failure_does_not_fail_recommendation_or_websocket_session() -> None:
    container = FakeContainer()
    tts_client = FakeTtsClient(fail=True)
    container.tts_client = tts_client
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_bytes(SPEECH)
            _receive_until(websocket, "turn.started")
            websocket.send_bytes(SILENCE * 75)
            candidates, _ = _receive_until(websocket, "menu.candidates")
            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})

    assert candidates["candidates"][0]["menuId"] == "menu-1"
    assert tts_client.texts
    assert container.speech.closed is True


def test_out_of_order_search_results_remain_bound_to_their_turns() -> None:
    container = FakeContainer()
    container.speech = MultiTurnFakeSpeech()
    container.recommendation_service = ReorderingRecommendationService()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 7,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            observed: list[dict] = []

            websocket.send_bytes(SPEECH)
            first_started, seen = _receive_until(websocket, "turn.started")
            observed.extend(seen)
            websocket.send_bytes(SILENCE * 75)
            _, seen = _receive_until(websocket, "turn.final")
            observed.extend(seen)

            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 8,
                    "cartItems": [],
                }
            )
            websocket.send_bytes(SPEECH)
            second_started, seen = _receive_until(websocket, "turn.started")
            observed.extend(seen)
            websocket.send_bytes(SILENCE * 75)
            _, seen = _receive_until(websocket, "turn.final")
            observed.extend(seen)

            candidate_events = [event for event in observed if event["type"] == "menu.candidates"]
            while len(candidate_events) < 2:
                event = websocket.receive_json()
                if event["type"] == "menu.candidates":
                    candidate_events.append(event)

            by_turn = {event["turnId"]: event for event in candidate_events}
            assert by_turn[first_started["turnId"]]["basedOnCartVersion"] == 7
            assert by_turn[first_started["turnId"]]["candidates"][0]["menuId"] == "first-menu"
            assert by_turn[second_started["turnId"]]["basedOnCartVersion"] == 8
            assert by_turn[second_started["turnId"]]["candidates"][0]["menuId"] == "second-menu"

            websocket.send_json({"type": "session.end", "sessionId": ready["sessionId"]})


def test_internal_reindex_requires_service_key() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)
    payload = {"menuIds": ["m-1"], "sourceRevision": 3, "reason": "menu.updated"}

    with TestClient(app) as client:
        denied = client.post("/ai/internal/v1/stores/s-1/reindex", json=payload)
        accepted = client.post(
            "/ai/internal/v1/stores/s-1/reindex",
            json=payload,
            headers={"X-Internal-API-Key": "internal-secret"},
        )

    assert denied.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["sourceRevision"] == 3


def test_binary_first_frame_gets_typed_protocol_error() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_bytes(SPEECH)
            error = websocket.receive_json()

    assert error == {
        "type": "error",
        "code": "protocol_error",
        "message": "the first message must be a valid session.start",
        "retryable": False,
    }


def test_speech_start_failure_closes_client_and_returns_provider_error() -> None:
    container = FakeContainer()
    container.speech = FailingStartSpeech()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 0,
                    "cartItems": [],
                }
            )
            error = websocket.receive_json()

    assert error["code"] == "clova_unavailable"
    assert error["retryable"] is True
    assert container.speech.closed is True


def test_cart_context_version_cannot_move_backwards() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        with client.websocket_connect("/ai/ws") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "accessToken": "valid-token",
                    "basedOnCartVersion": 7,
                    "cartItems": [],
                }
            )
            ready = websocket.receive_json()
            websocket.send_json(
                {
                    "type": "cart.context",
                    "sessionId": ready["sessionId"],
                    "basedOnCartVersion": 6,
                    "cartItems": [],
                }
            )
            error = websocket.receive_json()
            websocket.send_json(
                {
                    "type": "session.end",
                    "sessionId": ready["sessionId"],
                }
            )

    assert error["code"] == "stale_cart_context"
    assert error["sessionId"] == ready["sessionId"]
    assert error["retryable"] is True


def test_health_endpoints_use_container_readiness() -> None:
    container = FakeContainer()
    app = create_app(settings=container.settings, container=container)

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").status_code == 200
