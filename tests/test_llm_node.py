from unittest.mock import AsyncMock, patch

import pytest


# ── execute (action routing) ──


async def test_llm_node_summarize():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.summarize = AsyncMock(return_value="요약 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        result = await node.execute({"text": "긴 텍스트"})

    assert result["llm_result"] == "요약 결과"
    assert result["text"] == "긴 텍스트"
    mock_instance.summarize.assert_called_once_with("긴 텍스트")


async def test_llm_node_classify():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.classify = AsyncMock(return_value="긍정")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "classify", "categories": ["긍정", "부정"]})
        node._llm_service = mock_instance

        result = await node.execute({"text": "좋은 제품"})

    assert result["llm_result"] == "긍정"
    mock_instance.classify.assert_called_once_with("좋은 제품", ["긍정", "부정"])


async def test_llm_node_process_default():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.process = AsyncMock(return_value="처리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "분석해줘"})
        node._llm_service = mock_instance

        result = await node.execute({"data": "입력 데이터"})

    assert result["llm_result"] == "처리 결과"
    mock_instance.process.assert_called_once()


async def test_llm_node_default_action_is_process():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.process = AsyncMock(return_value="결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"prompt": "요청"})
        node._llm_service = mock_instance

        result = await node.execute({"key": "value"})

    assert result["llm_result"] == "결과"
    mock_instance.process.assert_called_once()


# ── _extract_text ──


async def test_extract_text_prefers_llm_result():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute({"llm_result": "이전 결과", "text": "원본 텍스트"})

    mock_instance.summarize.assert_called_once_with("이전 결과")


async def test_extract_text_falls_back_to_text_field():
    with patch("app.core.nodes.llm_node.LLMService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute({"text": "텍스트 내용"})

    mock_instance.summarize.assert_called_once_with("텍스트 내용")


# ── validate ──


def test_validate_process_requires_prompt():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert LLMNodeStrategy(config={"action": "process", "prompt": "test"}).validate() is True
        assert LLMNodeStrategy(config={"action": "process"}).validate() is False
        assert LLMNodeStrategy(config={"prompt": "test"}).validate() is True  # default=process
        assert LLMNodeStrategy(config={}).validate() is False


def test_validate_summarize_classify_no_prompt_needed():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert LLMNodeStrategy(config={"action": "summarize"}).validate() is True
        assert LLMNodeStrategy(config={"action": "classify"}).validate() is True


def test_validate_unknown_action():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert LLMNodeStrategy(config={"action": "unknown"}).validate() is False
