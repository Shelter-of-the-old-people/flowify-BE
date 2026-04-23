"""InputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_source 기반 라우팅. canonical payload 반환.
conftest.py의 service_tokens fixture 사용 가능.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.core.nodes.input_node import InputNodeStrategy


# ── 테스트 헬퍼 ──────────────────────────────────────────────────


def _source_node(service: str, mode: str, target: str = "") -> dict:
    """runtime_source가 설정된 노드 dict 생성."""
    return {
        "runtime_source": {
            "service": service,
            "mode": mode,
            "target": target,
            "canonical_input_type": "TEXT",
        }
    }


# ── Google Drive ─────────────────────────────────────────────────

# TODO: test_google_drive_single_file
# TODO: test_google_drive_folder_all_files


# ── Gmail ────────────────────────────────────────────────────────

# TODO: test_gmail_new_email
# TODO: test_gmail_label_emails


# ── Slack ────────────────────────────────────────────────────────

# TODO: test_slack_channel_messages


# ── Google Sheets ────────────────────────────────────────────────

# TODO: test_sheets_sheet_all


# ── 에러 케이스 ──────────────────────────────────────────────────

# TODO: test_missing_token_raises_oauth_error
# TODO: test_unsupported_source_raises


# ── validate ─────────────────────────────────────────────────────

# TODO: test_validate_supported_source_returns_true
# TODO: test_validate_unknown_source_returns_false
# TODO: test_validate_no_runtime_source_returns_false
