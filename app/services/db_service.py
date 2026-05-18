"""
db_service.py — All database read/write operations.

WHY A DEDICATED SERVICE FOR DB OPERATIONS?
  The polling service decides WHAT to do (fetch, summarize, label).
  This service decides HOW to persist it.
  Separating them means you can swap the database layer without
  touching the business logic, and vice versa.
"""

import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.db_models import EmailRecord
from app.models.email_models import EmailSummary

logger = logging.getLogger(__name__)


def save_email_summary(db: Session, summary: EmailSummary, labels_applied: list) -> EmailRecord:
    """
    Persist an EmailSummary to the database.

    IDEMPOTENCY:
      We check if the gmail_message_id already exists before inserting.
      This means running the poll twice on the same emails is safe —
      the second run updates the existing record instead of duplicating it.
      Idempotency is a required property of any background job.
    """
    existing = db.query(EmailRecord).filter_by(
        gmail_message_id=summary.message_id
    ).first()

    if existing:
        # Update the existing record — summary may have improved on retry
        existing.summary = summary.summary
        existing.category = summary.category.value
        existing.priority = summary.priority.value
        existing.action_required = summary.action_required
        existing.action_description = summary.action_description
        existing.key_points = json.dumps(summary.key_points)
        existing.labels_applied = json.dumps(labels_applied)
        db.commit()
        logger.info("Updated existing record for message %s", summary.message_id)
        return existing

    record = EmailRecord(
        gmail_message_id=summary.message_id,
        sender=summary.sender,
        subject=summary.subject,
        received_at=summary.date,
        summary=summary.summary,
        category=summary.category.value,
        priority=summary.priority.value,
        action_required=summary.action_required,
        action_description=summary.action_description,
        key_points=json.dumps(summary.key_points),
        labels_applied=json.dumps(labels_applied),
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Saved new email record id=%d subject='%s'", record.id, (record.subject or "")[:50])
    return record


def get_email_history(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    priority: str = None,
    category: str = None,
    action_required: bool = None,
) -> tuple:
    """
    Query stored email summaries with optional filtering and pagination.

    Returns (records, total_count) so the API can include pagination metadata.

    WHY OFFSET PAGINATION?
      Simple to implement and understand. For large datasets you'd switch
      to cursor-based pagination (using the last seen ID), but offset is
      correct for hundreds or thousands of rows.
    """
    query = db.query(EmailRecord)

    if priority:
        query = query.filter(EmailRecord.priority == priority.lower())
    if category:
        query = query.filter(EmailRecord.category == category.lower())
    if action_required is not None:
        query = query.filter(EmailRecord.action_required == action_required)

    total = query.count()
    records = query.order_by(desc(EmailRecord.processed_at)).offset(offset).limit(limit).all()

    return records, total


def get_email_stats(db: Session) -> dict:
    """
    Aggregate statistics across all stored emails.
    Used for the analytics/dashboard endpoint.
    """
    total = db.query(EmailRecord).count()

    if total == 0:
        return {"total": 0}

    # Count by priority
    from sqlalchemy import func
    priority_counts = dict(
        db.query(EmailRecord.priority, func.count(EmailRecord.id))
        .group_by(EmailRecord.priority)
        .all()
    )

    # Count by category
    category_counts = dict(
        db.query(EmailRecord.category, func.count(EmailRecord.id))
        .group_by(EmailRecord.category)
        .all()
    )

    action_required_count = db.query(EmailRecord).filter_by(action_required=True).count()

    # Draft quality telemetry
    from sqlalchemy import func
    drafts_generated = db.query(EmailRecord).filter_by(draft_generated=True).count()
    drafts_sent_as_is = db.query(EmailRecord).filter_by(draft_edited_before_send=False).count()
    drafts_edited = db.query(EmailRecord).filter_by(draft_edited_before_send=True).count()

    # Approval rate: drafts sent without edits / total drafts with feedback
    drafts_with_feedback = drafts_sent_as_is + drafts_edited
    approval_rate = round(drafts_sent_as_is / drafts_with_feedback, 2) if drafts_with_feedback > 0 else None

    # Quality breakdown by prompt version
    version_stats = dict(
        db.query(EmailRecord.draft_prompt_version, func.count(EmailRecord.id))
        .filter(EmailRecord.draft_generated.is_(True))
        .filter(EmailRecord.draft_prompt_version.isnot(None))
        .group_by(EmailRecord.draft_prompt_version)
        .all()
    )

    return {
        "total": total,
        "by_priority": priority_counts,
        "by_category": category_counts,
        "action_required": action_required_count,
        "draft_telemetry": {
            "drafts_generated": drafts_generated,
            "drafts_sent_as_is": drafts_sent_as_is,
            "drafts_edited": drafts_edited,
            "approval_rate": approval_rate,
            "by_prompt_version": version_stats,
        },
    }


def record_to_dict(record: EmailRecord) -> dict:
    """Convert an EmailRecord ORM object to a plain dict for API responses."""
    return {
        "id": record.id,
        "gmail_message_id": record.gmail_message_id,
        "sender": record.sender,
        "subject": record.subject,
        "received_at": record.received_at,
        "summary": record.summary,
        "category": record.category,
        "priority": record.priority,
        "action_required": record.action_required,
        "action_description": record.action_description,
        "key_points": json.loads(record.key_points) if record.key_points else [],
        "labels_applied": json.loads(record.labels_applied) if record.labels_applied else [],
        "processed_at": record.processed_at.isoformat() if record.processed_at else None,
        "draft_generated": record.draft_generated,
        "gmail_draft_id": record.gmail_draft_id,
        "draft_generated_at": record.draft_generated_at.isoformat() if record.draft_generated_at else None,
    }
