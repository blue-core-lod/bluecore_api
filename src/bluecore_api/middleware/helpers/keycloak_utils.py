from __future__ import annotations
from typing import Optional, Tuple
from fastapi import Request
import base64
import json
import logging
import sys

logger = logging.getLogger("keycloak_auth")


def _decode_bearer_claims(auth_header: Optional[str]) -> dict:
    """
    Extract standard OIDC fields (sub, username, email, given/family name) from a
    Bearer JWT *without verification* (just to log who is calling). Returns a
    dict of claims or {} if the header is missing/invalid.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return {}
    token = auth_header.split(None, 1)[1]
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    pad = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        payload = json.loads(raw.decode("utf-8"))
        keep = (
            "sub",
            "preferred_username",
            "username",
            "email",
            "given_name",
            "family_name",
            "name",
        )
        return {k: payload.get(k) for k in keep if k in payload}
    except Exception:
        return {}


def get_keycloak_user_info(
    request: Request,
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Pull user-identifying fields from the JWT decoded above.
    Returns: (uid, username, email, given_name, family_name)
    """
    claims = _decode_bearer_claims(request.headers.get("authorization"))

    uid = (
        claims.get("sub")
        or claims.get("username")
        or claims.get("preferred_username")
        or claims.get("email")
        or "anonymous"
    )
    username = claims.get("preferred_username") or claims.get("username")
    email = claims.get("email")
    given_name = claims.get("given_name")
    family_name = claims.get("family_name")
    return uid, username, email, given_name, family_name


def log_user_info(
    uid,
    username: Optional[str] = None,
    email: Optional[str] = None,
    given_name: Optional[str] = None,
    family_name: Optional[str] = None,
    request: Optional[Request] = None,
    level: int = logging.INFO,
) -> None:
    # color only in an interactive terminal
    use_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    RESET, BOLD, MAGENTA = (
        ("\033[0m", "\033[1m", "\033[95m") if use_color else ("", "", "")
    )

    path = getattr(getattr(request, "url", None), "path", "-")
    logger.log(
        level,
        "\n".join(
            [
                "",
                f"{MAGENTA}{'#' * 71}{RESET}",
                f"{BOLD}{MAGENTA}User Info (from Bearer):{RESET}",
                f"{BOLD}{MAGENTA}UID:{RESET} {uid}",
                f"{BOLD}{MAGENTA}Username:{RESET} {username or '-'}",
                f"{BOLD}{MAGENTA}Email:{RESET} {email or '-'}",
                f"{BOLD}{MAGENTA}First Name:{RESET} {given_name or '-'}",
                f"{BOLD}{MAGENTA}Last Name:{RESET} {family_name or '-'}",
                f"{BOLD}{MAGENTA}API Path Called:{RESET} {path}",
                f"{MAGENTA}{'#' * 71}{RESET}",
                "",
            ]
        ),
    )
