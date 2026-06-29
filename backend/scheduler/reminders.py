"""Schedule and dispatch follow-up reminders for job applications."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from rich.console import Console

from backend.storage.qdrant_client import get_storage

load_dotenv()

logger = logging.getLogger(__name__)
console = Console()

REMINDER_CHECK_INTERVAL_HOURS = int(os.getenv("REMINDER_CHECK_INTERVAL_HOURS", "24"))
FOLLOW_UP_AFTER_DAYS = int(os.getenv("FOLLOW_UP_AFTER_DAYS", "7"))


def check_followups() -> int:
    """Find applications awaiting a follow-up, remind, and mark them sent.

    Returns the number of reminders triggered.
    """
    storage = get_storage()
    pending = storage.get_pending_followups(after_days=FOLLOW_UP_AFTER_DAYS)

    now = datetime.now(timezone.utc)
    triggered = 0
    for job in pending:
        applied = job.date_applied
        if applied.tzinfo is None:
            # Treat naive timestamps as UTC so the subtraction is valid.
            applied = applied.replace(tzinfo=timezone.utc)
        days_ago = (now - applied).days

        console.print(
            f"[yellow]⏰ Follow up:[/yellow] [bold]{job.role}[/bold] at "
            f"[bold]{job.company}[/bold] — applied {days_ago} days ago · "
            f"[dim]{job.url}[/dim]"
        )

        # Flip follow_up_sent so this application isn't reminded again.
        storage.mark_followup_sent(job.id)
        triggered += 1

    logger.info("Follow-up check complete: %d reminder(s) triggered.", triggered)
    return triggered


def start_scheduler() -> BackgroundScheduler:
    """Start a background scheduler that periodically checks for follow-ups."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_followups,
        trigger=IntervalTrigger(hours=REMINDER_CHECK_INTERVAL_HOURS),
        id="followup_check",
        name="Follow-up reminder check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Reminder scheduler started (interval: every %d hour(s)).",
        REMINDER_CHECK_INTERVAL_HOURS,
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler) -> None:
    """Gracefully shut down the scheduler."""
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Reminder scheduler stopped.")
