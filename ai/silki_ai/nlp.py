"""Turn-final query normalization for menu retrieval.

Gemini is deliberately kept behind a narrow boundary: it may only rewrite a final
STT transcript into :class:`GeminiQuery`.  It never sees an API capable of selecting
a menu, confirming an order, or mutating a cart.  Every provider failure falls back
to deterministic local extraction so speech sessions can continue in degraded mode.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from silki_ai.contracts import (
    Caffeine,
    GeminiQuery,
    SearchAttributes,
    Sweetness,
    Temperature,
)

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_INSTRUCTION = """
당신은 한국어 키오스크 메뉴 검색어 정규화기다.
최종 음성 인식 문장을 검색용 문장, 주문 수량, 검색 속성으로만 변환하라.
반환 객체는 제공된 JSON 스키마를 정확히 따라야 한다.
temperature는 ice 또는 hot, sweetness는 low/medium/high, caffeine은
none/low/normal 중 문장에 근거가 있는 값만 사용하라.
수량 표현이 있으면 1~99 정수로 추출하고 search_query에서는 그 표현을 제거하라.
수량 표현이 없으면 quantity는 1이다. 메뉴를 선택하거나 menuId를 만들지 말고,
주문 확정·옵션 선택·장바구니 작업을 판단하거나 반환하지 마라.
문장에 근거가 없는 속성은 null 또는 빈 배열로 둔다.
""".strip()


class _GeminiAttributesSchema(BaseModel):
    """Provider-only snake_case schema; public contracts remain camelCase."""

    # Gemini's REST Schema message does not accept additionalProperties.
    # Pydantic emits that keyword for extra="forbid" and google-genai 1.75
    # serializes it as additional_properties, which the API rejects with 400.
    # The raw response is still validated against strict GeminiQuery below.
    model_config = ConfigDict(extra="ignore")

    category: str | None
    temperature: Temperature | None
    sweetness: Sweetness | None
    caffeine: Caffeine | None
    flavor_tags: list[str]
    excluded_tags: list[str]


class _GeminiResponseSchema(BaseModel):
    # See _GeminiAttributesSchema: provider compatibility belongs here while
    # strict response validation remains owned by GeminiQuery.
    model_config = ConfigDict(extra="ignore")

    search_query: str
    quantity: int = Field(ge=1, le=99)
    attributes: _GeminiAttributesSchema


class GeminiModels(Protocol):
    """Small provider seam used by the runtime and unit tests."""

    async def generate_content(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class QueryNormalizationResult:
    """A retrieval query plus whether deterministic fallback was used."""

    query: GeminiQuery
    degraded: bool

    @property
    def search_query(self) -> str:
        return self.query.search_query

    @property
    def attributes(self) -> SearchAttributes:
        return self.query.attributes

    @property
    def quantity(self) -> int:
        return self.query.quantity


_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "coffee",
        (
            "커피",
            "아메리카노",
            "카페 라떼",
            "에스프레소",
            "카푸치노",
            "모카",
            "마끼아또",
            "콜드브루",
            "콜드 브루",
        ),
    ),
    (
        "tea",
        (
            "티",
            "홍차",
            "녹차",
            "말차",
            "밀크티",
            "우롱차",
            "허브차",
            "캐모마일",
            "대추차",
            "유자차",
            "쌍화차",
        ),
    ),
    ("ade", ("에이드", "에이드류")),
    ("smoothie", ("스무디", "프라페", "블렌디드")),
    ("dessert", ("디저트", "케이크", "쿠키", "빵", "베이커리")),
)

_FLAVOR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chocolate", ("초콜릿", "초코", "코코아")),
    ("caramel", ("카라멜", "캐러멜")),
    ("vanilla", ("바닐라",)),
    ("nutty", ("고소", "견과", "너티")),
    ("fruity", ("과일", "프루티")),
    ("citrus", ("시트러스", "레몬", "라임", "오렌지", "자몽")),
    ("mint", ("민트",)),
    ("strawberry", ("딸기",)),
    ("peach", ("복숭아",)),
    ("grape", ("청포도", "포도")),
    ("sweet_potato", ("고구마",)),
    ("green_tea", ("녹차", "말차")),
    ("yogurt", ("요거트",)),
    ("jujube", ("대추",)),
    ("yuzu", ("유자",)),
    ("herbal", ("캐모마일", "허브")),
)

_EXCLUSION_SUFFIX = re.compile(r"(?:빼|제외|말고|싫|없|안\s*들)")

_KOREAN_QUANTITIES = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}
_QUANTITY_PATTERN = re.compile(
    r"(?<!\d)(?P<number>\d{1,2}|하나|다섯|여섯|일곱|여덟|아홉|한|두|둘|세|셋|네|넷|열)"
    r"\s*(?:개|잔|컵|병)(?:을|를|만|씩|이요|요)?(?=\s|$|[,.!?])"
)
_OPTION_QUANTITY_PREFIX = re.compile(r"(?:샷|시럽|펌프|휘핑|토핑)\s*$")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_excluded(text: str, words: tuple[str, ...]) -> bool:
    for word in words:
        start = 0
        while (position := text.find(word, start)) >= 0:
            before = text[max(0, position - 5) : position]
            after = text[position + len(word) : position + len(word) + 8]
            if _EXCLUSION_SUFFIX.search(after) or re.search(r"(?:없는|없는\s*걸)\s*$", before):
                return True
            start = position + len(word)
    return False


def extract_attributes(transcript: str) -> SearchAttributes:
    """Extract a conservative, deterministic subset of menu attributes.

    The canonical values are intentionally small and stable.  The Spring-owned menu
    source should expose the same values for attribute filters; unknown phrases stay
    unset and are still represented by the semantic query embedding.
    """

    text = " ".join(transcript.strip().lower().split())

    category = next(
        (canonical for canonical, words in _CATEGORY_RULES if _contains_any(text, words)),
        None,
    )

    temperature: str | None = None
    if _contains_any(text, ("아이스", "차갑", "차가", "시원", "얼음", "냉")):
        temperature = "ice"
    elif _contains_any(text, ("핫", "따뜻", "뜨겁", "데운", "따신", "뜨신")):
        temperature = "hot"

    sweetness: str | None = None
    if re.search(r"(?:안\s*(?:단|달)|달지\s*않|덜\s*달|단맛\s*(?:빼|없이|적))", text):
        sweetness = "low"
    elif re.search(r"(?:당도|단맛)(?:는|은|가)?\s*(?:보통|중간|적당)", text):
        sweetness = "medium"
    elif _contains_any(text, ("달달", "달콤", "단 거", "단것", "단맛")):
        sweetness = "high"

    caffeine: str | None = None
    if _contains_any(text, ("디카페인", "카페인 없이", "카페인 없는", "무카페인")):
        caffeine = "none"
    elif re.search(r"카페인(?:이|을|은)?\s*(?:적|낮|조금)", text):
        caffeine = "low"
    elif _contains_any(text, ("카페인", "샷", "각성")):
        caffeine = "normal"

    flavor_tags: list[str] = []
    excluded_tags: list[str] = []
    for canonical, words in _FLAVOR_RULES:
        if not _contains_any(text, words):
            continue
        target = excluded_tags if _is_excluded(text, words) else flavor_tags
        target.append(canonical)

    return SearchAttributes(
        category=category,
        temperature=temperature,
        sweetness=sweetness,
        caffeine=caffeine,
        flavor_tags=flavor_tags,
        excluded_tags=excluded_tags,
    )


def extract_quantity(transcript: str) -> tuple[int, str]:
    """Return an explicit item count and a search phrase without that count.

    Counter units keep quantities separate from menu terms such as ``2샷``.  If no
    valid 1~99 quantity exists, the safe ordering default is one and the transcript
    is left intact.
    """

    for match in _QUANTITY_PATTERN.finditer(transcript):
        if _OPTION_QUANTITY_PREFIX.search(transcript[: match.start()]):
            continue
        token = match.group("number")
        quantity = int(token) if token.isdigit() else _KOREAN_QUANTITIES[token]
        if not 1 <= quantity <= 99:
            continue
        without_quantity = f"{transcript[: match.start()]} {transcript[match.end() :]}"
        search_query = " ".join(without_quantity.split()).strip(" ,.!?")
        return quantity, search_query or " ".join(transcript.split())
    return 1, " ".join(transcript.split())


def deterministic_fallback(transcript: str) -> GeminiQuery:
    """Extract safe local fields and retain only rule-supported attributes."""

    normalized = " ".join(transcript.strip().split())
    if not normalized:
        raise ValueError("a final STT transcript must not be blank")
    quantity, search_query = extract_quantity(normalized)
    return GeminiQuery(
        search_query=search_query,
        quantity=quantity,
        attributes=extract_attributes(normalized),
    )


# Stable public name used by offline prompt/evaluation tooling.
deterministic_refinement = deterministic_fallback


class GeminiQueryNormalizer:
    """Normalize final STT with Gemini and fail closed to local extraction.

    ``client`` is injectable to keep provider calls testable.  When omitted, the
    Google Gen AI client is created lazily from ``api_key``.  Prompt text can be
    supplied directly or loaded from a path by the composition root.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-3.5-flash-lite",
        timeout_seconds: float = 3.0,
        client: Any | None = None,
        system_instruction: str | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if system_instruction is not None and prompt_path is not None:
            raise ValueError("provide system_instruction or prompt_path, not both")

        if prompt_path is not None:
            system_instruction = Path(prompt_path).read_text(encoding="utf-8").strip()

        self._model = model
        self._timeout_seconds = timeout_seconds
        self._system_instruction = system_instruction or DEFAULT_SYSTEM_INSTRUCTION
        self._client = client
        if self._client is None and api_key:
            from google import genai

            self._client = genai.Client(api_key=api_key)

    async def normalize(self, transcript: str) -> QueryNormalizationResult:
        """Return a strict query result, using deterministic fallback on any failure."""

        fallback = deterministic_fallback(transcript)
        if self._client is None:
            return QueryNormalizationResult(query=fallback, degraded=True)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw_response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=f"최종 STT 문장:\n{fallback.search_query}",
                    config=self._generation_config(),
                )
            query = self._parse_response(raw_response)
            return QueryNormalizationResult(query=query, degraded=False)
        except Exception as exc:  # provider/schema boundary; cancellation is not swallowed
            logger.warning("Gemini query normalization fell back (%s)", type(exc).__name__)
            return QueryNormalizationResult(query=fallback, degraded=True)

    def _generation_config(self) -> Any:
        from google.genai import types

        # Gemini rejects provider deadlines below ten seconds even though this
        # application deliberately gives query refinement a much smaller latency
        # budget.  Keep the real budget in the outer ``asyncio.timeout`` above and
        # clamp only the SDK/HTTP deadline sent to the provider.
        provider_timeout_ms = max(10_000, int(self._timeout_seconds * 1000))
        return types.GenerateContentConfig(
            system_instruction=self._system_instruction,
            temperature=0,
            response_mime_type="application/json",
            # Let the SDK translate the Pydantic model into Gemini's supported
            # schema subset instead of sending unsupported validation keywords.
            response_schema=_GeminiResponseSchema,
            http_options=types.HttpOptions(timeout=provider_timeout_ms),
        )

    @staticmethod
    def _parse_response(response: Any) -> GeminiQuery:
        # Prefer the unmodified provider JSON.  A provider-only Pydantic model
        # intentionally ignores extras so its generated schema stays compatible
        # with Gemini; validating the raw text here ensures GeminiQuery's
        # ``extra=\"forbid\"`` still rejects unexpected fields.
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return GeminiQuery.model_validate_json(text)

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, GeminiQuery):
            return parsed
        if isinstance(parsed, BaseModel):
            return GeminiQuery.model_validate(parsed.model_dump())
        if isinstance(parsed, Mapping):
            return GeminiQuery.model_validate(parsed)

        raise ValueError("Gemini returned no structured content")

    async def aclose(self) -> None:
        """Close an owned/injected provider client when it exposes an async close."""

        if self._client is None:
            return
        close = getattr(getattr(self._client, "aio", None), "aclose", None)
        if close is not None:
            await close()
