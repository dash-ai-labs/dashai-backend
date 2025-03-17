import secrets
from collections import OrderedDict

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.libs.const import STAGE
from src.routes import auth_router, email_router, label_router, proxy_router, compose_router

load_dotenv()


ALEMBIC_CFG = "alembic.ini"
CSP: dict[str, str | list[str]] = {
    "default-src": "'self'",
    "img-src": [
        "*",
        "data:",
    ],
    "connect-src": "'self'",
    "script-src": "'self'",
    "style-src": ["'self'", "'unsafe-inline'"],
}

app = FastAPI()


# @app.middleware("http")
# async def add_csp_header(request, call_next):
#     response = await call_next(request)
#     nonce = secrets.token_urlsafe(16)
#     csp = f"default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic'; style-src 'self' 'nonce-${nonce}'; img-src 'self' data: https:; font-src 'self'; frame-src 'self' data:; child-src 'self' data:; connect-src 'self' https://api.getdash.ai; frame-ancestors 'none'; form-action 'self'"
#     response.headers["Content-Security-Policy"] = csp
#     response.headers["X-Content-Security-Policy-Nonce"] = nonce
#     return response


def parse_policy() -> str:
    nonce = secrets.token_urlsafe(16)
    csp = f"default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic'; style-src 'self' 'nonce-${nonce}'; img-src 'self' data: https:; font-src 'self'; frame-src 'self' data:; child-src 'self' data:; connect-src 'self' https://api.getdash.ai; frame-ancestors 'none'; form-action 'self'"
    return csp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app: FastAPI, csp: bool = True) -> None:
        """Init SecurityHeadersMiddleware.

        :param app: FastAPI instance
        :param no_csp: If no CSP should be used;
            defaults to :py:obj:`False`
        """
        super().__init__(app)
        self.csp = csp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Dispatch of the middleware.

        :param request: Incoming request
        :param call_next: Function to process the request
        :return: Return response coming from from processed request
        """
        headers = {
            "Content-Security-Policy": "" if not self.csp else parse_policy(),
            "Cross-Origin-Opener-Policy": "same-origin",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31556926; includeSubDomains",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        }
        response = await call_next(request)
        response.headers.update(headers)
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["https://app.getdash.ai"] if STAGE == "production" else ["http://localhost:5173"]
    ),
    # Svelte dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(email_router)
app.include_router(label_router)
app.include_router(proxy_router)
app.include_router(compose_router)


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}
