from abc import ABC, abstractmethod

from app.domain.models import Passage


class LLMPort(ABC):
    @abstractmethod
    async def generate(self, question: str, context: list[Passage]) -> str: ...
