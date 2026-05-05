from unittest.mock import AsyncMock, MagicMock

import pytest

from app.common.errors import FlowifyException
from app.core.engine.executor import WorkflowExecutor, register_cancellation_event
from app.core.engine.state import WorkflowState
from app.models.workflow import EdgeDefinition, NodeDefinition


@pytest.fixture()
def mock_db():
    """모의 MongoDB 데이터베이스."""
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.workflow_executions = collection
    return db


def _make_nodes(*types: str) -> list[NodeDefinition]:
    return [NodeDefinition(id=f"node_{i + 1}", type=t, config={}) for i, t in enumerate(types)]


def _make_edges(*pairs: tuple[str, str]) -> list[EdgeDefinition]:
    return [EdgeDefinition(source=s, target=t) for s, t in pairs]


def _make_callback_service() -> MagicMock:
    callback_service = MagicMock()
    callback_service.notify_execution_complete = AsyncMock()
    return callback_service


class TestTopologicalSort:
    def test_linear_chain(self):
        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))
        order = WorkflowExecutor._topological_sort(nodes, edges)
        assert order == ["node_1", "node_2", "node_3"]

    def test_single_node(self):
        nodes = _make_nodes("input")
        order = WorkflowExecutor._topological_sort(nodes, [])
        assert order == ["node_1"]

    def test_diamond_shape(self):
        nodes = _make_nodes("input", "llm", "llm", "output")
        edges = _make_edges(
            ("node_1", "node_2"),
            ("node_1", "node_3"),
            ("node_2", "node_4"),
            ("node_3", "node_4"),
        )
        order = WorkflowExecutor._topological_sort(nodes, edges)
        assert order[0] == "node_1"
        assert order[-1] == "node_4"
        assert set(order[1:3]) == {"node_2", "node_3"}

    def test_cycle_raises(self):
        nodes = _make_nodes("input", "llm")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_1"))
        with pytest.raises(FlowifyException):
            WorkflowExecutor._topological_sort(nodes, edges)


class TestSanitizeForLog:
    def test_removes_credentials(self):
        data = {"key": "value", "credentials": {"google": "token"}}
        result = WorkflowExecutor._sanitize_for_log(data)
        assert "credentials" not in result
        assert result["key"] == "value"

    def test_empty_data(self):
        assert WorkflowExecutor._sanitize_for_log({}) == {}

    def test_none_data(self):
        assert WorkflowExecutor._sanitize_for_log(None) == {}

    def test_no_credentials_key(self):
        data = {"key": "value"}
        result = WorkflowExecutor._sanitize_for_log(data)
        assert result == {"key": "value"}


def _mock_factory(side_effect=None, return_value=None):
    """테스트용 mock factory를 생성합니다.

    v2: create_from_node_def를 mock하고, execute는 (node, input_data, service_tokens) 시그니처.
    """
    factory = MagicMock()
    mock_node = AsyncMock()
    if side_effect:
        mock_node.execute = AsyncMock(side_effect=side_effect)
    elif return_value is not None:
        mock_node.execute = AsyncMock(return_value=return_value)
    factory.create_from_node_def.return_value = mock_node
    return factory


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_linear_success(self, mock_db):
        """input -> llm -> output 선형 워크플로우 성공 테스트."""
        executor = WorkflowExecutor(mock_db)
        executor._factory = _mock_factory(
            side_effect=lambda node, input_data, service_tokens: {"type": "TEXT", "content": "ok"}
        )

        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_test1",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={"google": "token"},
        )

        assert result.state == WorkflowState.SUCCESS
        assert len(result.nodeLogs) == 3
        assert all(log.status == "success" for log in result.nodeLogs)

    @pytest.mark.asyncio
    async def test_node_failure_marks_rollback_available(self, mock_db):
        """노드 실패 시 이후 노드 skip, 상태 ROLLBACK_AVAILABLE."""
        executor = WorkflowExecutor(mock_db)

        call_count = 0

        async def side_effect(node, input_data, service_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # 두 번째 노드(llm)에서 실패
                raise RuntimeError("LLM failed")
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = _make_nodes("input", "llm", "output")
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_test2",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.ROLLBACK_AVAILABLE
        assert result.nodeLogs[0].status == "success"
        assert result.nodeLogs[1].status == "failed"
        assert result.nodeLogs[2].status == "skipped"

    @pytest.mark.asyncio
    async def test_credentials_stripped_from_logs(self, mock_db):
        """로그에 credentials가 포함되지 않는지 확인."""
        executor = WorkflowExecutor(mock_db)
        executor._factory = _mock_factory(
            return_value={
                "type": "TEXT",
                "content": "ok",
                "credentials": {"secret": "should_be_stripped"},
            }
        )

        nodes = _make_nodes("input")
        edges = []

        result = await executor.execute(
            execution_id="exec_test3",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={"google": "secret_token"},
        )

        log = result.nodeLogs[0]
        assert "credentials" not in (log.outputData or {})

    @pytest.mark.asyncio
    async def test_success_sends_spring_callback(self, mock_db):
        """성공 종료 시 Spring 완료 콜백이 호출되는지 검증합니다."""
        callback_service = _make_callback_service()
        executor = WorkflowExecutor(mock_db, callback_service=callback_service)
        executor._factory = _mock_factory(return_value={"type": "TEXT", "content": "ok"})

        result = await executor.execute(
            execution_id="exec_callback_success",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=_make_nodes("input"),
            edges=[],
            service_tokens={},
        )

        callback_service.notify_execution_complete.assert_awaited_once_with(
            "exec_callback_success", result
        )

    @pytest.mark.asyncio
    async def test_failure_sends_spring_callback(self, mock_db):
        """실패 종료 시 Spring 완료 콜백이 호출되는지 검증합니다."""
        callback_service = _make_callback_service()
        executor = WorkflowExecutor(mock_db, callback_service=callback_service)
        executor._factory = _mock_factory(
            side_effect=[
                {"type": "TEXT", "content": "ok"},
                RuntimeError("LLM failed"),
            ]
        )

        result = await executor.execute(
            execution_id="exec_callback_failure",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=_make_nodes("input", "llm", "output"),
            edges=_make_edges(("node_1", "node_2"), ("node_2", "node_3")),
            service_tokens={},
        )

        assert result.state == WorkflowState.ROLLBACK_AVAILABLE
        callback_service.notify_execution_complete.assert_awaited_once_with(
            "exec_callback_failure", result
        )

    @pytest.mark.asyncio
    async def test_stopped_execution_sends_spring_callback(self, mock_db):
        """중지 종료 시 Spring 완료 콜백이 호출되는지 검증합니다."""
        callback_service = _make_callback_service()
        executor = WorkflowExecutor(mock_db, callback_service=callback_service)
        executor._factory = _mock_factory(return_value={"type": "TEXT", "content": "ok"})

        cancel_event = register_cancellation_event("exec_callback_stopped")
        cancel_event.set()

        result = await executor.execute(
            execution_id="exec_callback_stopped",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=_make_nodes("input"),
            edges=[],
            service_tokens={},
        )

        assert result.state == WorkflowState.STOPPED
        callback_service.notify_execution_complete.assert_awaited_once_with(
            "exec_callback_stopped", result
        )


class TestLoopExecution:
    """Loop one-by-one executor-level 반복 실행 테스트."""

    def _make_loop_node(self, node_id: str = "node_2") -> NodeDefinition:
        """runtime_type='loop'인 노드를 생성합니다."""
        return NodeDefinition(
            id=node_id,
            type="loop",
            config={},
            runtime_type="loop",
            runtime_config={"node_type": "loop", "output_data_type": "SINGLE_FILE"},
        )

    def _make_loop_node_email(self, node_id: str = "node_2") -> NodeDefinition:
        return NodeDefinition(
            id=node_id,
            type="loop",
            config={},
            runtime_type="loop",
            runtime_config={"node_type": "loop", "output_data_type": "SINGLE_EMAIL"},
        )

    @pytest.mark.asyncio
    async def test_file_list_loop_executes_body_per_item(self, mock_db):
        """FILE_LIST → loop → llm: body 2회 실행, TEXT aggregate."""
        executor = WorkflowExecutor(mock_db)

        call_count = 0

        async def side_effect(node, input_data, service_tokens):
            nonlocal call_count
            call_count += 1
            node_type = node.get("type", "")
            if node_type == "input":
                return {
                    "type": "FILE_LIST",
                    "items": [
                        {"file_id": "f1", "filename": "a.txt", "content": "aaa"},
                        {"file_id": "f2", "filename": "b.txt", "content": "bbb"},
                    ],
                }
            if node_type == "loop":
                # LoopNodeStrategy just passes through
                return input_data
            if node_type == "llm":
                content = input_data.get("content", "")
                return {"type": "TEXT", "content": f"processed:{content}"}
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
            NodeDefinition(id="node_4", type="output", config={}),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"), ("node_3", "node_4"))

        result = await executor.execute(
            execution_id="exec_loop_1",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.SUCCESS
        # nodeLogs: input, loop, body(node_3 aggregate), output
        assert len(result.nodeLogs) == 4
        body_log = result.nodeLogs[2]
        assert body_log.nodeId == "node_3"
        assert body_log.status == "success"
        assert body_log.outputData["type"] == "TEXT"
        assert body_log.outputData["iterations"] == 2

    @pytest.mark.asyncio
    async def test_file_list_loop_preserves_text_results_for_drive_sink(self, mock_db):
        """FILE_LIST → loop → llm → Google Drive: TEXT 결과를 FILE_LIST로 보존합니다."""
        executor = WorkflowExecutor(mock_db)
        output_input: dict = {}

        async def side_effect(node, input_data, service_tokens):
            node_type = node.get("type", "")
            if node_type == "input":
                return {
                    "type": "FILE_LIST",
                    "items": [
                        {
                            "file_id": "f1",
                            "filename": "a.pdf",
                            "content": "aaa",
                            "mime_type": "application/pdf",
                        },
                        {
                            "file_id": "f2",
                            "filename": "b.docx",
                            "content": "bbb",
                            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        },
                    ],
                }
            if node_type == "loop":
                return input_data
            if node_type == "llm":
                return {
                    "type": "TEXT",
                    "content": f"processed:{input_data.get('content', '')}",
                    "file_id": input_data.get("file_id"),
                    "filename": input_data.get("filename"),
                    "mime_type": input_data.get("mime_type"),
                }
            if node.get("runtime_type") == "output":
                output_input.update(input_data)
                return {"type": "TEXT", "content": "sent"}
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
            NodeDefinition(
                id="node_4",
                type="google_drive",
                config={},
                runtime_type="output",
                runtime_sink={
                    "service": "google_drive",
                    "config": {"folder_id": "folder_123"},
                },
            ),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"), ("node_3", "node_4"))

        result = await executor.execute(
            execution_id="exec_loop_drive",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.SUCCESS
        body_log = result.nodeLogs[2]
        assert body_log.outputData["type"] == "FILE_LIST"
        assert body_log.outputData["iterations"] == 2
        assert body_log.outputData["items"] == [
            {
                "filename": "001-a.txt",
                "mime_type": "text/plain",
                "content": "processed:aaa",
                "source_file_id": "f1",
                "source_filename": "a.pdf",
                "source_mime_type": "application/pdf",
            },
            {
                "filename": "002-b.txt",
                "mime_type": "text/plain",
                "content": "processed:bbb",
                "source_file_id": "f2",
                "source_filename": "b.docx",
                "source_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        ]
        assert output_input["type"] == "FILE_LIST"
        assert len(output_input["items"]) == 2

    @pytest.mark.asyncio
    async def test_file_list_loop_keeps_text_aggregate_for_slack_sink(self, mock_db):
        """FILE_LIST → loop → llm → Slack: FILE_LIST 미지원 sink는 TEXT 집계를 유지합니다."""
        executor = WorkflowExecutor(mock_db)

        async def side_effect(node, input_data, service_tokens):
            node_type = node.get("type", "")
            if node_type == "input":
                return {
                    "type": "FILE_LIST",
                    "items": [
                        {"file_id": "f1", "filename": "a.txt", "content": "aaa"},
                        {"file_id": "f2", "filename": "b.txt", "content": "bbb"},
                    ],
                }
            if node_type == "loop":
                return input_data
            if node_type == "llm":
                return {"type": "TEXT", "content": f"processed:{input_data.get('content', '')}"}
            return {"type": "TEXT", "content": "sent"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
            NodeDefinition(
                id="node_4",
                type="slack",
                config={},
                runtime_type="output",
                runtime_sink={"service": "slack", "config": {"channel": "C123"}},
            ),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"), ("node_3", "node_4"))

        result = await executor.execute(
            execution_id="exec_loop_slack",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.SUCCESS
        body_log = result.nodeLogs[2]
        assert body_log.outputData["type"] == "TEXT"
        assert body_log.outputData["iterations"] == 2
        assert "1. processed:aaa" in body_log.outputData["content"]
        assert "2. processed:bbb" in body_log.outputData["content"]

    @pytest.mark.asyncio
    async def test_email_list_loop_executes_body_per_item(self, mock_db):
        """EMAIL_LIST → loop → llm: SINGLE_EMAIL input per iteration."""
        executor = WorkflowExecutor(mock_db)

        async def side_effect(node, input_data, service_tokens):
            node_type = node.get("type", "")
            if node_type == "input":
                return {
                    "type": "EMAIL_LIST",
                    "items": [
                        {"subject": "Mail 1", "from": "a@x.com", "body": "hi"},
                        {"subject": "Mail 2", "from": "b@x.com", "body": "bye"},
                    ],
                }
            if node_type == "loop":
                return input_data
            if node_type == "llm":
                return {"type": "TEXT", "content": f"reply to: {input_data.get('subject', '')}"}
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node_email("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_loop_email",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.SUCCESS
        body_log = result.nodeLogs[2]
        assert body_log.outputData["iterations"] == 2
        assert "reply to: Mail 1" in body_log.outputData["content"]
        assert "reply to: Mail 2" in body_log.outputData["content"]

    @pytest.mark.asyncio
    async def test_loop_no_outgoing_edge_raises(self, mock_db):
        """Loop에 outgoing edge 없으면 INVALID_REQUEST."""
        executor = WorkflowExecutor(mock_db)

        async def side_effect(node, input_data, service_tokens):
            if node.get("type") == "input":
                return {"type": "FILE_LIST", "items": [{"file_id": "f1"}]}
            return input_data

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
        ]
        edges = _make_edges(("node_1", "node_2"))

        with pytest.raises(FlowifyException):
            await executor.execute(
                execution_id="exec_loop_no_edge",
                workflow_id="wf_1",
                user_id="usr_1",
                nodes=nodes,
                edges=edges,
                service_tokens={},
            )

    @pytest.mark.asyncio
    async def test_loop_multiple_outgoing_edges_raises(self, mock_db):
        """Loop에 outgoing edge가 2개 이상이면 INVALID_REQUEST."""
        executor = WorkflowExecutor(mock_db)

        async def side_effect(node, input_data, service_tokens):
            if node.get("type") == "input":
                return {"type": "FILE_LIST", "items": [{"file_id": "f1"}]}
            return input_data

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
            NodeDefinition(id="node_4", type="llm", config={}),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"), ("node_2", "node_4"))

        with pytest.raises(FlowifyException):
            await executor.execute(
                execution_id="exec_loop_multi_edge",
                workflow_id="wf_1",
                user_id="usr_1",
                nodes=nodes,
                edges=edges,
                service_tokens={},
            )

    @pytest.mark.asyncio
    async def test_loop_body_failure_causes_workflow_failure(self, mock_db):
        """Body node 실패 시 workflow failure."""
        executor = WorkflowExecutor(mock_db)

        async def side_effect(node, input_data, service_tokens):
            node_type = node.get("type", "")
            if node_type == "input":
                return {
                    "type": "FILE_LIST",
                    "items": [{"file_id": "f1"}, {"file_id": "f2"}],
                }
            if node_type == "loop":
                return input_data
            if node_type == "llm":
                raise RuntimeError("LLM API error")
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
            NodeDefinition(id="node_4", type="output", config={}),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"), ("node_3", "node_4"))

        result = await executor.execute(
            execution_id="exec_loop_fail",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.ROLLBACK_AVAILABLE
        body_log = next(log for log in result.nodeLogs if log.nodeId == "node_3")
        assert body_log.status == "failed"
        assert "iteration 0" in body_log.error.message

    @pytest.mark.asyncio
    async def test_body_node_not_re_executed_in_topological_order(self, mock_db):
        """Body node는 handled_nodes에 의해 재실행되지 않는다."""
        executor = WorkflowExecutor(mock_db)
        execution_calls: list[str] = []

        async def side_effect(node, input_data, service_tokens):
            node_id = node.get("id", "")
            node_type = node.get("type", "")
            execution_calls.append(node_id)
            if node_type == "input":
                return {"type": "FILE_LIST", "items": [{"file_id": "f1"}]}
            if node_type == "loop":
                return input_data
            if node_type == "llm":
                return {"type": "TEXT", "content": "done"}
            return {"type": "TEXT", "content": "ok"}

        executor._factory = _mock_factory(side_effect=side_effect)

        nodes = [
            NodeDefinition(id="node_1", type="input", config={}),
            self._make_loop_node("node_2"),
            NodeDefinition(id="node_3", type="llm", config={}),
        ]
        edges = _make_edges(("node_1", "node_2"), ("node_2", "node_3"))

        result = await executor.execute(
            execution_id="exec_loop_no_reexec",
            workflow_id="wf_1",
            user_id="usr_1",
            nodes=nodes,
            edges=edges,
            service_tokens={},
        )

        assert result.state == WorkflowState.SUCCESS
        # The mock is shared, so node_3 appears from loop body execution
        # But the key check: nodeLogs should have exactly 3 entries (no duplicate for node_3)
        assert len(result.nodeLogs) == 3


class TestResolveLoopBodyNodeId:
    """_resolve_loop_body_node_id 유닛 테스트."""

    def test_single_outgoing_returns_target(self):
        edges = _make_edges(("loop_1", "body_1"))
        assert WorkflowExecutor._resolve_loop_body_node_id("loop_1", edges) == "body_1"

    def test_no_outgoing_raises(self):
        edges = _make_edges(("other", "body_1"))
        with pytest.raises(FlowifyException):
            WorkflowExecutor._resolve_loop_body_node_id("loop_1", edges)

    def test_multiple_outgoing_raises(self):
        edges = _make_edges(("loop_1", "body_1"), ("loop_1", "body_2"))
        with pytest.raises(FlowifyException):
            WorkflowExecutor._resolve_loop_body_node_id("loop_1", edges)


class TestToLoopItemPayload:
    """_to_loop_item_payload 유닛 테스트."""

    def test_file_list_to_single_file(self):
        item = {"file_id": "f1", "filename": "a.txt", "content": "hello"}
        result = WorkflowExecutor._to_loop_item_payload("FILE_LIST", "SINGLE_FILE", item, {})
        assert result["type"] == "SINGLE_FILE"
        assert result["file_id"] == "f1"

    def test_email_list_to_single_email(self):
        item = {"subject": "Hi", "from": "a@b.com", "body": "test"}
        result = WorkflowExecutor._to_loop_item_payload("EMAIL_LIST", "SINGLE_EMAIL", item, {})
        assert result["type"] == "SINGLE_EMAIL"
        assert result["subject"] == "Hi"

    def test_spreadsheet_data_row(self):
        loop_input = {"headers": ["name", "age"], "rows": [["Alice", 30]]}
        result = WorkflowExecutor._to_loop_item_payload(
            "SPREADSHEET_DATA", "SPREADSHEET_DATA", ["Alice", 30], loop_input
        )
        assert result == {
            "type": "SPREADSHEET_DATA",
            "headers": ["name", "age"],
            "rows": [["Alice", 30]],
        }

    def test_unsupported_conversion_raises(self):
        with pytest.raises(FlowifyException):
            WorkflowExecutor._to_loop_item_payload("UNKNOWN", "UNKNOWN", {}, {})


class TestAggregateLoopOutputs:
    """_aggregate_loop_outputs 유닛 테스트."""

    def test_text_aggregation(self):
        results = [
            {"type": "TEXT", "content": "first"},
            {"type": "TEXT", "content": "second"},
        ]
        agg = WorkflowExecutor._aggregate_loop_outputs(results)
        assert agg["type"] == "TEXT"
        assert agg["iterations"] == 2
        assert "1. first" in agg["content"]
        assert "2. second" in agg["content"]

    def test_single_file_to_file_list(self):
        results = [
            {"type": "SINGLE_FILE", "file_id": "f1"},
            {"type": "SINGLE_FILE", "file_id": "f2"},
        ]
        agg = WorkflowExecutor._aggregate_loop_outputs(results)
        assert agg["type"] == "FILE_LIST"
        assert len(agg["items"]) == 2

    def test_empty_results(self):
        agg = WorkflowExecutor._aggregate_loop_outputs([])
        assert agg["type"] == "TEXT"
        assert agg["iterations"] == 0

    def test_mixed_types_raises(self):
        results = [
            {"type": "TEXT", "content": "a"},
            {"type": "SINGLE_FILE", "file_id": "f1"},
        ]
        with pytest.raises(FlowifyException):
            WorkflowExecutor._aggregate_loop_outputs(results)


class TestGenerateExecutionId:
    def test_format(self):
        eid = WorkflowExecutor.generate_execution_id()
        assert eid.startswith("exec_")
        assert len(eid) == 17  # "exec_" + 12 hex chars

    def test_unique(self):
        ids = {WorkflowExecutor.generate_execution_id() for _ in range(100)}
        assert len(ids) == 100
