import hashlib
import json
import os

import psycopg
from fastembed import TextEmbedding
from pgvector.psycopg import register_vector

EMBEDDING_MODEL = "google/embeddinggemma-300m"
EMBEDDING_MODEL_PATH = os.environ.get("EMBEDDING_MODEL_PATH", "/models/embeddinggemma-300m")
DATASET_PATH = os.environ.get("DATASET_PATH", "data/wikipedia.jsonl")
MIN_PARAGRAPH_LENGTH = int(os.environ.get("MIN_PARAGRAPH_LENGTH", "80"))

DOCUMENT_EXISTS_SQL = "SELECT 1 FROM documents WHERE content_hash = %s"
DELETE_DOCUMENT_SQL = "DELETE FROM documents WHERE source = %s"
INSERT_DOCUMENT_SQL = (
    "INSERT INTO documents (title, source, content, content_hash) "
    "VALUES (%s, %s, %s, %s) RETURNING id"
)
EXISTING_CHUNK_HASHES_SQL = "SELECT content_hash FROM chunks WHERE content_hash = ANY(%s)"
INSERT_CHUNK_SQL = (
    "INSERT INTO chunks (document_id, content, content_hash, embedding) VALUES (%s, %s, %s, %s)"
)


def read_articles(path: str) -> list[dict]:
    articles = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            articles.append(json.loads(line))
    return articles


def split_into_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for line in text.split("\n"):
        if len(line) > MIN_PARAGRAPH_LENGTH:
            paragraphs.append(line)
    return paragraphs


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_exists(connection: psycopg.Connection, content_hash: str) -> bool:
    row = connection.execute(DOCUMENT_EXISTS_SQL, (content_hash,)).fetchone()
    return row is not None


def insert_document(connection: psycopg.Connection, article: dict, content_hash: str) -> int:
    values = (article["title"], article["source"], article["content"], content_hash)
    return connection.execute(INSERT_DOCUMENT_SQL, values).fetchone()[0]


def find_new_paragraphs(connection: psycopg.Connection, paragraphs: list[str]) -> list[str]:
    hashes = [hash_text(paragraph) for paragraph in paragraphs]
    rows = connection.execute(EXISTING_CHUNK_HASHES_SQL, (hashes,)).fetchall()
    known_hashes = {row[0] for row in rows}

    new_paragraphs = []
    for paragraph, paragraph_hash in zip(paragraphs, hashes, strict=True):
        if paragraph_hash in known_hashes:
            continue
        known_hashes.add(paragraph_hash)
        new_paragraphs.append(paragraph)
    return new_paragraphs


def save_chunks(
    connection: psycopg.Connection,
    document_id: int,
    title: str,
    paragraphs: list[str],
    model: TextEmbedding,
) -> None:
    texts_to_embed = [f"title: {title} | text: {paragraph}" for paragraph in paragraphs]
    embeddings = list(model.embed(texts_to_embed))

    for paragraph, embedding in zip(paragraphs, embeddings, strict=True):
        values = (document_id, paragraph, hash_text(paragraph), embedding)
        connection.execute(INSERT_CHUNK_SQL, values)


def main() -> None:
    model = TextEmbedding(EMBEDDING_MODEL, specific_model_path=EMBEDDING_MODEL_PATH)
    articles = read_articles(DATASET_PATH)

    new_documents = 0
    skipped_documents = 0
    new_chunks = 0
    skipped_chunks = 0

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        register_vector(connection)

        for article in articles:
            paragraphs = split_into_paragraphs(article["content"])
            article_hash = hash_text(article["content"])

            if document_exists(connection, article_hash):
                skipped_documents += 1
                skipped_chunks += len(paragraphs)
                continue

            connection.execute(DELETE_DOCUMENT_SQL, (article["source"],))
            document_id = insert_document(connection, article, article_hash)
            unique_paragraphs = find_new_paragraphs(connection, paragraphs)
            save_chunks(connection, document_id, article["title"], unique_paragraphs, model)

            new_documents += 1
            new_chunks += len(unique_paragraphs)
            skipped_chunks += len(paragraphs) - len(unique_paragraphs)

    print(f"Documents: {new_documents} new, {skipped_documents} duplicates skipped")
    print(f"Chunks: {new_chunks} new, {skipped_chunks} duplicates skipped")


if __name__ == "__main__":
    main()
