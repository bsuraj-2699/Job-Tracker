"""FastAPI application entry point for jobtrack-agent."""

from __future__ import annotations

import io
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastembed import TextEmbedding

from backend.config import settings
from backend.extraction.extractor import get_extractor
from backend.models import (
    ApplicationStatus,
    ApplicationUpdate,
    CaptureRequest,
    JobApplication,
    SearchRequest,
    detect_platform,
)
from backend.scheduler.reminders import start_scheduler, stop_scheduler
from backend.storage.qdrant_client import _recent_urls, get_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the follow-up reminder scheduler for the lifetime of the app.

    Also warms the embedding model at startup so the first /capture doesn't pay
    the one-time model-load cost (~10-30s) on the request path.
    """
    print("Warming embedding model...")
    get_embeddings()
    print("Embedding model ready.")

    scheduler = start_scheduler()
    try:
        yield
    finally:
        stop_scheduler(scheduler)


app = FastAPI(title="jobtrack-agent", version="0.1.0", lifespan=lifespan)

# The browser extension calls this API cross-origin. allow_credentials stays
# False so the "*" origin wildcard remains valid per the CORS spec.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy embedding singleton: loading the model is expensive, so defer it until
# the first request that actually needs an embedding.
_embeddings: TextEmbedding | None = None


def get_embeddings() -> TextEmbedding:
    """Return the shared FastEmbed model, loading it on first use."""
    global _embeddings
    if _embeddings is None:
        _embeddings = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embeddings


def get_embedding(text: str) -> list[float]:
    """Embed a piece of text into a 384-dimensional vector."""
    embeddings = list(get_embeddings().embed([text]))
    return embeddings[0].tolist()


@app.post("/capture", response_model=JobApplication)
def capture(
    request: CaptureRequest,
    status: ApplicationStatus = "applied",
) -> JobApplication:
    """Extract, embed, and store a captured job page.

    ``status`` is a query param defaulting to ``"applied"`` (the user is
    capturing because they applied or intend to). Pass ``?status=saved`` to
    bookmark a job without marking it applied.
    """
    if get_storage().url_exists(request.url):
        raise HTTPException(
            status_code=409,
            detail=f"Job already captured: {request.url}",
        )

    result = get_extractor().extract(request)

    # date_applied is only meaningful once the job is actually applied to; a
    # "saved" capture leaves it None (and is therefore excluded from reminders).
    date_applied = datetime.now(timezone.utc) if status == "applied" else None

    job = JobApplication(
        url=result.url,
        company=result.company,
        role=result.role,
        location=result.location,
        salary_min=result.salary_min,
        salary_max=result.salary_max,
        salary_raw=result.salary_raw,
        skills=result.skills,
        jd_summary=result.jd_summary,
        jd_full=result.jd_full,
        status=status,
        date_applied=date_applied,
        source_platform=detect_platform(result.url),
        extraction_confidence=result.extraction_confidence,
    )

    # Embed a compact representation of the role for semantic search.
    embed_input = f"{job.role} {job.company} {' '.join(job.skills)} {job.jd_summary}"
    embedding = get_embedding(embed_input)
    get_storage().save(job, embedding)

    # Record the save so rapid double-fires are deduped in-memory for ~60s.
    _recent_urls[request.url] = time.time()

    return job


@app.post("/search", response_model=list[JobApplication])
def search(request: SearchRequest) -> list[JobApplication]:
    """Semantic search over stored applications."""
    embedding = get_embedding(request.query)
    return get_storage().search(
        embedding,
        limit=request.limit,
        status_filter=request.status_filter,
    )


@app.patch("/application/{job_id}", response_model=JobApplication)
def update_application(job_id: str, update: ApplicationUpdate) -> JobApplication:
    """Update the status and/or notes of an existing application."""
    ok = get_storage().update_status(
        job_id,
        status=update.status,
        notes=update.notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Application {job_id!r} not found")

    return get_storage().get(job_id)


@app.get("/export")
def export() -> StreamingResponse:
    """Export all applications as a downloadable CSV."""
    df = get_storage().export_to_dataframe()
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


@app.get("/recent")
def recent(limit: int = Query(10, ge=1)) -> list[dict]:
    """Return the most recently applied-to applications (default 10).

    Backs the panel popup (limit 10) and the full dashboard (``?limit=200``).
    Sorted by ``date_applied`` descending; "saved" captures (no ``date_applied``)
    sort last. Going through ``to_json``/``json.loads`` keeps pandas Timestamps
    and NaT JSON-safe (ISO strings / null).
    """
    df = get_storage().export_to_dataframe()
    df = df.sort_values("date_applied", ascending=False, na_position="last")
    return json.loads(df.head(limit).to_json(orient="records", date_format="iso"))


@app.delete("/application/{job_id}")
def delete_application(job_id: str) -> dict[str, bool]:
    """Delete an application (Qdrant point) by id. Returns ``{"deleted": true}``."""
    storage = get_storage()
    if storage.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Application {job_id!r} not found")
    storage.client.delete(
        collection_name=storage.collection,
        points_selector=[job_id],
    )
    return {"deleted": True}


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness check, including Qdrant connectivity."""
    qdrant_ok = False
    try:
        get_storage().client.get_collections()
        qdrant_ok = True
    except Exception:  # noqa: BLE001 - health check must never raise
        qdrant_ok = False

    return {
        "status": "ok",
        "qdrant_connected": qdrant_ok,
        "primary_model": settings.primary_model,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
