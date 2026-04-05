# 4. 내부 데이터 모델 및 상태 스키마

> Spring Boot `2_database_design.md` 및 `6_design_classes.md`의 도메인 모델 대응 문서
> FastAPI 서버에서 사용하는 모든 데이터 모델의 상세 스키마를 정의합니다.

---

## 4.1 워크플로우 실행 요청 페이로드 (Workflow Execute Request)

Spring Boot가 워크플로우 실행 요청 시 FastAPI로 전달하는 JSON 페이로드 구조입니다.
`mapping_rules.json` 및 프론트엔드의 에디터 구성과 밀접하게 연관되어 있습니다.

```json
{
  "workflow_id": "wf_12345abc",
  "user_id": "usr_987xyz",
  "credentials": {
    "google": "ya29.a0AfB_byabc123...",
    "slack": "xoxb-1234567890-abc...",
    "notion": "ntn_abc123..."
  },
  "nodes": [
    {
      "id": "node_1",
      "type": "input",
      "category": "storage",
      "config": {
        "source": "google_drive",
        "target_folder": "folder_abc123"
      },
      "position": { "x": 100, "y": 200 },
      "data_type": null,
      "output_data_type": "FILE_LIST",
      "role": "start"
    },
    {
      "id": "node_2",
      "type": "llm",
      "category": "ai",
      "config": {
        "action": "summarize",
        "style": "brief_3line"
      },
      "position": { "x": 400, "y": 200 },
      "data_type": "FILE_LIST",
      "output_data_type": "TEXT",
      "role": "middle"
    },
    {
      "id": "node_3",
      "type": "output",
      "category": "communication",
      "config": {
        "target": "slack",
        "channel": "#reports"
      },
      "position": { "x": 700, "y": 200 },
      "data_type": "TEXT",
      "output_data_type": null,
      "role": "end"
    }
  ],
  "edges": [
    { "source": "node_1", "target": "node_2" },
    { "source": "node_2", "target": "node_3" }
  ]
}
```

### 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `workflow_id` | str | Y | 워크플로우 고유 ID |
| `user_id` | str | Y | 실행 요청 사용자 ID |
| `credentials` | dict | Y | 복호화된 OAuth 토큰 맵. Spring Boot가 AES-256 복호화 후 전달 |
| `nodes` | list[NodeDefinition] | Y | 실행할 노드 목록 (순서 보장) |
| `edges` | list[EdgeDefinition] | Y | 노드 간 연결 정보 |

---

## 4.2 노드 정의 모델 (NodeDefinition)

```python
class NodeDefinition(BaseModel):
    id: str                              # 노드 고유 ID (e.g., "node_1")
    type: str                            # 노드 실행 타입 (input, llm, if_else, loop, output)
    config: dict                         # 노드별 설정값
    position: dict = {"x": 0, "y": 0}   # 캔버스 좌표
    category: str | None = None          # 노드 카테고리 (storage, communication, ai, processing 등)
    data_type: str | None = None         # 입력 데이터 타입 (FILE_LIST, SINGLE_FILE, TEXT 등)
    output_data_type: str | None = None  # 출력 데이터 타입
    role: str | None = None              # 노드 역할 (start, end, middle)
    auth_warning: bool = False           # 미인증 서비스 경고 여부
```

### 데이터 타입 (data_type / output_data_type)

`mapping_rules.json`에 정의된 8가지 데이터 타입과 대응합니다:

| 데이터 타입 | 설명 | 처리 방식 필요 |
|------------|------|---------------|
| `FILE_LIST` | 복수 파일 목록 | Y (one_by_one / all_at_once) |
| `SINGLE_FILE` | 단일 파일 | N |
| `EMAIL_LIST` | 복수 이메일 | Y (one_by_one / all_at_once) |
| `SINGLE_EMAIL` | 단일 이메일 | N |
| `SPREADSHEET_DATA` | 스프레드시트 데이터 | Y (row_by_row / all_at_once) |
| `API_RESPONSE` | API 응답 데이터 | N |
| `SCHEDULE_DATA` | 캘린더/일정 데이터 | N |
| `TEXT` | 일반 텍스트 | N |

### 노드 카테고리와 타입 매핑

| category | 가능한 type 값 | 설명 |
|----------|---------------|------|
| `communication` | `input`, `output` | Slack, Gmail 등 커뮤니케이션 서비스 |
| `storage` | `input`, `output` | Google Drive, Notion 등 저장소 서비스 |
| `spreadsheet` | `input`, `output` | Google Sheets 등 스프레드시트 |
| `web_crawl` | `input` | 웹 크롤링 (쿠팡, 네이버 뉴스 등) |
| `calendar` | `input`, `output` | Google Calendar 등 캘린더 |
| `ai` | `llm` | LLM 기반 AI 처리 |
| `processing` | `if_else`, `loop` | 데이터 필터링, 반복, 조건 분기 |

---

## 4.3 노드 간 실행 데이터 흐름

각 `NodeStrategy`의 `execute(input_data)` 메소드를 거칠 때마다 데이터가 누적/변환됩니다.
노드 간 결합도를 낮추기 위해 통일된 딕셔너리(`dict`) 형태를 유지합니다.

```json
// === node_1 (Input - Google Drive) 실행 후 ===
{
  "raw_files": [
    { "name": "report.pdf", "content": "본문 내용입니다...", "mime_type": "application/pdf" },
    { "name": "data.xlsx", "content": "...", "mime_type": "application/vnd.openxmlformats..." }
  ],
  "source": "google_drive",
  "data_type": "FILE_LIST",
  "credentials": { "google": "ya29...", "slack": "xoxb-..." }
}

// === node_2 (LLM - Summarize) 실행 후 (입력 데이터 보존 + 새 데이터 추가) ===
{
  "raw_files": [ ... ],
  "source": "google_drive",
  "data_type": "TEXT",
  "credentials": { ... },
  "llm_result": "보고서의 핵심 요약 내용 3줄입니다.\n1. ...\n2. ...\n3. ..."
}

// === node_3 (Output - Slack) 실행 후 ===
{
  "raw_files": [ ... ],
  "source": "google_drive",
  "data_type": "TEXT",
  "credentials": { ... },
  "llm_result": "...",
  "output_result": {
    "target": "slack",
    "channel": "#reports",
    "sent": true,
    "timestamp": "1711800015.000200"
  }
}
```

### credentials 전파 규칙

- `credentials`는 실행 요청 시 Spring Boot가 전달하며, 최초 `input_data`에 포함됩니다.
- 각 노드는 `input_data["credentials"]`에서 필요한 서비스 토큰을 꺼내 사용합니다.
- **중요**: `credentials`는 실행 로그에 저장하지 않습니다 (보안). 로그 저장 시 제거합니다.

---

## 4.4 실행 로그 스키마 (MongoDB `workflow_executions`)

FastAPI가 실행을 마치거나 실패했을 때 추적 및 디버깅을 위해 MongoDB에 저장하는 도큐먼트 구조입니다.

```json
{
  "_id": "ObjectId('...')",
  "workflow_id": "wf_12345abc",
  "user_id": "usr_987xyz",
  "status": "success",
  "started_at": "2026-03-30T10:00:00Z",
  "finished_at": "2026-03-30T10:00:15Z",
  "node_logs": [
    {
      "node_id": "node_1",
      "status": "success",
      "input_data": { "source": "google_drive" },
      "output_data": { "raw_files": [...], "data_type": "FILE_LIST" },
      "snapshot": {
        "captured_at": "2026-03-30T10:00:01Z",
        "state_data": {}
      },
      "error": null,
      "duration_ms": 1200,
      "started_at": "2026-03-30T10:00:01Z",
      "finished_at": "2026-03-30T10:00:02.2Z"
    },
    {
      "node_id": "node_2",
      "status": "success",
      "input_data": { "raw_files": [...] },
      "output_data": { "llm_result": "..." },
      "snapshot": {
        "captured_at": "2026-03-30T10:00:02.3Z",
        "state_data": { "raw_files": [...] }
      },
      "error": null,
      "duration_ms": 8500,
      "started_at": "2026-03-30T10:00:02.3Z",
      "finished_at": "2026-03-30T10:00:10.8Z"
    }
  ],
  "error_message": null
}
```

### 실행 상태 (status) 전이 규칙

```
PENDING ──→ RUNNING ──→ SUCCESS (완료)
                │
                └──→ FAILED ──→ ROLLBACK_AVAILABLE ──→ PENDING (재실행)
```

| 상태 | 설명 |
|------|------|
| `pending` | 실행 대기 중 (초기 상태) |
| `running` | 실행 중 |
| `success` | 모든 노드 실행 성공 (종료 상태) |
| `failed` | 노드 실행 중 오류 발생 |
| `rollback_available` | 스냅샷 기반 롤백 가능 상태 |

---

## 4.5 NodeLog 상세 스키마

```python
class NodeLog(BaseModel):
    node_id: str                           # 노드 ID
    status: str                            # pending | running | success | failed | skipped
    input_data: dict                       # 노드 입력 데이터 (credentials 제외)
    output_data: dict                      # 노드 출력 데이터
    snapshot: NodeSnapshot | None = None   # 실행 전 상태 스냅샷 (롤백용)
    error: ErrorDetail | None = None       # 오류 상세 (실패 시)
    duration_ms: int = 0                   # 실행 소요 시간 (밀리초)
    started_at: datetime                   # 노드 실행 시작 시각
    finished_at: datetime | None = None    # 노드 실행 종료 시각
```

### NodeSnapshot

```python
class NodeSnapshot(BaseModel):
    captured_at: datetime       # 스냅샷 캡처 시각
    state_data: dict           # 캡처된 상태 데이터 (deep copy)
```

### ErrorDetail

```python
class ErrorDetail(BaseModel):
    code: str                  # 에러 코드 (ErrorCode enum 값)
    message: str               # 에러 메시지
    stack_trace: str | None = None  # 스택 트레이스 (개발 환경만)
```

---

## 4.6 실행 결과 응답 모델 (ExecutionResult)

FastAPI가 Spring Boot에 반환하는 실행 결과 응답입니다.

```python
class ExecutionResult(BaseModel):
    execution_id: str                      # 실행 고유 ID
    workflow_id: str                       # 워크플로우 ID
    status: str                            # 최종 상태
    message: str                           # 상태 메시지
    node_logs: list[NodeLog] = []          # 노드별 실행 로그
    started_at: datetime                   # 실행 시작 시각
    finished_at: datetime | None = None    # 실행 종료 시각
```

---

## 4.7 에러 응답 스키마 (ApiErrorResponse)

FastAPI에서 발생하는 모든 에러는 통일된 형식으로 반환됩니다.

```json
{
  "success": false,
  "error_code": "NODE_EXECUTION_FAILED",
  "message": "node_2 (llm) 실행 중 오류가 발생했습니다.",
  "detail": {
    "node_id": "node_2",
    "node_type": "llm",
    "original_error": "OpenAI API rate limit exceeded"
  }
}
```

```python
class ApiErrorResponse(BaseModel):
    success: bool = False
    error_code: str              # ErrorCode enum 값
    message: str                 # 사용자 친화적 에러 메시지
    detail: dict | None = None   # 추가 컨텍스트 (디버깅용)
```

---

## 4.8 LLM 관련 요청/응답 모델

### 단일 LLM 처리 요청 (POST /api/v1/llm/process)

```python
class LLMProcessRequest(BaseModel):
    prompt: str                     # 처리할 프롬프트
    context: str | None = None      # 추가 컨텍스트
    max_tokens: int = 1024          # 최대 토큰 수

class LLMProcessResponse(BaseModel):
    result: str                     # LLM 응답 결과
    tokens_used: int = 0            # 사용된 토큰 수
```

### 워크플로우 자동 생성 요청 (POST /api/v1/llm/generate-workflow)

```python
class GenerateWorkflowRequest(BaseModel):
    prompt: str                     # 사용자 자연어 프롬프트
    context: str | None = None      # 대화 컨텍스트 (채팅형 생성 시)

class GenerateWorkflowResponse(BaseModel):
    result: dict                    # 생성된 워크플로우 구조 { nodes: [...], edges: [...] }
```

---

## 4.9 트리거 관련 모델

```python
class TriggerCreateRequest(BaseModel):
    workflow_id: str                 # 대상 워크플로우 ID
    user_id: str                    # 사용자 ID
    type: str                       # "cron" | "interval"
    config: dict                    # { hour: 9, minute: 0 } 또는 { seconds: 3600 }
    workflow_definition: dict       # 실행할 워크플로우 정의
    credentials: dict               # 복호화된 서비스 토큰

class TriggerResponse(BaseModel):
    trigger_id: str                 # 트리거 고유 ID
    workflow_id: str                # 워크플로우 ID
    type: str                       # 트리거 유형
    status: str                     # "active" | "inactive"
    next_run: datetime | None       # 다음 실행 예정 시각
```
