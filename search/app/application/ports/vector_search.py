from abc import ABC, abstractmethod

from app.domain.models import Passage


class VectorSearchPort(ABC):
    @abstractmethod
    async def search(self, query: str, embedding: list[float], top_k: int) -> list[Passage]: ...

    @abstractmethod
    async def document_titles(self) -> list[str]: ...
