# 작업자 B — 실행 엔진 안정화 & 스케줄러

> 작성일: 2026-04-17 | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/db/mongodb.py` | 🔴 인덱스 필드명 버그 — 즉시 수정 필요 |
| `app/core/engine/executor.py` | 🐛 `_build_branch_map()` IfElse 타입 미확인 버그 |
| `app/core/nodes/logic_node.py` | ⚠️ `LoopNodeStrategy` 서브플로우 TODO |
| `app/services/scheduler_service.py` | ⚠️ jobstore 없음 (in-memory 휘발성) |
| `app/api/v1/endpoints/trigger.py` | ❌ 없음 — 신규 생성 |
| `app/api/v1/router.py` | ⚠️ trigger 라우터 미등록 |
| `app/main.py` | ⚠️ SchedulerService 초기화 누락 |
| `tests/test_loop_node.py` | ❌ 없음 — 신규 작성 |
| `tests/test_scheduler.py` | ❌ 없음 — 신규 작성 |

---

## B-1. [🔴 Critical] MongoDB 인덱스 필드명 수정

**즉시 수정 필요 — 코드 변경 4줄**

### 현재 버그 (`app/db/mongodb.py:48-54`)

```python
async def _create_indexes(db: AsyncIOMotorDatabase) -> None:
    collection = db.workflow_executions
    await collection.create_index("id", unique=True)         # ❌ 실제 필드: "_id"
    await collection.create_index("workflow_id")             # ❌ 실제 필드: "workflowId"
    await collection.create_index("user_id")                 # ❌ 실제 필드: "userId"
    await collection.create_index("started_at")              # ❌ 실제 필드: "startedAt"
```

`WorkflowExecution` 모델(`app/models/execution.py`)은 camelCase 필드를 사용하지만, 인덱스는 snake_case로 생성됨. MongoDB는 존재하지 않는 필드에도 인덱스를 만들지만 쿼리에서 전혀 사용되지 않음.

### 수정

```python
async def _create_indexes(db: AsyncIOMotorDatabase) -> None:
    collection = db.workflow_executions
    # _id는 MongoDB 기본 인덱스 — 별도 생성 불필요
    await collection.create_index("workflowId")
    await collection.create_index("userId")
    await collection.create_index("startedAt")
```

### 기존 잘못된 인덱스 제거 (개발 환경)

기존에 잘못된 인덱스가 이미 DB에 생성되어 있을 수 있음. 개발 환경에서는 아래 명령으로 정리:

```javascript
// MongoDB Shell
db.workflow_executions.dropIndexes()
```

프로덕션 환경이면 개별 인덱스 삭제 후 재생성.

---

## B-2. [🔴 Critical] `_build_branch_map()` — IfElse 타입 필터링

### 현재 버그 (`app/core/engine/executor.py:320-335`)

```python
@staticmethod
def _build_branch_map(edges: list[EdgeDefinition]) -> dict[str, dict[str, str]]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge.target)

    branch_map: dict[str, dict[str, str]] = {}
    for source, targets in outgoing.items():
        if len(targets) == 2:  # ← 모든 노드 타입! IfElse 여부 미확인
            branch_map[source] = {"true": targets[0], "false": targets[1]}
    return branch_map
```

LoopNode, LLMNode 등이 우연히 2개의 outgoing edge를 가지면 잘못된 분기 처리 발생.

### 수정 방향 (권장: IfElse 노드 ID 필터링)

메서드 시그니처에 `nodes` 파라미터 추가 필요. **호출부(`executor.py:93`)도 함께 수정해야 함.**

```python
@staticmethod
def _build_branch_map(
    nodes: list[NodeDefinition], edges: list[EdgeDefinition]
) -> dict[str, dict[str, str]]:
    # IfElse 노드 ID만 추출
    if_else_node_ids = {n.id for n in nodes if n.type == "if_else"}

    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge.target)

    branch_map: dict[str, dict[str, str]] = {}
    for source, targets in outgoing.items():
        if source in if_else_node_ids and len(targets) == 2:
            branch_map[source] = {"true": targets[0], "false": targets[1]}
    return branch_map
```

### 호출부 수정 (`executor.py:93`)

```python
# 기존
branch_map = self._build_branch_map(edges)

# 수정 후
branch_map = self._build_branch_map(nodes, edges)
```

### Edge Label 기반 분기 (선택적 고도화)

작업자 C가 `EdgeDefinition`에 `label` 필드를 추가하면 더 정확한 분기 가능:

```python
# EdgeDefinition에 label이 추가된 경우
for edge in edges:
    if edge.source in if_else_node_ids and edge.label in ("true", "false"):
        if edge.source not in branch_map:
            branch_map[edge.source] = {}
        branch_map[edge.source][edge.label] = edge.target
```

작업자 C (C-3)와 협의 필요.

---

## B-3. [🟡 High] LoopNodeStrategy — 구현 완성

### 현재 상태 (`app/core/nodes/logic_node.py:33-37`)

```python
for i, item in enumerate(items):
    if i >= max_iterations:
        break
    # TODO: 내부 노드 체인 실행  ← 미구현
    results.append(item)
```

현재는 items를 순회하기만 하고 실제 변환 없음. 타임아웃 체크(`DEFAULT_TIMEOUT_SECONDS = 300`)도 선언만 되어 있고 실제로 사용 안 됨.

### 구현 방향 1 (권장 — 중간 발표용 단순 접근)

Loop 노드가 각 아이템에서 특정 필드를 추출하거나 단순 변환:

```python
import time

class LoopNodeStrategy(NodeStrategy):
    async def execute(self, input_data: dict) -> dict:
        items_field = self.config.get("items_field", "items")
        items = input_data.get(items_field, [])
        max_iterations = min(
            self.config.get("max_iterations", MAX_LOOP_ITERATIONS),
            MAX_LOOP_ITERATIONS
        )
        transform_field = self.config.get("transform_field")
        results = []
        start_time = time.monotonic()

        for i, item in enumerate(items):
            if i >= max_iterations:
                break
            if time.monotonic() - start_time > DEFAULT_TIMEOUT_SECONDS:
                break

            if transform_field and isinstance(item, dict):
                results.append(item.get(transform_field, item))
            else:
                results.append(item)

        return {**input_data, "loop_results": results, "iterations": len(results)}
```

### 구현 방향 2 (고도화 — 최종 발표 전 검토)

Loop 내부에서 서브 워크플로우 실행. `WorkflowExecutor`와의 순환 의존성 문제가 있으므로 별도 `SubflowExecutor` 분리 또는 executor를 주입하는 방식 필요. 복잡도가 높으므로 중간 발표 이후에 구현 검토.

---

## B-4. [🟡 High] 스케줄러 API — `trigger.py` 신규 생성

### 개요

`SchedulerService` (`app/services/scheduler_service.py`)는 이미 구현되어 있지만, API 엔드포인트가 없음. `trigger.py` 파일을 신규 생성하고 라우터에 등록해야 함.

### 구현할 엔드포인트

```
POST   /api/v1/triggers              → 스케줄 등록
GET    /api/v1/triggers              → 등록된 스케줄 목록 조회
DELETE /api/v1/triggers/{trigger_id} → 스케줄 삭제
```

### `app/api/v1/endpoints/trigger.py` 생성

```python
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from app.api.v1.deps import get_user_id
from app.services.scheduler_service import SchedulerService

router = APIRouter()


class TriggerCreateRequest(BaseModel):
    workflow_id: str
    trigger_type: str           # "cron" | "interval"
    config: dict = {}           # {"hour": 9, "minute": 0} 또는 {"seconds": 3600}


class TriggerResponse(BaseModel):
    trigger_id: str
    workflow_id: str
    trigger_type: str
    config: dict
    status: str


def get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


@router.post("", response_model=TriggerResponse)
async def create_trigger(
    body: TriggerCreateRequest,
    request: Request,
    user_id: str = Depends(get_user_id),
):
    scheduler = get_scheduler(request)
    trigger_id = f"trigger_{user_id}_{body.workflow_id}"

    if body.trigger_type == "cron":
        scheduler.add_cron_job(
            job_id=trigger_id,
            func=lambda: None,  # TODO: 실제 워크플로우 실행 함수로 교체
            hour=body.config.get("hour", 0),
            minute=body.config.get("minute", 0),
        )
    elif body.trigger_type == "interval":
        scheduler.add_interval_job(
            job_id=trigger_id,
            func=lambda: None,  # TODO: 실제 워크플로우 실행 함수로 교체
            seconds=body.config.get("seconds", 3600),
        )

    return TriggerResponse(
        trigger_id=trigger_id,
        workflow_id=body.workflow_id,
        trigger_type=body.trigger_type,
        config=body.config,
        status="active",
    )


@router.delete("/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
    request: Request,
    user_id: str = Depends(get_user_id),
):
    scheduler = get_scheduler(request)
    scheduler.remove_job(trigger_id)
    return {"trigger_id": trigger_id, "status": "deleted"}
```

### APScheduler MongoDB Jobstore 설정

현재 `SchedulerService`는 메모리에만 저장 → 프로세스 재시작 시 스케줄 손실.

```python
# scheduler_service.py 수정
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class SchedulerService:
    def __init__(self, mongodb_url: str = None):
        jobstores = {}
        if mongodb_url:
            try:
                from apscheduler.jobstores.mongodb import MongoDBJobStore
                jobstores["default"] = MongoDBJobStore(
                    database="flowify",
                    collection="scheduled_jobs",
                    host=mongodb_url,
                )
            except ImportError:
                pass  # MongoDB jobstore 패키지 없으면 in-memory 사용
        self._scheduler = AsyncIOScheduler(jobstores=jobstores or None)
```

`requirements.txt` 확인: `apscheduler` 버전에 따라 MongoDB jobstore 포함 여부 다름.
- `apscheduler>=3.10` → `pip install apscheduler[mongodb]` 필요할 수 있음
- `apscheduler>=4.0` → API 변경으로 `AsyncIOScheduler` 사용 불가, 3.x 버전 고정 권장

---

## B-5. [🟡 High] `main.py` — SchedulerService 초기화 추가

### 현재 문제 (`app/main.py:13-17`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()
```

`SchedulerService`가 초기화되지 않으므로 trigger API에서 `app.state.scheduler`에 접근하면 AttributeError 발생.

### 수정

```python
from app.services.scheduler_service import SchedulerService
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()

    scheduler = SchedulerService(mongodb_url=settings.MONGODB_URL)
    scheduler.start()
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown()
    await close_mongo_connection()
```

### `app/api/v1/router.py` 수정 — trigger 라우터 등록

```python
from app.api.v1.endpoints import execution, health, llm, workflow, trigger

api_router.include_router(trigger.router, prefix="/triggers", tags=["triggers"])
```

---

## B-6. [🟡 High] Stop 엔드포인트 Race Condition 수정

### 현재 문제

`stop` API → `request_cancellation()` → MongoDB 업데이트 순서로 실행됨.
동시에 executor가 마지막 노드를 완료하고 `_save_execution()` 호출 시 STOPPED 상태를 SUCCESS로 덮어쓸 수 있음.

### 수정 (`app/core/engine/executor.py` `_save_execution()`)

최종 상태 저장 시 STOPPED 상태 보호:

```python
async def _save_execution(self, execution_id: str, execution: WorkflowExecution) -> None:
    doc = execution.model_dump(mode="json")
    doc["state"] = execution.state.value if hasattr(execution.state, "value") else execution.state
    doc["_id"] = execution_id

    # STOPPED 상태를 SUCCESS로 덮어쓰지 않도록 조건부 업데이트
    terminal_states = [
        WorkflowState.STOPPED.value,
        WorkflowState.FAILED.value,
        WorkflowState.ROLLBACK_AVAILABLE.value,
    ]

    if execution.state == WorkflowState.SUCCESS:
        # SUCCESS 저장은 STOPPED 상태일 때 무시
        await self._db.workflow_executions.update_one(
            {"_id": execution_id, "state": {"$nin": terminal_states}},
            {"$set": doc},
            upsert=False,
        )
    else:
        await self._db.workflow_executions.update_one(
            {"_id": execution_id},
            {"$set": doc},
            upsert=True,
        )
```

---

## B-7. [🟠 Medium] 테스트 작성

### `tests/test_loop_node.py` (신규)

```python
import pytest
from app.core.nodes.logic_node import LoopNodeStrategy


@pytest.mark.asyncio
async def test_basic_iteration():
    node = LoopNodeStrategy({"items_field": "items"})
    result = await node.execute({"items": [1, 2, 3]})
    assert result["iterations"] == 3
    assert result["loop_results"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_max_iterations_limit():
    node = LoopNodeStrategy({"items_field": "items", "max_iterations": 2})
    result = await node.execute({"items": [1, 2, 3, 4, 5]})
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_empty_items():
    node = LoopNodeStrategy({"items_field": "items"})
    result = await node.execute({})
    assert result["iterations"] == 0
    assert result["loop_results"] == []


@pytest.mark.asyncio
async def test_transform_field():
    node = LoopNodeStrategy({"items_field": "items", "transform_field": "name"})
    items = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    result = await node.execute({"items": items})
    assert result["loop_results"] == ["Alice", "Bob"]


def test_validate_requires_items_field():
    assert LoopNodeStrategy({}).validate() is False
    assert LoopNodeStrategy({"items_field": "items"}).validate() is True
```

### `tests/test_scheduler.py` (신규)

```python
import pytest
from unittest.mock import MagicMock, patch
from app.services.scheduler_service import SchedulerService


def test_scheduler_start_stop():
    svc = SchedulerService()
    svc.start()
    assert svc._scheduler.running
    svc.shutdown()
    assert not svc._scheduler.running


def test_add_and_remove_cron_job():
    svc = SchedulerService()
    svc.start()
    svc.add_cron_job("test_job", func=lambda: None, hour=9, minute=0)
    job = svc._scheduler.get_job("test_job")
    assert job is not None
    svc.remove_job("test_job")
    assert svc._scheduler.get_job("test_job") is None
    svc.shutdown()
```

---

## 잠재적 오류 & 주의사항

### 1. APScheduler 버전 호환성

`requirements.txt`의 현재 APScheduler 버전 확인 필수:
- **3.x**: `AsyncIOScheduler` 사용 가능, MongoDB jobstore는 별도 설치
- **4.x**: API 완전 변경 → `AsyncIOScheduler` 없음, `Scheduler` 클래스 사용

현재 코드는 3.x 스타일이므로 4.x로 업그레이드하면 전면 재작성 필요. 안전하게 3.10.x 버전으로 고정 권장.

### 2. `_build_branch_map` 시그니처 변경 주의

`executor.py`에서 `_build_branch_map(edges)` → `_build_branch_map(nodes, edges)`로 변경하면 호출부(`executor.py:93`)도 반드시 함께 수정해야 함. 누락하면 `TypeError`.

### 3. 싱글톤 스케줄러 접근 방식

`trigger.py`에서 `request.app.state.scheduler`로 접근하므로, 테스트 시 `TestClient`의 `app.state.scheduler` mock 설정이 필요:
```python
from fastapi.testclient import TestClient
app.state.scheduler = MockSchedulerService()
client = TestClient(app)
```

### 4. MongoDB 인덱스 수정 후 기존 데이터

이미 잘못된 인덱스(`workflow_id`, `user_id`, `started_at`)가 생성되어 있을 수 있음. 개발 환경이면 컬렉션 drop 후 재기동 권장. 그렇지 않으면 불필요한 인덱스가 남아있어도 동작에는 영향 없음.

### 5. Stop 엔드포인트 수정 후 테스트

`test_executor.py`에 stop 관련 테스트가 있으면 수정 후 반드시 재실행하여 회귀 없는지 확인.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [ ] `mongodb.py` 인덱스 필드명 수정 (즉시 — 30분)
- [ ] `executor.py` `_build_branch_map()` IfElse 타입 필터링
- [ ] `logic_node.py` LoopNodeStrategy 타임아웃 + 단순 변환 구현
- [ ] `trigger.py` 신규 생성 (기본 CRUD)
- [ ] `main.py` SchedulerService 초기화 추가
- [ ] `router.py` trigger 라우터 등록

**최종 제출 (6/17) 전:**
- [ ] Stop 엔드포인트 race condition 수정
- [ ] APScheduler MongoDB jobstore 설정
- [ ] `tests/test_loop_node.py` 작성
- [ ] `tests/test_scheduler.py` 작성
- [ ] Loop 서브플로우 고도화 (Option 2, 선택적)
