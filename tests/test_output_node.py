"""OutputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_sink 기반 라우팅. canonical payload 소비.
conftest.py의 service_tokens fixture 사용 가능.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.output_node import OutputNodeStrategy

# ── 테스트 헬퍼 ──────────────────────────────────────────────────


def _sink_node(service: str, **config) -> dict:
    """runtime_sink가 설정된 노드 dict 생성."""
    return {"runtime_sink": {"service": service, "config": config}}


# ── Slack ────────────────────────────────────────────────────────


async def test_slack_send_text(service_tokens: dict) -> None:
    """TEXT payload를 Slack 메시지로 전송합니다."""
    strategy = OutputNodeStrategy({})
    node = _sink_node("slack", channel="#test")
    input_data = {"type": "TEXT", "content": "Hello Slack"}

    with patch("app.core.nodes.output_node.SlackService") as mock_slack_class:
        mock_slack = mock_slack_class.return_value
        mock_slack.send_message = AsyncMock(return_value={"ok": True, "ts": "1.23"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "slack",
        "detail": {"ok": True, "ts": "1.23"},
    }
    mock_slack.send_message.assert_awaited_once_with(
        service_tokens["slack"], "#test", "Hello Slack"
    )


# ── Gmail ────────────────────────────────────────────────────────


async def test_gmail_send_text(service_tokens: dict) -> None:
    """TEXT payload를 Gmail 본문으로 전송합니다."""
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Flowify",
        action="send",
    )
    input_data = {"type": "TEXT", "content": "메일 본문"}

    with patch("app.core.nodes.output_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(return_value={"id": "msg_123"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "gmail",
        "detail": {"id": "msg_123"},
    }
    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"], "receiver@example.com", "Flowify", "메일 본문"
    )


async def test_gmail_send_single_email_type(service_tokens: dict) -> None:
    """SINGLE_EMAIL payload의 body를 Gmail 본문으로 전송합니다."""
    strategy = OutputNodeStrategy({})
    node = _sink_node(
        "gmail",
        to="receiver@example.com",
        subject="Forward",
        action="send",
    )
    input_data = {
        "type": "SINGLE_EMAIL",
        "subject": "원본 제목",
        "from": "sender@example.com",
        "body": "원본 본문",
    }

    with patch("app.core.nodes.output_node.GmailService") as mock_gmail_class:
        mock_gmail = mock_gmail_class.return_value
        mock_gmail.send_message = AsyncMock(return_value={"id": "msg_456"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result["status"] == "sent"
    assert result["service"] == "gmail"
    mock_gmail.send_message.assert_awaited_once_with(
        service_tokens["gmail"], "receiver@example.com", "Forward", "원본 본문"
    )


# ── Notion ───────────────────────────────────────────────────────


async def test_notion_create_page_text(service_tokens: dict) -> None:
    """TEXT payload를 Notion 페이지로 생성합니다."""
    strategy = OutputNodeStrategy({})
    node = _sink_node("notion", target_type="page", target_id="page_123")
    input_data = {"type": "TEXT", "content": "Notion 내용"}

    with patch("app.core.nodes.output_node.NotionService") as mock_notion_class:
        mock_notion = mock_notion_class.return_value
        mock_notion.create_page = AsyncMock(return_value={"id": "notion_page"})

        result = await strategy.execute(node, input_data, service_tokens)

    assert result == {
        "status": "sent",
        "service": "notion",
        "detail": {"id": "notion_page"},
    }
    mock_notion.create_page.assert_awaited_once_with(
        service_tokens["notion"], "page_123", "Flowify Output", "Notion 내용"
    )


# ── 에러 케이스 ──────────────────────────────────────────────────


async def test_unsupported_sink_raises() -> None:
    """지원하지 않는 sink는 UNSUPPORTED_RUNTIME_SINK를 발생시킵니다."""
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("unknown_service"),
            {"type": "TEXT", "content": ""},
            {"unknown_service": "token"},
        )

    assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_RUNTIME_SINK


async def test_incompatible_input_type_raises(service_tokens: dict) -> None:
    """sink가 허용하지 않는 input type이면 INVALID_REQUEST를 발생시킵니다."""
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("slack", channel="#test"),
            {"type": "SPREADSHEET_DATA", "headers": [], "rows": []},
            service_tokens,
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


async def test_missing_token_raises() -> None:
    """서비스 토큰이 없으면 OAuth 토큰 에러를 발생시킵니다."""
    strategy = OutputNodeStrategy({})

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            _sink_node("slack", channel="#test"),
            {"type": "TEXT", "content": "hello"},
            {},
        )

    assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID


# ── validate ─────────────────────────────────────────────────────


def test_validate_supported_sink_returns_true() -> None:
    """필수 config가 있으면 True를 반환합니다."""
    strategy = OutputNodeStrategy({})

    assert strategy.validate(_sink_node("slack", channel="#test")) is True


def test_validate_missing_required_config_returns_false() -> None:
    """필수 config가 없으면 False를 반환합니다."""
    strategy = OutputNodeStrategy({})

    assert strategy.validate(_sink_node("slack")) is False
    assert strategy.validate({}) is False
