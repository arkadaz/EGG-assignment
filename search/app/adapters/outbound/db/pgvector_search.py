import numpy as np
from psycopg_pool import AsyncConnectionPool

from app.application.ports.vector_search import VectorSearchPort
from app.domain.models import Passage

HYBRID_SEARCH_SQL = """
    WITH by_meaning AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s) AS rank
        FROM chunks
        ORDER BY embedding <=> %(embedding)s
        LIMIT %(candidates)s
    ),
    by_keywords AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(content_tsv, query) DESC) AS rank
        FROM chunks, websearch_to_tsquery('english', %(query)s) AS query
        WHERE content_tsv @@ query
        ORDER BY ts_rank_cd(content_tsv, query) DESC
        LIMIT %(candidates)s
    ),
    combined AS (
        SELECT id, SUM(1.0 / (%(rrf_k)s + rank)) AS rrf_score
        FROM (SELECT * FROM by_meaning UNION ALL SELECT * FROM by_keywords) AS both_lists
        GROUP BY id
    )
    SELECT d.title, d.source, c.content, 1 - (c.embedding <=> %(embedding)s) AS score
    FROM combined
    JOIN chunks c ON c.id = combined.id
    JOIN documents d ON d.id = c.document_id
    ORDER BY combined.rrf_score DESC
    LIMIT %(top_k)s
"""

DOCUMENT_TITLES_SQL = "SELECT title FROM documents ORDER BY title"


class PgVectorSearch(VectorSearchPort):
    def __init__(self, pool: AsyncConnectionPool, candidates: int, rrf_k: int) -> None:
        self._pool = pool
        self._candidates = candidates
        self._rrf_k = rrf_k

    async def search(self, query: str, embedding: list[float], top_k: int) -> list[Passage]:
        params = {
            "query": query,
            "embedding": np.array(embedding),
            "candidates": self._candidates,
            "rrf_k": self._rrf_k,
            "top_k": top_k,
        }
        async with self._pool.connection() as connection:
            cursor = await connection.execute(HYBRID_SEARCH_SQL, params)
            rows = await cursor.fetchall()
        return [Passage(title, source, content, score) for title, source, content, score in rows]

    async def document_titles(self) -> list[str]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(DOCUMENT_TITLES_SQL)
            rows = await cursor.fetchall()
        return [title for (title,) in rows]
