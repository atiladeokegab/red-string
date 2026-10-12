"""The one app factory: health, login, the error map, request logging, seeding, and mounting
every vertical. A new part of the product is a module in starter/verticals/, not a new app."""

import hmac
import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from starter import verticals
from starter.agent import routes
from starter.core.errors import ConflictError, NotFound, ProviderNotConfigured
from starter.core.gateway import build_gateway
from starter.core.store import Store
from starter.runtime.config import Settings
from starter.runtime.deps import session_token
from starter.web import pages

ERROR_STATUS = {ConflictError: 409, NotFound: 404, ProviderNotConfigured: 503, ValueError: 422}


class Login(BaseModel):
    password: str


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or Store(settings.data_path)
    app = FastAPI(title="starter")
    app.state.settings = settings
    app.state.store = store
    app.state.gateway = build_gateway(store)

    for exc, status in ERROR_STATUS.items():
        app.add_exception_handler(exc, _error_handler(status))

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        line = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
        }
        print(json.dumps(line), flush=True)  # Cloud Run reads stdout JSON as structured logs
        return response

    @app.get("/health")  # Cloud Run reserves paths ending in "z": /healthz is local only
    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", **settings.public()}

    @app.post("/api/login")
    def login(body: Login) -> dict:
        if not hmac.compare_digest(body.password, settings.admin_password):
            raise HTTPException(401, "wrong password")
        return {"token": session_token(settings.admin_password)}

    app.include_router(routes.router)
    app.include_router(pages.router)
    app.mount("/static", pages.static, name="static")

    for module in verticals.modules():
        if hasattr(module, "router"):
            app.include_router(module.router)
        if settings.mode == "local" and hasattr(module, "seed"):
            module.seed(store)
    return app


def _error_handler(status: int):
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=status)

    return handle
