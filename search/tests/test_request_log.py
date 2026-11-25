import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.login.google_login import COOKIE_NAME
from app.adapters.inbound.request_log import REQUEST_ID_HEADER, JsonFormatter, logger
from app.main import app
from tests.fake_google import OWNER, FakeGoogleKeys, google_token
from tests.fake_users import FakeUserDirectory

app.state.google_login.keys = FakeGoogleKeys()
app.state.users = FakeUserDirectory({OWNER: "user"})


class CollectRecords(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class BrokenAskQuestion:
    async def ask(self, question):
        raise RuntimeError("database is down")


@pytest.fixture
def records():
    handler = CollectRecords()
    logger.addHandler(handler)
    yield handler.records
    logger.removeHandler(handler)


def test_each_request_is_logged_as_json_with_its_id_and_user(records):
    client = TestClient(app, cookies={COOKIE_NAME: google_token()})

    response = client.get("/docs", headers={REQUEST_ID_HEADER: "abc-123"})

    entry = json.loads(JsonFormatter().format(records[-1]))
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"
    assert entry["severity"] == "INFO"
    assert entry["message"] == "GET /docs 200"
    assert entry["request_id"] == "abc-123"
    assert entry["user"] == OWNER
    assert entry["status"] == 200
    assert entry["duration_ms"] >= 0


def test_an_error_is_logged_with_its_traceback(records):
    app.state.ask_question = BrokenAskQuestion()
    client = TestClient(app, cookies={COOKIE_NAME: google_token()}, raise_server_exceptions=False)

    response = client.post("/ask", json={"question": "What is PostgreSQL?"})

    entry = json.loads(JsonFormatter().format(records[-1]))
    assert response.status_code == 500
    assert entry["severity"] == "ERROR"
    assert entry["status"] == 500
    assert entry["error"] == "RuntimeError: database is down"
    assert "Traceback" in entry["traceback"]
