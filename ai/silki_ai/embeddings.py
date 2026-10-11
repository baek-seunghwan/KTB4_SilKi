"""Sentence-transformer embedding boundary and menu document construction."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

DEFAULT_EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"


class TextEmbedder(Protocol):
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]: ...


def _value(source: object, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def build_menu_search_text(menu: object) -> str:
    """Build the stable Korean search document persisted alongside an embedding."""

    tags = _value(menu, "flavor_tags", ()) or ()
    if isinstance(tags, str):
        tags = (tags,)

    name = str(_value(menu, "name", "")).strip()
    canonical_name = re.sub(r"[\W_]+", "", name, flags=re.UNICODE).casefold()
    fields = (
        ("메뉴명", name),
        (
            "검색 별칭",
            canonical_name if canonical_name and canonical_name != name.casefold() else "",
        ),
        ("설명", _value(menu, "description", "")),
        ("카테고리", _value(menu, "category", "")),
        ("온도", _value(menu, "temperature", "")),
        ("당도", _value(menu, "sweetness", "")),
        ("카페인", _value(menu, "caffeine", "")),
        ("맛 태그", ", ".join(str(tag).strip() for tag in tags if str(tag).strip())),
    )
    return "\n".join(f"{label}: {str(value).strip()}" for label, value in fields if value)


class SentenceTransformerEmbedder:
    """Lazy, async facade over the CPU-bound sentence-transformers model."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        *,
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self._model = model
        self._load_lock = asyncio.Lock()
        self._encode_lock = asyncio.Lock()

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load_model)
        return self._model

    def _load_model(self) -> Any:
        from sentence_transformers import SentenceTransformer

        # Production runs on CPU-only EC2. Keep that execution contract explicit
        # on every host so deployments remain deterministic.
        return SentenceTransformer(self.model_name, device="cpu")

    @property
    def loaded(self) -> bool:
        return self._model is not None

    async def warmup(self) -> None:
        """Load/cache the model before serving the first recommendation."""

        await self._get_model()

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts]
        if any(not text for text in cleaned):
            raise ValueError("embedding texts must not be blank")
        if not cleaned:
            return []

        model = await self._get_model()
        async with self._encode_lock:
            encoded = await asyncio.to_thread(
                model.encode,
                cleaned,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

        raw_vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        vectors = [[float(component) for component in vector] for vector in raw_vectors]
        if len(vectors) != len(cleaned):
            raise RuntimeError("embedding provider returned an unexpected batch size")
        if any(
            not vector or not all(math.isfinite(value) for value in vector) for vector in vectors
        ):
            raise RuntimeError("embedding provider returned an invalid vector")
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise RuntimeError("embedding provider returned inconsistent dimensions")
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]
