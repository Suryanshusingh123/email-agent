"""
gemini_service.py — Gemini AI integration for email summarization.

KEY CONCEPTS IN THIS FILE:
  1. Prompt engineering — how you instruct the AI
  2. Structured output — forcing the AI to return valid JSON
  3. Error handling — AI responses are non-deterministic, so we handle failures
  4. Model configuration — temperature, safety settings, etc.
"""

import json
import re
import logging
import time
from typing import Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)

from app.config import settings
from app.models.email_models import EmailSummary, Priority, Category, RawEmail
from app.utils.email_parser import prepare_email_for_ai


# Configure the Gemini client once at module load time.
# This sets the API key globally for all genai calls in this module.
genai.configure(api_key=settings.gemini_api_key)


# --- The System Prompt ---
# WHY THIS IS SEPARATE FROM THE USER PROMPT:
#   System prompt = the AI's persona and rules (set once, stable)
#   User prompt = the specific task for each request (changes per email)
#   Keeping them separate makes the prompt easier to tune and reason about.

SYSTEM_PROMPT = """You are an expert email analyst assistant. Your job is to analyze emails and extract structured information from them.

You always respond with valid JSON only — no markdown, no explanation, no code blocks. Just raw JSON.

You must be concise, accurate, and professional. Never make up information not present in the email."""


def build_user_prompt(email_text: str) -> str:
    """
    Build the per-email prompt.

    PROMPT ENGINEERING PRINCIPLES USED HERE:
      1. Explicit output format — show the exact JSON shape expected
      2. Constrained choices — list valid values for category/priority
         (prevents the model from inventing new categories)
      3. Clear field definitions — tell it exactly what each field means
      4. Fallback instructions — tell it what to do when unsure

    BEGINNER MISTAKE:
      Saying "summarize this email". You get back a paragraph of free text
      that you can't reliably parse. Always specify the exact structure.
    """
    return f"""Analyze the following email and return a JSON object with exactly these fields:

{{
  "summary": "2-3 sentence summary of what this email is about",
  "category": "one of: work, personal, newsletter, promotional, finance, security, social, other",
  "priority": "one of: high, medium, low",
  "action_required": true or false,
  "action_description": "what action is needed (null if action_required is false)",
  "key_points": ["point 1", "point 2", "point 3"]
}}

Priority rules:
- high: requires response or action within 24 hours, urgent matters, security alerts
- medium: requires attention but not immediately, FYI items with follow-up needed
- low: newsletters, promotions, automated notifications, no response needed

Return ONLY the JSON object. No other text.

EMAIL:
{email_text}"""


def summarize_email(email: RawEmail) -> EmailSummary:
    """
    Send one email to Gemini and return a structured EmailSummary.

    ARCHITECTURE NOTE:
      We use gemini-1.5-flash (not pro) because:
        - Flash is faster and cheaper — important when processing many emails
        - Email summarization doesn't need the full reasoning depth of Pro
        - You can always switch to Pro by changing the model name string

    TEMPERATURE = 0.1:
      Temperature controls randomness. Range: 0.0 (deterministic) to 1.0 (creative).
      For structured JSON output, we want near-zero randomness.
      High temperature = model might add fields, change JSON structure, or ramble.
      Low temperature = consistent, predictable JSON every time.
    """
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,          # Near-deterministic for consistent JSON
            max_output_tokens=1024,   # Summaries don't need more than this
        ),
    )

    email_text = prepare_email_for_ai(email)
    user_prompt = build_user_prompt(email_text)

    ai_text = _call_with_retry(model, user_prompt, email.message_id)
    if ai_text is None:
        return _fallback_summary(email, reason="Gemini API failed after retries (timeout or quota)")

    # Parse the JSON Gemini returned
    parsed = _parse_ai_response(ai_text)
    if parsed is None:
        logger.warning("Failed to parse Gemini response for message %s. Raw output: %r", email.message_id, ai_text[:500])
        return _fallback_summary(email, reason="Could not parse Gemini JSON response")

    # Build and return the final EmailSummary
    return EmailSummary(
        message_id=email.message_id,
        subject=email.subject or "No Subject",
        sender=email.sender or "Unknown",
        date=email.date,
        summary=parsed.get("summary", "No summary available."),
        category=_safe_category(parsed.get("category", "other")),
        priority=_safe_priority(parsed.get("priority", "medium")),
        action_required=bool(parsed.get("action_required", False)),
        action_description=parsed.get("action_description"),
        key_points=parsed.get("key_points", []),
    )


def _call_with_retry(model, prompt: str, message_id: str, max_attempts: int = 3) -> Optional[str]:
    """
    Call Gemini with exponential backoff retry on transient errors.

    WHAT IS EXPONENTIAL BACKOFF?
      Attempt 1 fails → wait 1s → Attempt 2 fails → wait 2s → Attempt 3 fails → give up
      Waiting longer each time avoids hammering an already-struggling API.
      This is the industry-standard pattern for calling any external service.

    WHICH ERRORS ARE RETRYABLE?
      504 Deadline Exceeded  → transient, always retry
      429 Resource Exhausted → rate limit, retry after waiting
      500 Internal Error     → sometimes transient, worth retrying
      400 Bad Request        → our fault (bad prompt), don't retry
      401 Unauthorized       → bad API key, don't retry
    """
    retryable_codes = ("504", "429", "500", "503")

    for attempt in range(1, max_attempts + 1):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()

        except Exception as e:
            error_str = str(e)
            is_retryable = any(code in error_str for code in retryable_codes)

            if is_retryable and attempt < max_attempts:
                wait = 2 ** (attempt - 1)  # 1s, 2s, 4s ...
                logger.warning(
                    "Gemini transient error for %s (attempt %d/%d), retrying in %ds: %s",
                    message_id, attempt, max_attempts, wait, error_str[:100]
                )
                time.sleep(wait)
            else:
                logger.error("Gemini failed for %s after %d attempt(s): %s", message_id, attempt, error_str[:200])
                return None

    return None


def _parse_ai_response(text: str) -> Optional[dict]:
    """
    Parse the JSON string from Gemini's response.

    WHY NOT JUST json.loads(text)?
      Even with temperature=0.1, Gemini occasionally wraps JSON in
      ```json ... ``` markdown blocks, or adds a leading sentence.
      We defensively strip those before parsing.

    REAL-WORLD LESSON:
      AI outputs are non-deterministic. Even if it works 99% of the time,
      the 1% failure will happen in production. Always handle it.
    """
    if not text:
        return None

    # Strip Gemini 2.5 thinking blocks (<thinking>...</thinking>)
    # These appear when the model reasons before answering
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Strip markdown code blocks (```json ... ``` or ``` ... ```)
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)

    text = text.strip()

    # Attempt 1: parse the whole cleaned text directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract the first {...} JSON object found anywhere in the text
    # Handles cases where Gemini adds a sentence before or after the JSON
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _safe_category(value: str) -> Category:
    """
    Convert the AI's category string to our Category enum safely.

    WHY: The AI might return "Work" (capitalized) or "WORK" or a value
    not in our enum. We normalize and fall back to "other" if invalid.
    """
    try:
        return Category(value.lower().strip())
    except ValueError:
        return Category.OTHER


def _safe_priority(value: str) -> Priority:
    """Convert AI's priority string to Priority enum safely."""
    try:
        return Priority(value.lower().strip())
    except ValueError:
        return Priority.MEDIUM


def _fallback_summary(email: RawEmail, reason: str) -> EmailSummary:
    """
    Return a safe default EmailSummary when AI processing fails.

    WHY NOT RAISE AN EXCEPTION?
      If one email fails to summarize, we still want to return results
      for the other emails. A fallback lets the system degrade gracefully
      instead of failing the entire request.

      The caller can detect failures by checking if summary starts with
      "Summary unavailable" or by adding a dedicated error field later.
    """
    return EmailSummary(
        message_id=email.message_id,
        subject=email.subject or "No Subject",
        sender=email.sender or "Unknown",
        date=email.date,
        summary=f"Summary unavailable. {reason}",
        category=Category.OTHER,
        priority=Priority.MEDIUM,
        action_required=False,
        action_description=None,
        key_points=[],
    )


# Increment this string whenever you change the draft prompt below.
# Lets you query the DB later: "show me all drafts generated by v1.0 vs v1.1"
DRAFT_PROMPT_VERSION = "1.1"

VALID_TONES = ("professional", "friendly", "concise", "detailed")

_TONE_INSTRUCTIONS = {
    "professional": (
        "Tone: formal and professional. Use complete sentences, courteous language, "
        "and a neutral business register. Avoid contractions and colloquialisms."
    ),
    "friendly": (
        "Tone: warm and conversational. Write as you would to a colleague you know well. "
        "Contractions and a light touch are fine. Sound like a person, not a template."
    ),
    "concise": (
        "Tone: brief and direct. Get to the point in 1-3 sentences maximum. "
        "No pleasantries, no filler. Every word should earn its place."
    ),
    "detailed": (
        "Tone: thorough and structured. Address each key point explicitly. "
        "Use short paragraphs if needed. Err on the side of completeness over brevity."
    ),
}


def generate_reply_draft(
    subject: str,
    sender: str,
    summary: str,
    key_points: list,
    action_description: Optional[str],
    tone: str = "professional",
) -> str:
    """
    Generate a professional reply draft using Gemini.

    WHY USE THE SUMMARY INSTEAD OF THE RAW EMAIL?
      The summary is already clean, structured, and focused.
      Feeding Gemini its own structured output gives it better context
      than raw HTML email with footers, disclaimers, and MIME artifacts.
      This is "AI chaining" — one AI pass feeds the next.

    TEMPERATURE = 0.4:
      Higher than summarization (0.1) because drafts need natural language
      variation. Too low and every draft sounds robotic and identical.
      Too high and the model hallucinates facts. 0.4 is the sweet spot
      for professional writing tasks.

    SAFETY CONSTRAINT IN PROMPT:
      We explicitly tell the model not to invent facts, dates, or commitments
      not present in the summary. This is a critical guardrail for email drafts —
      the human MUST review before sending.
    """
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=(
            "You are a professional email assistant. You draft clear, concise, "
            "and polite email replies. You never invent facts, make promises, "
            "or include information not present in what you've been given."
        ),
        generation_config=genai.GenerationConfig(
            temperature=0.4,
            max_output_tokens=512,
        ),
    )

    action_line = f"\nThe required action is: {action_description}" if action_description else ""
    key_points_text = "\n".join(f"- {p}" for p in key_points) if key_points else "None provided"
    tone_instruction = _TONE_INSTRUCTIONS.get(tone, _TONE_INSTRUCTIONS["professional"])

    prompt = f"""Draft a reply to the following email.

Original email details:
Subject: {subject}
From: {sender}
Summary: {summary}
Key points:
{key_points_text}{action_line}

Instructions:
- {tone_instruction}
- Do NOT invent facts, dates, numbers, or commitments not present above
- Do NOT include a subject line
- End with: Best regards,
- Leave the sender name blank (the user will fill it in)

Return ONLY the email body text. Nothing else."""

    result = _call_with_retry(model, prompt, message_id="draft")
    if not result:
        raise RuntimeError("Gemini failed to generate a draft after retries")

    return result.strip(), DRAFT_PROMPT_VERSION
