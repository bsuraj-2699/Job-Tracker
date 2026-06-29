# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (Python 3.12)
pip install -r requirements.txt
pip install -e .                      # makes the `jobtrack` CLI available

# Infrastructure
docker compose up -d                  # Qdrant on 6333 (REST) / 6334 (gRPC), volume: qdrant_storage

# Run the backend (also starts the reminder scheduler via lifespan)
uvicorn backend.main:app --reload     # http://localhost:8000

# CLI (either form)
jobtrack <command>
python -m backend.cli.commands <command>
```

There is **no test suite and no linter configured** yet — don't assume `pytest`/`ruff`
exist. All imports are absolute (`from backend...`), so commands must run from the repo
root with `backend` importable as a package.

## Architecture

The data flow is: **browser extension → `/capture` → extractor (Groq) → embed → Qdrant**,
then the **CLI** reads it back. The pieces that require reading several files to understand:

### CLI has two data paths (important)
`backend/cli/commands.py` does **not** go through the API uniformly:
- `search`, `update`, `export` → HTTP calls to the running FastAPI server (`httpx`).
- `list`, `stats`, `reminders` → call `get_storage()` / the scheduler logic **directly**.

Consequence: `list`/`stats`/`reminders` need Qdrant up but **not** the uvicorn server,
while the other three need the server running. There is intentionally no "list all" or
"stats" HTTP endpoint — those reads use `QdrantStorage.export_to_dataframe()`.

### Embedding dimension is load-bearing
Embeddings are `sentence-transformers/all-MiniLM-L6-v2` → **384-dim**. The Qdrant
collection is created with `VECTOR_SIZE = 384` in `backend/storage/qdrant_client.py`.
`_ensure_collection()` only creates the collection **if it doesn't already exist**, so
changing the model/dimension requires dropping the `qdrant_storage` volume (or the
collection) to recreate it — otherwise inserts fail with a dimension mismatch.

### Extraction fallback ladder
`backend/extraction/extractor.py` runs `PRIMARY_MODEL` (Llama 3.3 70B) first, then re-runs with
`FALLBACK_MODEL` (GPT-OSS 120B) when `extraction_confidence < 0.6` **or** `len(missing_fields) > 2`,
setting `used_fallback=True`. Models are wired via `ChatGroq(...).with_structured_output(ExtractionResult)`.

### Storage = Qdrant payloads, not a relational store
Each application is one Qdrant point: the 384-d vector + the full `JobApplication` as the
payload (`job.model_dump(mode="json")`). Reads reconstruct with `JobApplication(**payload)`.
`get_pending_followups()` filters server-side using a `DatetimeRange` over the ISO
`date_applied` string plus `status == "applied"` and `follow_up_sent == False`.

### Reminders
The scheduler is started/stopped by the FastAPI **lifespan** in `backend/main.py`, running
`check_followups()` on an `IntervalTrigger(hours=REMINDER_CHECK_INTERVAL_HOURS)` — the first
run is one interval after startup, not immediate. `jobtrack reminders` triggers an on-demand
check. Note: follow-ups are marked via `storage.mark_followup_sent(id)`, **not**
`update_status()` (which only writes `status`/`notes`/`last_updated`).

### Models (`backend/models.py`)
`ApplicationStatus` is a shared `Literal` reused across `JobApplication`, `SearchRequest`,
and `ApplicationUpdate`. `ExtractionResult` is the LLM's pre-persistence shape (adds
`missing_fields`, `used_fallback`; omits id/timestamps/status/notes). `detect_platform(url)`
is a standalone domain matcher. Timestamps are timezone-aware UTC (`datetime.now(timezone.utc)`).

## Conventions

- **Lazy singletons**: `get_storage()`, `get_extractor()`, `get_embeddings()` defer all
  connections / model loading to first use, so importing any module is side-effect free
  (no Qdrant connection, no model download, no API key required just to import).
- Config is centralized in `backend/config.py` via `pydantic-settings` (`settings` instance);
  some modules also read `os.getenv` directly with the same `.env` defaults.
- CORS uses `allow_credentials=False` so the `allow_origins=["*"]` wildcard stays valid.
