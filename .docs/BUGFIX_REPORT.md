# FastAPI 버그 수정 보고서

> 작성일: 2026-04-13
> 기준 문서: `FASTAPI_SPRINGBOOT_API_SPEC.md`, `FRONTEND_BACKEND_GAP_ANALYSIS.md`
> 수정 전 상태: Spring Boot ↔ FastAPI 통신이 모든 엔드포인트에서 422/404로 실패하는 상태

---

## 수정 요약

| # | 심각도 | 항목 | 수정 파일 |
|---|--------|------|-----------|
| 1 | 🔴 치명 | `WorkflowExecuteRequest` 구조 불일치 | `models/requests.py`, `endpoints/workflow.py` |
| 2 | 🔴 치명 | `NodeDefinition` camelCase 매핑 누락 | `models/workflow.py` |
| 3 | 🔴 치명 | `POST /api/v1/workflows/generate` 엔드포인트 없음 | `endpoints/workflow.py` |
| 4 | 🔴 치명 | `generate_workflow` 응답 형식 불일치 | `services/llm_service.py`, `endpoints/llm.py` |
| 5 | 🔴 치명 | MongoDB 필드명 snake_case → camelCase 불일치 | `models/execution.py`, `core/engine/executor.py` |
| 6 | 🔴 치명 | MongoDB `_id` 미설정 | `core/engine/executor.py` |
| 7 | 🟠 심각 | `RollbackRequest.node_id` 필드명 불일치 | `models/requests.py`, `endpoints/execution.py` |
| 8 | 🟠 심각 | Rollback 허용 상태에 `failed` 누락 | `endpoints/execution.py` |
| 9 | 🟡 데이터 손실 | `NodeDefinition`에 `label` 필드 없음 | `models/workflow.py` |
| 10 | 🟡 데이터 손실 | `EdgeDefinition`에 `id` 필드 없음 | `models/workflow.py` |

---

## 상세 수정 내역

### Fix #1 — `WorkflowExecuteRequest` 구조 완전 교체

**문제:**
Spring Boot는 `{ "workflow": {...}, "service_tokens": {...} }` 형식으로 전송하지만,
FastAPI 모델은 `workflow_id`, `user_id`, `credentials`, `nodes`, `edges`를 최상위 필드로 기대하고 있었음.
→ **모든 실행 요청이 422 Unprocessable Entity로 실패.**

**수정:**
```python
# 수정 전
class WorkflowExecuteRequest(BaseModel):
    workflow_id: str
    user_id: str
    credentials: dict
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition]

# 수정 후
class WorkflowExecuteRequest(BaseModel):
    workflow: WorkflowDefinition
    service_tokens: dict[str, str] = Field(default_factory=dict)
```

executor.py의 `execute()` 시그니처도 `credentials` → `service_tokens`로 변경.

---

### Fix #2 — `NodeDefinition` camelCase alias 추가

**문제:**
Spring Boot는 Jackson 직렬화로 camelCase JSON을 전송하지만 (`dataType`, `outputDataType`, `authWarning`),
Pydantic V2는 기본적으로 exact name matching이므로 snake_case 필드에 매핑 실패.
→ **`data_type`, `output_data_type`, `auth_warning` 모두 `None`/`False`로 무시됨.**

**수정:**
```python
class NodeDefinition(BaseModel):
    model_config = {"populate_by_name": True, "alias_generator": to_camel}
    # 이제 JSON "dataType" → data_type, "authWarning" → auth_warning 자동 매핑
```

`WorkflowDefinition`, `TriggerConfig`에도 동일하게 적용.

**주의:** `populate_by_name=True`로 snake_case 직접 생성도 허용 (내부 코드, 테스트 호환).

**⚠️ boolean 필드 예외 처리 (추가 수정):**

Spring Boot의 `boolean isActive` 필드는 다음 경로로 직렬화됩니다:
```
Java: boolean isActive
  → Lombok: isActive() getter 생성
  → Jackson: "is" 접두사 제거 → JSON 키 "active"
```

`alias_generator = to_camel`을 그대로 적용하면:
```
Python 필드: is_active → to_camel → "isActive"  ← "active"와 불일치!
```

**해결:** `WorkflowDefinition`의 해당 필드명을 Python에서도 `active`/`template`으로 선언.
`to_camel("active") = "active"`, `to_camel("template") = "template"` 이므로 별도 alias 불필요.

```python
# 수정 전 (잘못된 방식 — alias와 alias_generator 충돌 가능)
is_active: bool = Field(default=True, alias="active")
is_template: bool = Field(default=False, alias="template")

# 수정 후 (올바른 방식)
active: bool = True      # to_camel("active") = "active" ✓
template: bool = False   # to_camel("template") = "template" ✓
```

---

### Fix #3 — `POST /api/v1/workflows/generate` 엔드포인트 추가

**문제:**
Spring Boot는 `POST /api/v1/workflows/generate`를 호출하지만,
해당 경로가 FastAPI 라우터에 등록되지 않아 **404 Not Found**.
(기존 구현은 `/api/v1/llm/generate-workflow` 경로에만 있었음)

**수정:**
`app/api/v1/endpoints/workflow.py`에 `POST /generate` 핸들러 추가:
```python
@router.post("/generate")
async def generate_workflow(request: GenerateWorkflowRequest, ...) -> GenerateWorkflowResponse:
    ...
```
`router`가 `/api/v1/workflows` prefix로 등록되어 있으므로 최종 경로: `POST /api/v1/workflows/generate`.

---

### Fix #4 — `generate_workflow` 응답 형식 수정

**문제:**
Spring Boot는 응답을 `ObjectMapper.convertValue()` → `WorkflowCreateRequest`로 변환 후 MongoDB에 저장.
`WorkflowCreateRequest.name`이 `@NotBlank`인데 FastAPI 응답에 `name` 필드가 없었음.
→ **Spring Boot 저장 실패.**

추가로 LLM 프롬프트에 `name`, `trigger` 필드 생성 지시가 없었음.

**수정:**

`GenerateWorkflowResponse` 모델:
```python
# 수정 전
class GenerateWorkflowResponse(BaseModel):
    result: dict  # 래핑된 형식

# 수정 후
class GenerateWorkflowResponse(BaseModel):
    name: str          # @NotBlank — 필수
    description: str | None = None
    nodes: list[dict]
    edges: list[dict]
    trigger: dict      # Spring Boot TriggerConfig 호환
```

LLM 시스템 프롬프트에 `name`, `trigger` 필드 포함 지시 추가.

---

### Fix #5 — MongoDB 필드명 camelCase 통일

**문제:**
Pydantic `model_dump()`는 기본적으로 Python 필드명(snake_case)을 반환.
FastAPI가 `workflow_id`, `user_id`, `node_logs`, `started_at`으로 저장하면
Spring Boot가 `workflowId`, `userId`, `nodeLogs`, `startedAt`으로 읽어도 모두 `null`.

**수정:**
`models/execution.py`의 모든 필드를 camelCase로 변경:

| 수정 전 (snake_case) | 수정 후 (camelCase) |
|---------------------|---------------------|
| `workflow_id` | `workflowId` |
| `user_id` | `userId` |
| `node_logs` | `nodeLogs` |
| `error_message` | `errorMessage` |
| `started_at` | `startedAt` |
| `finished_at` | `finishedAt` |
| `node_id` | `nodeId` |
| `input_data` | `inputData` |
| `output_data` | `outputData` |
| `captured_at` | `capturedAt` |
| `state_data` | `stateData` |
| `stack_trace` | `stackTrace` |

executor.py의 `WorkflowExecution` 생성 코드, `NodeExecutionLog` 생성 코드 모두 camelCase 필드명으로 업데이트.

---

### Fix #6 — MongoDB `_id`를 executionId로 설정

**문제:**
명세서: `"_id": "<executionId>"` — executionId가 MongoDB 문서 ID여야 함.
기존 구현: `_id`는 MongoDB 자동 생성 ObjectId, 별도 `id` 필드에 executionId 저장.
→ Spring Boot가 `_id`로 쿼리하면 조회 실패.

**수정:**
```python
async def _save_execution(self, execution_id: str, execution: WorkflowExecution):
    doc = execution.model_dump(mode="json")
    doc["_id"] = execution_id  # _id를 executionId로 명시 설정
    await self._db.workflow_executions.update_one(
        {"_id": execution_id},
        {"$set": doc},
        upsert=True,
    )
```

`execution.py` endpoint의 `find_one({"id": ...})` → `find_one({"_id": ...})`로 변경.

---

### Fix #7 — `RollbackRequest.node_id` 필드명 수정

**문제:**
Spring Boot는 `{ "node_id": "..." }` 형식으로 전송하지만
FastAPI 모델 필드명이 `target_node_id`여서 항상 `None`으로 역직렬화됨.

**수정:**
```python
# 수정 전
class RollbackRequest(BaseModel):
    target_node_id: str | None = None

# 수정 후
class RollbackRequest(BaseModel):
    node_id: str | None = None
```

`execution.py` endpoint에서 `body.target_node_id` → `body.node_id`로 변경.

---

### Fix #8 — Rollback 허용 상태에 `failed` 추가

**문제:**
명세서: `state == "rollback_available"` **또는** `"failed"` 시 롤백 허용.
기존 코드: `ROLLBACK_AVAILABLE`만 체크.

**수정:**
```python
_ROLLBACK_ALLOWED_STATES = {
    WorkflowState.ROLLBACK_AVAILABLE.value,
    WorkflowState.FAILED.value,      # 추가
}
```

---

### Fix #9 — `NodeDefinition`에 `label` 필드 추가

**문제:**
프론트가 저장하는 노드 제목(`label`)이 Spring Boot를 통해 FastAPI로 전달되지만
FastAPI `NodeDefinition`에 `label` 필드가 없어서 Pydantic이 무시.
→ 저장 후 재로드 시 모든 노드 제목이 초기화됨.

**수정:**
```python
class NodeDefinition(BaseModel):
    ...
    label: str | None = None  # 추가
```

---

### Fix #10 — `EdgeDefinition`에 `id` 필드 추가

**문제:**
Spring Boot는 `{ "id": "edge_abc12345", "source": "...", "target": "..." }` 형식으로 전송.
FastAPI `EdgeDefinition`에 `id` 필드가 없어서 무시됨.
→ 저장-로드 시 edge id가 매번 달라짐 (프론트가 `crypto.randomUUID()`로 임시 생성).

**수정:**
```python
class EdgeDefinition(BaseModel):
    id: str | None = None  # 추가
    source: str
    target: str
```

---

## 수정된 파일 목록

| 파일 | 변경 유형 |
|------|-----------|
| `app/models/workflow.py` | 전면 재작성 — camelCase alias, label, edge.id, TriggerConfig, WorkflowDefinition 추가 |
| `app/models/requests.py` | 전면 재작성 — WorkflowExecuteRequest, GenerateWorkflowResponse, RollbackRequest 재정의 |
| `app/models/execution.py` | 전면 재작성 — 모든 필드명 camelCase, `id` 필드 제거 |
| `app/core/engine/executor.py` | execute() 시그니처, _save_execution() _id 설정, camelCase 필드 참조 수정 |
| `app/api/v1/endpoints/workflow.py` | execute 핸들러 리팩터, generate 핸들러 추가 |
| `app/api/v1/endpoints/execution.py` | _id 기준 쿼리, camelCase 필드 참조, rollback 허용 상태 수정 |
| `app/api/v1/endpoints/llm.py` | generate-workflow 응답 형식을 GenerateWorkflowResponse로 변경 |
| `app/services/llm_service.py` | generate_workflow 프롬프트에 name, trigger, label 포함 지시 추가 |
| `tests/test_executor.py` | credentials → service_tokens, node_logs → nodeLogs 등 필드명 업데이트 |
| `tests/test_execution_api.py` | mock doc camelCase, _id 기준, 새 롤백 테스트 케이스 추가 |
| `tests/test_models.py` | 새 WorkflowExecuteRequest 구조, camelCase 검증 테스트로 전면 교체 |
| `tests/test_llm_api.py` | generate-workflow 응답 형식 검증 업데이트 |

---

## 테스트 결과

```
94 passed, 37 warnings in 2.16s
```

---

## 남은 과제 (Spring Boot 측 수정 필요)

`FRONTEND_BACKEND_GAP_ANALYSIS.md` P0 항목 중 FastAPI가 아닌 Spring Boot에서 해결해야 할 사항:

| 항목 | 설명 |
|------|------|
| OAuth 콜백 리다이렉트 | `AuthController.googleCallback()` → JSON 반환 대신 302 redirect + exchange_code |
| `POST /api/auth/exchange` | 신규 엔드포인트 구현 |
| `WorkflowResponse @JsonProperty("isActive")` | REVERT 필요 (`"active"` 키 유지) |
| `WorkflowUpdateRequest @JsonProperty("active")` | 추가 필요 (프론트가 `"active"` 키 전송) |
| `FRONT_REDIRECT_URI` 환경변수 | `application.yml`에 추가 |

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-13 | 최초 작성. Fix #1~#10 전체 수정 완료. 94개 테스트 통과. |
| 2026-04-13 | Fix #2 보완: WorkflowDefinition boolean 필드 `is_active`/`is_template` → `active`/`template` 로 변경. alias_generator 충돌 방지. |
