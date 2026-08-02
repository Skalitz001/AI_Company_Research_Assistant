"""Pydantic contracts shared by the API, services, and frontend."""

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit


def _validate_public_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    return value


def _looks_like_url(value: str) -> bool:
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlsplit(candidate)
    return bool(parsed.hostname and "." in parsed.hostname and " " not in parsed.hostname)


from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2048)
    model_id: str = Field(min_length=3, max_length=160)

    @field_validator("query", "model_id", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if "/" not in value or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("model_id must be an exact provider model ID containing '/'")
        return value
    @model_validator(mode="after")
    def validate_query_length(self) -> "ResearchRequest":
        if not _looks_like_url(self.query) and len(self.query) > 120:
            raise ValueError("Company names must be 120 characters or fewer")
        return self



class CompanyInfo(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    website: str = Field(min_length=1, max_length=2048)
    phone: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=400)
    country: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=180)
    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str) -> str:
        return _validate_public_url(value)



class Competitor(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    website: str = Field(min_length=1, max_length=2048)
    fit: str = Field(default="Relevant category or market competitor", max_length=300)
    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str) -> str:
        return _validate_public_url(value)



class Source(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(min_length=1, max_length=2048)
    source_type: Literal["website", "search", "public"] = "website"
    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_public_url(value)


class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: CompanyInfo
    summary: str = Field(min_length=1, max_length=2500)
    products_services: list[str] = Field(default_factory=list, max_length=12)
    pain_points: list[str] = Field(default_factory=list, max_length=6)
    competitors: list[Competitor] = Field(default_factory=list, max_length=5)
    sources: list[Source] = Field(default_factory=list, max_length=15)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_id: str = Field(min_length=3, max_length=160)

    @field_validator("products_services", "pain_points", "warnings")
    @classmethod
    def trim_and_bound_items(cls, values: list[str]) -> list[str]:
        return [item.strip()[:500] for item in values if item and item.strip()]

    @model_validator(mode="after")
    def unique_competitors(self) -> "ResearchReport":
        seen: set[str] = set()
        unique: list[Competitor] = []
        for competitor in self.competitors:
            key = competitor.name.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(competitor)
        self.competitors = unique[:5]
        return self


class ConfigResponse(BaseModel):
    ready: bool
    default_model: str
    model_suggestions: list[str]
    discord_enabled: bool


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ResearchError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    stage: Literal["resolving", "crawling", "searching", "analyzing", "finalizing"]
    percent: int = Field(ge=0, le=100)
    message: str = Field(max_length=240)


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    report: ResearchReport


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: ResearchError


class HeartbeatEvent(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    message: str = "Still working…"


StreamEvent = ProgressEvent | ResultEvent | ErrorEvent | HeartbeatEvent
