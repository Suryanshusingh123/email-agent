"""
email_models.py — Pydantic data models (your data contracts).

WHY PYDANTIC MODELS:
  They serve three jobs simultaneously:
  1. Validation: If `priority` isn't one of the valid values, Pydantic rejects it.
  2. Serialization: .model_dump() gives you a clean dict; FastAPI auto-serializes
     these to JSON in responses.
  3. Documentation: FastAPI reads these models and generates your Swagger docs
     automatically. No extra work.

BEGINNER MISTAKE:
  Using plain dicts everywhere. Dicts have no validation, no autocomplete,
  no docs generation, and bugs hide silently. Models make bugs loud and early.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Priority(str, Enum):
    """
    Using an Enum instead of raw strings prevents typos.
    "hig" and "HIGH" and "High" are all possible with raw strings.
    With an Enum, only these exact values are valid.
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    """Email category options Gemini will choose from."""
    WORK = "work"
    PERSONAL = "personal"
    NEWSLETTER = "newsletter"
    PROMOTIONAL = "promotional"
    FINANCE = "finance"
    SECURITY = "security"
    SOCIAL = "social"
    OTHER = "other"


class RawEmail(BaseModel):
    """
    The raw data we pull from Gmail before any processing.
    Optional fields because not every email has every field.
    """
    message_id: str
    subject: Optional[str] = "No Subject"
    sender: Optional[str] = "Unknown Sender"
    recipient: Optional[str] = None
    date: Optional[str] = None
    body: Optional[str] = ""
    snippet: Optional[str] = ""  # Gmail's auto-generated preview


class EmailSummary(BaseModel):
    """
    The structured output we return after Gemini processes an email.
    This is the core value your agent produces.
    """
    message_id: str
    subject: str
    sender: str
    date: Optional[str] = None

    # AI-generated fields
    summary: str = Field(description="2-3 sentence summary of the email")
    category: Category = Field(description="Email category")
    priority: Priority = Field(description="Priority level")
    action_required: bool = Field(description="Whether the email requires action")
    action_description: Optional[str] = Field(
        default=None,
        description="What action is needed, if any"
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Bullet points of key information"
    )


class EmailSummaryResponse(BaseModel):
    """
    The top-level API response wrapper.

    WHY A WRAPPER?
    Wrapping responses lets you add metadata (total count, page info,
    request_id for tracing) without changing the inner EmailSummary shape.
    This is a production pattern — your API consumers thank you later.
    """
    success: bool = True
    total: int
    emails: list[EmailSummary]
