"""
polling.py — Endpoints to control and observe the background scheduler.

ENDPOINTS:
  POST /polling/start   → start the scheduler (or change interval)
  POST /polling/stop    → stop the scheduler
  GET  /polling/status  → is it running? last run? errors?
  GET  /polling/results → all summaries collected so far
  POST /polling/run-now → trigger one poll immediately (useful for testing)
  DELETE /polling/results → clear the in-memory result store
"""

from fastapi import APIRouter, HTTPException, Query
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.polling_service import (
    poll_for_new_emails,
    get_results,
    get_poll_stats,
    clear_results,
)

router = APIRouter()

# --- The scheduler instance ---
# Module-level so it lives for the entire lifetime of the process.
# Only one scheduler exists no matter how many times /start is called.
scheduler = BackgroundScheduler(
    # Timezone-aware scheduling — always use UTC for servers
    timezone="UTC",
    # Prevent job pile-up: if a job is still running when the next tick fires,
    # skip the new tick instead of running two jobs simultaneously
    job_defaults={"coalesce": True, "max_instances": 1},
)

JOB_ID = "email_poll"


@router.post("/start")
def start_polling(
    interval_minutes: int = Query(default=5, ge=1, le=60, description="How often to poll Gmail (1-60 minutes)")
):
    """
    Start the background polling job.

    If already running, replaces the existing job with the new interval.
    Safe to call multiple times — will not create duplicate jobs.
    """
    # Start the scheduler process if it hasn't been started yet
    if not scheduler.running:
        scheduler.start()

    # Remove existing job if present (allows changing the interval)
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)

    # Schedule the poll job on a fixed interval
    # IntervalTrigger fires every N minutes starting from now
    scheduler.add_job(
        func=poll_for_new_emails,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=JOB_ID,
        name="Gmail Email Poller",
        replace_existing=True,
    )

    # Get the next scheduled run time to show in the response
    job = scheduler.get_job(JOB_ID)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "status": "started",
        "interval_minutes": interval_minutes,
        "next_run": next_run,
        "message": f"Polling Gmail every {interval_minutes} minute(s). First run in {interval_minutes} minute(s).",
    }


@router.post("/stop")
def stop_polling():
    """
    Stop the background polling job.
    The scheduler process keeps running (cheap) but no jobs will fire.
    """
    if not scheduler.running or not scheduler.get_job(JOB_ID):
        return {"status": "not_running", "message": "Polling was not active."}

    scheduler.remove_job(JOB_ID)

    return {"status": "stopped", "message": "Polling stopped. Results are still in memory."}


@router.get("/status")
def poll_status():
    """
    Check the current state of the scheduler and the last poll run.
    Use this to monitor the agent's health.
    """
    job = scheduler.get_job(JOB_ID)
    stats = get_poll_stats()

    return {
        "scheduler_running": scheduler.running,
        "polling_active": job is not None,
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        **stats,
    }


@router.post("/run-now")
def run_now(
    max_results: int = Query(default=5, ge=1, le=20, description="Emails to fetch in this run")
):
    """
    Trigger one poll immediately without waiting for the next scheduled tick.

    WHY THIS IS USEFUL:
      - Testing: verify the job works without waiting N minutes
      - Manual catch-up: run immediately after fixing an error
      - Debugging: trigger on demand and watch the logs
    """
    try:
        poll_for_new_emails(max_results=max_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Poll job failed: {str(e)}")

    stats = get_poll_stats()
    return {
        "status": "completed",
        "message": "Manual poll run complete.",
        **stats,
    }


@router.get("/results")
def polling_results(
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    priority: str = Query(default="", description="Filter by priority: high, medium, low"),
    category: str = Query(default="", description="Filter by category: work, security, etc."),
):
    """
    Return email summaries collected by the background poller.

    Supports filtering by priority and category so you can quickly
    surface what matters (e.g., all high-priority emails).
    """
    results = get_results()

    # Apply filters if provided
    if priority:
        results = [r for r in results if r.priority.value == priority.lower()]
    if category:
        results = [r for r in results if r.category.value == category.lower()]

    return {
        "total": len(results),
        "showing": min(limit, len(results)),
        "emails": [r.model_dump() for r in results[:limit]],
    }


@router.delete("/results")
def clear_polling_results():
    """Clear the in-memory result store. Does not affect the poll state file."""
    clear_results()
    return {"status": "cleared", "message": "Result store cleared."}
