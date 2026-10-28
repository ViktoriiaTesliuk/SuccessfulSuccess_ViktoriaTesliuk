"""Agenda parsing endpoint for local development or direct backend proxy."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.agenda import PROMPT_VERSION, AgendaParseError, cost_usd, parse_agenda
from app.api.deps import CurrentUserDep
from app.config import settings

logger = logging.getLogger("meetings.api.agenda")

router = APIRouter(prefix="/agenda", tags=["agenda"])


class AgendaParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    today: date | None = None
    tz: str | None = None


class AgendaParseResponse(BaseModel):
    agenda: dict[str, Any]
    model: str
    prompt_version: str


@router.post(
    "/parse",
    response_model=AgendaParseResponse,
    summary="Parse raw agenda text using Claude on Amazon Bedrock",
)
async def parse_raw_agenda(
    payload: AgendaParseRequest,
    current_user: CurrentUserDep,
) -> AgendaParseResponse:
    today_val = payload.today or date.today()
    tz_val = payload.tz or settings.app_timezone
    model = os.environ.get("PARSER_MODEL") or settings.parser_model

    started = time.monotonic()
    try:
        agenda, usage = parse_agenda(payload.text, today_val, tz_val, model=model)
    except AgendaParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to parse agenda: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invoke model: {exc}",
        ) from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    cost = cost_usd(model, usage)

    logger.info(
        '{"event": "agenda_parsed", "user": "%s", "model": "%s", "prompt_version": "%s", '
        '"usage": %s, "latency_ms": %d, "cost_usd": %f}',
        current_user.sub,
        model,
        PROMPT_VERSION,
        usage,
        latency_ms,
        cost,
    )

    return AgendaParseResponse(
        agenda=agenda.model_dump(mode="json"),
        model=model,
        prompt_version=PROMPT_VERSION,
    )
