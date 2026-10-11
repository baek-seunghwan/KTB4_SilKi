"""Typed public and internal contracts for the Silki AI service.

Python code uses snake_case names while public WebSocket and HTTP payloads are
serialized with camelCase aliases. Gemini output remains a deliberately narrow
schema: it can describe a search but cannot choose a menu item or mutate a cart.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    field_validator,
)


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
TranscriptText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
CartVersion = Annotated[StrictInt, Field(ge=0)]
AccessToken = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8192)
]
AudioBase64 = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=4, max_length=11_200_000)
]
Temperature = Literal["ice", "hot"]
Sweetness = Literal["low", "medium", "high"]
Caffeine = Literal["none", "low", "normal"]
DialogCapability = Literal["dialog.v1"]
DialogPurpose = Literal["clarification", "proposal", "completion"]
DialogActionName = Literal["accept", "reject", "continue", "finish"]


class ContractModel(BaseModel):
    """Strict base model for service boundaries."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class SearchAttributes(ContractModel):
    """Optional constraints inferred from a completed user utterance."""

    category: NonEmptyString | None = None
    temperature: Temperature | None = None
    sweetness: Sweetness | None = None
    caffeine: Caffeine | None = None
    flavor_tags: list[NonEmptyString] = Field(default_factory=list, max_length=20)
    excluded_tags: list[NonEmptyString] = Field(default_factory=list, max_length=20)

    @field_validator("flavor_tags", "excluded_tags")
    @classmethod
    def deduplicate_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class GeminiQuery(ContractModel):
    """The complete, and intentionally limited, Gemini response schema."""

    search_query: TranscriptText
    quantity: StrictInt = Field(default=1, ge=1, le=99)
    attributes: SearchAttributes

    @classmethod
    def response_json_schema(cls) -> dict[str, object]:
        """Return the snake_case schema sent to Gemini structured output."""

        return cls.model_json_schema(by_alias=False)


# Descriptive alias retained for callers that prefer an explicit result name.
GeminiQueryResult = GeminiQuery


class CartItemContext(ContractModel):
    menu_id: Identifier
    quantity: StrictInt = Field(ge=1, le=99)
    option_ids: list[Identifier] = Field(default_factory=list, max_length=30)


class SessionStart(ContractModel):
    type: Literal["session.start"] = "session.start"
    access_token: AccessToken
    based_on_cart_version: CartVersion
    cart_items: list[CartItemContext] = Field(default_factory=list, max_length=200)
    capabilities: list[DialogCapability] = Field(default_factory=list, max_length=1)

    @field_validator("capabilities")
    @classmethod
    def deduplicate_capabilities(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class CartContext(ContractModel):
    type: Literal["cart.context"] = "cart.context"
    session_id: UUID
    based_on_cart_version: CartVersion
    cart_items: list[CartItemContext] = Field(default_factory=list, max_length=200)


class SessionEnd(ContractModel):
    type: Literal["session.end"] = "session.end"
    session_id: UUID
    reason: NonEmptyString | None = None


class DialogListen(ContractModel):
    type: Literal["dialog.listen"] = "dialog.listen"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)


class DialogChoice(ContractModel):
    type: Literal["dialog.choice"] = "dialog.choice"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    choice_id: Identifier
    value: NonEmptyString
    label: NonEmptyString


class DialogReject(ContractModel):
    type: Literal["dialog.reject"] = "dialog.reject"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)


class DialogReset(ContractModel):
    type: Literal["dialog.reset"] = "dialog.reset"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)


ClientControlMessage: TypeAlias = Annotated[
    SessionStart
    | CartContext
    | SessionEnd
    | DialogListen
    | DialogChoice
    | DialogReject
    | DialogReset,
    Field(discriminator="type"),
]
CLIENT_MESSAGE_ADAPTER = TypeAdapter(ClientControlMessage)


class TurnEndReason(StrEnum):
    SILENCE = "silence"
    INCOMPLETE_TIMEOUT = "incomplete_timeout"
    TRANSCRIPT_STABLE_TIMEOUT = "transcript_stable_timeout"
    MAX_DURATION = "max_duration"
    SESSION_END = "session_end"
    CLOVA_FINAL = "clova_final"


class ErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    SESSION_START_TIMEOUT = "session_start_timeout"
    PROTOCOL_ERROR = "protocol_error"
    AUDIO_FORMAT_INVALID = "audio_format_invalid"
    CLOVA_UNAVAILABLE = "clova_unavailable"
    GEMINI_DEGRADED = "gemini_degraded"
    NO_MATCH = "no_match"
    STALE_CART_CONTEXT = "stale_cart_context"
    STALE_DIALOG = "stale_dialog"
    DIALOG_NOT_READY = "dialog_not_ready"
    INTERNAL_ERROR = "internal_error"


class SessionReady(ContractModel):
    type: Literal["session.ready"] = "session.ready"
    session_id: UUID
    order_session_id: Identifier
    store_id: Identifier
    capabilities: list[DialogCapability] = Field(default_factory=list, max_length=1)


class TurnStarted(ContractModel):
    type: Literal["turn.started"] = "turn.started"
    session_id: UUID
    turn_id: UUID
    based_on_cart_version: CartVersion


class SttPartial(ContractModel):
    type: Literal["stt.partial"] = "stt.partial"
    session_id: UUID
    turn_id: UUID
    text: str = Field(max_length=10_000)


class TurnFinal(ContractModel):
    type: Literal["turn.final"] = "turn.final"
    session_id: UUID
    turn_id: UUID
    text: TranscriptText
    reason: TurnEndReason


class MenuCandidate(ContractModel):
    menu_id: Identifier
    name: NonEmptyString
    description: str = Field(default="", max_length=2_000)
    score: float = Field(ge=0, le=1)
    matched_attributes: list[NonEmptyString] = Field(default_factory=list, max_length=30)
    available_temperatures: list[Temperature] = Field(default_factory=list, max_length=2)

    @field_validator("available_temperatures")
    @classmethod
    def deduplicate_available_temperatures(cls, value: list[Temperature]) -> list[Temperature]:
        """Keep source capability metadata compact and deterministic on the wire."""

        return list(dict.fromkeys(value))


class DialogChoiceItem(ContractModel):
    id: Identifier
    label: NonEmptyString
    value: NonEmptyString


class DialogAccumulatedSlots(ContractModel):
    search_query: str = Field(default="", max_length=10_000)
    quantity: StrictInt = Field(default=1, ge=1, le=20)
    attributes: SearchAttributes


class DialogClarification(ContractModel):
    type: Literal["dialog.clarification"] = "dialog.clarification"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    turn_id: UUID
    based_on_cart_version: CartVersion
    text: NonEmptyString
    missing_slot: NonEmptyString
    choices: list[DialogChoiceItem] = Field(default_factory=list, max_length=10)
    accumulated_slots: DialogAccumulatedSlots
    tts_expected: bool


class ResolvedOption(ContractModel):
    group_code: NonEmptyString
    value_code: NonEmptyString


class DialogProposal(ContractModel):
    type: Literal["dialog.proposal"] = "dialog.proposal"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    turn_id: UUID
    based_on_cart_version: CartVersion
    text: NonEmptyString
    menu: MenuCandidate
    quantity: StrictInt = Field(default=1, ge=1, le=20)
    attributes: SearchAttributes
    resolved_options: list[ResolvedOption] = Field(default_factory=list, max_length=30)
    degraded: bool = False
    tts_expected: bool


class DialogCompleted(ContractModel):
    type: Literal["dialog.completed"] = "dialog.completed"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    turn_id: UUID
    text: NonEmptyString = "장바구니에 담았어요. 더 주문하시겠어요?"
    tts_expected: bool


class DialogAction(ContractModel):
    """A spoken decision that the FE maps to its existing button handler."""

    type: Literal["dialog.action"] = "dialog.action"
    session_id: UUID
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    turn_id: UUID
    action: DialogActionName


class MenuCandidates(ContractModel):
    type: Literal["menu.candidates"] = "menu.candidates"
    session_id: UUID
    turn_id: UUID
    based_on_cart_version: CartVersion
    search_query: TranscriptText
    quantity: StrictInt = Field(default=1, ge=1, le=99)
    attributes: SearchAttributes
    degraded: bool = False
    candidates: list[MenuCandidate] = Field(min_length=1, max_length=3)


class NoMatch(ContractModel):
    type: Literal["no_match"] = "no_match"
    session_id: UUID
    turn_id: UUID
    based_on_cart_version: CartVersion
    search_query: TranscriptText
    quantity: StrictInt = Field(default=1, ge=1, le=99)
    attributes: SearchAttributes
    degraded: bool = False
    message: NonEmptyString = "조건에 맞는 메뉴를 찾지 못했습니다. 다시 말씀해 주세요."


class TtsAudio(ContractModel):
    """One complete non-streaming TTS result, encoded for a JSON WebSocket frame."""

    type: Literal["tts.audio"] = "tts.audio"
    session_id: UUID
    turn_id: UUID
    media_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    audio_base64: AudioBase64
    text: NonEmptyString
    conversation_id: UUID | None = None
    dialog_id: UUID | None = None
    revision: StrictInt | None = Field(default=None, ge=0)
    purpose: DialogPurpose | None = None


class TtsUnavailable(ContractModel):
    type: Literal["tts.unavailable"] = "tts.unavailable"
    session_id: UUID
    turn_id: UUID | None = None
    conversation_id: UUID
    dialog_id: UUID
    revision: StrictInt = Field(ge=0)
    purpose: DialogPurpose
    text: NonEmptyString


class ErrorMessage(ContractModel):
    type: Literal["error"] = "error"
    session_id: UUID | None = None
    turn_id: UUID | None = None
    code: ErrorCode
    message: NonEmptyString
    retryable: bool


ServerMessage: TypeAlias = Annotated[
    SessionReady
    | TurnStarted
    | SttPartial
    | TurnFinal
    | MenuCandidates
    | NoMatch
    | DialogClarification
    | DialogProposal
    | DialogCompleted
    | DialogAction
    | TtsAudio
    | TtsUnavailable
    | ErrorMessage,
    Field(discriminator="type"),
]
SERVER_MESSAGE_ADAPTER = TypeAdapter(ServerMessage)


class ReindexRequest(ContractModel):
    menu_ids: list[Identifier] = Field(default_factory=list, max_length=10_000)
    source_revision: StrictInt = Field(ge=0)
    reason: NonEmptyString

    @field_validator("menu_ids")
    @classmethod
    def deduplicate_menu_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class ReindexStatus(StrEnum):
    PROCESSED = "processed"
    IGNORED_STALE = "ignored_stale"


class ReindexResponse(ContractModel):
    store_id: Identifier
    source_revision: int = Field(ge=0)
    indexed_count: int = Field(default=0, ge=0)
    deleted_count: int = Field(default=0, ge=0)
    status: ReindexStatus
