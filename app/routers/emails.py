"""
emails.py — Email fetch and summarization endpoints.

This router is the orchestrator:
  1. Verify auth
  2. Fetch emails (gmail_service)
  3. Summarize each email (gemini_service)
  4. Return structured response

The router itself has NO business logic. It only orchestrates calls
to services and shapes the HTTP response.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.routers.auth import get_valid_credentials
from app.services.gmail_service import fetch_emails, create_gmail_draft
from app.services.gemini_service import summarize_email, generate_reply_draft, VALID_TONES
from app.models.email_models import EmailSummaryResponse, RawEmail
from app.models.db_models import EmailRecord
from app.database import get_db

router = APIRouter()


@router.get("/summarize", response_model=None)
async def summarize_emails(
    max_results: int = Query(default=5, ge=1, le=20, description="Number of emails to fetch (1-20)"),
    query: str = Query(default="", description="Gmail search query, e.g. 'is:unread' or 'from:boss@company.com'"),
    skip_ai: bool = Query(default=False, description="Return raw emails only, skip Gemini summarization"),
):
    """
    Fetch emails from Gmail and summarize them using Gemini.

    - **max_results**: How many emails to process (keep low in dev to save quota)
    - **query**: Gmail search syntax — same as the Gmail search bar
    - **skip_ai**: Set true to test Gmail fetching without calling Gemini
    """
    # Step 1: Get valid credentials (raises 401 if not authenticated)
    credentials = get_valid_credentials()

    # Step 2: Fetch raw emails from Gmail
    try:
        raw_emails: list[RawEmail] = fetch_emails(
            credentials=credentials,
            max_results=max_results,
            query=query,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not raw_emails:
        return EmailSummaryResponse(success=True, total=0, emails=[])

    # Step 3 (optional skip): Return raw emails for debugging
    if skip_ai:
        return {
            "success": True,
            "total": len(raw_emails),
            "emails": [
                {
                    "message_id": e.message_id,
                    "subject": e.subject,
                    "sender": e.sender,
                    "date": e.date,
                    "snippet": e.snippet,
                    "body_preview": (e.body or "")[:300],
                }
                for e in raw_emails
            ],
        }

    # Step 4: Summarize each email with Gemini
    # WHY NOT ASYNC HERE?
    #   google-generativeai's Python SDK is synchronous.
    #   For now we process emails sequentially — simple and correct.
    #   Phase 6 will introduce concurrent processing with asyncio.gather()
    #   once you understand why it matters.
    summaries = []
    for email in raw_emails:
        summary = summarize_email(email)
        summaries.append(summary)

    # Step 5: Return structured response
    return EmailSummaryResponse(
        success=True,
        total=len(summaries),
        emails=summaries,
    )


@router.get("/raw", response_model=None)
async def get_raw_emails(
    max_results: int = Query(default=3, ge=1, le=10),
    query: str = Query(default=""),
):
    """
    Fetch raw emails without any AI processing.
    Useful for debugging Gmail API responses and seeing what data we get.
    """
    credentials = get_valid_credentials()

    try:
        raw_emails = fetch_emails(credentials=credentials, max_results=max_results, query=query)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "total": len(raw_emails),
        "emails": [e.model_dump() for e in raw_emails],
    }


@router.post("/{gmail_message_id}/draft")
def generate_draft(
    gmail_message_id: str,
    tone: str = Query(default="professional", description=f"Reply tone: {', '.join(VALID_TONES)}"),
    instructions: Optional[str] = Query(default=None, description="Optional freeform instructions for the AI (e.g. 'mention I'll be out next week')"),
    db: Session = Depends(get_db),
):
    """
    Generate an AI reply draft and save it directly to Gmail Drafts.

    Flow:
      1. Load the email summary from our DB (already processed by Gemini)
      2. Send summary to Gemini → get draft reply text
      3. Create the draft in Gmail via the API
      4. Update the DB record with draft_id
      5. Return the draft_id and a direct Gmail URL

    WHY LOAD FROM DB INSTEAD OF RE-FETCHING FROM GMAIL?
      We already have the structured summary (category, key points, action).
      This is richer context for drafting than the raw email.
      It's also faster — no Gmail API call needed for the content.
    """
    # Load from DB
    record = db.query(EmailRecord).filter_by(gmail_message_id=gmail_message_id).first()
    if not record:
        raise HTTPException(
            status_code=404,
            detail="Email not found. Make sure it has been processed by the poller first."
        )

    # Validate tone — fall back to professional rather than 400-erroring
    safe_tone = tone.lower() if tone.lower() in VALID_TONES else "professional"

    # Get valid OAuth credentials
    credentials = get_valid_credentials()

    # Generate draft text with Gemini
    import json
    key_points = json.loads(record.key_points) if record.key_points else []

    try:
        draft_text, prompt_version = generate_reply_draft(
            subject=record.subject or "",
            sender=record.sender or "",
            summary=record.summary or "",
            key_points=key_points,
            action_description=record.action_description,
            tone=safe_tone,
            user_instructions=instructions,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Draft generation failed: {str(e)}")

    # Create the draft in Gmail
    try:
        result = create_gmail_draft(
            credentials=credentials,
            reply_to_sender=record.sender or "",
            original_subject=record.subject or "",
            draft_body=draft_text,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Gmail draft creation failed: {str(e)}")

    # Update DB record
    record.draft_generated = True
    record.gmail_draft_id = result["draft_id"]
    record.draft_generated_at = datetime.now(timezone.utc)
    record.draft_prompt_version = prompt_version
    db.commit()

    return {
        "success": True,
        "draft_id": result["draft_id"],
        "gmail_url": result["gmail_url"],
        "draft_preview": draft_text[:300],
        "message": "Draft saved to Gmail. Open Gmail Drafts to review and send.",
    }


@router.post("/{gmail_message_id}/draft/feedback")
def record_draft_feedback(
    gmail_message_id: str,
    edited: bool,
    db: Session = Depends(get_db),
):
    """
    Record whether the user edited the draft before sending.

    Call this from the Flutter app after the user sends their reply:
      edited=true  → user rewrote the draft (prompt needs work)
      edited=false → user sent as-is (prompt is working well)

    This creates the ground-truth quality signal that makes
    draft_prompt_version actually useful for comparison.

    In the Flutter app, you'd show a quick "Did you edit the draft?"
    prompt after the user returns from Gmail, then call this endpoint.
    """
    record = db.query(EmailRecord).filter_by(gmail_message_id=gmail_message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Email not found.")
    if not record.draft_generated:
        raise HTTPException(status_code=400, detail="No draft has been generated for this email.")

    record.draft_edited_before_send = edited
    db.commit()

    return {
        "success": True,
        "gmail_message_id": gmail_message_id,
        "draft_edited_before_send": edited,
        "prompt_version": record.draft_prompt_version,
    }
