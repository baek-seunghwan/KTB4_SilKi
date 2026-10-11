"""PostgreSQL/pgvector persistence for menu retrieval and reindexing.

The default source relation is the Spring-owned, read-only compatibility view
``public.ai_menu_source``.  Only ``ai.menu_embeddings`` and
``ai.reindex_state`` are written by the AI service.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from silki_ai.contracts import MenuCandidate, SearchAttributes, Temperature

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CANONICAL_MENU_SEPARATOR = re.compile(r"[\W_]+", re.UNICODE)


def _qualified_identifier(name: str) -> str:
    parts = name.split(".")
    if not 1 <= len(parts) <= 2 or any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return ".".join(f'"{part}"' for part in parts)


def _schema_name(qualified_name: str) -> str | None:
    parts = qualified_name.split(".")
    return parts[0] if len(parts) == 2 else None


def _vector_literal(vector: Sequence[float]) -> str:
    values = [float(value) for value in vector]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("vector must contain finite values")
    return "[" + ",".join(format(value, ".17g") for value in values) + "]"


def _source_available_temperatures(value: object) -> list[Temperature]:
    """Translate the Spring source enum without leaking malformed DB values."""

    normalized = str(value).strip().casefold() if value is not None else ""
    if normalized == "ice":
        return ["ice"]
    if normalized == "hot":
        return ["hot"]
    return []


def _canonical_menu_name(value: str) -> str:
    return _CANONICAL_MENU_SEPARATOR.sub("", value.casefold())


@dataclass(frozen=True, slots=True)
class SourceMenu:
    store_id: str
    menu_id: str
    name: str
    description: str
    category: str | None
    temperature: str | None
    sweetness: str | None
    caffeine: str | None
    flavor_tags: tuple[str, ...]
    is_available: bool


@dataclass(frozen=True, slots=True)
class EmbeddedMenu:
    menu_id: str
    vector: Sequence[float]
    content_hash: str


@dataclass(frozen=True, slots=True)
class StoreReindexResult:
    status: Literal["processed", "ignored_stale"]
    indexed_count: int = 0
    deleted_count: int = 0


class PgVectorMenuStore:
    """Async psycopg-pool-backed menu vector repository."""

    def __init__(
        self,
        pool: Any,
        *,
        menu_table: str = "public.ai_menu_source",
        embedding_table: str = "ai.menu_embeddings",
        revision_table: str = "ai.reindex_state",
        embedding_dimension: int = 768,
    ) -> None:
        if embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        self._pool = pool
        self._menu_table = _qualified_identifier(menu_table)
        self._embedding_table = _qualified_identifier(embedding_table)
        self._revision_table = _qualified_identifier(revision_table)
        self._embedding_schema = _schema_name(embedding_table)
        self._embedding_dimension = embedding_dimension

    async def initialize(self, *, create_extension: bool = False) -> None:
        """Create AI-owned relations; pgvector extension creation is opt-in.

        Production normally provisions the extension through cloud migrations.  The
        opt-in exists for local Docker startup where the application owns the DB.
        """

        statements: list[str] = []
        if create_extension:
            statements.append("CREATE EXTENSION IF NOT EXISTS vector")
        if self._embedding_schema:
            statements.append(
                f"CREATE SCHEMA IF NOT EXISTS {_qualified_identifier(self._embedding_schema)}"
            )
        statements.extend(
            (
                f"""
                CREATE TABLE IF NOT EXISTS {self._embedding_table} (
                    store_id TEXT NOT NULL,
                    menu_id TEXT NOT NULL,
                    embedding vector({self._embedding_dimension}) NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_revision BIGINT NOT NULL CHECK (source_revision >= 0),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (store_id, menu_id)
                )
                """,
                f"""
                CREATE TABLE IF NOT EXISTS {self._revision_table} (
                    store_id TEXT PRIMARY KEY,
                    source_revision BIGINT NOT NULL CHECK (source_revision >= 0),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """,
                f"""
                CREATE INDEX IF NOT EXISTS menu_embeddings_cosine_idx
                ON {self._embedding_table}
                USING hnsw (embedding vector_cosine_ops)
                """,
            )
        )
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                for statement in statements:
                    await cursor.execute(statement)

    async def check_source_contract(self) -> None:
        """Verify that the configured relation is readable and exposes the P1 columns.

        ``LIMIT 0`` makes this a schema/permission check only.  The explicit casts
        also catch relations whose columns cannot satisfy the query contract without
        reading or retaining any menu data.
        """

        query = f"""
            SELECT
                store_id::TEXT,
                menu_id::TEXT,
                name,
                COALESCE(description, ''),
                category::TEXT,
                temperature::TEXT,
                sweetness::TEXT,
                caffeine::TEXT,
                COALESCE(flavor_tags, ARRAY[]::TEXT[]),
                is_available IS TRUE
            FROM {self._menu_table}
            LIMIT 0
        """
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query)

    async def search(
        self,
        *,
        store_id: str,
        query_vector: Sequence[float],
        attributes: SearchAttributes,
        limit: int = 3,
        score_threshold: float = 0.45,
    ) -> list[MenuCandidate]:
        if not store_id.strip():
            raise ValueError("store_id must not be blank")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        if not 0 <= score_threshold <= 1:
            raise ValueError("score_threshold must be between 0 and 1")

        vector = _vector_literal(query_vector)
        conditions = [
            "e.store_id = %s",
            "m.is_available IS TRUE",
            "(1 - (e.embedding <=> %s::vector)) >= %s",
        ]
        parameters: list[Any] = [store_id, vector, score_threshold]
        for column, value in (
            ("category", attributes.category),
            ("temperature", attributes.temperature),
            ("sweetness", attributes.sweetness),
            ("caffeine", attributes.caffeine),
        ):
            if value is not None:
                conditions.append(f"LOWER(COALESCE(m.{column}::TEXT, '')) = LOWER(%s)")
                parameters.append(value)
        if attributes.flavor_tags:
            conditions.append("COALESCE(m.flavor_tags, ARRAY[]::TEXT[]) @> %s::TEXT[]")
            parameters.append(attributes.flavor_tags)
        if attributes.excluded_tags:
            conditions.append("NOT (COALESCE(m.flavor_tags, ARRAY[]::TEXT[]) && %s::TEXT[])")
            parameters.append(attributes.excluded_tags)

        parameters.extend((vector, limit))
        query = f"""
            SELECT
                m.menu_id::TEXT,
                m.name,
                COALESCE(m.description, ''),
                m.category,
                m.temperature,
                m.sweetness,
                m.caffeine,
                COALESCE(m.flavor_tags, ARRAY[]::TEXT[]),
                1 - (e.embedding <=> %s::vector) AS score
            FROM {self._embedding_table} AS e
            JOIN {self._menu_table} AS m
              ON m.store_id::TEXT = e.store_id AND m.menu_id::TEXT = e.menu_id
            WHERE {" AND ".join(conditions)}
            ORDER BY e.embedding <=> %s::vector, m.menu_id
            LIMIT %s
        """

        # The SELECT score adds one vector parameter before the WHERE parameters.
        query_parameters = [vector, *parameters]
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, query_parameters)
                rows = await cursor.fetchall()

        candidates: list[MenuCandidate] = []
        for row in rows:
            matched = _matched_attribute_names(attributes, row)
            candidates.append(
                MenuCandidate(
                    menu_id=str(row[0]),
                    name=str(row[1]),
                    description=str(row[2]),
                    score=max(0.0, min(1.0, float(row[8]))),
                    matched_attributes=matched,
                    available_temperatures=_source_available_temperatures(row[4]),
                )
            )
        return candidates

    async def find_unique_in_text(
        self,
        *,
        store_id: str,
        text: str,
    ) -> MenuCandidate | None:
        """Return one store-local menu whose canonical name occurs in ``text``.

        The raw STT is used instead of Gemini's normalized query so a transient
        category/query mistake cannot discard an explicitly spoken menu.  A match
        is accepted only when exactly one available menu name occurs in the text;
        multiple names remain ambiguous and fall back to semantic clarification.
        Dialog validation still applies the source menu's supported temperature.
        """

        if not store_id.strip():
            raise ValueError("store_id must not be blank")
        canonical_text = _canonical_menu_name(text)
        if not canonical_text:
            return None
        query = f"""
            SELECT
                m.menu_id::TEXT,
                m.name,
                COALESCE(m.description, ''),
                m.category,
                m.temperature,
                m.sweetness,
                m.caffeine,
                COALESCE(m.flavor_tags, ARRAY[]::TEXT[])
            FROM {self._menu_table} AS m
            WHERE m.store_id::TEXT = %s
              AND m.is_available IS TRUE
            ORDER BY m.menu_id::TEXT
        """
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, (store_id,))
                rows = await cursor.fetchall()

        matches = [
            row
            for row in rows
            if (canonical_name := _canonical_menu_name(str(row[1])))
            and canonical_name in canonical_text
        ]
        if len(matches) != 1:
            return None
        row = matches[0]
        return MenuCandidate(
            menu_id=str(row[0]),
            name=str(row[1]),
            description=str(row[2]),
            score=1.0,
            available_temperatures=_source_available_temperatures(row[4]),
        )

    async def current_revision(self, store_id: str) -> int | None:
        query = f"SELECT source_revision FROM {self._revision_table} WHERE store_id = %s"
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, (store_id,))
                row = await cursor.fetchone()
        return None if row is None else int(row[0])

    async def fetch_source_menus(
        self,
        store_id: str,
        menu_ids: Sequence[str] | None,
    ) -> list[SourceMenu]:
        # Spring may use TEXT, UUID, or BIGINT identifiers. The AI boundary
        # represents them as strings and compares canonical PostgreSQL text.
        conditions = ["store_id::TEXT = %s"]
        parameters: list[Any] = [store_id]
        if menu_ids is not None:
            conditions.append("menu_id::TEXT = ANY(%s::TEXT[])")
            parameters.append(list(menu_ids))

        query = f"""
            SELECT
                store_id::TEXT,
                menu_id::TEXT,
                name,
                COALESCE(description, ''),
                category,
                temperature,
                sweetness,
                caffeine,
                COALESCE(flavor_tags, ARRAY[]::TEXT[]),
                is_available
            FROM {self._menu_table}
            WHERE {" AND ".join(conditions)}
            ORDER BY menu_id::TEXT
        """
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, parameters)
                rows = await cursor.fetchall()
        return [
            SourceMenu(
                store_id=str(row[0]),
                menu_id=str(row[1]),
                name=str(row[2]),
                description=str(row[3]),
                category=None if row[4] is None else str(row[4]),
                temperature=None if row[5] is None else str(row[5]),
                sweetness=None if row[6] is None else str(row[6]),
                caffeine=None if row[7] is None else str(row[7]),
                flavor_tags=tuple(str(tag) for tag in row[8]),
                is_available=bool(row[9]),
            )
            for row in rows
        ]

    async def apply_reindex(
        self,
        *,
        store_id: str,
        source_revision: int,
        embedded_menus: Sequence[EmbeddedMenu],
        requested_menu_ids: Sequence[str] | None,
    ) -> StoreReindexResult:
        """Atomically apply vectors only when ``source_revision`` is newer."""

        indexed_ids = [menu.menu_id for menu in embedded_menus]
        async with self._pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (store_id,),
                    )
                    await cursor.execute(
                        f"SELECT source_revision FROM {self._revision_table} WHERE store_id = %s",
                        (store_id,),
                    )
                    row = await cursor.fetchone()
                    current = None if row is None else int(row[0])
                    if current is not None and source_revision <= current:
                        return StoreReindexResult(status="ignored_stale")

                    upsert = f"""
                        INSERT INTO {self._embedding_table}
                            (store_id, menu_id, embedding, content_hash, source_revision)
                        VALUES (%s, %s, %s::vector, %s, %s)
                        ON CONFLICT (store_id, menu_id) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            content_hash = EXCLUDED.content_hash,
                            source_revision = EXCLUDED.source_revision,
                            updated_at = now()
                    """
                    for menu in embedded_menus:
                        await cursor.execute(
                            upsert,
                            (
                                store_id,
                                menu.menu_id,
                                _vector_literal(menu.vector),
                                menu.content_hash,
                                source_revision,
                            ),
                        )

                    if requested_menu_ids is None:
                        if indexed_ids:
                            await cursor.execute(
                                f"DELETE FROM {self._embedding_table} "
                                "WHERE store_id = %s AND NOT (menu_id = ANY(%s::TEXT[]))",
                                (store_id, indexed_ids),
                            )
                        else:
                            await cursor.execute(
                                f"DELETE FROM {self._embedding_table} WHERE store_id = %s",
                                (store_id,),
                            )
                    else:
                        missing_ids = sorted(set(requested_menu_ids) - set(indexed_ids))
                        if missing_ids:
                            await cursor.execute(
                                f"DELETE FROM {self._embedding_table} "
                                "WHERE store_id = %s AND menu_id = ANY(%s::TEXT[])",
                                (store_id, missing_ids),
                            )
                        else:
                            # Preserve a stable rowcount contract when nothing is deleted.
                            await cursor.execute("SELECT 1 WHERE FALSE")
                    deleted_count = max(0, cursor.rowcount)

                    await cursor.execute(
                        f"""
                        INSERT INTO {self._revision_table} (store_id, source_revision)
                        VALUES (%s, %s)
                        ON CONFLICT (store_id) DO UPDATE SET
                            source_revision = EXCLUDED.source_revision,
                            updated_at = now()
                        """,
                        (store_id, source_revision),
                    )

        return StoreReindexResult(
            status="processed",
            indexed_count=len(embedded_menus),
            deleted_count=deleted_count,
        )


def _matched_attribute_names(attributes: SearchAttributes, row: Sequence[Any]) -> list[str]:
    matched: list[str] = []
    values = {
        "category": row[3],
        "temperature": row[4],
        "sweetness": row[5],
        "caffeine": row[6],
    }
    for name, menu_value in values.items():
        requested = getattr(attributes, name)
        if requested is not None and menu_value is not None:
            if str(requested).casefold() == str(menu_value).casefold():
                matched.append(name)
    menu_tags = {str(tag).casefold() for tag in row[7]}
    if attributes.flavor_tags and all(
        tag.casefold() in menu_tags for tag in attributes.flavor_tags
    ):
        matched.append("flavor_tags")
    if attributes.excluded_tags and all(
        tag.casefold() not in menu_tags for tag in attributes.excluded_tags
    ):
        matched.append("excluded_tags")
    return matched
