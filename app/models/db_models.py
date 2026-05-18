"""
db_models.py — SQLAlchemy ORM models (database table definitions).

IMPORTANT DISTINCTION:
  email_models.py  → Pydantic models  → shape your API data (HTTP layer)
  db_models.py     → SQLAlchemy models → shape your database rows (DB layer)

They look similar but serve different purposes. Pydantic validates and
serializes. SQLAlchemy maps Python objects to database rows and handles
transactions.

BEGINNER MISTAKE:
  Using the same model for both. Works until you need a field in the API
  that doesn't belong in the DB, or a DB column the API should never expose.
  Keeping them separate gives you full control over both surfaces.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

from app.database import Base


class EmailRecord(Base):
    """
    Maps to the 'emails' table in the database.

    Every attribute decorated with Column() becomes a table column.
    The type (String, Boolean, etc.) maps to the appropriate SQL type
    for whatever database you're using (SQLite or PostgreSQL).

    COLUMN DESIGN DECISIONS:
      - gmail_message_id is UNIQUE — prevents storing the same email twice
        if the poller runs and finds an email it already processed.
        This is idempotency — a critical property for any background job.
      - processed_at is separate from received_at — lets you query
        "emails processed in the last hour" vs "emails received today"
      - key_points stored as Text (JSON string) — storing arrays in SQLite
        requires serialization. PostgreSQL can use a native ARRAY column
        but we keep it simple and compatible here.
    """
    __tablename__ = "emails"

    # Primary key — auto-incrementing integer
    # WHY NOT USE gmail_message_id AS PRIMARY KEY?
    #   Gmail message IDs are strings. Integer PKs are faster to index,
    #   join, and reference. Use the Gmail ID as a unique constraint instead.
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Gmail identifiers
    gmail_message_id = Column(String(64), unique=True, nullable=False, index=True)

    # Email metadata
    sender = Column(String(512), nullable=True)
    subject = Column(String(998), nullable=True)  # 998 = RFC 2822 max subject length
    received_at = Column(String(128), nullable=True)  # raw date string from Gmail

    # AI-generated fields
    summary = Column(Text, nullable=True)
    category = Column(String(32), nullable=True, index=True)  # indexed for filtering
    priority = Column(String(16), nullable=True, index=True)  # indexed for filtering
    action_required = Column(Boolean, default=False, nullable=False)
    action_description = Column(Text, nullable=True)
    key_points = Column(Text, nullable=True)  # JSON-encoded list of strings
    labels_applied = Column(Text, nullable=True)  # JSON-encoded list of label names

    # Draft reply fields
    draft_generated = Column(Boolean, default=False, nullable=False)
    gmail_draft_id = Column(String(128), nullable=True)
    draft_generated_at = Column(DateTime(timezone=True), nullable=True)
    # Tracks which prompt version produced this draft.
    # Increment DRAFT_PROMPT_VERSION in gemini_service.py whenever you change the draft prompt.
    draft_prompt_version = Column(String(16), nullable=True)
    # True = user edited before sending, False = sent as-is, None = not sent yet.
    # This becomes your ground-truth quality signal for prompt evaluation.
    draft_edited_before_send = Column(Boolean, nullable=True)

    # System timestamps
    processed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<EmailRecord id={self.id} subject='{self.subject[:30]}...' priority={self.priority}>"
