import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.services.llm_service import LLMService


@pytest.fixture
def llm_service():
    with patch("app.services.llm_service.ChatOpenAI"):
        return LLMService()


# ── process ──


async def test_process_without_context(llm_service):
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value="응답 결과"):
        result = await llm_service.process("테스트 프롬프트")
    assert result == "응답 결과"


async def test_process_with_context(llm_service):
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value="컨텍스트 응답"):
        result = await llm_service.process("요청", context="참고 자료")
    assert result == "컨텍스트 응답"


# ── summarize ──


async def test_summarize(llm_service):
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value="요약 결과"):
        result = await llm_service.summarize("긴 텍스트 내용")
    assert result == "요약 결과"


# ── classify ──


async def test_classify_with_categories(llm_service):
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value="긍정"):
        result = await llm_service.classify("좋은 제품입니다", categories=["긍정", "부정", "중립"])
    assert result == "긍정"


async def test_classify_without_categories(llm_service):
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value="기술"):
        result = await llm_service.classify("AI 관련 뉴스")
    assert result == "기술"


# ── generate_workflow ──


async def test_generate_workflow_success(llm_service):
    mock_result = {
        "nodes": [{"id": "node_1", "type": "input"}],
        "edges": [],
    }
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value=mock_result):
        result = await llm_service.generate_workflow("지메일 → 슬랙 워크플로우")
    assert "nodes" in result
    assert result["nodes"][0]["id"] == "node_1"


async def test_generate_workflow_with_context(llm_service):
    mock_result = {"nodes": [], "edges": []}
    with patch.object(llm_service, "_invoke_with_retry", new_callable=AsyncMock, return_value=mock_result):
        result = await llm_service.generate_workflow("워크플로우 만들어줘", context="추가 정보")
    assert "nodes" in result


async def test_generate_workflow_parse_failure(llm_service):
    with patch.object(
        llm_service,
        "_invoke_with_retry",
        new_callable=AsyncMock,
        side_effect=ValueError("JSON 파싱 실패"),
    ):
        with pytest.raises(FlowifyException) as exc_info:
            await llm_service.generate_workflow("잘못된 요청")
        assert exc_info.value.error_code == ErrorCode.LLM_GENERATION_FAILED


# ── _invoke_with_retry ──


async def test_retry_on_rate_limit(llm_service):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(
        side_effect=[Exception("rate limit exceeded"), "성공"]
    )

    with patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock):
        result = await llm_service._invoke_with_retry(chain, {"prompt": "test"})
    assert result == "성공"


async def test_retry_on_server_error(llm_service):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(
        side_effect=[Exception("500 server error"), Exception("502 server error"), "성공"]
    )

    with patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock):
        result = await llm_service._invoke_with_retry(chain, {"prompt": "test"})
    assert result == "성공"


async def test_no_retry_on_unknown_error(llm_service):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(side_effect=Exception("unknown error"))

    with pytest.raises(FlowifyException) as exc_info:
        await llm_service._invoke_with_retry(chain, {"prompt": "test"})
    assert exc_info.value.error_code == ErrorCode.LLM_API_ERROR


async def test_rate_limit_max_one_retry(llm_service):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(
        side_effect=[Exception("rate limit"), Exception("rate limit")]
    )

    with patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(FlowifyException) as exc_info:
            await llm_service._invoke_with_retry(chain, {"prompt": "test"})
        assert exc_info.value.error_code == ErrorCode.LLM_API_ERROR


# ── _extract_retry_after ──


def test_extract_retry_after_from_header():
    result = LLMService._extract_retry_after(Exception("Retry-After: 5"))
    assert result == 5.0


def test_extract_retry_after_default():
    result = LLMService._extract_retry_after(Exception("some error"))
    assert result == 1.0
