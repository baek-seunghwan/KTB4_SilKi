"""Application service for Spring-triggered, revision-safe menu reindexing."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol

from silki_ai.contracts import ReindexRequest, ReindexResponse, ReindexStatus
from silki_ai.embeddings import TextEmbedder, build_menu_search_text
from silki_ai.pgvector_store import EmbeddedMenu, SourceMenu, StoreReindexResult


class ReindexStore(Protocol):
    async def current_revision(self, store_id: str) -> int | None: ...

    async def fetch_source_menus(
        self, store_id: str, menu_ids: Sequence[str] | None
    ) -> list[SourceMenu]: ...

    async def apply_reindex(
        self,
        *,
        store_id: str,
        source_revision: int,
        embedded_menus: Sequence[EmbeddedMenu],
        requested_menu_ids: Sequence[str] | None,
    ) -> StoreReindexResult: ...


class MenuReindexService:
    """Read Spring menu rows, create vectors, and atomically publish a revision."""

    def __init__(self, store: ReindexStore, embedder: TextEmbedder) -> None:
        self._store = store
        self._embedder = embedder

    async def reindex(self, store_id: str, request: ReindexRequest) -> ReindexResponse:
        current = await self._store.current_revision(store_id)
        if current is not None and request.source_revision <= current:
            return self._response(
                store_id,
                request.source_revision,
                StoreReindexResult(status="ignored_stale"),
            )

        # P1 always rebuilds the current authoritative store snapshot. If
        # callbacks arrive out of order, a newer revision still contains all
        # changes already committed by older revisions. Payload-level partial
        # upsert/delete remains a P2 optimization.
        source_menus = await self._store.fetch_source_menus(store_id, None)
        available_menus = [menu for menu in source_menus if menu.is_available]
        documents = [build_menu_search_text(menu) for menu in available_menus]
        vectors = await self._embedder.embed_texts(documents)
        if len(vectors) != len(available_menus):
            raise RuntimeError("embedding count does not match available menu count")

        embedded_menus = [
            EmbeddedMenu(
                menu_id=menu.menu_id,
                vector=vector,
                content_hash=hashlib.sha256(document.encode("utf-8")).hexdigest(),
            )
            for menu, document, vector in zip(available_menus, documents, vectors, strict=True)
        ]
        result = await self._store.apply_reindex(
            store_id=store_id,
            source_revision=request.source_revision,
            embedded_menus=embedded_menus,
            requested_menu_ids=None,
        )
        return self._response(store_id, request.source_revision, result)

    @staticmethod
    def _response(
        store_id: str,
        source_revision: int,
        result: StoreReindexResult,
    ) -> ReindexResponse:
        return ReindexResponse(
            store_id=store_id,
            source_revision=source_revision,
            indexed_count=result.indexed_count,
            deleted_count=result.deleted_count,
            status=ReindexStatus(result.status),
        )
