CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
