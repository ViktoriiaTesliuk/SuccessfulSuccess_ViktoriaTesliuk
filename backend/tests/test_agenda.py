"""Tests for the agenda parser module and lambda handler (Lab 6)."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.ai.agenda import (
    ActionItem,
    AgendaItem,
    AgendaParseError,
    ParsedAgenda,
    cost_usd,
    parse_agenda,
)
from app.ai.agenda_lambda import handler


@pytest.fixture(autouse=True)
def schema():
    """Override database setup from conftest since agenda unit tests need no db."""
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    """Override database cleaning from conftest."""
    yield


def test_agenda_models():
    item = AgendaItem(topic="Review roadmap", owner="Alice", minutes=30)
    assert item.topic == "Review roadmap"
    assert item.owner == "Alice"
    assert item.minutes == 30

    action = ActionItem(task="Send slides", owner="Bob", due=date(2026, 10, 30))
    assert action.task == "Send slides"
    assert action.due == date(2026, 10, 30)

    parsed = ParsedAgenda(
        title="Weekly sync",
        items=[item],
        action_items=[action],
        language="en",
    )
    assert parsed.title == "Weekly sync"
    assert len(parsed.items) == 1
    assert len(parsed.action_items) == 1


def test_cost_calculation():
    # Haiku pricing: $0.10 / 1M in, $0.50 / 1M out
    usage_haiku = {"input_tokens": 1000, "output_tokens": 200}
    cost = cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", usage_haiku)
    # (1000 * 0.10 + 200 * 0.50) / 1,000,000 = (100 + 100) / 1,000,000 = 0.0002
    assert cost == 0.0002

    # Opus pricing: $4.00 / 1M in, $20.00 / 1M out
    usage_opus = {"input_tokens": 1000, "output_tokens": 100}
    cost_op = cost_usd("anthropic.claude-opus-3-5", usage_opus)
    # (1000 * 4 + 100 * 20) / 1,000,000 = (4000 + 2000) / 1,000,000 = 0.006
    assert cost_op == 0.006


@patch("app.ai.agenda.get_anthropic_client")
def test_parse_agenda_success(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Mock tool call response
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "call_123"
    mock_tool_block.input = {
        "title": "Pricing sync",
        "starts_at": "2026-10-26T10:00:00",
        "duration_minutes": 45,
        "items": [
            {"topic": "Pro tier pricing", "owner": "Olena", "minutes": 15},
        ],
        "action_items": [
            {"task": "Prepare report", "owner": "Taras", "due": "2026-10-30"},
        ],
        "language": "uk",
    }

    mock_msg = MagicMock()
    mock_msg.content = [mock_tool_block]
    mock_msg.stop_reason = "tool_use"
    mock_msg.usage.input_tokens = 500
    mock_msg.usage.output_tokens = 100

    mock_client.messages.create.return_value = mock_msg

    agenda, usage = parse_agenda("text", date(2026, 10, 26), "Europe/Kyiv")
    assert agenda.title == "Pricing sync"
    assert len(agenda.items) == 1
    assert agenda.items[0].topic == "Pro tier pricing"
    assert usage["input_tokens"] == 500
    assert usage["output_tokens"] == 100


@patch("app.ai.agenda.get_anthropic_client")
def test_parse_agenda_no_tool_call(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_msg = MagicMock()
    mock_msg.content = []
    mock_msg.stop_reason = "refusal"
    mock_msg.usage.input_tokens = 100
    mock_msg.usage.output_tokens = 10

    mock_client.messages.create.return_value = mock_msg

    with pytest.raises(AgendaParseError, match="No agenda returned"):
        parse_agenda("text", date(2026, 10, 26), "Europe/Kyiv")


def test_lambda_handler_unauthorized():
    event = {
        "headers": {},
        "body": '{"text": "some agenda"}',
    }
    response = handler(event, None)
    assert response["statusCode"] == 401
    assert "Unauthorized" in response["body"]


def test_lambda_handler_text_too_long():
    with patch("app.ai.agenda_lambda.verify_cognito_token") as mock_auth:
        mock_auth.return_value = MagicMock(sub="user-123")
        event = {
            "headers": {"authorization": "Bearer token"},
            "body": '{"text": "' + ("A" * 10001) + '"}',
        }
        response = handler(event, None)
        assert response["statusCode"] == 413
        assert "Text too long" in response["body"]


@patch("app.ai.agenda_lambda.verify_cognito_token")
@patch("app.ai.agenda_lambda.parse_agenda")
def test_lambda_handler_success(mock_parse, mock_auth):
    mock_auth.return_value = MagicMock(sub="user-456")
    parsed_mock = ParsedAgenda(
        title="Sync",
        items=[AgendaItem(topic="Topic 1", owner="Me", minutes=10)],
        action_items=[],
        language="en",
    )
    mock_parse.return_value = (parsed_mock, {"input_tokens": 1200, "output_tokens": 200})

    event = {
        "headers": {"authorization": "Bearer valid-token"},
        "body": '{"text": "Sync at 10: Topic 1"}',
    }
    response = handler(event, None)
    assert response["statusCode"] == 200
    assert "application/json" in response["headers"]["Content-Type"]
    assert "Topic 1" in response["body"]
