"""Validated report-to-PDF endpoint."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from ..schemas import ResearchError, ResearchReport
from ..services.pdf import render_pdf, safe_filename

router = APIRouter(prefix="/api/v1", tags=["pdf"])
MAX_BODY = 1_500_000


@router.post("/pdf")
async def pdf(request: Request):
    body = await request.body()
    if len(body) > MAX_BODY:
        error = ResearchError(code="PDF_INPUT_TOO_LARGE", message="The report payload is too large.", retryable=False)
        return JSONResponse(status_code=413, content={"error": error.model_dump(mode="json")})
    try:
        value = json.loads(body)
        report = ResearchReport.model_validate(value.get("report") if isinstance(value, dict) else None)
    except (json.JSONDecodeError, ValidationError, TypeError, AttributeError):
        error = ResearchError(code="INVALID_REPORT", message="The supplied report is invalid.", retryable=False)
        return JSONResponse(status_code=422, content={"error": error.model_dump(mode="json")})
    try:
        data = render_pdf(report)
    except Exception:
        error = ResearchError(code="PDF_FAILED", message="The PDF could not be generated.", retryable=True)
        return JSONResponse(status_code=500, content={"error": error.model_dump(mode="json")})
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(report.company.name)}"', "Cache-Control": "no-store"},
    )
