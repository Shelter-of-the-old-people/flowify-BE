"""OutputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_sink 기반 라우팅. canonical payload 소비.
conftest.py의 service_tokens fixture 사용 가능.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.core.nodes.output_node import OutputNodeStrategy


# ── 테스트 헬퍼 ──────────────────────────────────────────────────


def _sink_node(service: str, **config) -> dict:
    """runtime_sink가 설정된 노드 dict 생성."""
    return {"runtime_sink": {"service": service, "config": config}}


# ── Slack ────────────────────────────────────────────────────────

# TODO: test_slack_send_text


# ── Gmail ────────────────────────────────────────────────────────

# TODO: test_gmail_send_text
# TODO: test_gmail_send_single_email_type


# ── Notion ───────────────────────────────────────────────────────

# TODO: test_notion_create_page_text


# ── 에러 케이스 ──────────────────────────────────────────────────

# TODO: test_unsupported_sink_raises
# TODO: test_incompatible_input_type_raises
# TODO: test_missing_token_raises


# ── validate ─────────────────────────────────────────────────────

# TODO: test_validate_supported_sink_returns_true
# TODO: test_validate_missing_required_config_returns_false
