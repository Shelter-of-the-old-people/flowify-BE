import copy
import time
import traceback
import uuid
from collections import defaultdict, deque
from datetime import datetime

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


class WorkflowExecutor:
    """워크플로우 실행 엔진.

    edges 기반 토폴로지 정렬, 스냅샷, MongoDB 로깅, IfElse 분기 처리를 지원합니다.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._factory = NodeFactory()

    async def execute(
        self,
        execution_id: str,
        workflow_id: str,
        user_id: str,
        nodes: list[NodeDefinition],
        edges: list[EdgeDefinition],
        credentials: dict,
    ) -> WorkflowExecution:
        state_manager = WorkflowStateManager()
        snapshot_manager = SnapshotManager()
        node_map = {n.id: n for n in nodes}

        execution = WorkflowExecution(
            id=execution_id,
            workflow_id=workflow_id,
            user_id=user_id,
            state=WorkflowState.PENDING,
            started_at=datetime.utcnow(),
        )

        # edges -> 토폴로지 정렬로 실행 순서 결정
        execution_order = self._topological_sort(nodes, edges)
        # edges -> 인접 리스트 (분기 처리용)
        adjacency = self._build_adjacency(edges)
        # IfElse 분기 edge 매핑: source -> {label: target}
        branch_map = self._build_branch_map(edges)

        state_manager.transition(WorkflowState.RUNNING)
        execution.state = WorkflowState.RUNNING
        await self._save_execution(execution)

        data: dict = {"credentials": credentials}
        skipped_nodes: set[str] = set()

        for node_id in execution_order:
            if node_id in skipped_nodes:
                # 분기에 의해 skip된 노드
                execution.node_logs.append(
                    NodeExecutionLog(
                        node_id=node_id,
                        status="skipped",
                        started_at=datetime.utcnow(),
                        finished_at=datetime.utcnow(),
                    )
                )
                continue

            node_def = node_map[node_id]
            node_log = await self._execute_node(
                node_def, data, snapshot_manager
            )
            execution.node_logs.append(node_log)

            if node_log.status == "failed":
                # 실패 시: 이후 모든 노드 skip
                remaining = set(execution_order) - {
                    log.node_id for log in execution.node_logs
                }
                for rem_id in execution_order:
                    if rem_id in remaining:
                        execution.node_logs.append(
                            NodeExecutionLog(
                                node_id=rem_id,
                                status="skipped",
                                started_at=datetime.utcnow(),
                                finished_at=datetime.utcnow(),
                            )
                        )

                state_manager.transition(WorkflowState.FAILED)
                state_manager.transition(WorkflowState.ROLLBACK_AVAILABLE)
                execution.state = WorkflowState.ROLLBACK_AVAILABLE
                execution.error_message = node_log.error.message if node_log.error else "노드 실행 실패"
                execution.finished_at = datetime.utcnow()
                await self._save_execution(execution)
                return execution

            # 성공 시 output을 다음 데이터로 전파
            data = node_log.output_data

            # IfElse 분기 처리: branch 값에 따라 반대쪽 서브트리 skip
            if node_def.type == "if_else" and "branch" in data:
                branch_value = data["branch"]  # "true" or "false"
                skip_value = "false" if branch_value == "true" else "true"
                if node_id in branch_map:
                    skip_target = branch_map[node_id].get(skip_value)
                    if skip_target:
                        descendants = self._get_descendants(skip_target, adjacency)
                        skipped_nodes.update(descendants)
                        skipped_nodes.add(skip_target)

        state_manager.transition(WorkflowState.SUCCESS)
        execution.state = WorkflowState.SUCCESS
        execution.finished_at = datetime.utcnow()
        await self._save_execution(execution)
        return execution

    async def _execute_node(
        self,
        node_def: NodeDefinition,
        input_data: dict,
        snapshot_manager: SnapshotManager,
    ) -> NodeExecutionLog:
        """단일 노드 실행. 스냅샷 저장, 타이밍 측정, 에러 캐치."""
        started_at = datetime.utcnow()

        # 실행 전 스냅샷 저장
        snapshot_data = self._strip_credentials(input_data)
        snapshot_manager.save(node_def.id, input_data)

        try:
            node = self._factory.create(node_def.type, node_def.config)
            start_time = time.monotonic()
            output_data = await node.execute(input_data)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            return NodeExecutionLog(
                node_id=node_def.id,
                status="success",
                input_data=self._strip_credentials(input_data),
                output_data=self._strip_credentials(output_data),
                snapshot=NodeSnapshot(
                    captured_at=started_at,
                    state_data=snapshot_data,
                ),
                duration_ms=duration_ms,
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )

        except FlowifyException as e:
            return NodeExecutionLog(
                node_id=node_def.id,
                status="failed",
                input_data=self._strip_credentials(input_data),
                snapshot=NodeSnapshot(
                    captured_at=started_at,
                    state_data=snapshot_data,
                ),
                error=ErrorDetail(
                    code=e.error_code.name,
                    message=e.detail,
                    stack_trace=traceback.format_exc() if settings.APP_DEBUG else None,
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )

        except Exception as e:
            return NodeExecutionLog(
                node_id=node_def.id,
                status="failed",
                input_data=self._strip_credentials(input_data),
                snapshot=NodeSnapshot(
                    captured_at=started_at,
                    state_data=snapshot_data,
                ),
                error=ErrorDetail(
                    code=ErrorCode.NODE_EXECUTION_FAILED.name,
                    message=str(e),
                    stack_trace=traceback.format_exc() if settings.APP_DEBUG else None,
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )

    async def _save_execution(self, execution: WorkflowExecution) -> None:
        """실행 상태를 MongoDB에 upsert합니다."""
        doc = execution.model_dump(mode="json")
        await self._db.workflow_executions.update_one(
            {"id": execution.id},
            {"$set": doc},
            upsert=True,
        )

    @staticmethod
    def _strip_credentials(data: dict) -> dict:
        """credentials 필드를 제거한 복사본을 반환합니다."""
        if not data:
            return {}
        cleaned = copy.deepcopy(data)
        cleaned.pop("credentials", None)
        return cleaned

    @staticmethod
    def _topological_sort(
        nodes: list[NodeDefinition], edges: list[EdgeDefinition]
    ) -> list[str]:
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
    def _build_branch_map(edges: list[EdgeDefinition]) -> dict[str, dict[str, str]]:
        """IfElse 분기 매핑 생성.

        EdgeDefinition에 label이 없으면, source에서 나가는 edge가 2개인 경우
        첫 번째를 true, 두 번째를 false로 간주합니다.
        """
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            outgoing[edge.source].append(edge.target)

        branch_map: dict[str, dict[str, str]] = {}
        for source, targets in outgoing.items():
            if len(targets) == 2:
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
