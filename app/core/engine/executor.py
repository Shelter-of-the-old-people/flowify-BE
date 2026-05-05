import asyncio
from collections import defaultdict, deque
import copy
from datetime import UTC, datetime
from pathlib import Path
import traceback
from typing import Any
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings
from app.core.engine.snapshot import SnapshotManager
from app.core.engine.state import WorkflowState, WorkflowStateManager
from app.core.nodes.factory import NodeFactory
from app.core.nodes.output_node import ACCEPTED_INPUT_TYPES
from app.models.execution import (
    ErrorDetail,
    NodeExecutionLog,
    NodeSnapshot,
    WorkflowExecution,
)
from app.models.workflow import EdgeDefinition, NodeDefinition
from app.services.spring_callback_service import SpringExecutionCallbackService

# ── 취소 레지스트리 ──
# execution_id → asyncio.Event. stop 엔드포인트가 event.set() 호출,
# executor가 노드 간 루프에서 is_set() 체크.

_cancellation_events: dict[str, asyncio.Event] = {}


def register_cancellation_event(execution_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _cancellation_events[execution_id] = event
    return event


def request_cancellation(execution_id: str) -> bool:
    event = _cancellation_events.get(execution_id)
    if event:
        event.set()
        return True
    return False


def cleanup_cancellation_event(execution_id: str) -> None:
    _cancellation_events.pop(execution_id, None)


class WorkflowExecutor:
    """워크플로우 실행 엔진.

    v2 runtime contract:
    - runtime_type 기반 전략 선택 (fallback: role + type 추론)
    - canonical payload 기반 노드 간 데이터 전달
    - service_tokens를 별도 파라미터로 전략에 전달
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        callback_service: SpringExecutionCallbackService | None = None,
    ):
        self._db = db
        self._factory = NodeFactory()
        self._callback_service = callback_service or SpringExecutionCallbackService()

    async def execute(
        self,
        execution_id: str,
        workflow_id: str,
        user_id: str,
        nodes: list[NodeDefinition],
        edges: list[EdgeDefinition],
        service_tokens: dict,
    ) -> WorkflowExecution:
        state_manager = WorkflowStateManager()
        snapshot_manager = SnapshotManager()
        node_map = {n.id: n for n in nodes}

        execution = WorkflowExecution(
            workflowId=workflow_id,
            userId=user_id,
            state=WorkflowState.PENDING,
            startedAt=datetime.now(UTC),
        )

        # edges -> 토폴로지 정렬로 실행 순서 결정
        execution_order = self._topological_sort(nodes, edges)
        # edges -> 인접 리스트 (분기 처리용)
        adjacency = self._build_adjacency(edges)
        # IfElse 분기 edge 매핑: source -> {label: target}
        branch_map = self._build_branch_map(nodes, edges)

        state_manager.transition(WorkflowState.RUNNING)
        execution.state = WorkflowState.RUNNING
        await self._save_execution(execution_id, execution)

        # v2: 노드별 출력을 canonical payload로 관리
        node_outputs: dict[str, dict[str, Any]] = {}
        skipped_nodes: set[str] = set()
        handled_nodes: set[str] = set()

        try:
            for node_id in execution_order:
                # ── 취소 체크 ──
                cancel_event = _cancellation_events.get(execution_id)
                if cancel_event and cancel_event.is_set():
                    logged_ids = {log.nodeId for log in execution.nodeLogs}
                    for rem_id in execution_order:
                        if rem_id not in logged_ids:
                            execution.nodeLogs.append(
                                NodeExecutionLog(
                                    nodeId=rem_id,
                                    status="skipped",
                                    startedAt=datetime.now(UTC),
                                    finishedAt=datetime.now(UTC),
                                )
                            )
                    state_manager.transition(WorkflowState.STOPPED)
                    execution.state = WorkflowState.STOPPED
                    execution.errorMessage = "Execution stopped by user request"
                    execution.finishedAt = datetime.now(UTC)
                    await self._finalize_execution(execution_id, execution)
                    return execution

                if node_id in skipped_nodes or node_id in handled_nodes:
                    if node_id in skipped_nodes:
                        execution.nodeLogs.append(
                            NodeExecutionLog(
                                nodeId=node_id,
                                status="skipped",
                                startedAt=datetime.now(UTC),
                                finishedAt=datetime.now(UTC),
                            )
                        )
                    continue

                node_def = node_map[node_id]

                # v2: predecessor의 canonical payload를 input_data로 전달
                prev_node_ids = self._get_predecessors(node_id, edges)
                input_data: dict[str, Any] | None = None
                if prev_node_ids:
                    input_data = node_outputs.get(prev_node_ids[0])

                node_log = await self._execute_node(
                    node_def, input_data, service_tokens, snapshot_manager
                )
                execution.nodeLogs.append(node_log)

                if node_log.status == "failed":
                    # 실패 시: 이후 모든 노드 skip
                    logged_ids = {log.nodeId for log in execution.nodeLogs}
                    for rem_id in execution_order:
                        if rem_id not in logged_ids:
                            execution.nodeLogs.append(
                                NodeExecutionLog(
                                    nodeId=rem_id,
                                    status="skipped",
                                    startedAt=datetime.now(UTC),
                                    finishedAt=datetime.now(UTC),
                                )
                            )

                    state_manager.transition(WorkflowState.FAILED)
                    state_manager.transition(WorkflowState.ROLLBACK_AVAILABLE)
                    execution.state = WorkflowState.ROLLBACK_AVAILABLE
                    execution.errorMessage = (
                        node_log.error.message if node_log.error else "노드 실행 실패"
                    )
                    execution.finishedAt = datetime.now(UTC)
                    await self._finalize_execution(execution_id, execution)
                    return execution

                # v2: 성공 시 canonical payload를 node_outputs에 저장
                node_outputs[node_id] = node_log.outputData or {}

                # Loop 반복 실행 처리
                runtime_type = getattr(node_def, "runtime_type", None) or node_def.type
                if runtime_type == "loop":
                    loop_output = node_outputs[node_id]
                    body_node_id = self._resolve_loop_body_node_id(node_id, edges)

                    if body_node_id not in node_map:
                        raise FlowifyException(
                            ErrorCode.INVALID_REQUEST,
                            detail=f"Loop body node '{body_node_id}' not found in workflow.",
                        )

                    body_node_def = node_map[body_node_id]
                    downstream_nodes = self._get_direct_downstream_nodes(
                        body_node_id, edges, node_map
                    )
                    aggregate_log = await self._execute_loop_body(
                        loop_node_def=node_def,
                        body_node_def=body_node_def,
                        loop_output=loop_output,
                        service_tokens=service_tokens,
                        snapshot_manager=snapshot_manager,
                        downstream_nodes=downstream_nodes,
                    )
                    execution.nodeLogs.append(aggregate_log)

                    if aggregate_log.status == "failed":
                        logged_ids = {log.nodeId for log in execution.nodeLogs}
                        for rem_id in execution_order:
                            if rem_id not in logged_ids:
                                execution.nodeLogs.append(
                                    NodeExecutionLog(
                                        nodeId=rem_id,
                                        status="skipped",
                                        startedAt=datetime.now(UTC),
                                        finishedAt=datetime.now(UTC),
                                    )
                                )
                        state_manager.transition(WorkflowState.FAILED)
                        state_manager.transition(WorkflowState.ROLLBACK_AVAILABLE)
                        execution.state = WorkflowState.ROLLBACK_AVAILABLE
                        execution.errorMessage = (
                            aggregate_log.error.message
                            if aggregate_log.error
                            else "Loop body execution failed"
                        )
                        execution.finishedAt = datetime.now(UTC)
                        await self._finalize_execution(execution_id, execution)
                        return execution

                    node_outputs[body_node_id] = aggregate_log.outputData or {}
                    handled_nodes.add(body_node_id)
                    continue

                # IfElse 분기 처리: branch 값에 따라 반대쪽 서브트리 skip
                output_data = node_outputs[node_id]
                if (
                    runtime_type == "if_else"
                    and isinstance(output_data, dict)
                    and "branch" in output_data
                ):
                    branch_value = output_data["branch"]  # "true" or "false"
                    skip_value = "false" if branch_value == "true" else "true"
                    if node_id in branch_map:
                        skip_target = branch_map[node_id].get(skip_value)
                        if skip_target:
                            descendants = self._get_descendants(skip_target, adjacency)
                            skipped_nodes.update(descendants)
                            skipped_nodes.add(skip_target)

            state_manager.transition(WorkflowState.SUCCESS)
            execution.state = WorkflowState.SUCCESS
            execution.finishedAt = datetime.now(UTC)
            await self._finalize_execution(execution_id, execution)
            return execution

        finally:
            cleanup_cancellation_event(execution_id)

    async def _execute_node(
        self,
        node_def: NodeDefinition,
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
        snapshot_manager: SnapshotManager,
    ) -> NodeExecutionLog:
        """단일 노드 실행. 스냅샷 저장, 타이밍 측정, 에러 캐치."""
        started_at = datetime.now(UTC)

        # 실행 전 스냅샷 저장
        snapshot_data = self._sanitize_for_log(input_data)
        snapshot_manager.save(node_def.id, input_data or {})

        # v2: runtime_type 기반 전략 생성
        node = self._factory.create_from_node_def(node_def)
        # node dict로 변환 (runtime 필드 포함, snake_case 유지)
        node_dict = node_def.model_dump(by_alias=False)

        try:
            output_data = await node.execute(
                node=node_dict,
                input_data=input_data,
                service_tokens=service_tokens,
            )

            return NodeExecutionLog(
                nodeId=node_def.id,
                status="success",
                inputData=self._sanitize_for_log(input_data),
                outputData=self._sanitize_for_log(output_data),
                snapshot=NodeSnapshot(
                    capturedAt=started_at,
                    stateData=snapshot_data,
                ),
                startedAt=started_at,
                finishedAt=datetime.now(UTC),
            )

        except FlowifyException as e:
            return NodeExecutionLog(
                nodeId=node_def.id,
                status="failed",
                inputData=self._sanitize_for_log(input_data),
                snapshot=NodeSnapshot(
                    capturedAt=started_at,
                    stateData=snapshot_data,
                ),
                error=ErrorDetail(
                    code=e.error_code.name,
                    message=e.detail,
                    stackTrace=traceback.format_exc() if settings.APP_DEBUG else None,
                ),
                startedAt=started_at,
                finishedAt=datetime.now(UTC),
            )

        except Exception as e:
            return NodeExecutionLog(
                nodeId=node_def.id,
                status="failed",
                inputData=self._sanitize_for_log(input_data),
                snapshot=NodeSnapshot(
                    capturedAt=started_at,
                    stateData=snapshot_data,
                ),
                error=ErrorDetail(
                    code=ErrorCode.NODE_EXECUTION_FAILED.name,
                    message=str(e),
                    stackTrace=traceback.format_exc() if settings.APP_DEBUG else None,
                ),
                startedAt=started_at,
                finishedAt=datetime.now(UTC),
            )

    async def _save_execution(self, execution_id: str, execution: WorkflowExecution) -> None:
        """실행 상태를 MongoDB에 upsert합니다."""
        doc = execution.model_dump(mode="json")
        doc["state"] = (
            execution.state.value if hasattr(execution.state, "value") else execution.state
        )
        doc["_id"] = execution_id

        # STOPPED 상태를 SUCCESS로 덮어쓰지 않도록 조건부 upsert
        if doc.get("state") == WorkflowState.SUCCESS.value:
            await self._db.workflow_executions.update_one(
                {"_id": execution_id, "state": {"$ne": WorkflowState.STOPPED.value}},
                {"$set": doc},
                upsert=True,
            )
        else:
            await self._db.workflow_executions.update_one(
                {"_id": execution_id},
                {"$set": doc},
                upsert=True,
            )

    async def _finalize_execution(self, execution_id: str, execution: WorkflowExecution) -> None:
        """종료 상태를 저장하고 Spring 완료 콜백을 전송합니다."""
        await self._save_execution(execution_id, execution)
        await self._callback_service.notify_execution_complete(execution_id, execution)

    @staticmethod
    def _sanitize_for_log(data: dict | None) -> dict:
        """로깅/스냅샷용: credentials 등 민감 정보 제거."""
        if not data:
            return {}
        cleaned = copy.deepcopy(data)
        cleaned.pop("credentials", None)
        return cleaned

    @staticmethod
    def _get_predecessors(node_id: str, edges: list[EdgeDefinition]) -> list[str]:
        """주어진 노드의 선행 노드 ID 목록을 반환."""
        return [e.source for e in edges if e.target == node_id]

    @staticmethod
    def _topological_sort(nodes: list[NodeDefinition], edges: list[EdgeDefinition]) -> list[str]:
        """edges 기반 토폴로지 정렬 (Kahn's algorithm)."""
        in_degree: dict[str, int] = {n.id: 0 for n in nodes}
        adj: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            adj[edge.source].append(edge.target)
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: list[str] = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(nodes):
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="워크플로우에 순환 참조가 있습니다.",
            )
        return result

    @staticmethod
    def _build_adjacency(edges: list[EdgeDefinition]) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adj[edge.source].append(edge.target)
        return adj

    @staticmethod
    def _get_direct_downstream_nodes(
        node_id: str,
        edges: list[EdgeDefinition],
        node_map: dict[str, NodeDefinition],
    ) -> list[NodeDefinition]:
        return [
            node_map[edge.target]
            for edge in edges
            if edge.source == node_id and edge.target in node_map
        ]

    @staticmethod
    def _build_branch_map(
        nodes: list[NodeDefinition], edges: list[EdgeDefinition]
    ) -> dict[str, dict[str, str]]:
        """IfElse 분기 매핑 생성.

        label이 있는 edge는 label 기반으로, 없으면 if_else 노드에 한해
        첫 번째 edge를 true, 두 번째를 false로 간주합니다.
        """
        if_else_ids = {
            n.id for n in nodes if (getattr(n, "runtime_type", None) or n.type) == "if_else"
        }

        # label이 있는 edge 먼저 처리
        branch_map: dict[str, dict[str, str]] = {}
        for edge in edges:
            if edge.source in if_else_ids and edge.label in ("true", "false"):
                branch_map.setdefault(edge.source, {})[edge.label] = edge.target

        # label 없는 경우: if_else 노드의 outgoing edge 순서로 true/false 지정
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.source in if_else_ids and edge.label not in ("true", "false"):
                outgoing[edge.source].append(edge.target)

        for source, targets in outgoing.items():
            if source not in branch_map and len(targets) == 2:
                branch_map[source] = {"true": targets[0], "false": targets[1]}

        return branch_map

    @staticmethod
    def _get_descendants(start: str, adjacency: dict[str, list[str]]) -> set[str]:
        """BFS로 start 노드의 모든 후손 노드를 반환합니다."""
        visited: set[str] = set()
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for child in adjacency.get(node, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited

    # ── Loop helpers ──

    @staticmethod
    def _resolve_loop_body_node_id(loop_node_id: str, edges: list[EdgeDefinition]) -> str:
        """Loop 노드의 첫 번째 outgoing target을 body node로 반환한다.

        v1 제약: outgoing edge가 정확히 1개여야 한다.
        """
        targets = [e.target for e in edges if e.source == loop_node_id]
        if len(targets) == 0:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Loop node '{loop_node_id}' has no outgoing edge.",
            )
        if len(targets) > 1:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Loop node '{loop_node_id}' has multiple outgoing edges. v1 supports single body node only.",
            )
        return targets[0]

    @staticmethod
    def _to_loop_item_payload(
        source_type: str,
        item_type: str,
        item: dict[str, Any] | list[Any],
        loop_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Loop items의 개별 항목을 body node용 canonical payload로 변환."""
        if source_type == "FILE_LIST" and item_type == "SINGLE_FILE":
            payload = dict(item) if isinstance(item, dict) else {}
            payload["type"] = "SINGLE_FILE"
            return payload

        if source_type == "EMAIL_LIST" and item_type == "SINGLE_EMAIL":
            payload = dict(item) if isinstance(item, dict) else {}
            payload["type"] = "SINGLE_EMAIL"
            return payload

        if source_type == "SPREADSHEET_DATA" and item_type == "SPREADSHEET_DATA":
            row = item if isinstance(item, list) else []
            return {
                "type": "SPREADSHEET_DATA",
                "headers": loop_input.get("headers", []),
                "rows": [row],
            }

        if source_type == "SCHEDULE_DATA" and item_type == "SCHEDULE_DATA":
            entry = item if isinstance(item, dict) else {}
            return {
                "type": "SCHEDULE_DATA",
                "items": [entry],
            }

        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail=f"Unsupported loop item conversion: {source_type} -> {item_type}",
        )

    @staticmethod
    def _aggregate_loop_outputs(
        results: list[dict[str, Any]],
        preserve_text_as_file_list: bool = False,
    ) -> dict[str, Any]:
        """Body node 반복 결과를 기존 canonical type으로 집계한다."""
        if not results:
            return {"type": "TEXT", "content": "", "loop_results": [], "iterations": 0}

        output_type = results[0].get("type", "TEXT")

        # 혼합 타입 검사
        for r in results:
            if r.get("type", "TEXT") != output_type:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Loop body produced mixed output types. v1 does not support this.",
                )

        iterations = len(results)

        if output_type == "TEXT":
            if preserve_text_as_file_list:
                return {
                    "type": "FILE_LIST",
                    "items": [
                        WorkflowExecutor._text_result_to_file_item(result, idx)
                        for idx, result in enumerate(results, start=1)
                    ],
                    "loop_results": results,
                    "iterations": iterations,
                }

            parts = []
            for idx, r in enumerate(results, start=1):
                parts.append(f"{idx}. {r.get('content', '')}")
            return {
                "type": "TEXT",
                "content": "\n\n---\n\n".join(parts),
                "loop_results": results,
                "iterations": iterations,
            }

        if output_type == "SINGLE_FILE":
            return {
                "type": "FILE_LIST",
                "items": results,
                "loop_results": results,
                "iterations": iterations,
            }

        if output_type == "SINGLE_EMAIL":
            return {
                "type": "EMAIL_LIST",
                "items": results,
                "loop_results": results,
                "iterations": iterations,
            }

        if output_type == "SPREADSHEET_DATA":
            headers = results[0].get("headers", [])
            all_rows: list[list] = []
            for r in results:
                all_rows.extend(r.get("rows", []))
            return {
                "type": "SPREADSHEET_DATA",
                "headers": headers,
                "rows": all_rows,
                "loop_results": results,
                "iterations": iterations,
            }

        # Fallback for other types
        return {
            "type": output_type,
            "loop_results": results,
            "iterations": iterations,
        }

    @staticmethod
    def _should_preserve_text_results_as_file_list(
        downstream_nodes: list[NodeDefinition],
    ) -> bool:
        if not downstream_nodes:
            return False

        for node in downstream_nodes:
            runtime_type = getattr(node, "runtime_type", None) or node.type
            if runtime_type != "output":
                return False

            runtime_sink = getattr(node, "runtime_sink", None)
            if runtime_sink is None:
                return False

            accepted_types = ACCEPTED_INPUT_TYPES.get(runtime_sink.service, set())
            if "FILE_LIST" not in accepted_types:
                return False

        return True

    @staticmethod
    def _text_result_to_file_item(result: dict[str, Any], index: int) -> dict[str, Any]:
        source_filename = result.get("filename") or f"loop-result-{index}"
        item: dict[str, Any] = {
            "filename": WorkflowExecutor._to_text_result_filename(str(source_filename), index),
            "mime_type": "text/plain",
            "content": result.get("content", ""),
        }

        passthrough_keys = {
            "file_id": "source_file_id",
            "filename": "source_filename",
            "mime_type": "source_mime_type",
            "url": "source_url",
            "created_time": "source_created_time",
            "modified_time": "source_modified_time",
        }
        for source_key, target_key in passthrough_keys.items():
            value = result.get(source_key)
            if value not in (None, ""):
                item[target_key] = value

        return item

    @staticmethod
    def _to_text_result_filename(source_filename: str, index: int) -> str:
        stem = Path(source_filename).stem or f"loop-result-{index}"
        return f"{index:03d}-{stem}.txt"

    async def _execute_loop_body(
        self,
        loop_node_def: NodeDefinition,
        body_node_def: NodeDefinition,
        loop_output: dict[str, Any],
        service_tokens: dict[str, str],
        snapshot_manager: "SnapshotManager",
        downstream_nodes: list[NodeDefinition] | None = None,
    ) -> NodeExecutionLog:
        """Loop body node를 items 수만큼 반복 실행하고 aggregate log를 반환."""
        started_at = datetime.now(UTC)

        # Loop output에서 items 추출
        items = loop_output.get("items", [])
        source_type = loop_output.get("type", "")

        # item type은 loop node의 runtime_config.output_data_type에서 결정
        rc = loop_node_def.runtime_config
        item_type = rc.output_data_type if rc else ""
        if not item_type:
            item_type = "SINGLE_FILE"  # fallback

        # Body node strategy 생성
        body_strategy = self._factory.create_from_node_def(body_node_def)
        body_node_dict = body_node_def.model_dump(by_alias=False)

        body_results: list[dict[str, Any]] = []

        for idx, item in enumerate(items):
            try:
                item_payload = self._to_loop_item_payload(source_type, item_type, item, loop_output)
            except FlowifyException as e:
                return NodeExecutionLog(
                    nodeId=body_node_def.id,
                    status="failed",
                    inputData=self._sanitize_for_log(loop_output),
                    error=ErrorDetail(
                        code=e.error_code.name,
                        message=e.detail,
                        context={"iteration": idx},
                    ),
                    startedAt=started_at,
                    finishedAt=datetime.now(UTC),
                )

            try:
                result = await body_strategy.execute(
                    node=body_node_dict,
                    input_data=item_payload,
                    service_tokens=service_tokens,
                )
                body_results.append(result)
            except FlowifyException as e:
                return NodeExecutionLog(
                    nodeId=body_node_def.id,
                    status="failed",
                    inputData=self._sanitize_for_log(loop_output),
                    error=ErrorDetail(
                        code=e.error_code.name,
                        message=f"Loop body failed at iteration {idx}: {e.detail}",
                        context={"iteration": idx, "body_node_id": body_node_def.id},
                    ),
                    startedAt=started_at,
                    finishedAt=datetime.now(UTC),
                )
            except Exception as e:
                return NodeExecutionLog(
                    nodeId=body_node_def.id,
                    status="failed",
                    inputData=self._sanitize_for_log(loop_output),
                    error=ErrorDetail(
                        code=ErrorCode.NODE_EXECUTION_FAILED.name,
                        message=f"Loop body failed at iteration {idx}: {e!s}",
                        context={"iteration": idx, "body_node_id": body_node_def.id},
                    ),
                    startedAt=started_at,
                    finishedAt=datetime.now(UTC),
                )

        # 집계
        try:
            preserve_text_as_file_list = self._should_preserve_text_results_as_file_list(
                downstream_nodes or []
            )
            aggregate_output = self._aggregate_loop_outputs(
                body_results,
                preserve_text_as_file_list=preserve_text_as_file_list,
            )
        except FlowifyException as e:
            return NodeExecutionLog(
                nodeId=body_node_def.id,
                status="failed",
                inputData=self._sanitize_for_log(loop_output),
                error=ErrorDetail(
                    code=e.error_code.name,
                    message=e.detail,
                ),
                startedAt=started_at,
                finishedAt=datetime.now(UTC),
            )

        # 성공 aggregate log
        input_summary = {
            "type": source_type,
            "items": items,
            "iterations": len(items),
        }

        return NodeExecutionLog(
            nodeId=body_node_def.id,
            status="success",
            inputData=self._sanitize_for_log(input_summary),
            outputData=self._sanitize_for_log(aggregate_output),
            snapshot=NodeSnapshot(
                capturedAt=started_at,
                stateData=self._sanitize_for_log(input_summary),
            ),
            startedAt=started_at,
            finishedAt=datetime.now(UTC),
        )

    @staticmethod
    def generate_execution_id() -> str:
        return f"exec_{uuid.uuid4().hex[:12]}"
