from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool


async def open_pool(database_url: str, max_size: int, timeout: float) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={"autocommit": True},
        configure=register_vector_async,
    )
    await pool.open(wait=True, timeout=timeout)
    return pool
