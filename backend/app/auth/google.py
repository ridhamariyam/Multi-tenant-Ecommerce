from __future__ import annotations

import anyio.to_thread
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


async def verify_google_credential(credential: str) -> dict:
    audience = get_settings().google_client_id
    if not audience:
        raise AuthenticationError("Google sign-in is not configured")

    try:
        claims = await anyio.to_thread.run_sync(
            id_token.verify_oauth2_token,
            credential,
            Request(),
            audience,
        )
    except (ValueError, GoogleAuthError) as exc:
        raise AuthenticationError("Invalid Google credential") from exc

    if claims.get("iss") not in {
        "accounts.google.com",
        "https://accounts.google.com",
    }:
        raise AuthenticationError("Invalid Google credential")

    if claims.get("email_verified") is not True:
        raise AuthenticationError("Google email is not verified")

    if not claims.get("sub") or not claims.get("email"):
        raise AuthenticationError("Google credential is missing required claims")

    return claims
