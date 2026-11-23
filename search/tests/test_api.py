import pytest
from fastapi.testclient import TestClient

from app.adapters.outbound.llm.mock_llm import MockLLM
from app.application.ask_agent import AskAgent
from app.application.ask_question import NO_ANSWER, AskQuestion
from app.application.ports.agent import AgentPort
from app.application.ports.embedder import EmbedderPort
from app.application.ports.vector_search import VectorSearchPort
from app.application.prompts import PROMPT_VERSION, answer_user_message
from app.application.search_docs import SearchDocs
from app.domain.models import Passage
from app.main import app

POSTGRES = Passage(
    "PostgreSQL", "https://example.org/pg", "PostgreSQL is a relational database.", 0.8
)
KUBERNETES = Passage("Kubernetes", "https://example.org/k8s", "Kubernetes runs containers.", 0.3)


class FakeEmbedder(EmbedderPort):
    async def embed_query(self, query):
        return [0.0]


class InMemorySearch(VectorSearchPort):
    def __init__(self, passages):
        self.passages = passages

    async def search(self, query, embedding, top_k):
        return self.passages[:top_k]

    async def document_titles(self):
        return sorted({passage.title for passage in self.passages})


class FakeAgent(AgentPort):
    async def run(self, question, tools):
        search_knowledge_base, list_documents = tools
        await search_knowledge_base("first try")
        await search_knowledge_base(question)
        titles = await list_documents()
        return f"Found in {titles[0]}"


def search_docs_over(passages):
    return SearchDocs(FakeEmbedder(), InMemorySearch(passages), top_k=4, min_score=0.4)


def ask(passages, question, path="/ask"):
    app.state.ask_question = AskQuestion(search_docs_over(passages), MockLLM())
    return TestClient(app).post(path, json={"question": question}).json()


@pytest.mark.parametrize("path", ["/ask", "/api/v1/ask"])
def test_answers_from_relevant_passages_only(path):
    body = ask([POSTGRES, KUBERNETES], "What is PostgreSQL?", path)

    assert "PostgreSQL is a relational database." in body["answer"]
    assert [source["title"] for source in body["sources"]] == ["PostgreSQL"]
    assert body["prompt_version"] == PROMPT_VERSION


def test_says_not_found_when_nothing_is_relevant():
    body = ask([KUBERNETES], "Who won in 1998?")

    assert body["answer"] == NO_ANSWER
    assert body["sources"] == []


def test_agent_lists_each_found_passage_once():
    passages = [POSTGRES, KUBERNETES]
    app.state.ask_agent = AskAgent(
        FakeAgent(), search_docs_over(passages), InMemorySearch(passages)
    )

    body = TestClient(app).post("/agent/ask", json={"question": "What is PostgreSQL?"}).json()

    assert body["answer"] == "Found in Kubernetes"
    assert [source["title"] for source in body["sources"]] == ["PostgreSQL"]


def test_agent_needs_an_llm_key():
    app.state.ask_agent = None

    response = TestClient(app).post("/agent/ask", json={"question": "What is PostgreSQL?"})

    assert response.status_code == 503


def test_answer_message_numbers_the_passages():
    message = answer_user_message("What is PostgreSQL?", [POSTGRES, KUBERNETES])

    assert "[1] PostgreSQL: PostgreSQL is a relational database." in message
    assert "[2] Kubernetes: Kubernetes runs containers." in message
    assert message.endswith("Question: What is PostgreSQL?")
