from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.main import app

TEST_SECRET = "test-secret-key"
AUTH_HEADERS = {"X-Internal-Token": TEST_SECRET, "X-User-ID": "test_user"}


@pytest.fixture
def client():
    """LLMService를 모킹하고 인증을 우회한 테스트 클라이언트."""
    with (
        patch("app.api.v1.middleware.settings") as mock_settings,
        patch("app.api.v1.endpoints.llm._get_llm_service") as mock_factory,
    ):
        mock_settings.INTERNAL_API_SECRET = TEST_SECRET

        mock_service = AsyncMock()
        mock_service.process = AsyncMock(return_value="처리 결과")
        mock_service.summarize = AsyncMock(return_value="요약 결과")
        mock_service.classify = AsyncMock(return_value="분류 결과")
        mock_service.generate_workflow = AsyncMock(
            return_value={
                "name": "테스트 워크플로우",
                "description": "테스트 설명",
                "nodes": [
                    {
                        "id": "node_1",
                        "type": "input",
                        "category": "trigger",
                        "config": {},
                        "position": {"x": 0, "y": 0},
                        "role": "start",
                        "authWarning": False,
                    }
                ],
                "edges": [],
                "trigger": {"type": "manual", "config": {}},
            }
        )
        mock_factory.return_value = mock_service

        yield TestClient(app, raise_server_exceptions=False), mock_service


# ── POST /llm/process ──


def test_process_endpoint(client):
    c, mock = client
    resp = c.post("/api/v1/llm/process", json={"prompt": "테스트"}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "처리 결과"
    assert "tokens_used" in data


def test_process_with_context(client):
    c, mock = client
    resp = c.post(
        "/api/v1/llm/process",
        json={"prompt": "요청", "context": "컨텍스트", "max_tokens": 512},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200


# ── POST /llm/summarize ──


def test_summarize_endpoint(client):
    c, mock = client
    resp = c.post("/api/v1/llm/summarize", json={"prompt": "긴 문서 내용"}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["result"] == "요약 결과"


# ── POST /llm/classify ──


def test_classify_endpoint(client):
    c, mock = client
    resp = c.post("/api/v1/llm/classify", json={"prompt": "뉴스 기사"}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["result"] == "분류 결과"


# ── POST /llm/generate-workflow ──


def test_generate_workflow_endpoint(client):
    c, mock = client
    resp = c.post(
        "/api/v1/llm/generate-workflow",
        json={"prompt": "지메일 → 슬랙 워크플로우"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    # Spring Boot WorkflowCreateRequest 호환 형식
    assert "name" in data
    assert "nodes" in data
    assert "edges" in data
    assert "trigger" in data


def test_generate_workflow_with_context(client):
    c, mock = client
    resp = c.post(
        "/api/v1/llm/generate-workflow",
        json={"prompt": "워크플로우", "context": "추가 정보"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200


# ── Error cases ──


def test_process_llm_api_error(client):
    c, mock = client
    mock.process = AsyncMock(
        side_effect=FlowifyException(ErrorCode.LLM_API_ERROR, detail="LLM 호출 실패")
    )
    resp = c.post("/api/v1/llm/process", json={"prompt": "테스트"}, headers=AUTH_HEADERS)
    assert resp.status_code == 502
    assert resp.json()["error_code"] == "LLM_API_ERROR"


def test_generate_workflow_generation_failed(client):
    c, mock = client
    mock.generate_workflow = AsyncMock(
        side_effect=FlowifyException(ErrorCode.LLM_GENERATION_FAILED, detail="JSON 파싱 실패")
    )
    resp = c.post(
        "/api/v1/llm/generate-workflow",
        json={"prompt": "잘못된 요청"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "LLM_GENERATION_FAILED"


# ── Validation ──


def test_process_missing_prompt(client):
    c, mock = client
    resp = c.post("/api/v1/llm/process", json={}, headers=AUTH_HEADERS)
    assert resp.status_code == 422  # Pydantic validation error
