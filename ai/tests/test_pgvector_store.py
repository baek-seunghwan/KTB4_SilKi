from __future__ import annotations

from typing import Any

import pytest

from silki_ai.contracts import SearchAttributes
from silki_ai.pgvector_store import PgVectorMenuStore


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, object]] = []

    async def execute(self, query: str, parameters: object = None) -> None:
        self.executions.append((query, parameters))

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


@pytest.mark.asyncio
async def test_source_contract_check_uses_compatible_view_and_all_required_columns() -> None:
    pool = FakePool([])
    store = PgVectorMenuStore(pool, embedding_dimension=2)

    await store.check_source_contract()

    query, parameters = pool.cursor.executions[0]
    assert 'FROM "public"."ai_menu_source"' in query
    assert "store_id::TEXT" in query
    assert "menu_id::TEXT" in query
    assert "COALESCE(flavor_tags, ARRAY[]::TEXT[])" in query
    assert "is_available IS TRUE" in query
    assert "LIMIT 0" in query
    assert parameters is None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> AsyncContext:
        return AsyncContext(self._cursor)


class FakePool:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.cursor = FakeCursor(rows)
        self.connection_value = FakeConnection(self.cursor)

    def connection(self) -> AsyncContext:
        return AsyncContext(self.connection_value)


@pytest.mark.asyncio
async def test_search_is_store_isolated_and_supports_non_text_source_ids() -> None:
    pool = FakePool(
        [
            (
                "menu-1",
                "레몬 디카페인",
                "상큼한 음료",
                "coffee",
                "ice",
                "low",
                "none",
                ["citrus"],
                0.82,
            )
        ]
    )
    store = PgVectorMenuStore(pool, embedding_dimension=2)
    attributes = SearchAttributes(
        category="coffee",
        temperature="ice",
        sweetness="low",
        caffeine="none",
        flavor_tags=["citrus"],
        excluded_tags=["mint"],
    )

    candidates = await store.search(
        store_id="store-1",
        query_vector=[0.1, 0.2],
        attributes=attributes,
        score_threshold=0.45,
    )

    query, parameters = pool.cursor.executions[0]
    assert "e.store_id = %s" in query
    assert "m.store_id::TEXT = e.store_id" in query
    assert "m.menu_id::TEXT = e.menu_id" in query
    assert "m.is_available IS TRUE" in query
    assert "m.temperature::TEXT" in query
    assert query.count("%s") == len(parameters)
    assert parameters[1] == "store-1"
    assert candidates[0].menu_id == "menu-1"
    assert candidates[0].matched_attributes == [
        "category",
        "temperature",
        "sweetness",
        "caffeine",
        "flavor_tags",
        "excluded_tags",
    ]
    assert candidates[0].available_temperatures == ["ice"]


@pytest.mark.asyncio
async def test_unique_canonical_menu_name_is_found_inside_raw_stt() -> None:
    pool = FakePool(
        [
            (
                "americano",
                "아메리카노",
                "진한 커피",
                "coffee",
                None,
                "medium",
                "normal",
                [],
            ),
            (
                "cold-brew",
                "콜드 브루",
                "차가운 커피",
                "coffee",
                "ice",
                "medium",
                "normal",
                [],
            ),
        ]
    )
    store = PgVectorMenuStore(pool, embedding_dimension=2)

    candidate = await store.find_unique_in_text(
        store_id="store-1",
        text="아아메리카노 따뜻하게",
    )

    query, parameters = pool.cursor.executions[0]
    assert "m.store_id::TEXT = %s" in query
    assert "m.is_available IS TRUE" in query
    assert parameters == ("store-1",)
    assert candidate is not None
    assert candidate.menu_id == "americano"
    assert candidate.score == 1.0
    assert candidate.available_temperatures == []


@pytest.mark.asyncio
async def test_multiple_spoken_menu_names_are_not_selected_arbitrarily() -> None:
    pool = FakePool(
        [
            ("americano", "아메리카노", "", "coffee", None, None, None, []),
            ("latte", "카페 라떼", "", "coffee", None, None, None, []),
        ]
    )
    store = PgVectorMenuStore(pool, embedding_dimension=2)

    candidate = await store.find_unique_in_text(
        store_id="store-1",
        text="아메리카노 말고 카페라떼",
    )

    assert candidate is None


@pytest.mark.asyncio
async def test_source_fetch_casts_uuid_or_numeric_identifiers_at_ai_boundary() -> None:
    pool = FakePool(
        [
            (
                "12",
                "42",
                "아이스티",
                "",
                "tea",
                "ice",
                "low",
                "none",
                [],
                True,
            )
        ]
    )
    store = PgVectorMenuStore(pool, embedding_dimension=2)

    menus = await store.fetch_source_menus("12", ["42"])

    query, parameters = pool.cursor.executions[0]
    assert "store_id::TEXT = %s" in query
    assert "menu_id::TEXT = ANY(%s::TEXT[])" in query
    assert parameters == ["12", ["42"]]
    assert menus[0].store_id == "12"
    assert menus[0].menu_id == "42"
