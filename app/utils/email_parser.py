"""
email_parser.py — Pure utility functions for cleaning email text.

WHY "PURE" FUNCTIONS?
  Every function here takes input and returns output with no side effects —
  no API calls, no file I/O, no global state. This makes them:
    - Easy to unit test (no mocks needed)
    - Safe to call anywhere without surprises
    - Reusable across the codebase

BEGINNER MISTAKE:
  Skipping this layer and sending raw email bodies to the AI.
  You get summaries of HTML tags and MIME headers instead of email content.
"""

import re
import quopri
from app.models.email_models import RawEmail


def clean_email_body(text: str) -> str:
    """
    Remove noise from email body text so the AI sees only real content.

    Applies a pipeline of cleaning steps in order. Each step handles
    a specific type of noise commonly found in email bodies.
    """
    if not text:
        return ""

    # Decode quoted-printable encoding (=C3=A9 → é, =20 → space, etc.)
    # Some email clients encode text this way instead of UTF-8
    try:
        text = quopri.decodestring(text.encode()).decode("utf-8", errors="replace")
    except Exception:
        pass  # If decoding fails, use the original text

    # Remove MIME boundaries (--abc123boundary--)
    text = re.sub(r"--[a-zA-Z0-9_\-]+(\s|$)", " ", text)

    # Remove inline image/attachment references like [image: logo.png]
    text = re.sub(r"\[image:[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[cid:[^\]]*\]", "", text, flags=re.IGNORECASE)

    # Remove URLs (they add noise; the AI can't visit them anyway)
    text = re.sub(r"https?://\S+", "[link]", text)

    # Remove email headers that sometimes bleed into body text
    text = re.sub(r"^(From|To|Cc|Bcc|Date|Subject|Reply-To):.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove legal disclaimers and confidentiality footers (common patterns)
    disclaimer_patterns = [
        r"this email.*?confidential.*?(?=\n\n|\Z)",
        r"disclaimer:.*?(?=\n\n|\Z)",
        r"this message.*?intended.*?(?=\n\n|\Z)",
        r"if you.*?received.*?error.*?(?=\n\n|\Z)",
        r"unsubscribe.*?(?=\n\n|\Z)",
    ]
    for pattern in disclaimer_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    # Collapse excessive blank lines (more than 2 in a row → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def truncate_for_ai(text: str, max_chars: int = 3000) -> str:
    """
    Truncate email body to avoid hitting token limits.

    WHY 3000 CHARS?
      Gemini can handle much more, but:
        1. Most of the signal is in the first ~3000 chars of an email
        2. Shorter prompts = faster responses + lower cost
        3. Long emails often have repetitive content, signatures, legal text

    We truncate at a word boundary to avoid cutting mid-word.
    We add a note so Gemini knows the email was truncated.
    """
    if len(text) <= max_chars:
        return text

    # Find the last space before the cutoff to avoid cutting mid-word
    cutoff = text.rfind(" ", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars

    return text[:cutoff] + "\n\n[Email truncated for length]"


def extract_sender_name(sender_string: str) -> str:
    """
    Extract a human-readable name from a sender string.

    Gmail returns sender as: 'John Smith <john@company.com>'
    or sometimes just: 'john@company.com'

    We want just 'John Smith' or 'john@company.com' for the summary.
    """
    if not sender_string:
        return "Unknown"

    # Pattern: "Name <email@domain.com>"
    match = re.match(r'^"?([^"<]+)"?\s*<[^>]+>$', sender_string.strip())
    if match:
        return match.group(1).strip()

    # Already just an email address
    return sender_string.strip()


def prepare_email_for_ai(email: RawEmail) -> str:
    """
    Format a RawEmail into a clean string ready to be injected into a prompt.

    WHY A DEDICATED FORMATTER?
      The AI needs context (subject, sender) not just the body. But we also
      need to control the format so the prompt template works reliably.
      This function owns that formatting decision in one place.
    """
    sender_name = extract_sender_name(email.sender or "")
    cleaned_body = clean_email_body(email.body or email.snippet or "")
    truncated_body = truncate_for_ai(cleaned_body)

    # If body is empty, fall back to Gmail's snippet (auto-preview)
    if not truncated_body and email.snippet:
        truncated_body = email.snippet

    lines = [
        f"Subject: {email.subject or 'No Subject'}",
        f"From: {sender_name}",
        f"Date: {email.date or 'Unknown'}",
        "",
        truncated_body or "(No readable content found)",
    ]

    return "\n".join(lines)
