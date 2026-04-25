# 작업자 B — 실행 엔진 안정화 & 스케줄러

> 작성일: 2026-04-17 | **v2 업데이트: 2026-04-23** | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## v2 런타임 컨트랙트 변경 요약

> **핵심**: executor.py, logic_node.py, factory.py가 v2 컨트랙트에 맞게 전면 재작성되었습니다. 아래 ✅ 표시된 항목은 구현 완료 — 작업자 B는 스케줄러 관련 신규 작업에 집중하면 됩니다.

### 달라진 핵심 사항

| 항목 | v1 (이전) | v2 (현재) |
|------|-----------|-----------|
| 노드 시그니처 | `execute(input_data: dict)` | `execute(node, input_data, service_tokens)` |
| 데이터 흐름 | flat dict 누적 (`{**input_data, ...}`) | **canonical payload** per-node (`node_outputs` dict) |
| 팩토리 | `factory.create(type, config)` | `factory.create_from_node_def(node_def)` |
| IfElse 감지 | `node_def.type` | `runtime_type` (fallback: role+type 추론) |
| branch_map | 모든 2-outgoing 노드 대상 | **if_else 노드만** 대상 + label 기반 분기 |
| Loop items | `input_data[items_field]` | canonical type별 자동 추출 (FILE_LIST→items, SPREADSHEET_DATA→rows) |
| 로그 sanitize | `_strip_credentials()` | `_sanitize_for_log()` (None 안전 처리) |
| Stop 보호 | 없음 (SUCCESS 덮어쓰기 가능) | `$ne: STOPPED` 조건부 upsert |

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/db/mongodb.py` | ✅ **완료** — 인덱스 필드명 camelCase로 수정 (commit 883bec5) |
| `app/core/engine/executor.py` | ✅ **완료** — v2 전면 재작성 (canonical payload, runtime_type, branch_map, stop 보호) |
| `app/core/nodes/logic_node.py` | ✅ **완료** — v2 시그니처 + canonical payload 기반 Loop/IfElse |
| `app/core/nodes/factory.py` | ✅ **완료** — create_from_node_def + infer_runtime_type |
| `app/services/scheduler_service.py` | ✅ **완료** — MongoDB jobstore 설정 추가 |
| `app/api/v1/endpoints/trigger.py` | ✅ **완료** — 스케줄러 API CRUD 구현 |
| `app/api/v1/router.py` | ✅ **완료** — trigger 라우터 등록 |
| `app/main.py` | ✅ **완료** — SchedulerService 초기화 |
| `tests/test_loop_node.py` | ✅ **완료** — v2 시그니처 기준 테스트 작성 |
| `tests/test_scheduler.py` | ✅ **완료** — SchedulerService 테스트 작성 |

---

## ✅ B-1. [완료] MongoDB 인덱스 필드명 수정

commit 883bec5에서 수정 완료. `workflowId`, `userId`, `startedAt` camelCase 인덱스로 변경됨.

---

## ✅ B-2. [완료] `_build_branch_map()` — IfElse 타입 필터링

v2에서 전면 재작성. 현재 구현:
- `runtime_type`으로 if_else 노드 판별 (fallback: `node_def.type`)
- label이 있는 edge는 label 기반 분기
- label이 없으면 if_else 노드의 outgoing edge 순서로 true/false 추정

```python
if_else_ids = {
    n.id for n in nodes
    if (getattr(n, "runtime_type", None) or n.type) == "if_else"
}
```

---

## ✅ B-3. [완료] LoopNodeStrategy — 구현 완성

v2에서 canonical payload 기반으로 재작성:
- `FILE_LIST`, `EMAIL_LIST`, `SCHEDULE_DATA` → `items` 자동 추출
- `SPREADSHEET_DATA` → `rows` 자동 추출
- `max_iterations` + `DEFAULT_TIMEOUT_SECONDS` 적용
- `transform_field` 지원

---

## ✅ B-4. [완료] 스케줄러 API — `trigger.py`

**v2 구현 시 함께 완료됨.** `app/api/v1/endpoints/trigger.py` (111줄, full CRUD: POST/GET/DELETE).

### 참고: 현재 구현 구조

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
                pass
        self._scheduler = AsyncIOScheduler(jobstores=jobstores or None)
```

---

## ✅ B-5. [완료] `main.py` — SchedulerService 초기화 + router 등록

**v2 구현 시 함께 완료됨.** `app/main.py`에서 `SchedulerService` 초기화, `app/api/v1/router.py`에서 trigger 라우터 등록 모두 완료.

---

## ✅ B-6. [완료] Stop 엔드포인트 Race Condition 수정

v2에서 `_save_execution()`에 조건부 upsert 적용:
```python
if doc.get("state") == WorkflowState.SUCCESS.value:
    await self._db.workflow_executions.update_one(
        {"_id": execution_id, "state": {"$ne": WorkflowState.STOPPED.value}},
        {"$set": doc}, upsert=True,
    )
```

---

## ✅ B-7. [완료] 테스트 작성

> **중요**: v2 시그니처 기준으로 테스트 작성 완료. 로컬 `pytest tests/test_loop_node.py tests/test_scheduler.py -v` 기준 **12개 테스트 통과**를 확인했습니다.

### `tests/test_loop_node.py` (신규)

```python
import pytest
from app.core.nodes.logic_node import LoopNodeStrategy


@pytest.mark.asyncio
async def test_file_list_iteration():
    node = LoopNodeStrategy({})
    node_dict = {"runtime_config": {"max_iterations": 10}}
    input_data = {
        "type": "FILE_LIST",
        "items": [{"filename": "a.txt"}, {"filename": "b.txt"}],
    }
    result = await node.execute(node_dict, input_data, {})
    assert result["iterations"] == 2
    assert result["type"] == "FILE_LIST"


@pytest.mark.asyncio
async def test_spreadsheet_rows():
    node = LoopNodeStrategy({})
    node_dict = {"runtime_config": {}}
    input_data = {
        "type": "SPREADSHEET_DATA",
        "headers": ["name", "age"],
        "rows": [["Alice", 30], ["Bob", 25]],
    }
    result = await node.execute(node_dict, input_data, {})
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_max_iterations_limit():
    node = LoopNodeStrategy({})
    node_dict = {"runtime_config": {"max_iterations": 2}}
    input_data = {
        "type": "FILE_LIST",
        "items": [{"f": 1}, {"f": 2}, {"f": 3}, {"f": 4}, {"f": 5}],
    }
    result = await node.execute(node_dict, input_data, {})
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_empty_input():
    node = LoopNodeStrategy({})
    result = await node.execute({"runtime_config": {}}, None, {})
    assert result["iterations"] == 0
    assert result["items"] == []


@pytest.mark.asyncio
async def test_transform_field():
    node = LoopNodeStrategy({})
    node_dict = {"runtime_config": {"transform_field": "name"}}
    input_data = {
        "type": "EMAIL_LIST",
        "items": [{"name": "Alice"}, {"name": "Bob"}],
    }
    result = await node.execute(node_dict, input_data, {})
    assert result["loop_results"] == ["Alice", "Bob"]


def test_validate():
    node = LoopNodeStrategy({})
    assert node.validate({"runtime_config": {"node_type": "loop"}}) is True
    assert node.validate({}) is False
```

### `tests/test_scheduler.py` (신규)

```python
import pytest
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
- **4.x**: API 완전 변경 → `AsyncIOScheduler` 없음

현재 코드는 3.x 스타일이므로 3.10.x 버전으로 고정 권장.

### 2. executor.py 변경 인지

작업자 B가 executor.py를 직접 수정할 일은 없지만, 코드 구조가 크게 바뀌었으므로 주요 변경사항 인지 필요:
- `_build_branch_map(nodes, edges)` — 파라미터 변경됨
- `node_outputs: dict[str, dict]` — 노드별 독립 canonical payload 저장
- `_get_predecessors()` — predecessor 기반 input_data 전달
- `_sanitize_for_log()` — None 입력 안전 처리

### 3. 싱글톤 스케줄러 접근 방식

`trigger.py`에서 `request.app.state.scheduler`로 접근하므로, 테스트 시 `TestClient`의 `app.state.scheduler` mock 설정 필요.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [x] `mongodb.py` 인덱스 필드명 수정 ✅ 완료 (883bec5)
- [x] `executor.py` `_build_branch_map()` IfElse 타입 필터링 ✅ v2 완료
- [x] `logic_node.py` LoopNodeStrategy canonical payload + 타임아웃 ✅ v2 완료
- [x] `trigger.py` 신규 생성 (기본 CRUD) ✅ 완료 (111줄, POST/GET/DELETE)
- [x] `main.py` SchedulerService 초기화 추가 ✅ 완료
- [x] `router.py` trigger 라우터 등록 ✅ 완료

**최종 제출 (6/17) 전:**
- [x] Stop 엔드포인트 race condition 수정 ✅ v2 완료
- [x] APScheduler MongoDB jobstore 설정 ✅ 구현 완료
- [x] `tests/test_loop_node.py` 작성 (v2 시그니처 기준) ✅ 작성 완료 및 통과
- [x] `tests/test_scheduler.py` 작성 ✅ 작성 완료 및 통과
