import asyncio
from pathlib import Path

import jwt
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
COOKIE_NAME = "google_id_token"
COOKIE_MAX_AGE = 3600
PUBLIC_PATHS = {"/login", "/auth/google", "/logout"}
LOGIN_PAGE = Path(__file__).with_name("login.html").read_text(encoding="utf-8")

login_router = APIRouter()


class GoogleCredential(BaseModel):
    credential: str


class GoogleLogin:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.keys = jwt.PyJWKClient(GOOGLE_KEYS_URL)

    def verified_email(self, token: str) -> str | None:
        try:
            signing_key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=GOOGLE_ISSUERS,
            )
        except jwt.PyJWTError:
            return None
        email = claims.get("email", "").lower()
        if claims.get("email_verified") is not True or not email:
            return None
        return email


async def known_email(app: FastAPI, token: str) -> str | None:
    email = await asyncio.to_thread(app.state.google_login.verified_email, token)
    if email is None:
        return None
    role = await app.state.users.role_of(email)
    if role is None:
        return None
    return email


@login_router.get("/login")
async def login_page(request: Request) -> HTMLResponse:
    page = LOGIN_PAGE.replace("{client_id}", request.app.state.google_login.client_id)
    return HTMLResponse(page)


@login_router.post("/auth/google")
async def sign_in(body: GoogleCredential, request: Request) -> JSONResponse:
    email = await known_email(request.app, body.credential)
    if email is None:
        return JSONResponse({"detail": "This Google account is not allowed"}, status_code=403)

    response = JSONResponse({"detail": "Signed in"})
    response.set_cookie(
        COOKIE_NAME,
        body.credential,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@login_router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/login")
    response.delete_cookie(COOKIE_NAME)
    return response


async def require_login(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME, "")
    email = await known_email(request.app, token)
    if email is not None:
        request.state.email = email
        return await call_next(request)

    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login")
    return JSONResponse({"detail": "Login required"}, status_code=401)
