import asyncio
from collections import defaultdict, deque
import copy
from datetime import datetime
import traceback
from typing import Any
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.common.errors import ErrorCode, FlowifyException
from app.config import settings
from app.core.engine.snapshot import SnapshotManager
from app.core.engine.state import WorkflowState, WorkflowStateManager
from app.core.nodes.factory import NodeFactory
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
            startedAt=datetime.utcnow(),
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
                                    startedAt=datetime.utcnow(),
                                    finishedAt=datetime.utcnow(),
                                )
                            )
                    state_manager.transition(WorkflowState.STOPPED)
                    execution.state = WorkflowState.STOPPED
                    execution.errorMessage = "Execution stopped by user request"
                    execution.finishedAt = datetime.utcnow()
                    await self._finalize_execution(execution_id, execution)
                    return execution

                if node_id in skipped_nodes:
                    execution.nodeLogs.append(
                        NodeExecutionLog(
                            nodeId=node_id,
                            status="skipped",
                            startedAt=datetime.utcnow(),
                            finishedAt=datetime.utcnow(),
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
                                    startedAt=datetime.utcnow(),
                                    finishedAt=datetime.utcnow(),
                                )
                            )

                    state_manager.transition(WorkflowState.FAILED)
                    state_manager.transition(WorkflowState.ROLLBACK_AVAILABLE)
                    execution.state = WorkflowState.ROLLBACK_AVAILABLE
                    execution.errorMessage = (
                        node_log.error.message if node_log.error else "노드 실행 실패"
                    )
                    execution.finishedAt = datetime.utcnow()
                    await self._finalize_execution(execution_id, execution)
                    return execution

                # v2: 성공 시 canonical payload를 node_outputs에 저장
                node_outputs[node_id] = node_log.outputData or {}

                # IfElse 분기 처리: branch 값에 따라 반대쪽 서브트리 skip
                runtime_type = getattr(node_def, "runtime_type", None) or node_def.type
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
            execution.finishedAt = datetime.utcnow()
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
        started_at = datetime.utcnow()

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
                finishedAt=datetime.utcnow(),
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
                finishedAt=datetime.utcnow(),
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
                finishedAt=datetime.utcnow(),
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

    @staticmethod
    def generate_execution_id() -> str:
        return f"exec_{uuid.uuid4().hex[:12]}"
