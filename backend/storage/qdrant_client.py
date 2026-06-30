"""Qdrant client wrapper for storing and querying job applications."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels

from backend.models import JobApplication

load_dotenv()

# Short-lived in-memory dedup cache: maps a captured URL to the timestamp it was
# last saved. Catches rapid double-fires (within 60s) before they hit Qdrant.
# Populated from backend.main after a successful save.
_recent_urls: dict[str, float] = {}

# Dimensionality of the embedding vectors stored alongside each application.
# Matches the BAAI/bge-small-en-v1.5 model used by the backend (384-dim).
VECTOR_SIZE = 384

# Columns (and their order) used when exporting applications to a spreadsheet.
EXPORT_COLUMNS = [
    "id",
    "company",
    "role",
    "location",
    "salary_min",
    "salary_max",
    "salary_raw",
    "skills",
    "status",
    "source_platform",
    "url",
    "date_applied",
    "last_updated",
    "follow_up_sent",
    "jd_summary",
    "notes",
]


class QdrantStorage:
    """Persistence layer for job applications backed by a Qdrant collection.

    Each application is stored as a single point: the embedding vector plus the
    full :class:`JobApplication` serialized as the point payload.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection: str | None = None,
    ) -> None:
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.collection = collection or os.getenv("QDRANT_COLLECTION", "job_applications")
        self.client = QdrantClient(host=self.host, port=self.port)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(
                    size=VECTOR_SIZE,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def save(self, job: JobApplication, vector: list[float]) -> str:
        """Upsert an application and its embedding. Returns the application id."""
        self.client.upsert(
            collection_name=self.collection,
            points=[
                qmodels.PointStruct(
                    id=job.id,
                    vector=vector,
                    payload=job.model_dump(mode="json"),
                )
            ],
        )
        return job.id

    def url_exists(self, url: str) -> bool:
        """Check if a job with this URL has already been captured."""
        # In-memory short-circuit for the last 60s, to catch rapid double-fires
        # before they reach Qdrant. Stale entries are evicted on access.
        now = time.time()
        if url in _recent_urls:
            if now - _recent_urls[url] < 60:
                return True
            del _recent_urls[url]

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="url",
                        match=qmodels.MatchValue(value=url),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )
        return len(results[0]) > 0

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        status_filter: str | None = None,
    ) -> list[JobApplication]:
        """Semantic search over stored applications, optionally by status."""
        query_filter = None
        if status_filter is not None:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="status",
                        match=qmodels.MatchValue(value=status_filter),
                    )
                ]
            )

        hits = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [JobApplication(**hit.payload) for hit in hits if hit.payload]

    def get(self, job_id: str) -> JobApplication | None:
        """Fetch a single application by id, or ``None`` if it does not exist."""
        points = self.client.retrieve(
            collection_name=self.collection,
            ids=[job_id],
            with_payload=True,
        )
        if not points or not points[0].payload:
            return None
        return JobApplication(**points[0].payload)

    def update_status(
        self,
        job_id: str,
        status: str | None = None,
        notes: str | None = None,
    ) -> bool:
        """Patch the status/notes of an application and bump ``last_updated``.

        Only the provided fields are written. Returns ``False`` if the
        application does not exist.
        """
        if self.get(job_id) is None:
            return False

        payload: dict[str, object] = {
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        if status is not None:
            payload["status"] = status
        if notes is not None:
            payload["notes"] = notes

        self.client.set_payload(
            collection_name=self.collection,
            payload=payload,
            points=[job_id],
        )
        return True

    def mark_followup_sent(self, job_id: str) -> bool:
        """Flag that a follow-up reminder has been sent for an application."""
        if self.get(job_id) is None:
            return False
        self.client.set_payload(
            collection_name=self.collection,
            payload={
                "follow_up_sent": True,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
            points=[job_id],
        )
        return True

    def get_pending_followups(self, after_days: int) -> list[JobApplication]:
        """Return applications still in ``applied`` status, with no follow-up
        sent, that were applied to more than ``after_days`` days ago.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=after_days)
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="status",
                    match=qmodels.MatchValue(value="applied"),
                ),
                qmodels.FieldCondition(
                    key="follow_up_sent",
                    match=qmodels.MatchValue(value=False),
                ),
                qmodels.FieldCondition(
                    key="date_applied",
                    range=qmodels.DatetimeRange(lt=cutoff.isoformat()),
                ),
            ]
        )

        results: list[JobApplication] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            results.extend(JobApplication(**p.payload) for p in points if p.payload)
            if offset is None:
                break
        return results

    def export_to_dataframe(self) -> pd.DataFrame:
        """Export every stored application as a pandas DataFrame."""
        rows: list[dict[str, object]] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                if not point.payload:
                    continue
                job = JobApplication(**point.payload)
                rows.append({col: getattr(job, col) for col in EXPORT_COLUMNS})
            if offset is None:
                break
        return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


# Module-level singleton; created lazily so importing this module never opens a
# connection (keeps tests and the CLI fast when storage isn't needed).
_storage: QdrantStorage | None = None


def get_storage() -> QdrantStorage:
    """Return the shared :class:`QdrantStorage`, instantiating it on first use."""
    global _storage
    if _storage is None:
        _storage = QdrantStorage()
    return _storage
