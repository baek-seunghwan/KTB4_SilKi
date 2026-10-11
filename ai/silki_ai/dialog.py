"""Bounded multi-turn dialog state for the voice-order WebSocket.

The reducer in this module is deliberately provider- and transport-agnostic.  Gemini
may refine the cumulative search through ``MenuRecommendationService``, but it never
owns menu identifiers, option identifiers, confirmation, or cart mutation.  Every
state transition is deterministic and scoped to one authenticated WebSocket.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Literal, TypeAlias
from uuid import UUID, uuid4

from silki_ai.contracts import (
    DialogAccumulatedSlots,
    DialogChoiceItem,
    MenuCandidate,
    ResolvedOption,
    SearchAttributes,
)
from silki_ai.nlp import extract_attributes, extract_quantity
from silki_ai.recommendation import RecommendationResult


class DialogPhase(StrEnum):
    LISTENING = "listening"
    PROCESSING = "processing"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    PENDING_ACTION = "pending_action"


class StaleDialogError(ValueError):
    """A client control referred to an older dialog revision or modal."""


class DialogNotReadyError(ValueError):
    """A validly correlated control is not allowed in the current phase."""


@dataclass(frozen=True, slots=True)
class DialogSlotPatch:
    """Only explicitly spoken fields are populated; missing values never erase state."""

    search_query: str | None = None
    quantity: int | None = None
    category: str | None = None
    temperature: str | None = None
    sweetness: str | None = None
    caffeine: str | None = None
    flavor_tags: tuple[str, ...] = ()
    excluded_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DialogSlots:
    search_query: str = ""
    quantity: int = 1
    invalid_quantity: int | None = None
    attributes: SearchAttributes = field(default_factory=SearchAttributes)

    def public(self) -> DialogAccumulatedSlots:
        return DialogAccumulatedSlots(
            search_query=self.search_query,
            quantity=self.quantity,
            attributes=self.attributes,
        )


@dataclass(frozen=True, slots=True)
class DialogSearchRequest:
    conversation_id: UUID
    revision: int
    search_text: str


@dataclass(frozen=True, slots=True)
class DialogClarificationDecision:
    conversation_id: UUID
    dialog_id: UUID
    revision: int
    text: str
    missing_slot: str
    choices: tuple[DialogChoiceItem, ...]
    accumulated_slots: DialogAccumulatedSlots
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DialogProposalDecision:
    conversation_id: UUID
    dialog_id: UUID
    revision: int
    text: str
    menu: MenuCandidate
    quantity: int
    attributes: SearchAttributes
    resolved_options: tuple[ResolvedOption, ...]
    degraded: bool


@dataclass(frozen=True, slots=True)
class DialogCompletedDecision:
    conversation_id: UUID
    dialog_id: UUID
    revision: int
    text: str = "장바구니에 담았어요. 더 주문하시겠어요?"


DialogAction: TypeAlias = Literal["accept", "reject", "continue", "finish"]


@dataclass(frozen=True, slots=True)
class DialogActionDecision:
    """Ask the client to invoke the same trusted handler as a visible button."""

    conversation_id: UUID
    dialog_id: UUID
    revision: int
    action: DialogAction


DialogDecision: TypeAlias = DialogClarificationDecision | DialogProposalDecision
DialogChoiceResult: TypeAlias = DialogSearchRequest | DialogDecision
DialogTurnResult: TypeAlias = (
    DialogSearchRequest | DialogDecision | DialogCompletedDecision | DialogActionDecision
)


@dataclass(frozen=True, slots=True)
class _ChoiceAction:
    item: DialogChoiceItem
    kind: str
    candidate: MenuCandidate | None = None


@dataclass(frozen=True, slots=True)
class _ClarificationRecord:
    missing_slot: str
    text: str
    choices: tuple[_ChoiceAction, ...]
    slots_before: DialogSlots


class _ListeningContext(StrEnum):
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    COMPLETION = "completion"


_ANSWER_ONLY = re.compile(
    r"^(?:아니[,.]?\s*)?(?:아이스|차갑게|차가운|시원하게|핫|따뜻하게|뜨겁게|"
    r"덜\s*달게|보통|더\s*달게)(?:\s*(?:주세요|할게요|이요|요))?$"
)
_MENU_TERM = re.compile(
    r"커피|아메리카노|라떼|에스프레소|카푸치노|모카|마끼아또|콜드\s*브루|"
    r"티|차|에이드|스무디|프라페|디저트|케이크|쿠키|빵"
)
_ICE = re.compile(r"아이스|차갑(?:게|고|거나|은)?|시원(?:하게|한)?|얼음|냉")
_HOT = re.compile(r"핫|따뜻(?:하게|한)?|뜨겁(?:게|고|거나|은)?|데운|따신|뜨신")
_POLITE = re.compile(r"\b(?:주세요|줘|주문|먹을래|먹고\s*싶어|할게요|이요|요)\b")
_DRINK_NAME = re.compile(
    r"커피|아메리카노|라떼|에스프레소|카푸치노|모카|마끼아또|콜드\s*브루|"
    r"티|차|에이드|스무디|프라페"
)
_CANONICAL_SEPARATOR = re.compile(r"[\W_]+", re.UNICODE)
_CONFIRMATION_ACCEPT = frozenset(("맞아", "맞아요", "네", "응", "그래"))
_CONFIRMATION_REJECT = frozenset(("아니", "아니요", "아니야", "다른거"))
_FOLLOW_UP_CONTINUE = frozenset(("더주문할게", "응", "네", "추가할게"))
_FOLLOW_UP_FINISH = frozenset(("아니", "없어", "주문마칠게", "그게다야"))


def _canonical_text(value: str) -> str:
    """Return a comparison-only spelling without whitespace or punctuation."""

    return _CANONICAL_SEPARATOR.sub("", value.casefold())


def deterministic_dialog_patch(transcript: str) -> DialogSlotPatch:
    """Extract a conservative delta that remains usable when Gemini is unavailable."""

    normalized = " ".join(transcript.strip().split())
    if not normalized:
        raise ValueError("dialog transcript must not be blank")

    quantity, without_quantity = extract_quantity(normalized)
    explicit_quantity = quantity if without_quantity != normalized else None
    attributes = extract_attributes(normalized)
    query = _POLITE.sub(" ", without_quantity)
    query = " ".join(query.split()).strip(" ,.!?")
    if _ANSWER_ONLY.fullmatch(query):
        query = ""

    return DialogSlotPatch(
        search_query=query or None,
        quantity=explicit_quantity,
        category=attributes.category,
        temperature=attributes.temperature,
        sweetness=attributes.sweetness,
        caffeine=attributes.caffeine,
        flavor_tags=tuple(attributes.flavor_tags),
        excluded_tags=tuple(attributes.excluded_tags),
    )


def _merge_slots(slots: DialogSlots, patch: DialogSlotPatch) -> DialogSlots:
    query = slots.search_query
    if patch.search_query:
        if not query or _MENU_TERM.search(patch.search_query):
            query = patch.search_query
        elif patch.search_query.casefold() not in query.casefold():
            query = f"{query} {patch.search_query}"

    old = slots.attributes
    flavors = list(old.flavor_tags)
    excluded = list(old.excluded_tags)
    for tag in patch.flavor_tags:
        if tag not in flavors:
            flavors.append(tag)
        if tag in excluded:
            excluded.remove(tag)
    for tag in patch.excluded_tags:
        if tag not in excluded:
            excluded.append(tag)
        if tag in flavors:
            flavors.remove(tag)

    return DialogSlots(
        search_query=query,
        quantity=(
            patch.quantity
            if patch.quantity is not None and patch.quantity <= 20
            else slots.quantity
        ),
        invalid_quantity=(
            slots.invalid_quantity
            if patch.quantity is None
            else patch.quantity
            if patch.quantity > 20
            else None
        ),
        attributes=SearchAttributes(
            category=patch.category or old.category,
            temperature=patch.temperature or old.temperature,
            sweetness=patch.sweetness or old.sweetness,
            caffeine=patch.caffeine or old.caffeine,
            flavor_tags=flavors,
            excluded_tags=excluded,
        ),
    )


def _temperature_from_name(name: str) -> str | None:
    if _ICE.search(name):
        return "ice"
    if _HOT.search(name):
        return "hot"
    return None


def _base_menu_name(name: str) -> str:
    value = _ICE.sub(" ", name.casefold())
    value = _HOT.sub(" ", value)
    return " ".join(value.split())


def _query_exactly_names(query: str, candidate: MenuCandidate) -> bool:
    normalized_query = _POLITE.sub(" ", query.casefold())
    return bool(
        (canonical_query := _canonical_text(normalized_query))
        and canonical_query == _canonical_text(candidate.name)
    )


def _resolved_options(attributes: SearchAttributes) -> tuple[ResolvedOption, ...]:
    values: list[ResolvedOption] = []
    if attributes.temperature is not None:
        values.append(
            ResolvedOption(group_code="TEMPERATURE", value_code=attributes.temperature.upper())
        )
    sweetness_codes = {"low": "LESS", "medium": "NORMAL", "high": "MORE"}
    if attributes.sweetness is not None:
        values.append(
            ResolvedOption(
                group_code="SWEETNESS",
                value_code=sweetness_codes[attributes.sweetness],
            )
        )
    return tuple(values)


class VoiceOrderDialogAgent:
    """Pure connection-scoped reducer for one bounded voice-order conversation."""

    def __init__(self, *, max_clarifications: int = 4, max_transcripts: int = 8) -> None:
        if max_clarifications < 1:
            raise ValueError("max_clarifications must be positive")
        if max_transcripts < 1:
            raise ValueError("max_transcripts must be positive")
        self._max_clarifications = max_clarifications
        self._transcripts: deque[str] = deque(maxlen=max_transcripts)
        self._conversation_id = uuid4()
        self._revision = 0
        self._phase = DialogPhase.LISTENING
        self._slots = DialogSlots()
        self._current_dialog_id: UUID | None = None
        self._current_choices: dict[str, _ChoiceAction] = {}
        self._current_missing_slot: str | None = None
        self._current_prompt_text = ""
        self._clarifications: list[_ClarificationRecord] = []
        self._proposal: DialogProposalDecision | None = None
        self._completed: DialogCompletedDecision | None = None
        self._selected_candidate: MenuCandidate | None = None
        self._selected_degraded = False
        self._listening_context: _ListeningContext | None = None
        self._pending_action: DialogActionDecision | None = None

    @property
    def conversation_id(self) -> UUID:
        return self._conversation_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def phase(self) -> DialogPhase:
        return self._phase

    @property
    def current_dialog_id(self) -> UUID | None:
        return self._current_dialog_id

    @property
    def slots(self) -> DialogSlots:
        return self._slots

    @property
    def can_complete_cart(self) -> bool:
        """Whether a newer authoritative cart version may complete this proposal."""

        return bool(
            self._proposal is not None
            and (
                self._phase is DialogPhase.AWAITING_CONFIRMATION
                or (
                    self._phase is DialogPhase.LISTENING
                    and self._listening_context is _ListeningContext.CONFIRMATION
                )
                or (
                    self._phase is DialogPhase.PENDING_ACTION
                    and self._pending_action is not None
                    and self._pending_action.action == "accept"
                )
            )
        )

    def begin_turn(self, transcript: str) -> DialogTurnResult:
        if self._phase is DialogPhase.COMPLETED:
            self._new_conversation()
        if self._phase not in {DialogPhase.LISTENING, DialogPhase.AWAITING_CLARIFICATION}:
            raise DialogNotReadyError("dialog is not accepting a speech turn")

        normalized = " ".join(transcript.strip().split())
        if not normalized:
            raise ValueError("dialog transcript must not be blank")
        self._transcripts.append(normalized)

        if self._listening_context is _ListeningContext.CONFIRMATION:
            return self._confirmation_voice_outcome(normalized)
        if self._listening_context is _ListeningContext.COMPLETION:
            return self._completion_voice_outcome(normalized)

        patch = deterministic_dialog_patch(normalized)
        if (
            self._listening_context is _ListeningContext.CLARIFICATION
            and self._current_missing_slot == "temperature"
        ):
            answer = _canonical_text(normalized)
            if patch.temperature is None and answer in _CONFIRMATION_ACCEPT:
                temperature_choices = tuple(
                    action
                    for action in self._current_choices.values()
                    if action.kind == "temperature"
                )
                if len(temperature_choices) == 1:
                    patch = replace(
                        patch,
                        temperature=temperature_choices[0].item.value,
                    )
            elif patch.temperature is None and answer in _CONFIRMATION_REJECT:
                temperature_choices = tuple(
                    action
                    for action in self._current_choices.values()
                    if action.kind == "temperature"
                )
                if len(temperature_choices) == 1:
                    self._slots = replace(
                        self._slots,
                        search_query="",
                        attributes=self._replace_temperature(None),
                    )
                    self._selected_candidate = None
                    self._selected_degraded = False
                    return self._clarify(
                        missing_slot="menu",
                        text="알겠습니다. 원하시는 다른 메뉴를 말씀해 주세요.",
                        choices=(),
                        replayed=True,
                        remember=False,
                    )
            if patch.temperature is None:
                return self._replay_current_clarification()
            candidate = self._candidate_for_temperature(patch.temperature)
            if candidate is None:
                return self._replay_current_clarification()
            self._slots = _merge_slots(self._slots, patch)
            self._selected_candidate = candidate
            self._listening_context = None
            return self._proposal_for(candidate, self._selected_degraded)

        self._listening_context = None
        self._slots = _merge_slots(self._slots, patch)
        self._phase = DialogPhase.PROCESSING
        self._current_missing_slot = None
        self._current_prompt_text = ""
        self._current_choices = {}
        self._advance_revision()
        return DialogSearchRequest(
            conversation_id=self._conversation_id,
            revision=self._revision,
            search_text=self._search_text(),
        )

    def resolve(self, result: RecommendationResult) -> DialogDecision:
        if self._phase is not DialogPhase.PROCESSING:
            raise DialogNotReadyError("dialog is not waiting for recommendation results")
        self._slots = replace(
            self._slots,
            search_query=result.search_query,
            quantity=(
                result.quantity
                if self._slots.quantity == 1 and 1 <= result.quantity <= 20
                else self._slots.quantity
            ),
            attributes=self._merge_normalized_attributes(result.attributes),
        )
        if self._slots.invalid_quantity is not None:
            return self._clarify(
                missing_slot="quantity",
                text="한 번에 20개까지 담을 수 있어요. 수량을 다시 말씀해 주세요.",
                choices=(),
            )
        all_candidates = tuple(result.candidates)
        if not all_candidates:
            self._selected_candidate = None
            self._selected_degraded = False
            return self._clarify(
                missing_slot="menu",
                text="원하시는 메뉴를 조금 더 자세히 말씀해 주세요.",
                choices=(),
            )

        exact = tuple(
            candidate
            for candidate in all_candidates
            if _query_exactly_names(self._slots.search_query, candidate)
        )
        if len(exact) == 1:
            return self._evaluate_selected(exact[0], result.degraded)

        candidates = all_candidates[:2]
        if len(candidates) == 1:
            return self._evaluate_selected(candidates[0], result.degraded)

        bases = {_base_menu_name(candidate.name) for candidate in candidates}
        if self._slots.attributes.temperature is None and len(bases) == 1:
            return self._temperature_clarification(candidates, degraded=result.degraded)

        self._selected_candidate = None
        self._selected_degraded = False
        actions = tuple(
            _ChoiceAction(
                item=DialogChoiceItem(
                    id=f"menu:{candidate.menu_id}",
                    label=candidate.name,
                    value=candidate.name,
                ),
                kind="menu",
                candidate=candidate,
            )
            for candidate in candidates
        )
        labels = " 또는 ".join(action.item.label for action in actions)
        return self._clarify(
            missing_slot="menu",
            text=f"{labels} 중 어떤 메뉴를 원하세요?",
            choices=actions,
        )

    def listen(
        self,
        *,
        conversation_id: UUID,
        dialog_id: UUID,
        revision: int,
    ) -> None:
        self._require_correlation(conversation_id, dialog_id, revision)
        contexts = {
            DialogPhase.AWAITING_CLARIFICATION: _ListeningContext.CLARIFICATION,
            DialogPhase.AWAITING_CONFIRMATION: _ListeningContext.CONFIRMATION,
            DialogPhase.COMPLETED: _ListeningContext.COMPLETION,
        }
        context = contexts.get(self._phase)
        if context is None:
            raise DialogNotReadyError("dialog.listen is not valid in the current phase")
        self._listening_context = context
        self._phase = DialogPhase.LISTENING

    def choose(
        self,
        *,
        conversation_id: UUID,
        dialog_id: UUID,
        revision: int,
        choice_id: str,
        value: str,
        label: str,
    ) -> DialogChoiceResult:
        self._require_correlation(conversation_id, dialog_id, revision)
        if self._phase is DialogPhase.LISTENING:
            listening_for_clarification = self._listening_context is _ListeningContext.CLARIFICATION
        else:
            listening_for_clarification = False
        if self._phase is not DialogPhase.AWAITING_CLARIFICATION and not (
            self._phase is DialogPhase.LISTENING and listening_for_clarification
        ):
            raise DialogNotReadyError(
                "dialog.choice is only valid while clarification is waiting or listening"
            )
        action = self._current_choices.get(choice_id)
        if action is None or action.item.value != value or action.item.label != label:
            raise StaleDialogError("dialog choice does not match the current prompt")

        self._listening_context = None
        if action.kind == "menu" and action.candidate is not None:
            self._slots = replace(self._slots, search_query=action.candidate.name)
            self._advance_revision()
            return self._evaluate_selected(action.candidate, degraded=False)
        if action.kind == "temperature":
            candidate = self._candidate_for_temperature(value)
            if candidate is None:
                raise DialogNotReadyError("temperature choice is not supported by this menu")
            self._slots = replace(
                self._slots,
                attributes=self._replace_temperature(value),
            )
            self._selected_candidate = candidate
            return self._proposal_for(candidate, self._selected_degraded)
        raise DialogNotReadyError("unsupported dialog choice")

    def reject(
        self,
        *,
        conversation_id: UUID,
        dialog_id: UUID,
        revision: int,
    ) -> DialogClarificationDecision:
        self._require_correlation(conversation_id, dialog_id, revision)
        if (
            self._phase is DialogPhase.PENDING_ACTION
            and self._pending_action is not None
            and self._pending_action.action == "reject"
        ):
            self._phase = DialogPhase.AWAITING_CONFIRMATION
            self._pending_action = None
        if self._phase is DialogPhase.LISTENING and (
            self._listening_context is _ListeningContext.CONFIRMATION
        ):
            self._phase = DialogPhase.AWAITING_CONFIRMATION
            self._listening_context = None
        if self._phase is not DialogPhase.AWAITING_CONFIRMATION:
            raise DialogNotReadyError("dialog.reject is only valid for a proposal")
        if self._clarifications:
            record = self._clarifications[-1]
            self._slots = record.slots_before
            return self._clarify(
                missing_slot=record.missing_slot,
                text=record.text,
                choices=record.choices,
                replayed=True,
                remember=False,
            )
        self._slots = DialogSlots()
        self._selected_candidate = None
        self._selected_degraded = False
        return self._clarify(
            missing_slot="menu",
            text="알겠습니다. 원하시는 메뉴를 다시 말씀해 주세요.",
            choices=(),
            replayed=True,
            remember=False,
        )

    def reset(
        self,
        *,
        conversation_id: UUID,
        dialog_id: UUID,
        revision: int,
    ) -> DialogClarificationDecision:
        self._require_correlation(conversation_id, dialog_id, revision)
        if self._phase is DialogPhase.PENDING_ACTION:
            if self._pending_action is None or self._pending_action.action != "continue":
                raise DialogNotReadyError("dialog.reset does not match the pending voice action")
            self._pending_action = None
        self._listening_context = None
        self._slots = DialogSlots()
        self._clarifications.clear()
        self._proposal = None
        self._completed = None
        self._selected_candidate = None
        self._selected_degraded = False
        return self._clarify(
            missing_slot="menu",
            text="원하시는 메뉴를 다시 말씀해 주세요.",
            choices=(),
            replayed=True,
            remember=False,
        )

    def cart_completed(self) -> DialogCompletedDecision:
        if (
            self._phase is DialogPhase.PENDING_ACTION
            and self._pending_action is not None
            and self._pending_action.action == "accept"
        ):
            self._phase = DialogPhase.AWAITING_CONFIRMATION
            self._pending_action = None
        if self._phase is DialogPhase.LISTENING and (
            self._listening_context is _ListeningContext.CONFIRMATION
        ):
            self._phase = DialogPhase.AWAITING_CONFIRMATION
            self._listening_context = None
        if self._phase is not DialogPhase.AWAITING_CONFIRMATION or self._proposal is None:
            raise DialogNotReadyError("cart completion requires an active proposal")
        proposal = self._proposal
        self._advance_revision()
        self._phase = DialogPhase.COMPLETED
        self._current_dialog_id = proposal.dialog_id
        self._current_missing_slot = None
        self._current_choices = {}
        self._pending_action = None
        completed = DialogCompletedDecision(
            conversation_id=self._conversation_id,
            dialog_id=proposal.dialog_id,
            revision=self._revision,
        )
        self._completed = completed
        self._current_prompt_text = completed.text
        return completed

    def _evaluate_selected(
        self,
        candidate: MenuCandidate,
        degraded: bool,
    ) -> DialogDecision:
        self._selected_candidate = candidate
        self._selected_degraded = degraded
        supported = tuple(candidate.available_temperatures)
        requested = self._slots.attributes.temperature
        if len(supported) == 1:
            only_temperature = supported[0]
            if requested is None:
                self._slots = replace(
                    self._slots,
                    attributes=self._replace_temperature(only_temperature),
                )
                return self._proposal_for(candidate, degraded)
            if requested != only_temperature:
                self._slots = replace(
                    self._slots,
                    attributes=self._replace_temperature(None),
                )
                return self._temperature_clarification((candidate,), degraded=degraded)
        elif supported and requested is not None and requested not in supported:
            self._slots = replace(
                self._slots,
                attributes=self._replace_temperature(None),
            )
            return self._temperature_clarification((candidate,), degraded=degraded)
        if self._needs_temperature(candidate):
            return self._temperature_clarification((candidate,), degraded=degraded)
        return self._proposal_for(candidate, degraded)

    def _needs_temperature(self, candidate: MenuCandidate) -> bool:
        if self._slots.attributes.temperature is not None:
            return False
        # A temperature word in a DB candidate name is not evidence that the
        # customer requested it.  Only deterministic transcript extraction or a
        # validated dialog.choice may populate the order-affecting slot.
        return bool(_DRINK_NAME.search(candidate.name))

    def _temperature_clarification(
        self,
        candidates: tuple[MenuCandidate, ...],
        *,
        degraded: bool,
    ) -> DialogClarificationDecision:
        if len(candidates) == 1:
            self._selected_candidate = candidates[0]
        self._selected_degraded = degraded
        declared = {
            temperature
            for candidate in candidates
            for temperature in candidate.available_temperatures
        }
        inferred = {
            temperature
            for candidate in candidates
            if (temperature := _temperature_from_name(candidate.name)) is not None
        }
        allowed = tuple(
            temperature
            for temperature in ("hot", "ice")
            if temperature in (declared or inferred or {"hot", "ice"})
        )
        actions = tuple(
            _ChoiceAction(
                item=DialogChoiceItem(
                    id=f"temperature:{temperature}",
                    label="따뜻하게" if temperature == "hot" else "차갑게",
                    value=temperature,
                ),
                kind="temperature",
                candidate=next(
                    (
                        candidate
                        for candidate in candidates
                        if temperature in candidate.available_temperatures
                        or (
                            not candidate.available_temperatures
                            and _temperature_from_name(candidate.name) == temperature
                        )
                    ),
                    None,
                ),
            )
            for temperature in allowed
        )
        if allowed == ("hot",):
            text = f"{candidates[0].name}는 따뜻하게만 주문할 수 있어요. 따뜻하게 드릴까요?"
        elif allowed == ("ice",):
            text = f"{candidates[0].name}는 차갑게만 주문할 수 있어요. 차갑게 드릴까요?"
        else:
            text = "따뜻하게 드릴까요, 차갑게 드릴까요?"
        return self._clarify(
            missing_slot="temperature",
            text=text,
            choices=actions,
        )

    def _clarify(
        self,
        *,
        missing_slot: str,
        text: str,
        choices: tuple[_ChoiceAction, ...],
        replayed: bool = False,
        remember: bool = True,
    ) -> DialogClarificationDecision:
        if remember and len(self._clarifications) >= self._max_clarifications:
            self._slots = DialogSlots()
            self._clarifications.clear()
            self._selected_candidate = None
            self._selected_degraded = False
            missing_slot = "menu"
            text = "질문이 길어졌어요. 원하시는 메뉴를 처음부터 다시 말씀해 주세요."
            choices = ()
        record = _ClarificationRecord(
            missing_slot=missing_slot,
            text=text,
            choices=choices,
            slots_before=self._slots,
        )
        if remember:
            self._clarifications.append(record)
        self._advance_revision()
        self._phase = DialogPhase.AWAITING_CLARIFICATION
        self._listening_context = None
        self._current_dialog_id = uuid4()
        self._current_missing_slot = missing_slot
        self._current_prompt_text = text
        self._current_choices = {choice.item.id: choice for choice in choices}
        self._proposal = None
        self._completed = None
        self._pending_action = None
        return DialogClarificationDecision(
            conversation_id=self._conversation_id,
            dialog_id=self._current_dialog_id,
            revision=self._revision,
            text=text,
            missing_slot=missing_slot,
            choices=tuple(choice.item for choice in choices),
            accumulated_slots=self._slots.public(),
            replayed=replayed,
        )

    def _proposal_for(
        self,
        candidate: MenuCandidate,
        degraded: bool,
    ) -> DialogProposalDecision:
        self._selected_candidate = candidate
        self._selected_degraded = degraded
        self._advance_revision()
        self._phase = DialogPhase.AWAITING_CONFIRMATION
        self._listening_context = None
        self._pending_action = None
        self._current_dialog_id = uuid4()
        self._current_missing_slot = None
        quantity = self._slots.quantity
        counter = "잔" if quantity > 0 else "개"
        proposal = DialogProposalDecision(
            conversation_id=self._conversation_id,
            dialog_id=self._current_dialog_id,
            revision=self._revision,
            text=f"{candidate.name} {quantity}{counter}이 맞나요?",
            menu=candidate,
            quantity=quantity,
            attributes=self._slots.attributes,
            resolved_options=_resolved_options(self._slots.attributes),
            degraded=degraded,
        )
        self._proposal = proposal
        self._completed = None
        self._current_prompt_text = proposal.text
        self._current_choices = {}
        return proposal

    def _candidate_for_temperature(self, value: str) -> MenuCandidate | None:
        action = next(
            (choice for choice in self._current_choices.values() if choice.item.value == value),
            None,
        )
        if action is None:
            return None
        candidate = action.candidate or self._selected_candidate
        if candidate is None:
            return None
        if candidate.available_temperatures and value not in candidate.available_temperatures:
            return None
        return candidate

    def _confirmation_voice_outcome(self, transcript: str) -> DialogTurnResult:
        self._phase = DialogPhase.AWAITING_CONFIRMATION
        self._listening_context = None
        answer = _canonical_text(transcript)
        if answer in _CONFIRMATION_ACCEPT:
            return self._dialog_action("accept")
        if answer in _CONFIRMATION_REJECT:
            return self._dialog_action("reject")
        if self._proposal is None:
            raise DialogNotReadyError("confirmation has no active proposal")
        return self._proposal_for(self._proposal.menu, self._proposal.degraded)

    def _completion_voice_outcome(self, transcript: str) -> DialogTurnResult:
        self._phase = DialogPhase.COMPLETED
        self._listening_context = None
        answer = _canonical_text(transcript)
        if answer in _FOLLOW_UP_CONTINUE:
            return self._dialog_action("continue")
        if answer in _FOLLOW_UP_FINISH:
            return self._dialog_action("finish")
        if self._completed is None:
            raise DialogNotReadyError("completion has no active prompt")
        self._advance_revision()
        replay = replace(self._completed, revision=self._revision)
        self._completed = replay
        self._current_prompt_text = replay.text
        return replay

    def _dialog_action(self, action: DialogAction) -> DialogActionDecision:
        if self._current_dialog_id is None:
            raise DialogNotReadyError("dialog action has no active prompt")
        decision = DialogActionDecision(
            conversation_id=self._conversation_id,
            dialog_id=self._current_dialog_id,
            revision=self._revision,
            action=action,
        )
        self._phase = DialogPhase.PENDING_ACTION
        self._listening_context = None
        self._pending_action = decision
        return decision

    def _replay_current_clarification(self) -> DialogClarificationDecision:
        if self._current_missing_slot is None or not self._current_prompt_text:
            raise DialogNotReadyError("clarification has no active prompt")
        return self._clarify(
            missing_slot=self._current_missing_slot,
            text=self._current_prompt_text,
            choices=tuple(self._current_choices.values()),
            replayed=True,
            remember=False,
        )

    def _merge_normalized_attributes(self, normalized: SearchAttributes) -> SearchAttributes:
        current = self._slots.attributes
        return SearchAttributes(
            category=current.category or normalized.category,
            # Gemini is allowed to improve retrieval, but these values change the
            # selected product/options.  Preserve only values that came from the
            # deterministic transcript patch or a server-issued visible choice.
            temperature=current.temperature,
            sweetness=current.sweetness,
            caffeine=current.caffeine,
            flavor_tags=list(dict.fromkeys([*current.flavor_tags, *normalized.flavor_tags])),
            excluded_tags=list(dict.fromkeys([*current.excluded_tags, *normalized.excluded_tags])),
        )

    def _replace_temperature(self, value: str | None) -> SearchAttributes:
        current = self._slots.attributes
        return SearchAttributes(
            category=current.category,
            temperature=value,  # type: ignore[arg-type]
            sweetness=current.sweetness,
            caffeine=current.caffeine,
            flavor_tags=current.flavor_tags,
            excluded_tags=current.excluded_tags,
        )

    def _search_text(self) -> str:
        attributes = self._slots.attributes
        words = [self._slots.search_query]
        if attributes.temperature:
            words.append("차갑게" if attributes.temperature == "ice" else "따뜻하게")
        if attributes.sweetness:
            words.append(
                {"low": "덜 달게", "medium": "보통 당도", "high": "달게"}[attributes.sweetness]
            )
        if attributes.caffeine == "none":
            words.append("디카페인")
        words.extend(attributes.flavor_tags)
        words.extend(f"{tag} 제외" for tag in attributes.excluded_tags)
        return " ".join(dict.fromkeys(word for word in words if word)).strip() or "메뉴"

    def _require_correlation(
        self,
        conversation_id: UUID,
        dialog_id: UUID,
        revision: int,
    ) -> None:
        if (
            conversation_id != self._conversation_id
            or dialog_id != self._current_dialog_id
            or revision != self._revision
        ):
            raise StaleDialogError("dialog correlation is stale")

    def _advance_revision(self) -> None:
        self._revision += 1

    def _new_conversation(self) -> None:
        self._conversation_id = uuid4()
        self._revision = 0
        self._phase = DialogPhase.LISTENING
        self._slots = DialogSlots()
        self._current_dialog_id = None
        self._current_choices = {}
        self._current_missing_slot = None
        self._current_prompt_text = ""
        self._clarifications.clear()
        self._proposal = None
        self._completed = None
        self._selected_candidate = None
        self._selected_degraded = False
        self._listening_context = None
        self._pending_action = None
        self._transcripts.clear()
