from abc import ABC, abstractmethod


class EmbedderPort(ABC):
    @abstractmethod
    async def embed_query(self, query: str) -> list[float]: ...
