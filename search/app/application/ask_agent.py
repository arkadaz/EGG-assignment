from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.application.ports.agent import AgentPort
from app.application.ports.vector_search import VectorSearchPort
from app.application.prompts import PROMPT_VERSION
from app.application.search_docs import SearchDocs
from app.domain.models import Answer, Passage


@dataclass
class KnowledgeBaseTools:
    search_docs: SearchDocs
    vectors: VectorSearchPort
    keep_sources: bool = False
    sources: dict[str, Passage] = field(default_factory=dict)

    async def search_knowledge_base(self, query: str) -> list[dict]:
        """Search the knowledge base and return the passages that match the query."""
        passages = await self.search_docs.search(query)
        if self.keep_sources:
            for passage in passages:
                if passage.content not in self.sources:
                    self.sources[passage.content] = passage
        return [{"title": passage.title, "content": passage.content} for passage in passages]

    async def list_documents(self) -> list[str]:
        """List the titles of all documents in the knowledge base."""
        return await self.vectors.document_titles()

    def as_list(self) -> list[Callable[..., Awaitable]]:
        return [self.search_knowledge_base, self.list_documents]


@dataclass
class AskAgent:
    agent: AgentPort
    search_docs: SearchDocs
    vectors: VectorSearchPort

    async def ask(self, question: str) -> Answer:
        tools = KnowledgeBaseTools(self.search_docs, self.vectors, keep_sources=True)
        text = await self.agent.run(question, tools.as_list())
        return Answer(text, list(tools.sources.values()), PROMPT_VERSION)
