import textwrap

from app.application.ports.llm import LLMPort
from app.domain.models import Passage


class MockLLM(LLMPort):
    async def generate(self, question: str, context: list[Passage]) -> str:
        best = context[0]
        return f'[mock LLM] From "{best.title}": {textwrap.shorten(best.content, 400)}'
