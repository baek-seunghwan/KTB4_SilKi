from __future__ import annotations

from uuid import uuid4

import pytest

from silki_ai.contracts import MenuCandidate, SearchAttributes
from silki_ai.dialog import (
    DialogActionDecision,
    DialogClarificationDecision,
    DialogCompletedDecision,
    DialogNotReadyError,
    DialogPhase,
    DialogProposalDecision,
    StaleDialogError,
    VoiceOrderDialogAgent,
    deterministic_dialog_patch,
)
from silki_ai.recommendation import RecommendationResult


def result(
    *candidates: MenuCandidate,
    query: str,
    attributes: SearchAttributes | None = None,
    quantity: int = 1,
    degraded: bool = False,
) -> RecommendationResult:
    return RecommendationResult(
        search_query=query,
        quantity=quantity,
        attributes=attributes or SearchAttributes(),
        degraded=degraded,
        candidates=tuple(candidates),
    )


def candidate(
    menu_id: str,
    name: str,
    score: float = 0.8,
    *,
    available_temperatures: tuple[str, ...] = (),
) -> MenuCandidate:
    return MenuCandidate(
        menu_id=menu_id,
        name=name,
        score=score,
        available_temperatures=list(available_temperatures),
    )


def correlated(
    decision: (
        DialogActionDecision
        | DialogClarificationDecision
        | DialogCompletedDecision
        | DialogProposalDecision
    ),
) -> dict:
    return {
        "conversation_id": decision.conversation_id,
        "dialog_id": decision.dialog_id,
        "revision": decision.revision,
    }


def test_deterministic_patch_keeps_unspoken_fields_unset() -> None:
    first = deterministic_dialog_patch("아메리카노 두 잔 주세요")
    answer = deterministic_dialog_patch("아니, 차갑게요")

    assert first.search_query == "아메리카노"
    assert first.quantity == 2
    assert answer.search_query is None
    assert answer.quantity is None
    assert answer.temperature == "ice"


def test_multi_turn_voice_answers_accumulate_until_one_proposal() -> None:
    agent = VoiceOrderDialogAgent()
    first_search = agent.begin_turn("커피 줘")
    menu_question = agent.resolve(
        result(
            candidate("americano-ice", "아이스 아메리카노", 0.82),
            candidate("latte", "카페 라떼", 0.78),
            query="커피",
            attributes=SearchAttributes(category="coffee"),
        )
    )

    assert first_search.search_text == "커피"
    assert isinstance(menu_question, DialogClarificationDecision)
    assert menu_question.missing_slot == "menu"
    assert [choice.id for choice in menu_question.choices] == [
        "menu:americano-ice",
        "menu:latte",
    ]

    agent.listen(**correlated(menu_question))
    agent.begin_turn("아메리카노")
    temperature_question = agent.resolve(
        result(
            candidate("americano-hot", "따뜻한 아메리카노", 0.84),
            candidate("americano-ice", "아이스 아메리카노", 0.83),
            query="아메리카노",
            attributes=SearchAttributes(category="coffee"),
        )
    )

    assert isinstance(temperature_question, DialogClarificationDecision)
    assert temperature_question.missing_slot == "temperature"
    assert {choice.value for choice in temperature_question.choices} == {"hot", "ice"}

    agent.listen(**correlated(temperature_question))
    proposal = agent.begin_turn("차갑게요")

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "americano-ice"
    assert proposal.attributes.temperature == "ice"
    assert [(option.group_code, option.value_code) for option in proposal.resolved_options] == [
        ("TEMPERATURE", "ICE")
    ]
    assert agent.phase is DialogPhase.AWAITING_CONFIRMATION

    agent.listen(**correlated(proposal))


def test_menu_clarification_limits_buttons_and_spoken_text_to_two_candidates() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("커피 추천해줘")

    question = agent.resolve(
        result(
            candidate("americano", "아메리카노", 0.9),
            candidate("latte", "카페 라떼", 0.8),
            candidate("mocha", "카페 모카", 0.7),
            query="커피",
        )
    )

    assert isinstance(question, DialogClarificationDecision)
    assert [choice.id for choice in question.choices] == [
        "menu:americano",
        "menu:latte",
    ]
    assert "아메리카노 또는 카페 라떼" in question.text
    assert "카페 모카" not in question.text


@pytest.mark.parametrize(
    ("query", "selected_menu_id"),
    [
        ("카페라떼", "latte"),
        ("카페-모카!", "mocha"),
    ],
)
def test_canonical_exact_match_ignores_spaces_and_punctuation(
    query: str,
    selected_menu_id: str,
) -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn(f"차갑게 {query} 주세요")

    proposal = agent.resolve(
        result(
            candidate("latte", "카페 라떼"),
            candidate("mocha", "카페 모카"),
            query=query,
            attributes=SearchAttributes(temperature="ice"),
        )
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == selected_menu_id


def test_duplicate_canonical_names_are_not_selected_arbitrarily() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("카페라떼")

    question = agent.resolve(
        result(
            candidate("latte-a", "카페 라떼"),
            candidate("latte-b", "카페-라떼"),
            query="카페라떼",
        )
    )

    assert isinstance(question, DialogClarificationDecision)
    assert question.missing_slot == "menu"
    assert [choice.id for choice in question.choices] == [
        "menu:latte-a",
        "menu:latte-b",
    ]


def test_visible_choice_is_validated_and_needs_no_audio_turn() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아메리카노")
    question = agent.resolve(
        result(
            candidate("hot", "따뜻한 아메리카노"),
            candidate("ice", "아이스 아메리카노"),
            query="아메리카노",
        )
    )
    assert isinstance(question, DialogClarificationDecision)
    ice = next(choice for choice in question.choices if choice.value == "ice")

    proposal = agent.choose(
        **correlated(question),
        choice_id=ice.id,
        value=ice.value,
        label=ice.label,
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "ice"
    assert proposal.attributes.temperature == "ice"

    with pytest.raises(StaleDialogError):
        agent.choose(
            **correlated(question),
            choice_id=ice.id,
            value="hot",
            label=ice.label,
        )


def test_menu_choice_can_lead_to_temperature_question_without_new_search() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("커피")
    menu_question = agent.resolve(
        result(
            candidate("americano", "아메리카노"),
            candidate("latte", "카페 라떼"),
            query="커피",
            attributes=SearchAttributes(category="coffee"),
        )
    )
    assert isinstance(menu_question, DialogClarificationDecision)
    americano = next(choice for choice in menu_question.choices if choice.id == "menu:americano")

    next_question = agent.choose(
        **correlated(menu_question),
        choice_id=americano.id,
        value=americano.value,
        label=americano.label,
    )

    assert isinstance(next_question, DialogClarificationDecision)
    assert next_question.missing_slot == "temperature"
    assert agent.slots.search_query == "아메리카노"


def test_temperature_voice_answer_keeps_generic_menu_id_without_search() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("카페라떼")
    question = agent.resolve(result(candidate("latte", "카페 라떼"), query="카페라떼"))
    assert isinstance(question, DialogClarificationDecision)

    agent.listen(**correlated(question))
    proposal = agent.begin_turn("차갑게요")

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "latte"
    assert proposal.menu.name == "카페 라떼"
    assert proposal.attributes.temperature == "ice"


def test_unknown_temperature_answer_replays_current_question_without_search() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("카페라떼")
    question = agent.resolve(result(candidate("latte", "카페 라떼"), query="카페라떼"))
    assert isinstance(question, DialogClarificationDecision)

    agent.listen(**correlated(question))
    replay = agent.begin_turn("글쎄요")

    assert isinstance(replay, DialogClarificationDecision)
    assert replay.replayed is True
    assert replay.missing_slot == "temperature"
    assert replay.text == question.text
    assert replay.dialog_id != question.dialog_id
    assert agent.phase is DialogPhase.AWAITING_CLARIFICATION


def test_visible_choice_remains_valid_after_voice_listening_opens() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아메리카노")
    question = agent.resolve(
        result(
            candidate("hot", "따뜻한 아메리카노"),
            candidate("ice", "아이스 아메리카노"),
            query="아메리카노",
        )
    )
    assert isinstance(question, DialogClarificationDecision)
    ice = next(choice for choice in question.choices if choice.value == "ice")
    agent.listen(**correlated(question))

    proposal = agent.choose(
        **correlated(question),
        choice_id=ice.id,
        value=ice.value,
        label=ice.label,
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "ice"
    assert proposal.attributes.temperature == "ice"


def test_reject_replays_most_recent_clarification_and_generic_without_history() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아메리카노")
    temperature = agent.resolve(
        result(
            candidate("hot", "따뜻한 아메리카노"),
            candidate("ice", "아이스 아메리카노"),
            query="아메리카노",
        )
    )
    assert isinstance(temperature, DialogClarificationDecision)
    ice = next(choice for choice in temperature.choices if choice.value == "ice")
    proposal = agent.choose(
        **correlated(temperature),
        choice_id=ice.id,
        value=ice.value,
        label=ice.label,
    )
    assert isinstance(proposal, DialogProposalDecision)

    replay = agent.reject(**correlated(proposal))

    assert replay.replayed is True
    assert replay.missing_slot == "temperature"
    assert replay.dialog_id != temperature.dialog_id
    assert agent.slots.attributes.temperature is None

    direct = VoiceOrderDialogAgent()
    direct.begin_turn("아이스 아메리카노")
    direct_proposal = direct.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(direct_proposal, DialogProposalDecision)
    generic = direct.reject(**correlated(direct_proposal))
    assert generic.missing_slot == "menu"
    assert "다시" in generic.text


@pytest.mark.parametrize("answer", ["맞아", "맞아요", "네", "응", "그래"])
def test_confirmation_voice_accept_returns_correlated_client_action(answer: str) -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)

    agent.listen(**correlated(proposal))
    action = agent.begin_turn(answer)

    assert isinstance(action, DialogActionDecision)
    assert action.action == "accept"
    assert correlated(action) == correlated(proposal)
    assert agent.phase is DialogPhase.PENDING_ACTION


@pytest.mark.parametrize("answer", ["아니", "아니요", "아니야", "다른 거"])
def test_confirmation_voice_reject_returns_action_usable_by_existing_handler(
    answer: str,
) -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)

    agent.listen(**correlated(proposal))
    action = agent.begin_turn(answer)
    assert isinstance(action, DialogActionDecision)
    assert action.action == "reject"

    replay = agent.reject(**correlated(action))
    assert isinstance(replay, DialogClarificationDecision)
    assert replay.missing_slot == "menu"


def test_unknown_confirmation_answer_replays_same_menu_proposal() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)

    agent.listen(**correlated(proposal))
    replay = agent.begin_turn("잘 모르겠어요")

    assert isinstance(replay, DialogProposalDecision)
    assert replay.menu.menu_id == proposal.menu.menu_id
    assert replay.text == proposal.text
    assert replay.dialog_id != proposal.dialog_id
    assert replay.revision > proposal.revision
    assert agent.phase is DialogPhase.AWAITING_CONFIRMATION


def test_cart_completion_resets_on_next_turn() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노 두 잔")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
            quantity=2,
        )
    )
    assert isinstance(proposal, DialogProposalDecision)
    completed = agent.cart_completed()
    assert isinstance(completed, DialogCompletedDecision)
    assert completed.conversation_id == proposal.conversation_id
    assert completed.text == "장바구니에 담았어요. 더 주문하시겠어요?"

    next_turn = agent.begin_turn("딸기 스무디")
    assert next_turn.conversation_id != proposal.conversation_id
    assert agent.slots.quantity == 1


@pytest.mark.parametrize("answer", ["더 주문할게", "응", "네", "추가할게"])
def test_completion_voice_continue_returns_action_usable_by_reset_handler(answer: str) -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)
    completed = agent.cart_completed()

    agent.listen(**correlated(completed))
    action = agent.begin_turn(answer)
    assert isinstance(action, DialogActionDecision)
    assert action.action == "continue"
    assert correlated(action) == correlated(completed)

    next_prompt = agent.reset(**correlated(action))
    assert next_prompt.missing_slot == "menu"
    assert agent.phase is DialogPhase.AWAITING_CLARIFICATION


@pytest.mark.parametrize("answer", ["아니", "없어", "주문 마칠게", "그게 다야"])
def test_completion_voice_finish_returns_correlated_client_action(answer: str) -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)
    completed = agent.cart_completed()

    agent.listen(**correlated(completed))
    action = agent.begin_turn(answer)

    assert isinstance(action, DialogActionDecision)
    assert action.action == "finish"
    assert correlated(action) == correlated(completed)
    assert agent.phase is DialogPhase.PENDING_ACTION

    with pytest.raises(DialogNotReadyError):
        agent.listen(**correlated(completed))


def test_unknown_completion_answer_replays_current_completed_prompt() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(proposal, DialogProposalDecision)
    completed = agent.cart_completed()

    agent.listen(**correlated(completed))
    replay = agent.begin_turn("글쎄요")

    assert isinstance(replay, DialogCompletedDecision)
    assert replay.text == completed.text
    assert replay.dialog_id == completed.dialog_id
    assert replay.revision > completed.revision
    assert agent.phase is DialogPhase.COMPLETED


def test_button_and_cart_controls_remain_valid_after_voice_listening_opens() -> None:
    rejected = VoiceOrderDialogAgent()
    rejected.begin_turn("아이스 아메리카노")
    reject_proposal = rejected.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(reject_proposal, DialogProposalDecision)
    rejected.listen(**correlated(reject_proposal))
    assert isinstance(
        rejected.reject(**correlated(reject_proposal)),
        DialogClarificationDecision,
    )

    accepted = VoiceOrderDialogAgent()
    accepted.begin_turn("아이스 아메리카노")
    accept_proposal = accepted.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
        )
    )
    assert isinstance(accept_proposal, DialogProposalDecision)
    accepted.listen(**correlated(accept_proposal))
    completed = accepted.cart_completed()
    assert completed.text == "장바구니에 담았어요. 더 주문하시겠어요?"

    accepted.listen(**correlated(completed))
    assert isinstance(accepted.reset(**correlated(completed)), DialogClarificationDecision)


def test_stale_or_wrong_phase_controls_are_rejected() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("커피")
    question = agent.resolve(result(query="커피", degraded=True))
    assert isinstance(question, DialogClarificationDecision)

    with pytest.raises(StaleDialogError):
        agent.listen(
            conversation_id=question.conversation_id,
            dialog_id=uuid4(),
            revision=question.revision,
        )

    agent.listen(**correlated(question))
    with pytest.raises(DialogNotReadyError):
        agent.listen(**correlated(question))


def test_gemini_degraded_no_match_asks_safe_template_instead_of_inventing_menu() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("뭔가 맛있는 거")
    clarification = agent.resolve(result(query="맛있는 메뉴", degraded=True))

    assert isinstance(clarification, DialogClarificationDecision)
    assert clarification.missing_slot == "menu"
    assert clarification.choices == ()
    assert agent.phase is DialogPhase.AWAITING_CLARIFICATION


def test_clarification_count_is_bounded_and_resets_to_generic_prompt() -> None:
    agent = VoiceOrderDialogAgent(max_clarifications=1)
    agent.begin_turn("커피")
    first = agent.resolve(result(query="커피", degraded=True))
    assert isinstance(first, DialogClarificationDecision)
    agent.listen(**correlated(first))
    agent.begin_turn("아무거나")
    second = agent.resolve(result(query="아무거나", degraded=True))

    assert isinstance(second, DialogClarificationDecision)
    assert "처음부터" in second.text
    assert second.accumulated_slots.search_query == ""


def test_temperature_choice_keeps_selected_menu_without_another_search() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("카페 라떼")
    question = agent.resolve(result(candidate("latte", "카페 라떼"), query="카페 라떼"))
    assert isinstance(question, DialogClarificationDecision)
    ice = next(choice for choice in question.choices if choice.value == "ice")

    proposal = agent.choose(
        **correlated(question),
        choice_id=ice.id,
        value=ice.value,
        label=ice.label,
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "latte"
    assert proposal.menu.name == "카페 라떼"
    assert proposal.attributes.temperature == "ice"
    assert proposal.resolved_options[0].value_code == "ICE"


def test_unique_canonical_exact_match_is_checked_before_display_candidate_cap() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("카페라떼 차갑게")

    proposal = agent.resolve(
        result(
            candidate("tea", "대추차", 0.91, available_temperatures=("hot",)),
            candidate("mocha", "카페 모카", 0.82),
            candidate("latte", "카페 라떼", 0.71),
            query="카페라떼",
            attributes=SearchAttributes(temperature="ice"),
        )
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "latte"


def test_fixed_ice_menu_auto_applies_its_only_temperature() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("콜드 브루")

    proposal = agent.resolve(
        result(
            candidate("cold-brew", "콜드 브루", available_temperatures=("ice",)),
            query="콜드 브루",
        )
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "cold-brew"
    assert proposal.attributes.temperature == "ice"
    assert [(item.group_code, item.value_code) for item in proposal.resolved_options] == [
        ("TEMPERATURE", "ICE")
    ]


def test_opposite_temperature_for_fixed_menu_reasks_only_valid_option() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("따뜻한 콜드 브루")

    clarification = agent.resolve(
        result(
            candidate("cold-brew", "콜드 브루", available_temperatures=("ice",)),
            query="콜드 브루",
            attributes=SearchAttributes(temperature="hot"),
        )
    )

    assert isinstance(clarification, DialogClarificationDecision)
    assert clarification.missing_slot == "temperature"
    assert [(choice.value, choice.label) for choice in clarification.choices] == [("ice", "차갑게")]
    assert "차갑게만" in clarification.text

    choice = clarification.choices[0]
    proposal = agent.choose(
        **correlated(clarification),
        choice_id=choice.id,
        value=choice.value,
        label=choice.label,
    )
    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "cold-brew"
    assert proposal.attributes.temperature == "ice"


def test_affirmative_voice_answer_accepts_only_supported_temperature() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("따뜻한 콜드 브루")
    clarification = agent.resolve(
        result(
            candidate("cold-brew", "콜드 브루", available_temperatures=("ice",)),
            query="콜드 브루",
        )
    )
    assert isinstance(clarification, DialogClarificationDecision)
    assert [choice.value for choice in clarification.choices] == ["ice"]

    agent.listen(**correlated(clarification))
    proposal = agent.begin_turn("네")

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.menu.menu_id == "cold-brew"
    assert proposal.attributes.temperature == "ice"


def test_negative_voice_answer_to_fixed_temperature_returns_to_menu_question() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("따뜻한 콜드 브루")
    clarification = agent.resolve(
        result(
            candidate("cold-brew", "콜드 브루", available_temperatures=("ice",)),
            query="콜드 브루",
        )
    )
    assert isinstance(clarification, DialogClarificationDecision)

    agent.listen(**correlated(clarification))
    menu_question = agent.begin_turn("아니요")

    assert isinstance(menu_question, DialogClarificationDecision)
    assert menu_question.missing_slot == "menu"
    assert "다른 메뉴" in menu_question.text
    assert agent.slots.search_query == ""


def test_fixed_hot_menu_never_offers_ice() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("차가운 유자차")

    clarification = agent.resolve(
        result(
            candidate("citron-tea", "유자차", available_temperatures=("hot",)),
            query="유자차",
            attributes=SearchAttributes(temperature="ice"),
        )
    )

    assert isinstance(clarification, DialogClarificationDecision)
    assert [choice.value for choice in clarification.choices] == ["hot"]


def test_quantity_above_cart_limit_requires_clarification_and_never_proposes() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아이스 아메리카노 21잔 주세요")
    clarification = agent.resolve(
        result(
            candidate("ice", "아이스 아메리카노"),
            query="아이스 아메리카노",
            attributes=SearchAttributes(temperature="ice"),
            quantity=21,
        )
    )

    assert isinstance(clarification, DialogClarificationDecision)
    assert clarification.missing_slot == "quantity"
    assert "20개" in clarification.text
    assert clarification.accumulated_slots.quantity == 1


def test_gemini_cannot_fill_unspoken_order_affecting_slots() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("아메리카노 주세요")
    decision = agent.resolve(
        result(
            candidate("hot", "따뜻한 아메리카노"),
            query="따뜻한 아메리카노",
            attributes=SearchAttributes(
                category="coffee",
                temperature="hot",
                sweetness="high",
                caffeine="normal",
            ),
        )
    )

    assert isinstance(decision, DialogClarificationDecision)
    assert decision.missing_slot == "temperature"
    assert agent.slots.attributes.temperature is None
    assert agent.slots.attributes.sweetness is None
    assert agent.slots.attributes.caffeine is None


def test_explicit_transcript_slots_survive_conflicting_gemini_attributes() -> None:
    agent = VoiceOrderDialogAgent()
    agent.begin_turn("따뜻하고 덜 달게 디카페인 아메리카노")
    proposal = agent.resolve(
        result(
            candidate("hot-decaf", "따뜻한 디카페인 아메리카노"),
            query="아메리카노",
            attributes=SearchAttributes(
                category="coffee",
                temperature="ice",
                sweetness="high",
                caffeine="normal",
            ),
        )
    )

    assert isinstance(proposal, DialogProposalDecision)
    assert proposal.attributes.temperature == "hot"
    assert proposal.attributes.sweetness == "low"
    assert proposal.attributes.caffeine == "none"
