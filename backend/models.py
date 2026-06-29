"""Pydantic data models for jobtrack-agent."""

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field

# Shared type alias for the lifecycle status of an application.
# "saved" is the pre-application state: the job was captured but not yet applied
# to, so it carries no date_applied and is excluded from follow-up reminders.
ApplicationStatus = Literal[
    "saved",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "ghosted",
]

# Mapping of domain substrings to their canonical platform names.
_PLATFORM_DOMAINS: list[tuple[str, str]] = [
    ("linkedin.", "LinkedIn"),
    ("naukri.", "Naukri"),
    ("wellfound.", "Wellfound"),
    ("internshala.", "Internshala"),
    ("indeed.", "Indeed"),
    ("glassdoor.", "Glassdoor"),
]


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def detect_platform(url: str) -> str | None:
    """Detect the job platform from a URL's domain.

    Recognizes LinkedIn, Naukri, Wellfound, Internshala, Indeed, and
    Glassdoor. Returns the canonical platform name, or ``None`` if the
    domain does not match any known platform.
    """
    if not url:
        return None

    host = urlparse(url).netloc.lower()
    if not host:
        # Fall back to scanning the raw string when there's no scheme.
        host = url.lower()

    for needle, name in _PLATFORM_DOMAINS:
        if needle in host:
            return name
    return None


class JobApplication(BaseModel):
    """A tracked job application, as persisted in storage."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    url: str
    company: str
    role: str
    location: str | None = None
    salary_min: int | None = None  # monthly, INR
    salary_max: int | None = None  # monthly, INR
    salary_raw: str | None = None  # original text before parsing, e.g. "12-18 LPA"
    skills: list[str] = Field(default_factory=list)
    jd_summary: str  # 2-3 sentence summary of the JD
    jd_full: str  # complete extracted JD text
    status: ApplicationStatus = "saved"
    # Only set once the job is actually applied to; "saved" captures leave it None.
    date_applied: datetime | None = None
    last_updated: datetime = Field(default_factory=_utcnow)
    follow_up_sent: bool = False
    source_platform: str | None = None  # auto-detected from URL
    extraction_confidence: float = Field(ge=0.0, le=1.0)  # set by extractor
    notes: str | None = None


class ExtractionResult(BaseModel):
    """Structured data returned by the LLM extractor before persistence.

    Every field is optional with a safe default. Groq's structured output throws
    a hard 400 when a *required* field is absent, so a partial extraction would
    crash the whole capture. With defaults the model can return partial data (or
    we can salvage partial JSON from an error) and it still validates.
    """

    url: str = ""
    company: str = ""
    role: str = ""
    location: str | None = None
    salary_min: int | None = None  # monthly, INR
    salary_max: int | None = None  # monthly, INR
    salary_raw: str | None = None  # original text before parsing, e.g. "12-18 LPA"
    skills: list[str] = Field(default_factory=list)
    jd_summary: str = ""  # 2-3 sentence summary of the JD
    jd_full: str = ""  # complete extracted JD text
    source_platform: str | None = None  # auto-detected from URL
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # set by extractor
    missing_fields: list[str] = Field(default_factory=list)  # fields the LLM could not find
    used_fallback: bool = False  # whether the fallback model was used instead of the primary


class CaptureRequest(BaseModel):
    """Payload POSTed by the Chrome extension to capture a page."""

    url: str
    raw_html: str
    page_title: str | None = None
    # Rendered visible text of the page (document.body.innerText). Preferred over
    # raw_html for extraction: it's far smaller and already has the JD expanded.
    body_text: str | None = None
    # Status chosen in the popup at capture time. Defaults to "saved".
    status: ApplicationStatus = "saved"


class SearchRequest(BaseModel):
    """A semantic search query over stored applications."""

    query: str
    limit: int = 10
    status_filter: ApplicationStatus | None = None


class ApplicationUpdate(BaseModel):
    """Partial update to an existing application."""

    status: ApplicationStatus | None = None
    notes: str | None = None
