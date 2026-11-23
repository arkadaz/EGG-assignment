import asyncio

from fastembed import TextEmbedding

from app.application.ports.embedder import EmbedderPort

MODEL_NAME = "google/embeddinggemma-300m"


class FastEmbedEmbedder(EmbedderPort):
    def __init__(self, model_path: str) -> None:
        self._model = TextEmbedding(MODEL_NAME, specific_model_path=model_path)

    async def embed_query(self, query: str) -> list[float]:
        text = f"task: search result | query: {query}"
        vectors = await asyncio.to_thread(list, self._model.embed([text]))
        return vectors[0].tolist()
