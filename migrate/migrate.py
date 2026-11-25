import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path("migrations")

CREATE_HISTORY_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
)
APPLIED_MIGRATIONS_SQL = "SELECT name FROM schema_migrations"
RECORD_MIGRATION_SQL = "INSERT INTO schema_migrations (name) VALUES (%s)"
SEED_FIRST_USER_SQL = (
    "INSERT INTO users (email, role) VALUES (%s, 'user') ON CONFLICT (email) DO NOTHING"
)


def main() -> None:
    first_user_email = os.environ["ALLOWED_EMAIL"].strip().lower()
    if not first_user_email:
        raise SystemExit("ALLOWED_EMAIL must be the first user's email")

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(CREATE_HISTORY_SQL)
        rows = connection.execute(APPLIED_MIGRATIONS_SQL).fetchall()
        applied = {row[0] for row in rows}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                print(f"{path.name}: already applied")
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(RECORD_MIGRATION_SQL, (path.name,))
            print(f"{path.name}: applied")

        connection.execute(SEED_FIRST_USER_SQL, (first_user_email,))
        print("first user: in the users table")


if __name__ == "__main__":
    main()
