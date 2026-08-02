"""FastAPI entrypoint for same-origin API and production SPA serving."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import get_settings
from .routers.config import router as config_router
from .routers.pdf import router as pdf_router
from .routers.discord import router as discord_router
from .routers.research import router as research_router
from .schemas import ResearchError


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(follow_redirects=False) as client:
        app.state.http_client = client
        yield


app = FastAPI(title="Company Research Assistant", lifespan=lifespan)
app.include_router(config_router)
app.include_router(research_router)
app.include_router(pdf_router)
app.include_router(discord_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    error = ResearchError(code="VALIDATION_ERROR", message="The request did not match the required format.", retryable=False)
    return JSONResponse(status_code=422, content={"error": error.model_dump(mode="json")})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return response


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    static_root = Path(get_settings().frontend_dist).resolve()
    requested = (static_root / path).resolve()
    if static_root.exists() and requested.is_relative_to(static_root) and requested.is_file():
        return FileResponse(requested)
    index = static_root / "index.html"
    if static_root.exists() and index.is_file():
        return FileResponse(index)
    return HTMLResponse("<html><body><h1>Company Research Assistant</h1><p>Frontend assets are not built.</p></body></html>")


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=settings.port)
