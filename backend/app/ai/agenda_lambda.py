"""Lambda handler for the Agenda Parser function (Lab 6).

Runs outside the VPC with no database access.
Calls Amazon Bedrock with Claude to parse raw agenda text into structured JSON.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from typing import Any

import jwt
from pydantic import BaseModel

from app.ai.agenda import PROMPT_VERSION, AgendaParseError, cost_usd, parse_agenda
from app.config import settings

logger = logging.getLogger("agenda_parser")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
if not logger.handlers:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
    logger.addHandler(sh)


class AuthUser(BaseModel):
    sub: str
    email: str | None = None


# Cache for JWKS keys to avoid re-fetching on every invocation
_JWKS_CLIENT: jwt.PyJWKClient | None = None


def get_jwks_client() -> jwt.PyJWKClient | None:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is not None:
        return _JWKS_CLIENT

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID") or settings.cognito_user_pool_id
    region = os.environ.get("COGNITO_REGION") or settings.cognito_region or "us-east-1"
    if not user_pool_id:
        return None

    jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    _JWKS_CLIENT = jwt.PyJWKClient(jwks_url)
    return _JWKS_CLIENT


def verify_cognito_token(auth_header: str | None) -> AuthUser:
    """Verify Cognito JWT token from Authorization header."""
    if not auth_header:
        raise ValueError("Missing Authorization header")

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("Invalid Authorization header format. Expected 'Bearer <token>'")

    token = parts[1]
    jwks_client = get_jwks_client()
    if not jwks_client:
        # If Cognito is not configured, deny access in production
        raise ValueError("Cognito authentication not configured on server")

    signing_key = jwks_client.get_signing_key_from_jwt(token)
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID") or settings.cognito_user_pool_id
    region = os.environ.get("COGNITO_REGION") or settings.cognito_region or "us-east-1"
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"require": ["exp", "sub"]},
    )

    return AuthUser(sub=claims["sub"], email=claims.get("email"))


def make_response(
    status_code: int,
    body_data: dict[str, Any],
    origin: str | None = None,
) -> dict[str, Any]:
    """Helper to return consistent JSON responses with CORS headers."""
    cors_origin = origin or "*"
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
        "body": json.dumps(body_data, ensure_ascii=False),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point for agenda parsing."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin")

    # Handle CORS preflight
    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()
    if http_method == "OPTIONS":
        return make_response(200, {"status": "ok"}, origin=origin)

    # 1. Authentication check
    auth_header = headers.get("authorization")
    try:
        user = verify_cognito_token(auth_header)
    except Exception as exc:
        logger.warning("Authentication failed: %s", exc)
        return make_response(401, {"error": f"Unauthorized: {exc}"}, origin=origin)

    # 2. Parse request body
    raw_body = event.get("body", "{}")
    if event.get("isBase64Encoded", False):
        import base64

        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
    except Exception as exc:
        return make_response(400, {"error": f"Invalid JSON body: {exc}"}, origin=origin)

    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return make_response(400, {"error": "Missing or empty 'text' field"}, origin=origin)

    # 3. Limit text length
    if len(text) > 10_000:
        return make_response(
            413,
            {"error": f"Text too long: {len(text)} characters (max 10,000)"},
            origin=origin,
        )

    # 4. Extract today and timezone
    today_str = body.get("today")
    try:
        today = date.fromisoformat(today_str) if today_str else date.today()
    except Exception:
        today = date.today()

    tz = body.get("tz") or os.environ.get("APP_TIMEZONE") or settings.app_timezone

    started = time.monotonic()
    model = os.environ.get("PARSER_MODEL") or settings.parser_model

    # 5. Call parse_agenda
    try:
        agenda, usage = parse_agenda(text, today, tz, model=model)
    except AgendaParseError as exc:
        logger.warning("Agenda parsing failed: %s", exc)
        return make_response(422, {"error": str(exc)}, origin=origin)
    except Exception as exc:
        logger.error("Unexpected error during parsing: %s", exc, exc_info=True)
        return make_response(500, {"error": f"Internal server error: {exc}"}, origin=origin)

    latency_ms = int((time.monotonic() - started) * 1000)
    cost = cost_usd(model, usage)

    # Required structured CloudWatch log line (submission item 4)
    log_line = {
        "event": "agenda_parsed",
        "user": user.sub,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "usage": usage,
        "latency_ms": latency_ms,
        "cost_usd": cost,
    }
    logger.info(json.dumps(log_line))

    return make_response(
        200,
        {
            "agenda": agenda.model_dump(mode="json"),
            "model": model,
            "prompt_version": PROMPT_VERSION,
        },
        origin=origin,
    )
