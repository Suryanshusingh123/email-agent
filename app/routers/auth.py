"""
auth.py — OAuth 2.0 authentication endpoints.

TWO ENDPOINTS:
  GET /auth/login    → Redirects the user to Google's login page
  GET /auth/callback → Google calls this after login with an auth code

WHY A ROUTER FILE?
  Routers are how FastAPI organizes endpoints by feature.
  This file owns everything auth-related. The emails router owns email stuff.
  main.py just wires them together. This keeps concerns separated cleanly.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import settings

# --- Constants ---
# The scope defines exactly what permissions we're requesting.
# gmail.readonly means we can read emails but CANNOT send, delete, or modify.
# Always request the minimum scope needed — this is the principle of least privilege.
# gmail.modify allows reading AND applying/creating labels.
# gmail.readonly is a subset of gmail.modify — upgrading here covers both.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Where we save the OAuth token after the user authenticates.
# In production you'd store this in a database. For now, a local file is fine.
TOKEN_FILE = Path("token.json")

# APIRouter is like a mini FastAPI app — it groups related endpoints.
# We set a prefix and tags in main.py when we include this router.
router = APIRouter()


def build_flow() -> Flow:
    """
    Creates a Google OAuth Flow object from our credentials.

    WHY A FUNCTION AND NOT A GLOBAL?
    The Flow object holds state (like the redirect URI). Creating it fresh
    for each request ensures no state leaks between users — important for
    correctness and security.

    Flow handles the hard parts:
      - Building the correct authorization URL
      - Exchanging the auth code for tokens
      - Validating responses from Google
    """
    # We build the client config dict from our env vars.
    # Alternative: download a credentials.json from Google Cloud Console.
    # We use env vars because it's easier to manage secrets this way.
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


@router.get("/login")
async def login():
    """
    Step 1 of OAuth: redirect the user to Google's login page.

    We build the authorization URL and send the user there.
    Google handles login entirely — we never see the password.

    'state' is a random string Google sends back in the callback.
    We'd normally verify it to prevent CSRF attacks. For now we use
    a simple placeholder — Phase 6 will add proper state validation.
    """
    flow = build_flow()

    # authorization_url is where we send the user (Google's login page)
    # state is a nonce Google echoes back in the callback for CSRF protection
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",        # forces Google to show consent + return refresh_token
    )

    # RedirectResponse tells FastAPI to send a 302 redirect to the user's browser.
    # The browser then navigates to Google automatically.
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def callback(code: str, state: str = None, error: str = None):
    """
    Step 2 of OAuth: Google redirects here after the user logs in.

    Google appends query parameters to the redirect URL:
      ?code=4/abc...   ← the authorization code (exchange this for tokens)
      &state=xyz       ← the state we sent (for CSRF validation)
      &error=access_denied ← if user clicked "Cancel" on Google's page

    FastAPI automatically parses query params as function arguments.
    So `code: str` maps to ?code=... in the URL. Clean.
    """
    # Handle the case where user denied permission on Google's page
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Google OAuth error: {error}. User may have denied access."
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="No authorization code received from Google."
        )

    try:
        flow = build_flow()

        # Exchange the short-lived code for long-lived tokens.
        # This is a server-to-server POST to Google's token endpoint.
        # After this call, flow.credentials contains access_token + refresh_token.
        flow.fetch_token(code=code)
        credentials = flow.credentials

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to exchange auth code for tokens: {str(e)}"
        )

    # Save tokens to disk so we can reuse them without re-authenticating.
    # token.json is in .gitignore — it stays off Git.
    _save_credentials(credentials)

    return {
        "message": "Authentication successful! You can now fetch emails.",
        "scopes_granted": list(credentials.scopes) if credentials.scopes else SCOPES,
        "token_saved": str(TOKEN_FILE),
    }


@router.get("/status")
async def auth_status():
    """
    Check if we have valid (non-expired) credentials saved.
    Useful for the frontend to know if the user needs to re-authenticate.
    """
    credentials = _load_credentials()

    if not credentials:
        return {"authenticated": False, "reason": "No token file found. Please visit /auth/login"}

    if not credentials.valid:
        # Try to refresh automatically if we have a refresh_token
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                _save_credentials(credentials)
                return {"authenticated": True, "status": "Token refreshed successfully"}
            except Exception as e:
                return {"authenticated": False, "reason": f"Token refresh failed: {str(e)}"}
        return {"authenticated": False, "reason": "Token expired and no refresh token available"}

    return {"authenticated": True, "status": "Valid token found"}


# --- Helper functions (private, not endpoints) ---
# Functions starting with _ are a Python convention for "internal use".

def _save_credentials(credentials: Credentials) -> None:
    """Persist OAuth credentials to disk as JSON."""
    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))


def _load_credentials() -> Optional[Credentials]:
    """Load credentials from disk. Returns None if file doesn't exist."""
    if not TOKEN_FILE.exists():
        return None

    token_data = json.loads(TOKEN_FILE.read_text())

    return Credentials(
        token=token_data["token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data.get("scopes", SCOPES),
    )


def get_valid_credentials() -> Credentials:
    """
    Load credentials and auto-refresh if expired.
    This is what the Gmail service will call to get a ready-to-use token.

    Raises HTTPException if not authenticated — the caller doesn't need
    to handle the auth logic, just catch the exception.
    """
    credentials = _load_credentials()

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Visit /auth/login first."
        )

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _save_credentials(credentials)
        else:
            raise HTTPException(
                status_code=401,
                detail="Token expired. Visit /auth/login to re-authenticate."
            )

    return credentials
