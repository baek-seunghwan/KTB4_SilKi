from __future__ import annotations

from collections.abc import Sequence

import pytest

from silki_ai.contracts import ReindexRequest, ReindexStatus
from silki_ai.embeddings import build_menu_search_text
from silki_ai.pgvector_store import EmbeddedMenu, SourceMenu, StoreReindexResult
from silki_ai.reindex import MenuReindexService


def menu(menu_id: str, *, available: bool = True) -> SourceMenu:
    return SourceMenu(
        store_id="store-1",
        menu_id=menu_id,
        name=f"메뉴 {menu_id}",
        description="고소한 음료",
        category="coffee",
        temperature="ice",
        sweetness="low",
        caffeine="low",
        flavor_tags=("nutty",),
        is_available=available,
    )


class FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts = list(texts)
        return [[float(index), 1.0] for index, _ in enumerate(texts)]


class FakeStore:
    def __init__(self, *, revision: int | None, menus: list[SourceMenu]) -> None:
        self.revision = revision
        self.menus = menus
        self.fetch_ids: Sequence[str] | None = ()
        self.apply_args: dict[str, object] | None = None

    async def current_revision(self, store_id: str) -> int | None:
        return self.revision

    async def fetch_source_menus(
        self, store_id: str, menu_ids: Sequence[str] | None
    ) -> list[SourceMenu]:
        self.fetch_ids = menu_ids
        return self.menus

    async def apply_reindex(
        self,
        *,
        store_id: str,
        source_revision: int,
        embedded_menus: Sequence[EmbeddedMenu],
        requested_menu_ids: Sequence[str] | None,
    ) -> StoreReindexResult:
        self.apply_args = {
            "store_id": store_id,
            "source_revision": source_revision,
            "embedded_menus": list(embedded_menus),
            "requested_menu_ids": requested_menu_ids,
        }
        return StoreReindexResult(
            status="processed",
            indexed_count=len(embedded_menus),
            deleted_count=1,
        )


def test_menu_search_document_includes_joined_name_alias() -> None:
    document = build_menu_search_text(
        {
            "name": "카페 라떼",
            "description": "고소한 우유 커피",
            "category": "coffee",
        }
    )

    assert "메뉴명: 카페 라떼" in document
    assert "검색 별칭: 카페라떼" in document


@pytest.mark.asyncio
async def test_same_or_older_revision_is_idempotently_ignored() -> None:
    store = FakeStore(revision=7, menus=[menu("m1")])
    embedder = FakeEmbedder()
    service = MenuReindexService(store, embedder)

    response = await service.reindex(
        "store-1",
        ReindexRequest(menu_ids=["m1"], source_revision=7, reason="duplicate"),
    )

    assert response.status is ReindexStatus.IGNORED_STALE
    assert response.indexed_count == 0
    assert store.apply_args is None
    assert embedder.texts == []


@pytest.mark.asyncio
async def test_mvp_reindex_refreshes_full_authoritative_store_snapshot() -> None:
    store = FakeStore(revision=7, menus=[menu("m1"), menu("m2", available=False)])
    embedder = FakeEmbedder()
    service = MenuReindexService(store, embedder)

    response = await service.reindex(
        "store-1",
        ReindexRequest(menu_ids=["m1", "m2", "deleted"], source_revision=8, reason="update"),
    )

    assert response.status is ReindexStatus.PROCESSED
    assert response.indexed_count == 1
    assert response.deleted_count == 1
    assert store.fetch_ids is None
    assert store.apply_args is not None
    embedded = store.apply_args["embedded_menus"]
    assert isinstance(embedded, list)
    assert [item.menu_id for item in embedded] == ["m1"]
    assert store.apply_args["requested_menu_ids"] is None
    assert "메뉴명: 메뉴 m1" in embedder.texts[0]


@pytest.mark.asyncio
async def test_empty_menu_ids_requests_full_store_reindex() -> None:
    store = FakeStore(revision=None, menus=[menu("m1")])
    service = MenuReindexService(store, FakeEmbedder())

    await service.reindex(
        "store-1",
        ReindexRequest(menu_ids=[], source_revision=1, reason="initial index"),
    )

    assert store.fetch_ids is None
    assert store.apply_args is not None
    assert store.apply_args["requested_menu_ids"] is None
