from unittest.mock import AsyncMock, patch

# v2 테스트 헬퍼: node dict와 canonical payload 사용
_DEFAULT_NODE = {
    "id": "n1",
    "type": "llm",
    "runtime_type": "llm",
    "runtime_config": {},
    "config": {},
}


def _node(**overrides):
    n = {**_DEFAULT_NODE, **overrides}
    if "action" in overrides and "runtime_config" not in overrides:
        n["runtime_config"] = {"action": overrides.pop("action")}
    return n


# ── execute (action routing) ──


async def test_llm_node_summarize():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "summarize", "output_data_type": "TEXT"}),
            input_data={"type": "TEXT", "content": "긴 텍스트"},
            service_tokens={},
        )

    assert result["type"] == "TEXT"
    assert result["content"] == "요약 결과"
    mock_instance.summarize.assert_called_once_with("긴 텍스트")


async def test_llm_node_classify():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.classify = AsyncMock(return_value="긍정")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "classify", "categories": ["긍정", "부정"]})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "classify", "categories": ["긍정", "부정"]}),
            input_data={"type": "TEXT", "content": "좋은 제품"},
            service_tokens={},
        )

    assert result["content"] == "긍정"
    mock_instance.classify.assert_called_once_with("좋은 제품", ["긍정", "부정"])


async def test_llm_node_process_default():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="처리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "분석해줘"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(runtime_config={"action": "process", "prompt": "분석해줘"}),
            input_data={"type": "TEXT", "content": "입력 데이터"},
            service_tokens={},
        )

    assert result["content"] == "처리 결과"
    mock_instance.process.assert_called_once()


async def test_llm_node_default_action_is_process():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"prompt": "요청"})
        node._llm_service = mock_instance

        result = await node.execute(
            node=_node(config={"prompt": "요청"}),
            input_data={"type": "TEXT", "content": "value"},
            service_tokens={},
        )

    assert result["content"] == "결과"
    mock_instance.process.assert_called_once()


# ── canonical payload 텍스트 추출 ──


async def test_extract_text_from_single_email():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={"type": "SINGLE_EMAIL", "subject": "제목", "body": "본문 내용"},
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "제목" in call_args
    assert "본문 내용" in call_args


async def test_extract_text_from_spreadsheet():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.summarize = AsyncMock(return_value="요약")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "summarize"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "summarize"}),
            input_data={
                "type": "SPREADSHEET_DATA",
                "headers": ["이름", "점수"],
                "rows": [["홍길동", "95"]],
            },
            service_tokens={},
        )

    call_args = mock_instance.summarize.call_args[0][0]
    assert "홍길동" in call_args


# ── validate ──


def test_validate_process_requires_prompt():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        node_dict = _node()
        assert (
            LLMNodeStrategy(config={"action": "process", "prompt": "test"}).validate(
                {**node_dict, "runtime_config": {"action": "process", "prompt": "test"}}
            )
            is True
        )
        assert (
            LLMNodeStrategy(config={"action": "process"}).validate(
                {**node_dict, "runtime_config": {"action": "process"}}
            )
            is False
        )
        assert (
            LLMNodeStrategy(config={"prompt": "test"}).validate(
                {**node_dict, "runtime_config": {"prompt": "test"}}
            )
            is True
        )
        assert LLMNodeStrategy(config={}).validate(node_dict) is False


def test_validate_summarize_classify_no_prompt_needed():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert (
            LLMNodeStrategy(config={"action": "summarize"}).validate(
                _node(runtime_config={"action": "summarize"})
            )
            is True
        )
        assert (
            LLMNodeStrategy(config={"action": "classify"}).validate(
                _node(runtime_config={"action": "classify"})
            )
            is True
        )


def test_validate_unknown_action():
    with patch("app.core.nodes.llm_node.LLMService"):
        from app.core.nodes.llm_node import LLMNodeStrategy

        assert (
            LLMNodeStrategy(config={"action": "unknown"}).validate(
                _node(runtime_config={"action": "unknown"})
            )
            is False
        )


async def test_extract_text_from_email_list_includes_mail_metadata():
    with patch("app.core.nodes.llm_node.LLMService") as mock_svc_cls:
        mock_instance = mock_svc_cls.return_value
        mock_instance.process = AsyncMock(return_value="정리 결과")

        from app.core.nodes.llm_node import LLMNodeStrategy

        node = LLMNodeStrategy(config={"action": "process", "prompt": "정리해줘"})
        node._llm_service = mock_instance

        await node.execute(
            node=_node(runtime_config={"action": "process", "prompt": "정리해줘"}),
            input_data={
                "type": "EMAIL_LIST",
                "items": [
                    {
                        "from": "sender@example.com",
                        "date": "2026-05-04",
                        "subject": "메일 제목",
                        "body": "메일 본문",
                    }
                ],
            },
            service_tokens={},
        )

    call_args = mock_instance.process.await_args.kwargs["context"]
    assert "[Email 1]" in call_args
    assert "From: sender@example.com" in call_args
    assert "Date: 2026-05-04" in call_args
    assert "Subject: 메일 제목" in call_args
    assert "Body:" in call_args
    assert "메일 본문" in call_args
