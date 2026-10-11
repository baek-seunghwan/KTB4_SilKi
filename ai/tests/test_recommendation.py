from __future__ import annotations

from silki_ai.contracts import GeminiQuery, MenuCandidate, SearchAttributes
from silki_ai.nlp import QueryNormalizationResult
from silki_ai.recommendation import MenuRecommendationService


class FakeNormalizer:
    async def normalize(self, transcript: str) -> QueryNormalizationResult:
        assert transcript == "차갑고 안 단 음료"
        return QueryNormalizationResult(
            query=GeminiQuery(
                search_query="차갑고 당도가 낮은 음료",
                attributes=SearchAttributes(temperature="ice", sweetness="low"),
            ),
            degraded=False,
        )


class ExcludingNormalizer:
    async def normalize(self, transcript: str) -> QueryNormalizationResult:
        assert transcript == "차갑고 안 단 음료"
        return QueryNormalizationResult(
            query=GeminiQuery(
                search_query="차갑고 당도가 낮은 음료",
                attributes=SearchAttributes(
                    temperature="ice",
                    sweetness="low",
                    excluded_tags=["chocolate"],
                ),
            ),
            degraded=False,
        )


class FakeEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        assert text == "차갑고 당도가 낮은 음료"
        return [0.1, 0.2]


class NoExactMenuStore:
    async def find_unique_in_text(self, **_kwargs: object) -> MenuCandidate | None:
        return None


class FakeStore(NoExactMenuStore):
    def __init__(self) -> None:
        self.store_id = ""
        self.calls: list[SearchAttributes] = []

    async def search(self, **kwargs: object) -> list[MenuCandidate]:
        self.store_id = str(kwargs["store_id"])
        self.calls.append(kwargs["attributes"])  # type: ignore[arg-type]
        assert kwargs["query_vector"] == [0.1, 0.2]
        assert kwargs["limit"] == 3
        return [
            MenuCandidate(menu_id="m-1", name="제로 아이스티", score=0.8),
        ]


async def test_recommendation_pipeline_returns_candidates_without_cart_actions() -> None:
    store = FakeStore()
    service = MenuRecommendationService(
        FakeNormalizer(),  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        store,
        top_k=3,
        score_threshold=0.2,
    )

    result = await service.recommend(store_id="store-7", transcript="차갑고 안 단 음료")

    assert store.store_id == "store-7"
    assert result.candidates[0].menu_id == "m-1"
    assert result.attributes.sweetness == "low"
    assert result.quantity == 1
    assert len(store.calls) == 1
    assert not hasattr(result, "cart_action")


class RelaxingStore(NoExactMenuStore):
    def __init__(self) -> None:
        self.calls: list[SearchAttributes] = []

    async def search(self, **kwargs: object) -> list[MenuCandidate]:
        attributes = kwargs["attributes"]
        assert isinstance(attributes, SearchAttributes)
        self.calls.append(attributes)
        if attributes.temperature is not None:
            return []
        return [MenuCandidate(menu_id="m-2", name="레몬티", score=0.7)]


async def test_recommendation_retries_without_hard_filters_when_first_search_is_empty() -> None:
    store = RelaxingStore()
    service = MenuRecommendationService(
        FakeNormalizer(),  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        store,
        top_k=3,
        score_threshold=0.2,
    )

    result = await service.recommend(store_id="store-7", transcript="차갑고 안 단 음료")

    assert len(store.calls) == 2
    assert store.calls[0].temperature == "ice"
    assert store.calls[1] == SearchAttributes()
    assert result.attributes.temperature == "ice"
    assert result.candidates[0].menu_id == "m-2"


class EmptyUnfilteredStore(NoExactMenuStore):
    def __init__(self) -> None:
        self.call_count = 0

    async def search(self, **kwargs: object) -> list[MenuCandidate]:
        self.call_count += 1
        assert kwargs["attributes"] == SearchAttributes()
        return []


class UnfilteredNormalizer:
    async def normalize(self, transcript: str) -> QueryNormalizationResult:
        return QueryNormalizationResult(
            query=GeminiQuery(search_query=transcript, attributes=SearchAttributes()),
            degraded=True,
        )


async def test_empty_unfiltered_search_is_not_repeated() -> None:
    store = EmptyUnfilteredStore()
    service = MenuRecommendationService(
        UnfilteredNormalizer(),  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        store,
        top_k=3,
        score_threshold=0.2,
    )

    result = await service.recommend(
        store_id="store-7",
        transcript="차갑고 당도가 낮은 음료",
    )

    assert store.call_count == 1
    assert result.candidates == ()


async def test_recommendation_keeps_excluded_tags_when_relaxing_other_filters() -> None:
    store = RelaxingStore()
    service = MenuRecommendationService(
        ExcludingNormalizer(),  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        store,
        top_k=3,
        score_threshold=0.2,
    )

    await service.recommend(store_id="store-7", transcript="차갑고 안 단 음료")

    assert len(store.calls) == 2
    assert store.calls[0].excluded_tags == ["chocolate"]
    assert store.calls[1] == SearchAttributes(excluded_tags=["chocolate"])


class ExactNormalizer:
    async def normalize(self, transcript: str) -> QueryNormalizationResult:
        assert transcript == "아아메리카노 따뜻하게"
        return QueryNormalizationResult(
            query=GeminiQuery(
                # Simulate a provider mistake observed in the live CLOVA smoke.
                search_query="따뜻한 전통차",
                quantity=1,
                attributes=SearchAttributes(category="tea", temperature="hot"),
            ),
            degraded=False,
        )


class ExactStore:
    def __init__(self) -> None:
        self.search_called = False

    async def find_unique_in_text(self, **kwargs: object) -> MenuCandidate | None:
        assert kwargs == {
            "store_id": "store-7",
            "text": "아아메리카노 따뜻하게",
        }
        return MenuCandidate(
            menu_id="americano",
            name="아메리카노",
            score=1.0,
            available_temperatures=[],
        )

    async def search(self, **_kwargs: object) -> list[MenuCandidate]:
        self.search_called = True
        raise AssertionError("an explicit menu name must bypass semantic candidate selection")


class UnusedEmbedder:
    async def embed_one(self, _text: str) -> list[float]:
        raise AssertionError("an explicit menu name must not require an embedding")


async def test_raw_unique_menu_name_wins_over_incorrect_gemini_query_and_category() -> None:
    store = ExactStore()
    service = MenuRecommendationService(
        ExactNormalizer(),  # type: ignore[arg-type]
        UnusedEmbedder(),  # type: ignore[arg-type]
        store,
    )

    result = await service.recommend(
        store_id="store-7",
        transcript="아아메리카노 따뜻하게",
    )

    assert [candidate.menu_id for candidate in result.candidates] == ["americano"]
    assert result.search_query == "따뜻한 전통차"
    assert result.attributes.temperature == "hot"
    assert store.search_called is False
