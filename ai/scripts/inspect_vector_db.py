"""Human-readable, read-only inspection of menu vectors and semantic search."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import OperationalError, connect, sql
from psycopg.conninfo import conninfo_to_dict

from silki_ai.config import Settings
from silki_ai.embeddings import SentenceTransformerEmbedder
from silki_ai.pgvector_store import _vector_literal


def _relation(name: str) -> sql.Identifier:
    parts = name.split(".")
    if not 1 <= len(parts) <= 2 or any(not part for part in parts):
        raise ValueError(f"invalid relation name: {name!r}")
    return sql.Identifier(*parts)


def _short(value: object, width: int = 24) -> str:
    text = "-" if value is None else str(value)
    return text if len(text) <= width else f"{text[: width - 1]}…"


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    rendered = [[_short(value) for value in row] for row in rows]
    widths = [
        max(len(header), *(len(row[index]) for row in rendered))
        for index, header in enumerate(headers)
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rendered:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _exists(cursor: Any, relation: str) -> bool:
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (relation,))
    row = cursor.fetchone()
    return bool(row and row[0])


def _count(cursor: Any, relation: str) -> int:
    cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(_relation(relation)))
    return int(cursor.fetchone()[0])


def _embedding_rows(
    cursor: Any,
    settings: Settings,
    *,
    store_id: str | None,
    limit: int,
    source_exists: bool,
) -> list[tuple[object, ...]]:
    embedding = _relation(settings.embedding_table)
    conditions = sql.SQL("")
    parameters: list[object] = []
    if store_id:
        conditions = sql.SQL("WHERE e.store_id = %s")
        parameters.append(store_id)

    if source_exists:
        source = _relation(settings.menu_source_table)
        query = sql.SQL(
            """
            SELECT e.store_id, e.menu_id, m.name, vector_dims(e.embedding),
                   left(e.content_hash, 12), e.source_revision, e.updated_at
            FROM {} AS e
            LEFT JOIN {} AS m
              ON m.store_id::TEXT = e.store_id AND m.menu_id::TEXT = e.menu_id
            {}
            ORDER BY e.updated_at DESC, e.store_id, e.menu_id
            LIMIT %s
            """
        ).format(embedding, source, conditions)
    else:
        query = sql.SQL(
            """
            SELECT e.store_id, e.menu_id, NULL::TEXT, vector_dims(e.embedding),
                   left(e.content_hash, 12), e.source_revision, e.updated_at
            FROM {} AS e
            {}
            ORDER BY e.updated_at DESC, e.store_id, e.menu_id
            LIMIT %s
            """
        ).format(embedding, conditions)

    cursor.execute(query, [*parameters, limit])
    return list(cursor.fetchall())


async def _query_vector(text: str, model_name: str) -> list[float]:
    return await SentenceTransformerEmbedder(model_name).embed_one(text)


def _search_rows(
    cursor: Any,
    settings: Settings,
    *,
    query_vector: Sequence[float],
    store_id: str | None,
    limit: int,
    source_exists: bool,
) -> list[tuple[object, ...]]:
    embedding = _relation(settings.embedding_table)
    vector = _vector_literal(query_vector)
    conditions: list[sql.Composable] = []
    parameters: list[object] = []
    if store_id:
        conditions.append(sql.SQL("e.store_id = %s"))
        parameters.append(store_id)

    where = (
        sql.SQL("WHERE ") + sql.SQL(" AND ").join(conditions)
        if conditions
        else sql.SQL("")
    )
    if source_exists:
        source = _relation(settings.menu_source_table)
        if conditions:
            where += sql.SQL(" AND m.is_available IS TRUE")
        else:
            where = sql.SQL("WHERE m.is_available IS TRUE")
        query = sql.SQL(
            """
            SELECT e.store_id, e.menu_id, m.name,
                   1 - (e.embedding <=> %s::vector) AS score
            FROM {} AS e
            JOIN {} AS m
              ON m.store_id::TEXT = e.store_id AND m.menu_id::TEXT = e.menu_id
            {}
            ORDER BY e.embedding <=> %s::vector, e.store_id, e.menu_id
            LIMIT %s
            """
        ).format(embedding, source, where)
    else:
        query = sql.SQL(
            """
            SELECT e.store_id, e.menu_id, NULL::TEXT,
                   1 - (e.embedding <=> %s::vector) AS score
            FROM {} AS e
            {}
            ORDER BY e.embedding <=> %s::vector, e.store_id, e.menu_id
            LIMIT %s
            """
        ).format(embedding, where)

    cursor.execute(query, [vector, *parameters, vector, limit])
    return list(cursor.fetchall())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="벡터 원문 대신 메뉴별 상태와 자연어 유사도 점수를 읽기 전용으로 확인합니다."
    )
    parser.add_argument("--store-id", help="특정 매장만 확인")
    parser.add_argument("--query", help="예: '달지 않은 차가운 커피'")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--connect-timeout", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    settings = Settings()
    connection_info = conninfo_to_dict(settings.database_url)
    print(
        "DB:",
        f"{connection_info.get('host')}:{connection_info.get('port', '5432')}",
        f"database={connection_info.get('dbname')}",
        f"user={connection_info.get('user')}",
    )

    with connect(
        settings.database_url,
        connect_timeout=args.connect_timeout,
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            relations = (
                settings.menu_source_table,
                settings.embedding_table,
                settings.reindex_state_table,
            )
            existence = {relation: _exists(cursor, relation) for relation in relations}

            print("\n[테이블 요약]")
            summary_rows = [
                (relation, _count(cursor, relation) if existence[relation] else "없음")
                for relation in relations
            ]
            _print_table(("테이블", "행 수"), summary_rows)

            if not existence[settings.embedding_table]:
                print("\n임베딩 테이블이 없습니다. 먼저 AI 스키마 초기화가 필요합니다.")
                return 1

            print("\n[메뉴 임베딩]")
            rows = _embedding_rows(
                cursor,
                settings,
                store_id=args.store_id,
                limit=args.limit,
                source_exists=existence[settings.menu_source_table],
            )
            display_rows = [
                (
                    *row[:6],
                    row[6].isoformat(timespec="seconds")
                    if isinstance(row[6], datetime)
                    else row[6],
                )
                for row in rows
            ]
            _print_table(
                ("store", "menu", "메뉴명", "차원", "content hash", "revision", "갱신 시각"),
                display_rows,
            )
            if not rows:
                print("저장된 메뉴 벡터가 없습니다.")

            if args.query:
                print(f"\n[자연어 검색] {args.query!r}")
                vector = asyncio.run(_query_vector(args.query, settings.embedding_model_name))
                search_rows = _search_rows(
                    cursor,
                    settings,
                    query_vector=vector,
                    store_id=args.store_id,
                    limit=min(args.limit, 20),
                    source_exists=existence[settings.menu_source_table],
                )
                _print_table(
                    ("store", "menu", "메뉴명", "유사도"),
                    [(*row[:3], f"{float(row[3]):.4f}") for row in search_rows],
                )
                if not search_rows:
                    print("검색할 메뉴 벡터가 없습니다.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OperationalError as exc:
        print(f"\nDB 접속 실패: {exc}")
        print("RDS 보안 그룹이 현재 실행 호스트의 5432 접근을 허용하는지 확인하세요.")
        raise SystemExit(2) from None
