import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fake_google import CLIENT_ID, OTHER_PRIVATE_KEY, FakeGoogleKeys, google_token

app.state.google_login.keys = FakeGoogleKeys()


def browser():
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def test_api_call_without_login_gets_401():
    response = browser().post("/ask", json={"question": "What is PostgreSQL?"})

    assert response.status_code == 401


def test_page_without_login_goes_to_the_login_page():
    response = browser().get("/dev-ui/", headers={"Accept": "text/html"})

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_login_page_shows_the_google_button():
    page = browser().get("/login").text

    assert f'data-client_id="{CLIENT_ID}"' in page
    assert "accounts.google.com/gsi/client" in page


def test_owner_signs_in_and_out():
    client = browser()

    assert client.post("/auth/google", json={"credential": google_token()}).status_code == 200
    assert client.get("/docs").status_code == 200

    client.get("/logout")
    assert client.get("/docs").status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        google_token(email="someone@example.com"),
        google_token(email_verified=False),
        google_token(aud="another-client"),
        google_token(iss="https://evil.example.com"),
        google_token(exp=int(time.time()) - 60),
        google_token(private_key=OTHER_PRIVATE_KEY),
        "not-a-jwt",
    ],
    ids=[
        "other account",
        "unverified",
        "other client",
        "other issuer",
        "expired",
        "forged",
        "junk",
    ],
)
def test_any_other_token_is_refused(token):
    client = browser()

    assert client.post("/auth/google", json={"credential": token}).status_code == 403
    assert client.get("/docs").status_code == 401
