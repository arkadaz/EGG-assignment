from dataclasses import dataclass

from app.application.ports.llm import LLMPort
from app.application.prompts import PROMPT_VERSION
from app.application.search_docs import SearchDocs
from app.domain.models import Answer

NO_ANSWER = "I could not find information about that in the knowledge base."


@dataclass
class AskQuestion:
    search_docs: SearchDocs
    llm: LLMPort

    async def ask(self, question: str) -> Answer:
        passages = await self.search_docs.search(question)
        if not passages:
            return Answer(NO_ANSWER, [], PROMPT_VERSION)
        answer = await self.llm.generate(question, passages)
        return Answer(answer, passages, PROMPT_VERSION)
