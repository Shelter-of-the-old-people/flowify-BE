# FastAPI ↔ Spring Boot 통합 명세서

> 최종 갱신: 2026-04-21
> 통합 대상: FASTAPI_SPRINGBOOT_API_SPEC, FASTAPI_RUNTIME_CONTRACT_REQUEST (v2),
> FASTAPI_RUNTIME_CONTRACT_REVISION_REQUEST
> 대상: FastAPI 서버 개발자
> 상태: runtime contract v2 반영 완료

---

## 1. 통신 기본 구조

### 인증 헤더

Spring Boot는 FastAPI로 보내는 **모든 요청**에 아래 두 헤더를 포함한다.

| 헤더 | 값 | 설명 |
|------|----|------|
| `X-Internal-Token` | `${INTERNAL_API_SECRET}` | 서버 간 공유 비밀 토큰 |
| `X-User-ID` | `"<MongoDB ObjectId>"` | 요청 트리거 사용자 ID |

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FASTAPI_URL` | `http://localhost:8000` | FastAPI 베이스 URL |
| `INTERNAL_API_SECRET` | (필수) | 서버 간 인증 토큰 |

### 로컬 개발 환경

```yaml
# application-dev.yml
app:
  fastapi:
    base-url: http://localhost:8000
    internal-token: dev-internal-api-secret

# docker-compose.yml
FASTAPI_URL: http://fastapi:8000
INTERNAL_API_SECRET: <공유된 비밀값>
```

---

## 2. Wire Contract Naming Policy

runtime payload는 dual-convention을 사용한다.

| 영역 | convention | 예시 |
|------|-----------|------|
| editor-origin 필드 | camelCase | `userId`, `dataType`, `outputDataType` |
| runtime 추가 필드 | snake_case | `runtime_type`, `runtime_source`, `runtime_sink`, `canonical_input_type` |

**이유:** editor 필드는 Jackson이 Java camelCase 엔티티를 직렬화한 것이고,
runtime 필드는 WorkflowTranslator가 Map key로 직접 생성한 snake_case다.

**FastAPI 권장:** Pydantic `alias` 또는 `model_config = ConfigDict(populate_by_name=True)` 활용.

---

## 3. API 엔드포인트

### 3.1 워크플로우 실행 (runtime contract v2)

```
POST {FASTAPI_URL}/api/v1/workflows/{workflowId}/execute
```

**요청 바디:**

```json
{
  "workflow": {
    "id": "workflow-123",
    "name": "워크플로우 이름",
    "userId": "user-abc",
    "nodes": [
      {
        "id": "n1",
        "category": "service",
        "type": "google_drive",
        "label": "Google Drive 파일",
        "config": { "source_mode": "single_file", "target": "file-xyz" },
        "dataType": null,
        "outputDataType": "SINGLE_FILE",
        "role": "start",
        "runtime_type": "input",
        "runtime_source": {
          "service": "google_drive",
          "mode": "single_file",
          "target": "file-xyz",
          "canonical_input_type": "SINGLE_FILE"
        }
      },
      {
        "id": "n2",
        "category": "ai",
        "type": "summarize",
        "label": "AI 요약",
        "config": { "action": "summarize", "style": "concise" },
        "dataType": "SINGLE_FILE",
        "outputDataType": "TEXT",
        "role": null,
        "runtime_type": "llm",
        "runtime_config": {
          "node_type": "summarize",
          "output_data_type": "TEXT",
          "action": "summarize",
          "style": "concise"
        }
      },
      {
        "id": "n3",
        "category": "service",
        "type": "slack",
        "label": "Slack 전송",
        "config": { "channel": "#general", "message_format": "markdown" },
        "dataType": "TEXT",
        "outputDataType": null,
        "role": "end",
        "runtime_type": "output",
        "runtime_sink": {
          "service": "slack",
          "config": { "channel": "#general", "message_format": "markdown" }
        }
      }
    ],
    "edges": [
      { "id": "e1", "source": "n1", "target": "n2" },
      { "id": "e2", "source": "n2", "target": "n3" }
    ],
    "trigger": {
      "type": "manual",
      "config": {}
    }
  },
  "service_tokens": {
    "google_drive": "ya29.a0AfH6SMBx...",
    "slack": "xoxb-123456789-..."
  }
}
```

**`service_tokens` 규칙:**
- 값은 **decrypted OAuth access token** (바로 외부 API 호출에 사용 가능)
- Spring이 암호화 저장소에서 복호화 후 전달. FastAPI는 추가 복호화 불필요
- `category == "service"` && `auth_required == true` 인 노드의 type을 키로 사용

**runtime_type 5종 매핑:**

| runtime_type | 조건 | FastAPI 전략 |
|-------------|------|-------------|
| `input` | role = "start" | InputNodeStrategy |
| `output` | role = "end" | OutputNodeStrategy |
| `llm` | AI, DATA_FILTER, AI_FILTER, PASSTHROUGH | LLMNodeStrategy |
| `if_else` | CONDITION_BRANCH | IfElseNodeStrategy |
| `loop` | LOOP | LoopNodeStrategy |

**FastAPI 응답 (필수):**
```json
{ "execution_id": "string" }
```

---

### 3.2 AI 워크플로우 자동 생성

```
POST {FASTAPI_URL}/api/v1/workflows/generate
```

**요청 바디:**
```json
{ "prompt": "매일 오전 9시에 Gmail 받은 편지함을 확인해서 Slack으로 요약 전달" }
```

**FastAPI 응답:** Spring의 `WorkflowCreateRequest`와 호환되는 JSON.
```json
{
  "name": "string (필수)",
  "description": "string | null",
  "nodes": [
    {
      "id": "node_abc12345",
      "category": "trigger | service | logic | output",
      "type": "string",
      "label": "string | null",
      "config": {},
      "position": { "x": 0.0, "y": 0.0 },
      "dataType": "string | null",
      "outputDataType": "string | null",
      "role": "start | end | null",
      "authWarning": false
    }
  ],
  "edges": [{ "id": "edge_abc12345", "source": "node_abc12345", "target": "node_def67890" }],
  "trigger": { "type": "manual | schedule | webhook", "config": {} }
}
```

### 3.3 실행 롤백

```
POST {FASTAPI_URL}/api/v1/executions/{executionId}/rollback
```

**요청 바디:**
```json
{ "node_id": "string | null" }
```

**FastAPI 응답:** HTTP 2xx면 성공. 바디 무시.

### 3.4 실행 중지

```
POST {FASTAPI_URL}/api/v1/executions/{executionId}/stop
```

**요청 바디:** 없음

**FastAPI 응답:** HTTP 2xx면 성공. 바디 무시.

**구현 요구:**
- 실행 중인 워크플로우의 노드 처리를 즉시 중단
- `workflow_executions.state`를 `"stopped"` 또는 `"failed"`로 업데이트
- 이미 중지된 실행에 대한 중복 요청은 멱등하게 처리 (에러 없이 2xx)

---

## 4. InputNodeStrategy 구현 요구사항

### 4.1 Phase 1 지원 source

> **runtime 1차 범위는 Spring source catalog의 부분집합이다.**
> 모든 mode key는 `source_catalog.json`에 실재하는 값만 사용한다.

**Phase 1** (Google OAuth 4종 + Slack):

| service | mode | canonical_input_type | trigger_kind |
|---------|------|---------------------|-------------|
| `google_drive` | `single_file` | SINGLE_FILE | manual |
| `google_drive` | `file_changed` | SINGLE_FILE | event |
| `google_drive` | `new_file` | SINGLE_FILE | event |
| `google_drive` | `folder_new_file` | SINGLE_FILE | event |
| `google_drive` | `folder_all_files` | FILE_LIST | manual |
| `gmail` | `single_email` | SINGLE_EMAIL | manual |
| `gmail` | `new_email` | SINGLE_EMAIL | event |
| `gmail` | `sender_email` | SINGLE_EMAIL | event |
| `gmail` | `starred_email` | SINGLE_EMAIL | manual |
| `gmail` | `label_emails` | EMAIL_LIST | manual |
| `gmail` | `attachment_email` | FILE_LIST | event |
| `google_sheets` | `sheet_all` | SPREADSHEET_DATA | manual |
| `google_sheets` | `new_row` | SPREADSHEET_DATA | event |
| `google_sheets` | `row_updated` | SPREADSHEET_DATA | event |
| `slack` | `channel_messages` | TEXT | manual |

**Phase 2** (이후 확장): google_calendar, youtube, naver_news, coupang, github, notion

### 4.2 Canonical Payload Schema

InputNodeStrategy가 반환하는 normalized payload. 모든 payload는 `type` discriminator 포함.

**SINGLE_FILE:**
```json
{
  "type": "SINGLE_FILE",
  "filename": "report.pdf",
  "content": "base64-or-text-content...",
  "mime_type": "application/pdf",
  "url": "https://drive.google.com/..."
}
```

**FILE_LIST:**
```json
{
  "type": "FILE_LIST",
  "items": [
    { "filename": "doc1.pdf", "mime_type": "application/pdf", "size": 1024, "url": "..." }
  ]
}
```

**SINGLE_EMAIL:**
```json
{
  "type": "SINGLE_EMAIL",
  "subject": "Meeting reminder",
  "from": "sender@example.com",
  "date": "2026-04-21T09:00:00Z",
  "body": "Don't forget the meeting at 3pm.",
  "attachments": [{ "filename": "agenda.pdf", "mime_type": "application/pdf", "size": 512 }]
}
```

**EMAIL_LIST:**
```json
{
  "type": "EMAIL_LIST",
  "items": [
    { "subject": "Weekly report", "from": "team@example.com", "date": "2026-04-20T10:00:00Z", "body": "..." }
  ]
}
```

**SPREADSHEET_DATA:**
```json
{
  "type": "SPREADSHEET_DATA",
  "headers": ["이름", "점수", "등급"],
  "rows": [["홍길동", 95, "A"], ["김철수", 82, "B"]],
  "sheet_name": "Sheet1"
}
```

**SCHEDULE_DATA:**
```json
{
  "type": "SCHEDULE_DATA",
  "items": [
    { "title": "팀 미팅", "start_time": "2026-04-21T14:00:00+09:00", "end_time": "2026-04-21T15:00:00+09:00", "location": "회의실 A", "description": "주간 진행상황 공유" }
  ]
}
```

**API_RESPONSE:**
```json
{
  "type": "API_RESPONSE",
  "data": { "videos": [{ "title": "How to...", "url": "https://youtube.com/..." }] },
  "source": "youtube"
}
```

**TEXT:**
```json
{
  "type": "TEXT",
  "content": "Slack #general 채널의 최근 메시지..."
}
```

### 4.3 Validation Contract

```python
# new contract (runtime_source 기준)
def validate(self, node: dict):
    runtime_source = node["runtime_source"]
    service = runtime_source["service"]
    mode = runtime_source["mode"]
    target = runtime_source.get("target")
    canonical_type = runtime_source["canonical_input_type"]
```

**Transition:** `runtime_source` 우선, 부재 시 `config["source"]` fallback 허용.
Spring은 input 노드에 항상 `runtime_source`를 생성하므로 실제 fallback은 드묾.

### 4.4 Unsupported Source Handling

Spring preflight에서 1차 차단. FastAPI도 방어적으로 reject:
```json
{ "error_code": "UNSUPPORTED_RUNTIME_SOURCE", "detail": "service=github, mode=new_pr is not supported in current runtime phase" }
```

---

## 5. OutputNodeStrategy 구현 요구사항

### 5.1 Phase 1 Sink 서비스

| service | accepted_input_types | 주요 required config |
|---------|---------------------|---------------------|
| `slack` | TEXT | `channel` |
| `gmail` | TEXT, SINGLE_FILE, FILE_LIST | `to`, `subject`, `action` (send/draft) |
| `notion` | TEXT, SPREADSHEET_DATA, API_RESPONSE | `target_type`, `target_id` |
| `google_drive` | TEXT, SINGLE_FILE, FILE_LIST, SPREADSHEET_DATA | `folder_id` |
| `google_sheets` | TEXT, SPREADSHEET_DATA, API_RESPONSE | `spreadsheet_id`, `write_mode` (append/overwrite) |
| `google_calendar` | TEXT, SCHEDULE_DATA | `calendar_id`, `event_title_template`, `action` (create/update) |

### 5.2 Input Payload Consumption

| sink | 입력 type | 소비 필드 |
|------|----------|---------|
| `slack` | TEXT | `content` -> 메시지 본문 |
| `gmail` | TEXT | `content` -> body, config `to`/`subject`/`action` 사용 |
| `gmail` | SINGLE_FILE | `filename`/`content`/`mime_type` -> 첨부파일 |
| `google_drive` | SINGLE_FILE | `filename`/`content`/`mime_type` -> 파일 업로드, config `folder_id` 사용 |
| `google_drive` | FILE_LIST | `items[*]` -> 각 파일 업로드 |
| `google_sheets` | SPREADSHEET_DATA | `headers`/`rows` -> 행 추가/덮어쓰기, config `spreadsheet_id`/`write_mode` 사용 |
| `google_calendar` | SCHEDULE_DATA | `items[*].title`/`start_time`/`end_time` -> 일정 생성, config `calendar_id` 사용 |
| `notion` | TEXT | `content` -> 페이지 본문, config `target_type`/`target_id` 사용 |

### 5.3 Validation Contract

```python
def validate(self, node: dict):
    runtime_sink = node["runtime_sink"]
    service = runtime_sink["service"]
    sink_config = runtime_sink["config"]
```

Transition 정책은 InputNodeStrategy와 동일.

### 5.4 Unsupported Sink Handling

```json
{ "error_code": "UNSUPPORTED_RUNTIME_SINK", "detail": "service=custom_webhook is not supported" }
```

---

## 6. Capability API (선택)

```
GET {FASTAPI_URL}/api/runtime/capabilities
```

```json
{
  "supported_runtime_types": ["input", "output", "llm", "if_else", "loop"],
  "supported_sources": {
    "google_drive": ["single_file", "file_changed", "new_file", "folder_new_file", "folder_all_files"],
    "gmail": ["single_email", "new_email", "sender_email", "starred_email", "label_emails", "attachment_email"],
    "google_sheets": ["sheet_all", "new_row", "row_updated"],
    "slack": ["channel_messages"]
  },
  "supported_sinks": ["slack", "gmail", "notion", "google_drive", "google_sheets", "google_calendar"]
}
```

---

## 7. Transition Policy

### 7.1 필드 전환

| 필드 | 역할 | 상태 |
|------|------|------|
| `runtime_type` | 전략 선택 PRIMARY | 즉시 사용 |
| `runtime_source` / `runtime_sink` | 노드 정보 PRIMARY | `config["source"]`/`config["target"]` 대체 |
| `type`, `category` | 전략 선택 FALLBACK | runtime_type 부재 시만 |
| `config` | 원본 설정 | 하위 호환용 유지 |

### 7.2 전환 일정

1. **즉시:** `runtime_type`을 PRIMARY 전략 선택자로 사용
2. **Phase 1 완료:** `runtime_source`/`runtime_sink` 기반 validate/execute 완전 전환
3. **Phase 1 검증 후:** old fallback 제거 가능

---

## 8. 데이터 타입 상세

### NodeDefinition

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | String | `"node_"` + UUID 8자리 |
| `category` | String | `"trigger"`, `"service"`, `"logic"`, `"output"` |
| `type` | String | 서비스 종류 (`"gmail"`, `"slack"`, `"condition"`) |
| `label` | String \| null | 사용자 지정 노드 제목 |
| `config` | Map | 노드 설정 (type별 상이) |
| `position` | { x, y } | 캔버스 좌표 |
| `dataType` | String \| null | 입력 데이터 타입 |
| `outputDataType` | String \| null | 출력 데이터 타입 |
| `role` | String \| null | `"start"`, `"end"`, `null` |
| `authWarning` | boolean | OAuth 미연결 경고 |
| `runtime_type` | String | `"input"`, `"output"`, `"llm"`, `"if_else"`, `"loop"` |
| `runtime_source` | Object \| null | input 노드 전용 (service, mode, target, canonical_input_type) |
| `runtime_sink` | Object \| null | output 노드 전용 (service, config) |
| `runtime_config` | Object \| null | middle/loop/branch 노드 전용 |

### EdgeDefinition

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | String | `"edge_"` + UUID 8자리 |
| `source` | String | 출발 노드 ID |
| `target` | String | 도착 노드 ID |

### TriggerConfig

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | String | `"manual"`, `"schedule"`, `"webhook"` |
| `config` | Map | 트리거 설정 (`{ "cron": "0 9 * * *" }`) |

---

## 9. 에러 코드

| 상황 | ErrorCode | HTTP |
|------|-----------|------|
| FastAPI 호출 실패 (4xx/5xx) | `FASTAPI_UNAVAILABLE` | 502 |
| 응답에 execution_id 없음 | `EXECUTION_FAILED` | 500 |
| 실행 불가 상태에서 롤백 | `EXECUTION_FAILED` | 400 |
| 실행 중 아닌 상태에서 중지 | `INVALID_REQUEST` | 400 |
| 미지원 source | `UNSUPPORTED_RUNTIME_SOURCE` | 400 |
| 미지원 sink | `UNSUPPORTED_RUNTIME_SINK` | 400 |

---

## 10. 실행 이력 저장 (MongoDB)

### `workflow_executions` 컬렉션 스키마

```json
{
  "_id": "<executionId>",
  "workflowId": "string",
  "userId": "string",
  "state": "running | completed | failed | rollback_available",
  "nodeLogs": [
    {
      "nodeId": "string",
      "status": "success | failed | skipped",
      "inputData": {},
      "outputData": {},
      "snapshot": { "capturedAt": "ISO8601", "stateData": {} },
      "error": { "code": "string", "message": "string", "stackTrace": "string | null" },
      "startedAt": "ISO8601",
      "finishedAt": "ISO8601"
    }
  ],
  "startedAt": "ISO8601",
  "finishedAt": "ISO8601 | null"
}
```

> **롤백 조건:** `state`가 `"rollback_available"` 또는 `"failed"`일 때만 허용.

---

## 11. 데이터 플로우

```
[사용자]
  │ POST /api/workflows/{id}/execute
  ▼
[Spring Boot]
  ├─ Workflow 조회 (MongoDB)
  ├─ validateForExecution() — preflight 검증
  ├─ 서비스 토큰 수집 (OAuthTokenService → 복호화)
  ├─ WorkflowTranslator.toRuntimeModel() — editor → runtime 변환
  └─ FastApiClient.execute() 호출
       │ POST /api/v1/workflows/{id}/execute
       │ Body: { workflow: runtimeModel, service_tokens }
       ▼
[FastAPI]
  ├─ runtime_type으로 전략 선택
  ├─ InputNodeStrategy: 외부 데이터 수집 → canonical payload 생성
  ├─ LLMNodeStrategy: AI 처리
  └─ OutputNodeStrategy: 결과를 외부 서비스에 전달
       │
       ▼ { "execution_id": "..." }
[Spring Boot]
  └─ executionId를 클라이언트에 반환
```

---

## 12. 콜백 방식

현재 **폴링 방식만** 지원:
- `GET /api/workflows/{id}/executions/{execId}` — MongoDB `workflow_executions` 컬렉션 조회

웹훅 콜백(`POST /api/internal/executions/{execId}/complete`)은 미구현.

---

## 13. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-13 | 최초 작성 (execute, generate, rollback 3개 엔드포인트) |
| 2026-04-13 | label, edge id 필드 추가. 실행 중지 API 추가. 페이지네이션 제거. |
| 2026-04-20 | WorkflowTranslator 도입 (runtime_source, runtime_sink). Source/Sink catalog API 추가. Schema preview API 추가. |
| 2026-04-21 | **v2 통합:** runtime contract 반영 — source mode key 정정, canonical payload schema 추가, naming policy 추가, unsupported handling 추가, validation migration 추가, service_tokens decrypted 명시, transition policy 추가. REVISION_REQUEST 피드백 7건 모두 반영. |
