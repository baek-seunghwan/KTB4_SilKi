from __future__ import annotations

from types import SimpleNamespace

import pytest

from silki_ai.nlp import (
    GeminiQueryNormalizer,
    _GeminiResponseSchema,
    deterministic_fallback,
)


class FakeModels:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def fake_client(models: FakeModels) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def schema_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in schema_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in schema_keys(child)}
    return set()


def test_deterministic_fallback_extracts_core_korean_attributes() -> None:
    query = deterministic_fallback("  차갑고 안 단 디카페인 커피  ")

    assert query.search_query == "차갑고 안 단 디카페인 커피"
    assert query.attributes.category == "coffee"
    assert query.attributes.temperature == "ice"
    assert query.attributes.sweetness == "low"
    assert query.attributes.caffeine == "none"


@pytest.mark.parametrize(
    ("transcript", "expected_query", "expected_quantity"),
    [
        ("아이스 아메리카노 두 잔", "아이스 아메리카노", 2),
        ("카페라떼 3개 주세요", "카페라떼 주세요", 3),
        ("바닐라 라떼 한개요", "바닐라 라떼", 1),
        ("아메리카노 2개", "아메리카노", 2),
    ],
)
def test_deterministic_fallback_extracts_quantity(
    transcript: str,
    expected_query: str,
    expected_quantity: int,
) -> None:
    query = deterministic_fallback(transcript)

    assert query.search_query == expected_query
    assert query.quantity == expected_quantity


@pytest.mark.parametrize("transcript", ["아메리카노 2샷 추가", "아메리카노 샷 두 개 추가"])
def test_option_count_is_not_mistaken_for_item_quantity(transcript: str) -> None:
    query = deterministic_fallback(transcript)

    assert query.search_query == transcript
    assert query.quantity == 1


def test_deterministic_fallback_separates_included_and_excluded_flavors() -> None:
    query = deterministic_fallback("초코는 빼고 고소한 라떼")

    assert query.attributes.flavor_tags == ["nutty"]
    assert query.attributes.excluded_tags == ["chocolate"]


def test_temperature_word_does_not_turn_cold_drink_into_tea() -> None:
    query = deterministic_fallback("차갑고 안 단 음료")

    assert query.attributes.category is None
    assert query.attributes.temperature == "ice"
    assert query.attributes.sweetness == "low"


def test_noncoffee_latte_does_not_get_a_false_coffee_filter() -> None:
    query = deterministic_fallback("딸기 라떼")

    assert query.attributes.category is None
    assert query.attributes.flavor_tags == ["strawberry"]


def test_catalog_tea_and_cold_brew_use_canonical_categories() -> None:
    assert deterministic_fallback("콜드 브루").attributes.category == "coffee"
    assert deterministic_fallback("캐모마일").attributes.category == "tea"


@pytest.mark.asyncio
async def test_gemini_returns_only_valid_structured_query() -> None:
    models = FakeModels(
        SimpleNamespace(
            parsed={
                "search_query": "카페인이 적은 커피",
                "quantity": 2,
                "attributes": {
                    "category": "coffee",
                    "temperature": None,
                    "sweetness": None,
                    "caffeine": "low",
                    "flavor_tags": [],
                    "excluded_tags": [],
                },
            }
        )
    )
    normalizer = GeminiQueryNormalizer(
        api_key=None,
        client=fake_client(models),
        model="gemini-3.5-flash-lite",
    )

    result = await normalizer.normalize("카페인 적은 커피 줘")

    assert result.degraded is False
    assert result.search_query == "카페인이 적은 커피"
    assert result.quantity == 2
    assert result.attributes.caffeine == "low"
    assert models.calls[0]["model"] == "gemini-3.5-flash-lite"
    assert models.calls[0]["config"].response_schema is not None
    assert models.calls[0]["config"].response_json_schema is None
    assert models.calls[0]["config"].http_options.timeout == 10_000
    provider_schema = models.calls[0]["config"].response_schema.model_json_schema()
    assert "search_query" in provider_schema["properties"]
    assert provider_schema["required"] == ["search_query", "quantity", "attributes"]
    assert "additionalProperties" not in schema_keys(provider_schema)


@pytest.mark.asyncio
async def test_gemini_provider_deadline_never_drops_below_ten_seconds() -> None:
    models = FakeModels(error=TimeoutError("provider should fall back"))
    normalizer = GeminiQueryNormalizer(
        api_key=None,
        client=fake_client(models),
        timeout_seconds=3.0,
    )

    result = await normalizer.normalize("아메리카노")

    assert result.degraded is True
    assert models.calls[0]["config"].http_options.timeout == 10_000

    longer = GeminiQueryNormalizer(
        api_key=None,
        client=fake_client(FakeModels(error=TimeoutError())),
        timeout_seconds=12.5,
    )
    await longer.normalize("아메리카노")
    assert longer._generation_config().http_options.timeout == 12_500


@pytest.mark.asyncio
async def test_raw_provider_json_is_strictly_revalidated_after_compatible_schema() -> None:
    # The provider model must ignore extras to avoid emitting Gemini's unsupported
    # additionalProperties keyword.  The SDK may therefore expose a sanitized
    # ``parsed`` model; the application must validate the original response text.
    provider_parsed = _GeminiResponseSchema.model_validate(
        {
            "search_query": "아메리카노",
            "quantity": 1,
            "attributes": {
                "category": "coffee",
                "temperature": None,
                "sweetness": None,
                "caffeine": "normal",
                "flavor_tags": [],
                "excluded_tags": [],
            },
            "menu_id": "provider-must-not-select",
        }
    )
    response = SimpleNamespace(
        parsed=provider_parsed,
        text=(
            '{"search_query":"아메리카노","quantity":1,'
            '"attributes":{"category":"coffee","temperature":null,'
            '"sweetness":null,"caffeine":"normal","flavor_tags":[],'
            '"excluded_tags":[]},"menu_id":"provider-must-not-select"}'
        ),
    )
    normalizer = GeminiQueryNormalizer(
        api_key=None,
        client=fake_client(FakeModels(response=response)),
    )

    result = await normalizer.normalize("아메리카노")

    assert result.degraded is True
    assert result.search_query == "아메리카노"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,error",
    [
        (SimpleNamespace(text="not json", parsed=None), None),
        (
            SimpleNamespace(
                parsed={
                    "search_query": "아메리카노",
                    "attributes": {},
                    "menu_id": "provider-must-not-select",
                }
            ),
            None,
        ),
        (None, TimeoutError("provider timed out")),
    ],
)
async def test_provider_or_schema_failure_uses_degraded_fallback(
    response: object,
    error: Exception | None,
) -> None:
    normalizer = GeminiQueryNormalizer(
        api_key=None,
        client=fake_client(FakeModels(response=response, error=error)),
    )

    result = await normalizer.normalize("달달한 것")

    assert result.degraded is True
    assert result.search_query == "달달한 것"
    assert result.quantity == 1
    assert result.attributes.sweetness == "high"


def test_blank_final_transcript_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        deterministic_fallback("  ")
