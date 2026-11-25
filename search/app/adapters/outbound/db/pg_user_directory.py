from psycopg_pool import AsyncConnectionPool

from app.application.ports.users import UserDirectoryPort

ROLE_OF_SQL = "SELECT role FROM users WHERE email = %s"


class PgUserDirectory(UserDirectoryPort):
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def role_of(self, email: str) -> str | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(ROLE_OF_SQL, (email,))
            row = await cursor.fetchone()
        if row is None:
            return None
        return row[0]
