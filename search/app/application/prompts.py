from app.domain.models import Passage

PROMPT_VERSION = "v1"

ANSWER_PROMPT = (
    "Answer the question using only the numbered context passages and cite them like [1]. "
    "If the context does not contain the answer, say that you don't know."
)

AGENT_PROMPT = (
    "You answer questions using only the knowledge base. Call search_knowledge_base first. "
    "If the passages do not answer the question, search again with different keywords. "
    "Call list_documents when you need to know which topics exist. Answer briefly and name "
    "the document titles you used. If the knowledge base has no answer, say you don't know."
)


def answer_user_message(question: str, passages: list[Passage]) -> str:
    numbered = []
    for number, passage in enumerate(passages, start=1):
        numbered.append(f"[{number}] {passage.title}: {passage.content}")
    context = "\n\n".join(numbered)
    return f"Context:\n{context}\n\nQuestion: {question}"
