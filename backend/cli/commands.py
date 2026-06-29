"""Typer-based CLI commands for jobtrack-agent."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="JobTrack Agent — track and search your job applications.")
console = Console()

BASE_URL = "http://localhost:8000"

# Status -> rich color used everywhere a status is rendered.
STATUS_COLORS: dict[str, str] = {
    "applied": "blue",
    "screening": "yellow",
    "interview": "cyan",
    "offer": "green",
    "rejected": "red",
    "ghosted": "dim",
}


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _fmt_date(value: Any) -> str:
    """Render a date/datetime/ISO-string as YYYY-MM-DD."""
    if not value:
        return "—"
    return str(value)[:10]


def _fmt_salary(record: dict[str, Any]) -> str:
    """Render salary, preferring the raw text, then a monthly INR range."""
    raw = record.get("salary_raw")
    if raw:
        return str(raw)
    low, high = record.get("salary_min"), record.get("salary_max")
    if low and high:
        return f"₹{low:,}–{high:,}/mo"
    if low:
        return f"₹{low:,}+/mo"
    return "—"


def _status_cell(status: str | None) -> str:
    """Render a status string wrapped in its rich color markup."""
    if not status:
        return "—"
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def _render_table(records: list[dict[str, Any]], title: str) -> None:
    """Render a list of application records as a rich table."""
    table = Table(title=title, header_style="bold magenta", expand=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Location")
    table.add_column("Salary")
    table.add_column("Status")
    table.add_column("Date Applied")
    table.add_column("Platform")

    for i, r in enumerate(records, start=1):
        table.add_row(
            str(i),
            str(r.get("company") or "—"),
            str(r.get("role") or "—"),
            str(r.get("location") or "—"),
            _fmt_salary(r),
            _status_cell(r.get("status")),
            _fmt_date(r.get("date_applied")),
            str(r.get("source_platform") or "—"),
        )

    if not records:
        console.print("[yellow]No applications found.[/yellow]")
        return
    console.print(table)


# --------------------------------------------------------------------------- #
# Backend access helpers
# --------------------------------------------------------------------------- #
def _api_error(exc: Exception) -> None:
    """Print a friendly API connection error and exit."""
    console.print(
        f"[red]✗ Could not reach the backend at {BASE_URL}.[/red] "
        "[dim]Is it running? (uvicorn backend.main:app)[/dim]"
    )
    console.print(f"[dim]{exc}[/dim]")
    raise typer.Exit(code=1)


def _get_storage():
    """Import and return the storage singleton, exiting cleanly on failure."""
    try:
        from backend.storage.qdrant_client import get_storage

        return get_storage()
    except Exception as exc:  # noqa: BLE001 - surface a single clear message
        console.print(
            "[red]✗ Could not connect to Qdrant storage.[/red] "
            "[dim]Is Qdrant running? (docker compose up -d)[/dim]"
        )
        console.print(f"[dim]{exc}[/dim]")
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def search(
    query: str = typer.Argument(..., help="Free-text search query."),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results."),
) -> None:
    """Semantic search over stored applications (POST /search)."""
    try:
        response = httpx.post(
            f"{BASE_URL}/search",
            json={"query": query, "limit": limit},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]✗ Search failed: {exc.response.status_code}[/red]")
        raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        _api_error(exc)

    _render_table(response.json(), title=f'Search results for "{query}"')


@app.command(name="list")
def list_jobs(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status."),
) -> None:
    """List all stored applications, optionally filtered by status."""
    storage = _get_storage()
    df = storage.export_to_dataframe()
    records = df.to_dict("records")

    if status:
        records = [r for r in records if r.get("status") == status]

    title = "All Applications" if not status else f"Applications — {status}"
    _render_table(records, title=title)


@app.command()
def update(
    job_id: str = typer.Argument(..., help="Application id to update."),
    status: str = typer.Option(None, "--status", help="New status."),
    notes: str = typer.Option(None, "--notes", help="Notes to attach."),
) -> None:
    """Update an application's status and/or notes (PATCH /application/{id})."""
    if status is None and notes is None:
        console.print("[yellow]Nothing to update — pass --status and/or --notes.[/yellow]")
        raise typer.Exit(code=1)

    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if notes is not None:
        payload["notes"] = notes

    try:
        response = httpx.patch(
            f"{BASE_URL}/application/{job_id}",
            json=payload,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        _api_error(exc)

    if response.status_code == 404:
        console.print(f"[red]✗ No application found with id {job_id!r}.[/red]")
        raise typer.Exit(code=1)

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]✗ Update failed: {exc.response.status_code}[/red]")
        raise typer.Exit(code=1)

    job = response.json()
    console.print(
        f"[green]✓ Updated[/green] {job.get('role')} at {job.get('company')} "
        f"→ {_status_cell(job.get('status'))}"
    )


@app.command()
def export(
    format: str = typer.Option("csv", "--format", "-f", help="csv or excel."),
) -> None:
    """Export all applications to a file (GET /export)."""
    fmt = format.lower()
    if fmt not in {"csv", "excel"}:
        console.print("[red]✗ --format must be 'csv' or 'excel'.[/red]")
        raise typer.Exit(code=1)

    try:
        response = httpx.get(f"{BASE_URL}/export", timeout=60.0)
        response.raise_for_status()
    except httpx.RequestError as exc:
        _api_error(exc)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]✗ Export failed: {exc.response.status_code}[/red]")
        raise typer.Exit(code=1)

    today = date.today().isoformat()

    if fmt == "csv":
        out_path = Path.cwd() / f"job_applications_{today}.csv"
        out_path.write_bytes(response.content)
    else:
        # The backend returns CSV; convert to an Excel workbook locally.
        import io

        import pandas as pd

        out_path = Path.cwd() / f"job_applications_{today}.xlsx"
        df = pd.read_csv(io.BytesIO(response.content))
        df.to_excel(out_path, index=False)

    console.print(f"[green]✓ Exported to[/green] {out_path}")


@app.command()
def stats() -> None:
    """Show aggregate statistics across all applications."""
    storage = _get_storage()
    df = storage.export_to_dataframe()
    records = df.to_dict("records")
    total = len(records)

    if total == 0:
        console.print(Panel("[yellow]No applications yet.[/yellow]", title="📊 Stats"))
        return

    # Status breakdown, ordered by the canonical lifecycle.
    status_counts = Counter(r.get("status") for r in records)
    lines: list[str] = [f"[bold]Total applications:[/bold] {total}\n"]
    lines.append("[bold]By status:[/bold]")
    bar_width = 24
    for st in STATUS_COLORS:
        count = status_counts.get(st, 0)
        filled = int((count / total) * bar_width) if total else 0
        color = STATUS_COLORS[st]
        bar = f"[{color}]{'█' * filled}[/{color}]{'░' * (bar_width - filled)}"
        lines.append(f"  {st:<10} {bar} {count}")

    # Top 5 skills across all applications.
    skill_counter: Counter[str] = Counter()
    for r in records:
        skills = r.get("skills") or []
        if isinstance(skills, (list, tuple)):
            skill_counter.update(s for s in skills if s)
    top_skills = skill_counter.most_common(5)
    lines.append("\n[bold]Top skills:[/bold]")
    if top_skills:
        for skill, n in top_skills:
            lines.append(f"  • {skill} ({n})")
    else:
        lines.append("  [dim]none[/dim]")

    # Most active platform.
    platform_counter = Counter(
        r.get("source_platform") for r in records if r.get("source_platform")
    )
    if platform_counter:
        platform, p_count = platform_counter.most_common(1)[0]
        lines.append(f"\n[bold]Most active platform:[/bold] {platform} ({p_count})")
    else:
        lines.append("\n[bold]Most active platform:[/bold] [dim]unknown[/dim]")

    console.print(Panel("\n".join(lines), title="📊 Stats", expand=False))


@app.command()
def reminders() -> None:
    """Trigger the follow-up check and list applications needing a nudge."""
    storage = _get_storage()

    try:
        from backend.config import settings

        after_days = settings.follow_up_after_days
    except Exception:  # noqa: BLE001 - fall back to the documented default
        after_days = 7

    pending = storage.get_pending_followups(after_days)
    if not pending:
        console.print(
            f"[green]✓ No follow-ups needed[/green] "
            f"[dim](nothing older than {after_days} days awaiting a response).[/dim]"
        )
        return

    console.print(
        f"[yellow]⏰ {len(pending)} application(s) need a follow-up "
        f"(applied > {after_days} days ago):[/yellow]"
    )
    _render_table([j.model_dump() for j in pending], title="Follow-ups due")


def main() -> None:
    """Console-script entry point (see pyproject.toml)."""
    app()


if __name__ == "__main__":
    app()
