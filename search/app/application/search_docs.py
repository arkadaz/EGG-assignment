from dataclasses import dataclass

from app.application.ports.embedder import EmbedderPort
from app.application.ports.vector_search import VectorSearchPort
from app.domain.models import Passage


@dataclass
class SearchDocs:
    embedder: EmbedderPort
    vectors: VectorSearchPort
    top_k: int
    min_score: float

    async def search(self, query: str) -> list[Passage]:
        embedding = await self.embedder.embed_query(query)
        passages = await self.vectors.search(query, embedding, self.top_k)
        return [passage for passage in passages if passage.score >= self.min_score]
