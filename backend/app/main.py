"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.utils import config
from app.services import repository as repo
from app.utils.database import init_db, session_scope
from app.utils.errors import DataValidationError

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with session_scope() as s:
        n = repo.fail_stale_runs(s)
    if n:
        log.warning("Marked %d interrupted analysis run(s) as failed after restart", n)
    yield


app = FastAPI(title="Product Review Intelligence API", version="0.9.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health() -> dict:
    s = config.settings
    live = bool(s.llm_api_key) and not s.use_mock_llm
    return {"status": "ok", "llm_mode": "live" if live else "mock",
            "llm_ready": s.use_mock_llm or bool(s.llm_api_key),
            "database": s.database_url.split(":")[0],
            "sentiment_backend": s.sentiment_backend, "embedding_backend": s.embedding_backend}


@app.exception_handler(DataValidationError)
async def handle_validation_error(_: Request, exc: DataValidationError):
    return JSONResponse(exc.to_dict(), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def handle_request_error(_: Request, exc: RequestValidationError):
    fields = [".".join(str(x) for x in e["loc"] if x != "body") for e in exc.errors()]
    return JSONResponse({"error": "invalid_request", "message": "The request is missing or has invalid fields: "
                         + ", ".join(f or "body" for f in fields), "details": {"fields": fields}}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": "http_error", "message": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"error": "internal_error",
                         "message": "Something went wrong on the server. Please try again."}, status_code=500)
