"""Final-turn orchestration from transcript to non-authoritative menu candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from silki_ai.contracts import MenuCandidate, SearchAttributes
from silki_ai.embeddings import TextEmbedder
from silki_ai.nlp import GeminiQueryNormalizer


class MenuSearchStore(Protocol):
    async def find_unique_in_text(
        self,
        *,
        store_id: str,
        text: str,
    ) -> MenuCandidate | None: ...

    async def search(
        self,
        *,
        store_id: str,
        query_vector: Sequence[float],
        attributes: SearchAttributes,
        limit: int,
        score_threshold: float,
    ) -> list[MenuCandidate]: ...


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    search_query: str
    quantity: int
    attributes: SearchAttributes
    degraded: bool
    candidates: tuple[MenuCandidate, ...]


class MenuRecommendationService:
    """Run Gemini refinement, embedding, and store-isolated retrieval once per turn."""

    def __init__(
        self,
        normalizer: GeminiQueryNormalizer,
        embedder: TextEmbedder,
        store: MenuSearchStore,
        *,
        top_k: int = 3,
        score_threshold: float = 0.45,
    ) -> None:
        if not 1 <= top_k <= 3:
            raise ValueError("public candidate count must be between 1 and 3")
        if not 0 <= score_threshold <= 1:
            raise ValueError("score_threshold must be between 0 and 1")
        self._normalizer = normalizer
        self._embedder = embedder
        self._store = store
        self._top_k = top_k
        self._score_threshold = score_threshold

    async def recommend(self, *, store_id: str, transcript: str) -> RecommendationResult:
        normalized = await self._normalizer.normalize(transcript)
        exact = await self._store.find_unique_in_text(
            store_id=store_id,
            text=transcript,
        )
        if exact is not None:
            return RecommendationResult(
                search_query=normalized.search_query,
                quantity=normalized.quantity,
                attributes=normalized.attributes,
                degraded=normalized.degraded,
                candidates=(exact,),
            )
        query_vector = await self._embedder.embed_one(normalized.search_query)
        candidates = await self._store.search(
            store_id=store_id,
            query_vector=query_vector,
            attributes=normalized.attributes,
            limit=self._top_k,
            score_threshold=self._score_threshold,
        )
        if not candidates and _has_search_constraints(normalized.attributes):
            candidates = await self._store.search(
                store_id=store_id,
                query_vector=query_vector,
                # Positive preferences may be relaxed to keep the search useful,
                # but a requested exclusion must never be removed.  In
                # particular, returning a chocolate-tagged menu for "초코는
                # 빼고" would contradict an explicit user constraint.
                attributes=SearchAttributes(excluded_tags=normalized.attributes.excluded_tags),
                limit=self._top_k,
                score_threshold=self._score_threshold,
            )
        return RecommendationResult(
            search_query=normalized.search_query,
            quantity=normalized.quantity,
            attributes=normalized.attributes,
            degraded=normalized.degraded,
            candidates=tuple(candidates[: self._top_k]),
        )


def _has_search_constraints(attributes: SearchAttributes) -> bool:
    return any(
        (
            attributes.category,
            attributes.temperature,
            attributes.sweetness,
            attributes.caffeine,
            attributes.flavor_tags,
            attributes.excluded_tags,
        )
    )
