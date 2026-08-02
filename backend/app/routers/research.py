"""NDJSON research endpoint with bounded concurrency and disconnect cleanup."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import get_settings, is_free_model_id
from ..schemas import ErrorEvent, HeartbeatEvent, ProgressEvent, ResearchError, ResearchRequest, ResultEvent
from ..services.research import ResearchServiceError, run_research

router = APIRouter(prefix="/api/v1", tags=["research"])
_global_jobs = asyncio.Semaphore(2)
_ip_active: set[str] = set()
_ip_times: dict[str, deque[float]] = defaultdict(deque)
_ip_guard = asyncio.Lock()


async def _reserve_ip(ip: str) -> bool:
    now = time.monotonic()
    async with _ip_guard:
        history = _ip_times[ip]
        while history and now - history[0] > 3600:
            history.popleft()
        if ip in _ip_active or len(history) >= 5:
            return False
        _ip_active.add(ip)
        history.append(now)
        return True


async def _release_ip(ip: str) -> None:
    async with _ip_guard:
        _ip_active.discard(ip)


def _error_response(error: ResearchError, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error.model_dump(mode="json")})


@router.post("/research")
async def research(payload: ResearchRequest, request: Request):
    settings = get_settings()
    if not is_free_model_id(payload.model_id):
        return _error_response(
            ResearchError(
                code="MODEL_NOT_ALLOWED",
                message="Only free OpenRouter models are enabled.",
                retryable=False,
            ),
            422,
        )
    if not settings.openrouter_api_key:
        return _error_response(ResearchError(code="CONFIG_MISSING", message="OpenRouter is not configured.", retryable=False), 503)
    ip = request.client.host if request.client else "unknown"
    if not await _reserve_ip(ip):
        return _error_response(ResearchError(code="SERVER_BUSY", message="Research is already running or the request limit was reached.", retryable=True), 429)
    if _global_jobs.locked():
        await _release_ip(ip)
        return _error_response(ResearchError(code="SERVER_BUSY", message="Research capacity is currently full.", retryable=True), 429)
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def progress(event: ProgressEvent):
        await queue.put(event)

    async def pipeline():
        try:
            async with asyncio.timeout(75):
                report = await run_research(payload.query, payload.model_id, request.app.state.http_client, settings, progress)
            await queue.put(ResultEvent(report=report))
        except asyncio.TimeoutError:
            await queue.put(ErrorEvent(error=ResearchError(code="RESEARCH_TIMEOUT", message="Research took too long to complete.", retryable=True)))
        except ResearchServiceError as exc:
            await queue.put(ErrorEvent(error=ResearchError(code=exc.code, message=exc.message, retryable=exc.retryable)))
        except asyncio.CancelledError:
            raise
        except Exception:
            await queue.put(ErrorEvent(error=ResearchError(code="RESEARCH_FAILED", message="Research could not be completed.", retryable=True)))

    async def stream() -> AsyncIterator[bytes]:
        acquired = False
        pipeline_task: asyncio.Task | None = None
        try:
            await _global_jobs.acquire()
            acquired = True
            pipeline_task = asyncio.create_task(pipeline())
            while True:
                if await request.is_disconnected():
                    pipeline_task.cancel()
                    await asyncio.gather(pipeline_task, return_exceptions=True)
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield (HeartbeatEvent().model_dump_json() + "\n").encode()
                    continue
                yield (event.model_dump_json() + "\n").encode()  # type: ignore[attr-defined]
                if isinstance(event, (ResultEvent, ErrorEvent)):
                    break
            await pipeline_task
        finally:
            if pipeline_task is not None and not pipeline_task.done():
                pipeline_task.cancel()
                await asyncio.gather(pipeline_task, return_exceptions=True)
            if acquired:
                _global_jobs.release()
            await _release_ip(ip)

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
