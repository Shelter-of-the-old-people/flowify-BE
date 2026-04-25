"""공용 pytest fixture 모음.

모든 테스트 파일에서 공통으로 사용하는 fixture를 정의합니다.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models.workflow import EdgeDefinition, NodeDefinition

# ── HTTP 클라이언트 ──────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """인증 미들웨어를 통과하는 테스트 HTTP 클라이언트."""
    return TestClient(
        app,
        headers={
            "X-Internal-Token": "test-secret",
            "X-User-ID": "usr_test123",
        },
    )


# ── MongoDB Mock ─────────────────────────────────────────────────


@pytest.fixture()
def mock_db() -> MagicMock:
    """workflow_executions 컬렉션이 설정된 모의 MongoDB 데이터베이스."""
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.insert_one = AsyncMock()
    db.workflow_executions = collection
    return db


# ── 워크플로우 빌더 헬퍼 ─────────────────────────────────────────


def make_nodes(*types: str) -> list[NodeDefinition]:
    """노드 타입 문자열로 NodeDefinition 리스트를 생성합니다."""
    return [
        NodeDefinition(id=f"node_{i + 1}", type=t, config={})
        for i, t in enumerate(types)
    ]


def make_edges(*pairs: tuple[str, str]) -> list[EdgeDefinition]:
    """(source, target) 튜플 쌍으로 EdgeDefinition 리스트를 생성합니다."""
    return [EdgeDefinition(source=s, target=t) for s, t in pairs]


@pytest.fixture()
def linear_workflow() -> dict:
    """input → llm → output 단순 선형 워크플로우."""
    return {
        "nodes": make_nodes("input", "llm", "output"),
        "edges": make_edges(("node_1", "node_2"), ("node_2", "node_3")),
    }


@pytest.fixture()
def if_else_workflow() -> dict:
    """input → if_else → (output_a | output_b) 분기 워크플로우."""
    return {
        "nodes": make_nodes("input", "if_else", "output", "output"),
        "edges": make_edges(
            ("node_1", "node_2"),
            ("node_2", "node_3"),
            ("node_2", "node_4"),
        ),
    }


# ── 서비스 토큰 ─────────────────────────────────────────────────


@pytest.fixture()
def service_tokens() -> dict:
    """테스트용 서비스 토큰 딕셔너리."""
    return {
        "gmail": "test_gmail_token",
        "slack": "test_slack_token",
        "notion": "test_notion_token",
        "google_drive": "test_drive_token",
        "google_sheets": "test_sheets_token",
        "google_calendar": "test_calendar_token",
    }
