from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from silki_ai.config import Settings
from silki_ai.contracts import (
    CLIENT_MESSAGE_ADAPTER,
    SERVER_MESSAGE_ADAPTER,
    CartContext,
    DialogAction,
    DialogChoice,
    DialogClarification,
    DialogCompleted,
    DialogProposal,
    GeminiQuery,
    MenuCandidate,
    MenuCandidates,
    ReindexRequest,
    SearchAttributes,
    SessionStart,
    SttPartial,
)


def test_client_message_accepts_camel_case_and_serializes_public_contract() -> None:
    message = CLIENT_MESSAGE_ADAPTER.validate_python(
        {
            "type": "session.start",
            "accessToken": "signed-token",
            "basedOnCartVersion": 7,
            "cartItems": [{"menuId": "menu-1", "quantity": 2, "optionIds": []}],
        }
    )

    assert isinstance(message, SessionStart)
    assert message.based_on_cart_version == 7
    assert message.model_dump(mode="json", by_alias=True) == {
        "type": "session.start",
        "accessToken": "signed-token",
        "basedOnCartVersion": 7,
        "cartItems": [{"menuId": "menu-1", "quantity": 2, "optionIds": []}],
        "capabilities": [],
    }


def test_dialog_v1_capability_and_choice_control_are_strict() -> None:
    start = CLIENT_MESSAGE_ADAPTER.validate_python(
        {
            "type": "session.start",
            "accessToken": "signed-token",
            "basedOnCartVersion": 0,
            "cartItems": [],
            "capabilities": ["dialog.v1"],
        }
    )
    assert isinstance(start, SessionStart)
    assert start.capabilities == ["dialog.v1"]

    correlation = {
        "sessionId": str(uuid4()),
        "conversationId": str(uuid4()),
        "dialogId": str(uuid4()),
        "revision": 3,
    }
    choice = CLIENT_MESSAGE_ADAPTER.validate_python(
        {
            "type": "dialog.choice",
            **correlation,
            "choiceId": "temperature:ice",
            "value": "ice",
            "label": "차갑게",
        }
    )
    assert isinstance(choice, DialogChoice)

    with pytest.raises(ValidationError):
        CLIENT_MESSAGE_ADAPTER.validate_python(
            {
                "type": "session.start",
                "accessToken": "signed-token",
                "basedOnCartVersion": 0,
                "cartItems": [],
                "capabilities": ["dialog.v2"],
            }
        )


def test_dialog_server_events_serialize_correlation_and_camel_case() -> None:
    common = {
        "session_id": uuid4(),
        "conversation_id": uuid4(),
        "dialog_id": uuid4(),
        "revision": 2,
        "turn_id": uuid4(),
        "based_on_cart_version": 7,
        "text": "차갑게 드릴까요?",
        "tts_expected": True,
    }
    clarification = DialogClarification(
        **common,
        missing_slot="temperature",
        choices=[{"id": "temperature:ice", "label": "차갑게", "value": "ice"}],
        accumulated_slots={"searchQuery": "아메리카노", "attributes": {}},
    )
    payload = clarification.model_dump(mode="json", by_alias=True)
    assert payload["conversationId"] == str(common["conversation_id"])
    assert payload["missingSlot"] == "temperature"
    assert payload["accumulatedSlots"]["quantity"] == 1

    proposal = DialogProposal(
        **(common | {"text": "아이스 아메리카노 한 잔이 맞나요?"}),
        menu={"menuId": "m-1", "name": "아이스 아메리카노", "score": 0.9},
        attributes={"temperature": "ice"},
        resolved_options=[{"groupCode": "TEMPERATURE", "valueCode": "ICE"}],
        degraded=False,
    )
    validated = SERVER_MESSAGE_ADAPTER.validate_python(
        proposal.model_dump(mode="json", by_alias=True)
    )
    assert isinstance(validated, DialogProposal)
    assert validated.resolved_options[0].value_code == "ICE"

    with pytest.raises(ValidationError):
        DialogProposal(
            **(common | {"text": "너무 많은 수량"}),
            menu={"menuId": "m-1", "name": "아메리카노", "score": 0.9},
            quantity=21,
            attributes={},
        )


def test_dialog_completion_and_spoken_action_keep_full_correlation() -> None:
    correlation = {
        "session_id": uuid4(),
        "conversation_id": uuid4(),
        "dialog_id": uuid4(),
        "revision": 4,
        "turn_id": uuid4(),
    }
    completed = DialogCompleted(**correlation, tts_expected=True)
    completed_payload = completed.model_dump(mode="json", by_alias=True)

    assert completed_payload["text"] == "장바구니에 담았어요. 더 주문하시겠어요?"
    assert completed_payload["ttsExpected"] is True
    assert completed_payload["turnId"] == str(correlation["turn_id"])

    for action_name in ("accept", "reject", "continue", "finish"):
        parsed = SERVER_MESSAGE_ADAPTER.validate_python(
            DialogAction(**correlation, action=action_name).model_dump(mode="json", by_alias=True)
        )
        assert isinstance(parsed, DialogAction)
        assert parsed.action == action_name

    with pytest.raises(ValidationError):
        DialogAction(**correlation, action="add_to_cart")


def test_cart_context_rejects_invalid_versions_and_unknown_fields() -> None:
    session_id = str(uuid4())
    with pytest.raises(ValidationError):
        CartContext.model_validate(
            {
                "type": "cart.context",
                "sessionId": session_id,
                "basedOnCartVersion": -1,
                "cartItems": [],
            }
        )

    with pytest.raises(ValidationError):
        CartContext.model_validate(
            {
                "type": "cart.context",
                "sessionId": session_id,
                "basedOnCartVersion": 1,
                "cartItems": [],
                "authoritative": True,
            }
        )

    for invalid_version in (True, "1"):
        with pytest.raises(ValidationError):
            CartContext.model_validate(
                {
                    "type": "cart.context",
                    "sessionId": session_id,
                    "basedOnCartVersion": invalid_version,
                    "cartItems": [],
                }
            )


def test_gemini_schema_cannot_select_or_mutate_menu_and_cart() -> None:
    result = GeminiQuery.model_validate(
        {
            "search_query": "차갑고 달지 않은 음료",
            "attributes": {
                "temperature": "ice",
                "sweetness": "low",
                "excluded_tags": ["sweet"],
            },
        }
    )
    assert result.search_query == "차갑고 달지 않은 음료"
    assert result.quantity == 1
    assert "search_query" in GeminiQuery.response_json_schema()["properties"]

    with pytest.raises(ValidationError):
        GeminiQuery.model_validate(
            {
                "search_query": "아메리카노",
                "attributes": {},
                "menuId": "menu-1",
                "cartAction": "add",
            }
        )

    for invalid_quantity in (0, 100, "2", True):
        with pytest.raises(ValidationError):
            GeminiQuery.model_validate(
                {
                    "search_query": "아메리카노",
                    "quantity": invalid_quantity,
                    "attributes": {},
                }
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", "cold"),
        ("sweetness", "very_high"),
        ("caffeine", "decaf"),
    ],
)
def test_search_attributes_reject_noncanonical_filter_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        SearchAttributes.model_validate({field: value})


def test_session_start_accepts_normal_rs256_token_length() -> None:
    message = SessionStart(
        access_token="x" * 2048,
        based_on_cart_version=0,
    )

    assert len(message.access_token) == 2048


def test_blank_optional_environment_values_are_unset() -> None:
    settings = Settings(
        _env_file=None,
        clova_secret_key="",
        clova_keyword_file="",
        gemini_api_key="",
        fish_tts_api_key="",
        fish_tts_reference_id="",
        internal_api_key="",
    )

    assert settings.clova_secret_key is None
    assert settings.clova_keyword_file is None
    assert settings.gemini_api_key is None
    assert settings.fish_tts_api_key is None
    assert settings.fish_tts_reference_id is None
    assert settings.internal_api_key is None


def test_fish_tts_requires_private_service_configuration_when_enabled() -> None:
    with pytest.raises(ValidationError, match="fish_tts_base_url"):
        Settings(_env_file=None, fish_tts_enabled=True)

    with pytest.raises(ValidationError, match="fish_tts_api_key"):
        Settings(
            _env_file=None,
            fish_tts_enabled=True,
            fish_tts_base_url="http://10.0.2.15:8080",
        )

    with pytest.raises(ValidationError, match="must not contain a path"):
        Settings(
            _env_file=None,
            fish_tts_enabled=True,
            fish_tts_base_url="http://10.0.2.15:8080/v1/tts",
            fish_tts_api_key="secret",
        )

    settings = Settings(
        _env_file=None,
        fish_tts_enabled=True,
        fish_tts_base_url="http://10.0.2.15:8080/",
        fish_tts_api_key="secret",
    )
    assert settings.fish_tts_base_url == "http://10.0.2.15:8080"


def test_tts_provider_and_edge_voice_settings_are_validated() -> None:
    settings = Settings(
        _env_file=None,
        tts_provider="edge",
        edge_tts_voice="  ko-KR-SunHiNeural  ",
        edge_tts_rate="-5%",
    )

    assert settings.effective_tts_provider == "edge"
    assert settings.edge_tts_voice == "ko-KR-SunHiNeural"

    with pytest.raises(ValidationError):
        Settings(_env_file=None, tts_provider="browser")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, edge_tts_rate="fast")


def test_explicit_provider_overrides_legacy_fish_enabled_flag() -> None:
    settings = Settings(
        _env_file=None,
        tts_provider="disabled",
        fish_tts_enabled=True,
    )

    assert settings.effective_tts_provider == "disabled"


def test_blank_required_jwt_issuer_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_issuer="")


def test_async_turn_events_keep_session_and_turn_ids_separate() -> None:
    session_id = uuid4()
    first_turn_id = uuid4()
    second_turn_id = uuid4()

    first = SttPartial(
        session_id=session_id,
        turn_id=first_turn_id,
        text="차가운",
    )
    second = SERVER_MESSAGE_ADAPTER.validate_python(
        {
            "type": "stt.partial",
            "sessionId": str(session_id),
            "turnId": str(second_turn_id),
            "text": "따뜻한",
        }
    )

    assert first.session_id == second.session_id
    assert first.turn_id != second.turn_id
    assert first.model_dump(mode="json", by_alias=True)["turnId"] == str(first_turn_id)


def test_menu_candidates_include_interpretation_cart_version() -> None:
    event = MenuCandidates(
        session_id=uuid4(),
        turn_id=uuid4(),
        based_on_cart_version=12,
        search_query="카페인이 적은 커피",
        attributes=SearchAttributes(caffeine="low"),
        candidates=[
            MenuCandidate(
                menu_id="decaf-1",
                name="디카페인 아메리카노",
                score=0.91,
                matched_attributes=["caffeine"],
            )
        ],
    )

    payload = event.model_dump(mode="json", by_alias=True)
    assert payload["basedOnCartVersion"] == 12
    assert "cartVersion" not in payload
    assert payload["quantity"] == 1
    assert payload["candidates"][0]["menuId"] == "decaf-1"


def test_reindex_request_is_idempotency_friendly() -> None:
    request = ReindexRequest(
        menu_ids=["menu-1", "menu-1", "menu-2"],
        source_revision=42,
        reason="menu_updated",
    )

    assert request.menu_ids == ["menu-1", "menu-2"]
    assert request.model_dump(by_alias=True)["sourceRevision"] == 42
