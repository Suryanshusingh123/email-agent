"""
polling_service.py — Background email polling logic.

THIS FILE HAS TWO RESPONSIBILITIES:
  1. The poll job itself (what runs on a schedule)
  2. An in-memory result store (so the API can read what the job found)

STATE DESIGN DECISION:
  We store results in a module-level list and timestamps in a JSON file.
  - Module-level list: fast to read, lost on restart (acceptable for now)
  - JSON file: survives restarts so we don't re-process old emails

  In production you'd replace both with a database, but this pattern lets
  you understand the fundamentals before adding that complexity.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.email_models import EmailSummary
from app.routers.auth import _load_credentials
from app.services.gmail_service import fetch_emails, label_email_by_summary
from app.services.gemini_service import summarize_email
from app.services.db_service import save_email_summary
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# --- State file ---
# Persists the last-checked timestamp across restarts.
# Without this, every restart would re-process all emails from the beginning.
POLL_STATE_FILE = Path("poll_state.json")

# --- In-memory result store ---
# A simple list that accumulates summaries across poll runs.
# The /polling/results endpoint reads from here.
# Capped at MAX_STORED_RESULTS to prevent unbounded memory growth.
MAX_STORED_RESULTS = 100
_results: list[EmailSummary] = []
_last_poll_time: Optional[datetime] = None
_last_poll_error: Optional[str] = None
_total_processed: int = 0


# --- Public API for the result store ---

def get_results() -> list[EmailSummary]:
    return list(_results)  # return a copy so callers can't mutate our store


def get_poll_stats() -> dict:
    return {
        "last_poll_time": _last_poll_time.isoformat() if _last_poll_time else None,
        "last_poll_error": _last_poll_error,
        "total_processed": _total_processed,
        "results_in_memory": len(_results),
        "last_checked_since": _load_last_checked(),
    }


def clear_results() -> None:
    global _results, _total_processed
    _results = []
    _total_processed = 0


# --- Poll state persistence ---

def _load_last_checked() -> Optional[str]:
    """Load the last-checked timestamp from disk. Returns None if first run."""
    if not POLL_STATE_FILE.exists():
        return None
    try:
        data = json.loads(POLL_STATE_FILE.read_text())
        return data.get("last_checked")
    except Exception:
        return None


def _save_last_checked(timestamp: str) -> None:
    """Persist the last-checked timestamp so we survive restarts."""
    POLL_STATE_FILE.write_text(json.dumps({"last_checked": timestamp}, indent=2))


# --- The poll job ---

def poll_for_new_emails(max_results: int = 10) -> None:
    """
    The function APScheduler calls on every tick.

    DESIGN: this function never raises — it catches all errors and logs them.
    WHY: if the job crashes, APScheduler keeps it scheduled. A crash should
    not kill the scheduler. Logging the error is enough — the next tick will
    try again.

    Gmail query strategy:
      We use Gmail's `after:` search operator to only fetch emails newer than
      our last check. This is more reliable than comparing timestamps ourselves
      because Gmail's search runs server-side — we only download what we need.

    Gmail `after:` format: Unix epoch seconds (e.g., after:1715000000)
    """
    global _last_poll_time, _last_poll_error, _total_processed, _results

    logger.info("Poll job started")
    _last_poll_time = datetime.now(timezone.utc)
    _last_poll_error = None

    # Step 1: Check we have valid credentials before doing anything
    credentials = _load_credentials()
    if not credentials or not credentials.valid:
        msg = "No valid credentials — skipping poll. Visit /auth/login."
        logger.warning(msg)
        _last_poll_error = msg
        return

    # Step 2: Build Gmail query to fetch only new emails
    last_checked = _load_last_checked()
    if last_checked:
        # Gmail's after: operator takes a Unix timestamp
        query = f"after:{last_checked}"
        logger.info("Polling for emails after timestamp %s", last_checked)
    else:
        # First run — fetch the most recent emails as a baseline
        query = ""
        logger.info("First poll run — fetching recent emails as baseline")

    # Step 3: Fetch emails
    try:
        raw_emails = fetch_emails(
            credentials=credentials,
            max_results=max_results,
            query=query,
        )
    except Exception as e:
        _last_poll_error = f"Gmail fetch failed: {str(e)}"
        logger.error(_last_poll_error)
        return

    if not raw_emails:
        logger.info("Poll complete — no new emails found")
        # Still update the timestamp so next poll uses now as the baseline
        _save_last_checked(_unix_now())
        return

    logger.info("Found %d new email(s) — summarizing", len(raw_emails))

    # Step 4: Summarize and label each email
    new_summaries: list[EmailSummary] = []
    for email in raw_emails:
        try:
            summary = summarize_email(email)
            new_summaries.append(summary)

            # Apply Gmail labels based on what the AI determined
            applied = label_email_by_summary(
                credentials=credentials,
                message_id=email.message_id,
                priority=summary.priority.value,
                category=summary.category.value,
                action_required=summary.action_required,
            )
            if applied:
                logger.info("Labeled '%s' with: %s", summary.subject[:50], applied)

            # Persist to database
            db = SessionLocal()
            try:
                save_email_summary(db, summary, applied)
            finally:
                db.close()

        except Exception as e:
            logger.error("Failed to process email %s: %s", email.message_id, str(e))

    # Step 5: Add to result store (cap at MAX_STORED_RESULTS)
    _results = (new_summaries + _results)[:MAX_STORED_RESULTS]
    _total_processed += len(new_summaries)

    # Step 6: Save the current timestamp as the new baseline
    _save_last_checked(_unix_now())

    logger.info(
        "Poll complete — %d email(s) summarized. Total processed: %d",
        len(new_summaries), _total_processed
    )


def _unix_now() -> str:
    """Current time as a Unix epoch string — the format Gmail's after: expects."""
    return str(int(datetime.now(timezone.utc).timestamp()))
