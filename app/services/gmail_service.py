"""
gmail_service.py — All Gmail API interactions live here.

WHY A SERVICE LAYER?
  The router's job is HTTP (parse request, return response).
  The service's job is business logic (talk to Gmail).
  Keeping them separate means:
    - If Gmail changes their API, you fix one file, not five.
    - You can test the Gmail logic without spinning up HTTP.
    - The router stays thin and readable.

BEGINNER MISTAKE:
  Writing API calls directly in endpoint functions. Works fine at first,
  then becomes untestable spaghetti as the project grows.
"""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
import base64
import email as email_lib
import logging
import re
from email.mime.text import MIMEText
from typing import Optional, List

from app.models.email_models import RawEmail

logger = logging.getLogger(__name__)

# --- Label name constants ---
# Defined here so polling_service imports from one place.
# Gmail supports nested labels using "/" — "AI/High Priority" appears as
# a sub-label under "AI" in the Gmail sidebar.
LABEL_HIGH_PRIORITY = "AI/High Priority"
LABEL_ACTION_REQUIRED = "AI/Action Required"
LABEL_SECURITY = "AI/Security"

# In-process cache: label name → Gmail label ID
# Gmail labels have opaque IDs like "Label_123456789".
# We fetch/create them once per process and cache to avoid redundant API calls.
_label_cache: dict = {}


def build_gmail_client(credentials: Credentials):
    """
    Build the Gmail API client object.

    'build()' from google-api-python-client uses a discovery document
    (fetched from Google) to construct a typed API client. The result
    is an object with methods like:
      service.users().messages().list(...)
      service.users().messages().get(...)

    This is Google's pattern — not our invention. Understanding it
    means you can use ANY Google API (Calendar, Drive, Sheets) the same way.
    """
    return build("gmail", "v1", credentials=credentials)


def fetch_emails(credentials: Credentials, max_results: int = 10, query: str = "") -> list[RawEmail]:
    """
    Fetch emails from Gmail and return them as RawEmail objects.

    Args:
        credentials: Valid OAuth credentials (from auth.py)
        max_results: How many emails to fetch (keep low in dev)
        query: Gmail search query. Same syntax as the Gmail search bar.
               Examples: "is:unread", "from:boss@company.com", "subject:invoice"

    Returns:
        List of RawEmail objects with subject, sender, body extracted.

    ARCHITECTURE NOTE:
        Gmail's API works in two steps:
        Step 1: messages.list() → returns a list of message IDs (no content)
        Step 2: messages.get(id) → returns the actual email for each ID

        This is by design — listing is cheap, fetching full content costs quota.
        We only pay the cost for emails we actually want.
    """
    service = build_gmail_client(credentials)
    raw_emails: list[RawEmail] = []

    try:
        # Step 1: Get list of message IDs
        # userId="me" is Gmail API's way of saying "the authenticated user"
        list_response = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q=query,  # empty string = no filter, returns all
        ).execute()

        messages = list_response.get("messages", [])

        if not messages:
            return []

        # Step 2: Fetch full content for each message ID
        for message_ref in messages:
            message_id = message_ref["id"]

            # format="full" gives us headers + body
            # format="metadata" gives headers only (faster but no body)
            raw_message = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()

            parsed = _parse_message(raw_message)
            raw_emails.append(parsed)

    except HttpError as e:
        # HttpError is Gmail API's specific error type.
        # Re-raise as a more descriptive exception — the router will catch this.
        raise RuntimeError(f"Gmail API error {e.resp.status}: {e.error_details}")

    return raw_emails


def _parse_message(message: dict) -> RawEmail:
    """
    Convert a raw Gmail API message dict into a clean RawEmail object.

    WHY THIS IS ITS OWN FUNCTION:
      Gmail's message format is... verbose. Headers are a list of
      {"name": "Subject", "value": "..."} dicts. Body is base64-encoded.
      This function isolates that complexity so the rest of the code
      never has to know about it.

    Gmail message structure (simplified):
      {
        "id": "abc123",
        "snippet": "Hey, can we talk about...",
        "payload": {
          "headers": [{"name": "Subject", "value": "..."}, ...],
          "body": {"data": "<base64-encoded content>"},
          "parts": [...]   ← for multipart emails (HTML + text + attachments)
        }
      }
    """
    message_id = message["id"]
    snippet = message.get("snippet", "")
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    # Headers is a list of dicts — we convert it to a simple dict for easy lookup
    header_map = {h["name"].lower(): h["value"] for h in headers}

    subject = header_map.get("subject", "No Subject")
    sender = header_map.get("from", "Unknown Sender")
    recipient = header_map.get("to", None)
    date = header_map.get("date", None)

    # Extract the body text — this is the complex part
    body = _extract_body(payload)

    return RawEmail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        recipient=recipient,
        date=date,
        body=body,
        snippet=snippet,
    )


def _extract_body(payload: dict) -> str:
    """
    Extract readable text from a Gmail message payload.

    WHY THIS IS HARD:
      Emails can be structured in multiple ways:
      1. Simple: body is directly in payload.body.data (base64 encoded)
      2. Multipart: body is split into parts (text/plain + text/html + attachments)
      3. Nested multipart: parts can contain sub-parts

    We prefer text/plain over text/html because:
      - text/plain is already readable
      - text/html has tags like <div>, <span> etc. that pollute the AI prompt

    BEGINNER MISTAKE:
      Just decoding the HTML version and sending it to the AI.
      The AI has to "see through" hundreds of HTML tags to find the content.
      Clean text = better summaries.
    """
    body_text = ""

    # Check if body is directly in the payload (simple emails)
    if payload.get("body", {}).get("data"):
        body_text = _decode_base64(payload["body"]["data"])

    # Check multipart emails
    elif "parts" in payload:
        body_text = _extract_from_parts(payload["parts"])

    return body_text.strip()


def _extract_from_parts(parts: list) -> str:
    """Recursively search multipart email parts for text/plain content."""
    text_plain = ""
    text_html = ""

    for part in parts:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")

        if mime_type == "text/plain" and data:
            text_plain = _decode_base64(data)

        elif mime_type == "text/html" and data:
            text_html = _decode_base64(data)

        # Recursively handle nested multipart parts
        elif "parts" in part:
            nested = _extract_from_parts(part["parts"])
            if nested:
                text_plain = nested

    # Prefer plain text; fall back to HTML (we'll strip tags minimally)
    return text_plain or _strip_html_basic(text_html)


def _decode_base64(data: str) -> str:
    """
    Gmail encodes message bodies in URL-safe base64.

    URL-safe base64 uses - and _ instead of + and /
    Python's base64 module needs padding (=) to be correct length.
    Both of these quirks catch beginners off-guard.
    """
    # Add padding if needed (base64 strings must be multiples of 4 chars)
    padded = data + "=" * (4 - len(data) % 4)
    decoded_bytes = base64.urlsafe_b64decode(padded)
    return decoded_bytes.decode("utf-8", errors="replace")


def _strip_html_basic(html: str) -> str:
    """
    Very basic HTML tag removal — not a full parser.

    We use Python's email library's parser trick here.
    For production you'd use beautifulsoup4, but we're keeping
    dependencies minimal for now.
    """
    import re
    # Remove script and style blocks entirely
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining HTML tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Collapse multiple spaces/newlines
    html = re.sub(r"\s+", " ", html)
    return html.strip()


# ---------------------------------------------------------------------------
# Label management — requires gmail.modify scope
# ---------------------------------------------------------------------------

def get_or_create_label(service, label_name: str) -> str:
    """
    Return the Gmail label ID for label_name, creating the label if needed.

    WHY THIS PATTERN (get-or-create)?
      Gmail labels are identified by opaque IDs, not names.
      You can't apply a label by name — you need its ID.
      Rather than requiring users to pre-create labels manually,
      we create them automatically on first use.

    The in-process cache (_label_cache) means we only call the API once
    per label per process lifetime. Cheap and simple.
    """
    if label_name in _label_cache:
        return _label_cache[label_name]

    # Fetch all existing labels and look for a match
    response = service.users().labels().list(userId="me").execute()
    for label in response.get("labels", []):
        if label["name"] == label_name:
            _label_cache[label_name] = label["id"]
            return label["id"]

    # Label doesn't exist — create it
    # Gmail renders labels with "/" as nested: "AI" → "High Priority"
    created = service.users().labels().create(
        userId="me",
        body={
            "name": label_name,
            "labelListVisibility": "labelShow",       # show in sidebar
            "messageListVisibility": "show",          # show on messages
        },
    ).execute()

    label_id = created["id"]
    _label_cache[label_name] = label_id
    logger.info("Created Gmail label '%s' with ID %s", label_name, label_id)
    return label_id


def apply_labels_to_message(service, message_id: str, label_ids: List[str]) -> None:
    """
    Apply one or more labels to a Gmail message.

    Uses messages.modify() which takes addLabelIds and removeLabelIds.
    We only add — never remove existing labels.
    Silently ignores messages that no longer exist (deleted between fetch and label).
    """
    if not label_ids:
        return

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": label_ids},
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            logger.warning("Message %s not found when applying labels — skipping", message_id)
        else:
            raise


def label_email_by_summary(credentials: Credentials, message_id: str, priority: str, category: str, action_required: bool) -> List[str]:
    """
    Decide which labels to apply based on the AI summary, then apply them.

    LABEL STRATEGY:
      high priority          → "AI/High Priority"
      action_required=True   → "AI/Action Required"
      category=security      → "AI/Security"

    Returns the list of label names that were applied (for logging/response).

    WHY THE DECISION LOGIC LIVES HERE AND NOT IN POLLING:
      The service layer owns all Gmail interactions including the business
      rules about what labels mean. The polling layer just calls this function
      and doesn't need to know the Gmail API details.
    """
    service = build_gmail_client(credentials)
    labels_to_apply = []

    if priority == "high":
        labels_to_apply.append(LABEL_HIGH_PRIORITY)

    if action_required:
        labels_to_apply.append(LABEL_ACTION_REQUIRED)

    if category == "security":
        labels_to_apply.append(LABEL_SECURITY)

    if not labels_to_apply:
        return []

    label_ids = [get_or_create_label(service, name) for name in labels_to_apply]
    apply_labels_to_message(service, message_id, label_ids)

    logger.info("Applied labels %s to message %s", labels_to_apply, message_id)
    return labels_to_apply


# ---------------------------------------------------------------------------
# Draft creation — requires gmail.modify scope (already granted)
# ---------------------------------------------------------------------------

def extract_email_address(sender_string: str) -> str:
    """
    Extract the raw email address from a sender string like 'John <john@example.com>'.
    Falls back to the full string if no angle-bracket format is found.
    """
    match = re.search(r"<([^>]+)>", sender_string)
    return match.group(1) if match else sender_string.strip()


def create_gmail_draft(
    credentials,
    reply_to_sender: str,
    original_subject: str,
    draft_body: str,
) -> dict:
    """
    Create a draft reply in the authenticated user's Gmail account.

    HOW GMAIL DRAFTS WORK:
      A draft is just a message stored under the DRAFT label.
      We construct a MIME email (the standard email format), encode it
      as URL-safe base64, and send it to drafts.create().
      Gmail stores it — the user sees it in their Drafts folder immediately.

    MIME (Multipurpose Internet Mail Extensions):
      The standard format for email. Even plain text emails are MIME.
      MIMEText('hello', 'plain') creates a text/plain MIME message.
      We could use 'html' for rich formatting, but plain text is safer
      and more universally readable.

    Returns a dict with the draft_id and a direct Gmail URL.
    """
    service = build_gmail_client(credentials)

    to_address = extract_email_address(reply_to_sender)
    subject = original_subject if original_subject.startswith("Re:") else f"Re: {original_subject}"

    # Build the MIME message
    message = MIMEText(draft_body, "plain", "utf-8")
    message["to"] = to_address
    message["subject"] = subject

    # Gmail API requires the message encoded as URL-safe base64
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw}},
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Gmail drafts.create failed ({e.resp.status}): {e.error_details}")

    draft_id = draft["id"]
    logger.info("Created Gmail draft id=%s for reply to '%s'", draft_id, original_subject[:50])

    return {
        "draft_id": draft_id,
        # Deep link opens directly to the draft in Gmail web
        "gmail_url": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}",
    }
