# FastAPI Runtime 구현 가이드

> 작성일: 2026-04-21
> 발신: Spring Backend (flowify-BE-spring)
> 수신: FastAPI Team (flowify-BE)
> 목적: FastAPI 팀이 runtime contract를 구현하기 위해 필요한 모든 정보를 하나의 문서로 제공한다.

---

## 목차

1. [전체 아키텍처](#1-전체-아키텍처)
2. [통신 규약](#2-통신-규약)
3. [API 엔드포인트 4종 상세](#3-api-엔드포인트-4종-상세)
4. [runtime_type 전략 패턴](#4-runtime_type-전략-패턴)
5. [InputNodeStrategy 구현 상세](#5-inputnodestrategy-구현-상세)
6. [OutputNodeStrategy 구현 상세](#6-outputnodestrategy-구현-상세)
7. [LLMNodeStrategy / LoopNodeStrategy / IfElseNodeStrategy](#7-llmnodestrategy--loopnodestrategy--ifelsestrategy)
8. [Canonical Payload Schema 전체 정의](#8-canonical-payload-schema-전체-정의)
9. [서비스별 외부 API 호출 가이드](#9-서비스별-외부-api-호출-가이드)
10. [에러 처리 규칙](#10-에러-처리-규칙)
11. [실행 이력 저장 (MongoDB)](#11-실행-이력-저장-mongodb)
12. [Pydantic 모델 참조 구현](#12-pydantic-모델-참조-구현)
13. [Validation 규칙](#13-validation-규칙)
14. [Transition Policy](#14-transition-policy)
15. [테스트 체크리스트](#15-테스트-체크리스트)

---

## 1. 전체 아키텍처

```
[사용자/FE]
  │ POST /api/workflows/{id}/execute
  ▼
[Spring Boot]  ← editor/public contract owner
  ├─ 1. Workflow 조회 (MongoDB)
  ├─ 2. preflight 검증 (WorkflowValidator)
  │     - 구조 검증 (순환참조, 고립노드, 필수설정)
  │     - catalog 검증 (service key, source_mode key 존재 확인)
  │     - lifecycle 검증 (configured + auth 연결)
  ├─ 3. 서비스 토큰 수집 (OAuthTokenService → 복호화)
  ├─ 4. WorkflowTranslator → runtime model 변환
  │     - runtime_type 결정 (input/output/llm/loop/if_else)
  │     - runtime_source / runtime_sink / runtime_config 생성
  └─ 5. FastApiClient.execute() → POST to FastAPI
       │
       ▼
[FastAPI]  ← runtime/execution owner
  ├─ 6. 인증 검증 (X-Internal-Token)
  ├─ 7. execution 생성 (MongoDB: state="running")
  ├─ 8. 노드 순차 실행
  │     ├─ runtime_type="input"  → InputNodeStrategy  → canonical payload 생성
  │     ├─ runtime_type="llm"    → LLMNodeStrategy     → AI 처리
  │     ├─ runtime_type="if_else"→ IfElseNodeStrategy   → 조건 분기
  │     ├─ runtime_type="loop"   → LoopNodeStrategy     → 반복 실행
  │     └─ runtime_type="output" → OutputNodeStrategy   → 외부 서비스 전송
  ├─ 9. 각 노드 결과를 nodeLogs에 기록
  └─ 10. 최종 상태 업데이트 (completed/failed)
       │
       ▼ { "execution_id": "..." }
[Spring Boot]
  └─ executionId를 클라이언트에 반환
```

**핵심 원칙:**
- Spring은 preflight만 수행하고, 실제 실행은 전부 FastAPI 담당
- Spring은 `workflow_executions`에 **쓰지 않는다** — FastAPI가 MongoDB에 직접 기록
- Spring은 실행 결과 조회 시 MongoDB를 직접 읽는다 (`executionRepository.findById()`)

---

## 2. 통신 규약

### 2.1 인증 헤더

Spring이 **모든 요청**에 포함하는 헤더:

| 헤더 | 값 | 설명 |
|------|----|------|
| `X-Internal-Token` | `${INTERNAL_API_SECRET}` | 서버 간 공유 비밀 토큰. FastAPI는 반드시 검증해야 한다. |
| `X-User-ID` | `"<MongoDB ObjectId>"` | 현재 요청 사용자 ID (Spring JWT에서 추출) |
| `Content-Type` | `application/json` | (WebClient 기본값) |

### 2.2 환경 변수

| 변수 | Spring 기본값 | 설명 |
|------|-------------|------|
| `FASTAPI_URL` | `http://localhost:8000` | FastAPI 베이스 URL |
| `INTERNAL_API_SECRET` | (필수) | 서버 간 인증 토큰 |

```yaml
# Spring application-dev.yml
app:
  fastapi:
    base-url: http://localhost:8000
    internal-token: dev-internal-api-secret
```

### 2.3 Naming Convention

| 영역 | convention | 예시 |
|------|-----------|------|
| editor-origin 필드 (Spring Jackson) | camelCase | `userId`, `dataType`, `outputDataType` |
| runtime 추가 필드 (WorkflowTranslator) | snake_case | `runtime_type`, `runtime_source`, `canonical_input_type` |

이것은 의도된 dual-convention이다. Pydantic에서 `model_config = ConfigDict(populate_by_name=True)` 또는 `alias`로 처리.

### 2.4 타임아웃

- Spring WebClient: `.block()` 호출, 기본 120초 타임아웃
- 재시도 로직 없음 (FastAPI execute에 대해)
- FastAPI는 즉시 `execution_id`를 반환하고 실행은 백그라운드로 처리하는 것을 권장

---

## 3. API 엔드포인트 4종 상세

### 3.1 워크플로우 실행 (핵심)

```
POST /api/v1/workflows/{workflowId}/execute
```

**요청 바디:**
```json
{
  "workflow": {
    "id": "workflow-123",
    "name": "Google Drive 파일 요약 후 Slack 전송",
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
    "trigger": { "type": "manual", "config": {} }
  },
  "service_tokens": {
    "google_drive": "ya29.a0AfH6SMBx...",
    "slack": "xoxb-123456789-..."
  }
}
```

**`service_tokens` 상세:**
- 키: 노드의 `type` 값 (예: `"google_drive"`, `"slack"`)
- 값: **decrypted OAuth access token** — 바로 외부 API 호출에 사용 가능한 평문 토큰
- Spring이 `OAuthTokenService.getDecryptedToken()`으로 복호화 후 전달
- **FastAPI는 추가 복호화 불필요.** 그대로 `Authorization: Bearer {token}` 헤더에 사용
- `auth_required == false`인 서비스(youtube, naver_news, coupang)는 토큰이 포함되지 않음

**응답 (필수):**
```json
{
  "execution_id": "exec_a1b2c3d4"
}
```

> Spring은 `response["execution_id"]`만 읽는다. 이 키가 없으면 `EXECUTION_FAILED` 에러 발생.
> 나머지 필드(status, message 등)는 있어도 무시된다.

---

### 3.2 AI 워크플로우 자동 생성

```
POST /api/v1/workflows/generate
```

**요청 바디:**
```json
{
  "prompt": "매일 오전 9시에 Gmail 받은 편지함을 확인해서 Slack으로 요약 전달"
}
```

**응답 (필수):** Spring `WorkflowCreateRequest` 호환 JSON

```json
{
  "name": "Gmail 요약 → Slack 전송",
  "description": "매일 Gmail을 확인하여 AI 요약 후 Slack으로 전송",
  "nodes": [
    {
      "id": "node_a1b2c3d4",
      "category": "service",
      "type": "gmail",
      "label": "Gmail 수신",
      "config": { "source_mode": "new_email" },
      "position": { "x": 100.0, "y": 200.0 },
      "dataType": null,
      "outputDataType": "SINGLE_EMAIL",
      "role": "start",
      "authWarning": false
    },
    {
      "id": "node_e5f6g7h8",
      "category": "ai",
      "type": "summarize",
      "label": "AI 요약",
      "config": { "action": "summarize" },
      "position": { "x": 100.0, "y": 400.0 },
      "dataType": "SINGLE_EMAIL",
      "outputDataType": "TEXT",
      "role": null,
      "authWarning": false
    },
    {
      "id": "node_i9j0k1l2",
      "category": "service",
      "type": "slack",
      "label": "Slack 전송",
      "config": { "channel": "" },
      "position": { "x": 100.0, "y": 600.0 },
      "dataType": "TEXT",
      "outputDataType": null,
      "role": "end",
      "authWarning": false
    }
  ],
  "edges": [
    { "id": "edge_m3n4o5p6", "source": "node_a1b2c3d4", "target": "node_e5f6g7h8" },
    { "id": "edge_q7r8s9t0", "source": "node_e5f6g7h8", "target": "node_i9j0k1l2" }
  ],
  "trigger": { "type": "schedule", "config": { "cron": "0 9 * * *" } }
}
```

> **주의:** `name` 필드는 필수 (@NotBlank). 없거나 빈 문자열이면 Spring에서 저장 실패.
> `config.source_mode` 값은 반드시 `source_catalog.json`에 존재하는 key여야 한다.

---

### 3.3 실행 중지

```
POST /api/v1/executions/{executionId}/stop
```

**요청 바디:** 없음 (빈 바디)

**응답:** HTTP 2xx면 성공. 바디 내용은 무시됨 (`bodyToMono(Void.class)`).

**구현 요구:**
- 실행 중인 워크플로우의 노드 처리를 즉시 중단
- `workflow_executions.state`를 `"stopped"`으로 업데이트
- 이미 중지된 실행에 대한 중복 요청은 멱등하게 처리 (2xx 반환)
- Spring은 호출 전에 `state == "running"` 검증 완료. 그 외 상태에서는 FastAPI 호출 자체가 발생하지 않음

---

### 3.4 실행 롤백

```
POST /api/v1/executions/{executionId}/rollback
```

**요청 바디:**
```json
{
  "node_id": "node_a1b2c3d4"
}
```

> `node_id`는 `null`일 수 있음 — 이 경우 전체 롤백을 의미

**응답:** HTTP 2xx면 성공. 바디 내용은 무시됨.

**구현 요구:**
- 지정된 노드까지의 실행 결과를 되돌림
- `snapshot.stateData`에 저장된 이전 상태로 복원
- `workflow_executions.state`를 `"rollback_available"` 또는 `"failed"`에서만 허용

---

## 4. runtime_type 전략 패턴

Spring의 `WorkflowTranslator`가 각 노드에 `runtime_type`을 부여한다. FastAPI는 이 값으로 전략을 선택한다.

### 4.1 매핑 규칙

| runtime_type | Spring 결정 조건 | FastAPI 전략 클래스 | 부가 필드 |
|-------------|-----------------|-------------------|----------|
| `input` | `node.role == "start"` | `InputNodeStrategy` | `runtime_source` |
| `output` | `node.role == "end"` | `OutputNodeStrategy` | `runtime_sink` |
| `llm` | AI, DATA_FILTER, AI_FILTER, PASSTHROUGH (기본값) | `LLMNodeStrategy` | `runtime_config` |
| `if_else` | CONDITION_BRANCH | `IfElseNodeStrategy` | `runtime_config` |
| `loop` | LOOP | `LoopNodeStrategy` | `runtime_config` |

### 4.2 전략 선택 구현 (Python 참조)

```python
STRATEGY_MAP = {
    "input": InputNodeStrategy,
    "output": OutputNodeStrategy,
    "llm": LLMNodeStrategy,
    "if_else": IfElseNodeStrategy,
    "loop": LoopNodeStrategy,
}

def get_strategy(node: dict) -> NodeStrategy:
    runtime_type = node.get("runtime_type")

    # runtime_type이 없는 경우 (transition 기간 fallback)
    if not runtime_type:
        role = node.get("role")
        if role == "start":
            runtime_type = "input"
        elif role == "end":
            runtime_type = "output"
        else:
            node_type = (node.get("type") or "").upper()
            if node_type == "LOOP":
                runtime_type = "loop"
            elif node_type == "CONDITION_BRANCH":
                runtime_type = "if_else"
            else:
                runtime_type = "llm"

    strategy_class = STRATEGY_MAP.get(runtime_type)
    if not strategy_class:
        raise UnsupportedRuntimeTypeError(runtime_type)
    return strategy_class()
```

### 4.3 노드 간 데이터 전달

```python
def execute_workflow(workflow: dict, service_tokens: dict):
    nodes = workflow["nodes"]
    edges = workflow["edges"]
    node_outputs = {}  # node_id -> canonical payload

    for node in topological_sort(nodes, edges):
        strategy = get_strategy(node)

        # 이전 노드의 출력을 현재 노드의 입력으로 전달
        prev_node_ids = get_predecessors(node["id"], edges)
        input_data = None
        if prev_node_ids:
            input_data = node_outputs.get(prev_node_ids[0])

        # 실행
        output = strategy.execute(
            node=node,
            input_data=input_data,
            service_tokens=service_tokens,
        )

        node_outputs[node["id"]] = output
```

---

## 5. InputNodeStrategy 구현 상세

### 5.1 역할

외부 서비스에서 데이터를 수집하고, canonical payload 형식으로 변환하여 반환한다.

### 5.2 입력 (Spring이 전달하는 정보)

```json
{
  "runtime_type": "input",
  "runtime_source": {
    "service": "google_drive",
    "mode": "single_file",
    "target": "file-xyz-123",
    "canonical_input_type": "SINGLE_FILE"
  }
}
```

| 필드 | 설명 | 사용처 |
|------|------|--------|
| `runtime_source.service` | 어떤 외부 서비스인지 | 서비스 라우팅 |
| `runtime_source.mode` | 데이터 수집 방식 | 서비스 내 세부 로직 분기 |
| `runtime_source.target` | 수집 대상 (파일 ID, 폴더 ID, 이메일 주소 등) | 외부 API 호출 파라미터 |
| `runtime_source.canonical_input_type` | 반환해야 할 payload 타입 | 출력 형식 결정 |
| `service_tokens[service]` | OAuth access token | 외부 API 인증 |

### 5.3 출력 (canonical payload)

반환값은 반드시 `canonical_input_type`에 맞는 canonical payload여야 한다. 모든 payload는 `"type"` discriminator를 포함한다.

### 5.4 Phase 1 지원 범위

> **runtime 1차 범위는 Spring source catalog의 부분집합이다.**

**Phase 1** — Google OAuth 4종 + Slack (5 서비스, 15 모드):

| service | mode | canonical_input_type | 설명 |
|---------|------|---------------------|------|
| `google_drive` | `single_file` | SINGLE_FILE | 특정 파일 1개 조회 |
| `google_drive` | `file_changed` | SINGLE_FILE | 변경된 파일 조회 |
| `google_drive` | `new_file` | SINGLE_FILE | 새 파일 조회 |
| `google_drive` | `folder_new_file` | SINGLE_FILE | 폴더 내 새 파일 조회 |
| `google_drive` | `folder_all_files` | FILE_LIST | 폴더 전체 파일 목록 |
| `gmail` | `single_email` | SINGLE_EMAIL | 특정 메일 1건 조회 |
| `gmail` | `new_email` | SINGLE_EMAIL | 최신 메일 조회 |
| `gmail` | `sender_email` | SINGLE_EMAIL | 특정 보낸 사람 메일 |
| `gmail` | `starred_email` | SINGLE_EMAIL | 별표 메일 조회 |
| `gmail` | `label_emails` | EMAIL_LIST | 라벨별 메일 목록 |
| `gmail` | `attachment_email` | FILE_LIST | 첨부파일 있는 메일의 파일들 |
| `google_sheets` | `sheet_all` | SPREADSHEET_DATA | 시트 전체 데이터 |
| `google_sheets` | `new_row` | SPREADSHEET_DATA | 새 행 데이터 |
| `google_sheets` | `row_updated` | SPREADSHEET_DATA | 수정된 행 데이터 |
| `slack` | `channel_messages` | TEXT | 채널 메시지 텍스트 |

**Phase 2** (미구현 — 수신 시 reject):

| service | mode(s) | 비고 |
|---------|--------|------|
| `google_calendar` | `daily_schedule`, `weekly_schedule` | schedule trigger 필요 |
| `youtube` | `search`, `channel_new_video`, `video_comments` | auth 불필요 |
| `naver_news` | `keyword_search`, `periodic_collect` | auth 불필요, 크롤링 |
| `coupang` | `product_price`, `product_reviews` | auth 불필요, 크롤링 |
| `github` | `new_pr` | webhook 기반 |
| `notion` | `page_content` | Notion API |

### 5.5 구현 구조 (Python 참조)

```python
class InputNodeStrategy:

    # service → handler 매핑
    SOURCE_HANDLERS = {
        "google_drive": GoogleDriveSourceHandler,
        "gmail": GmailSourceHandler,
        "google_sheets": GoogleSheetsSourceHandler,
        "slack": SlackSourceHandler,
    }

    def execute(self, node: dict, input_data: any, service_tokens: dict) -> dict:
        runtime_source = node["runtime_source"]
        service = runtime_source["service"]
        mode = runtime_source["mode"]
        target = runtime_source.get("target", "")
        canonical_type = runtime_source["canonical_input_type"]

        # 1. 핸들러 찾기
        handler_class = self.SOURCE_HANDLERS.get(service)
        if not handler_class:
            raise UnsupportedRuntimeSourceError(service, mode)

        # 2. 토큰 가져오기
        token = service_tokens.get(service)

        # 3. 외부 API 호출 + canonical payload 변환
        handler = handler_class(token=token)
        result = handler.fetch(mode=mode, target=target)

        # 4. type discriminator 확인
        assert result["type"] == canonical_type
        return result
```

---

## 6. OutputNodeStrategy 구현 상세

### 6.1 역할

이전 노드의 canonical payload를 받아서 외부 서비스에 전달(전송/저장/생성)한다.

### 6.2 입력

```json
{
  "runtime_type": "output",
  "runtime_sink": {
    "service": "slack",
    "config": {
      "channel": "#general",
      "message_format": "markdown"
    }
  }
}
```

| 필드 | 설명 |
|------|------|
| `runtime_sink.service` | 대상 외부 서비스 |
| `runtime_sink.config` | 사용자가 설정한 전송 설정 (channel, to, folder_id 등) |
| `service_tokens[service]` | OAuth access token |
| `input_data` (이전 노드 출력) | canonical payload (type, content 등) |

### 6.3 Phase 1 Sink 서비스 전체 (6종)

| service | accepted_input_types | required config | 동작 |
|---------|---------------------|-----------------|------|
| `slack` | TEXT | `channel` | 채널에 메시지 전송 |
| `gmail` | TEXT, SINGLE_FILE, FILE_LIST | `to`, `subject`, `action` | 메일 발송 또는 임시저장 |
| `notion` | TEXT, SPREADSHEET_DATA, API_RESPONSE | `target_type`, `target_id` | 페이지/DB 항목 생성 |
| `google_drive` | TEXT, SINGLE_FILE, FILE_LIST, SPREADSHEET_DATA | `folder_id` | 파일 업로드 |
| `google_sheets` | TEXT, SPREADSHEET_DATA, API_RESPONSE | `spreadsheet_id`, `write_mode` | 행 추가/덮어쓰기 |
| `google_calendar` | TEXT, SCHEDULE_DATA | `calendar_id`, `event_title_template`, `action` | 일정 생성/수정 |

### 6.4 sink별 input_data 소비 규칙

#### Slack
```python
# input_data: { "type": "TEXT", "content": "..." }
def send_to_slack(token, config, input_data):
    channel = config["channel"]
    message = input_data["content"]
    header = config.get("header", "")
    fmt = config.get("message_format", "plain")
    # Slack API: chat.postMessage
    # POST https://slack.com/api/chat.postMessage
    # Authorization: Bearer {token}
    # Body: { "channel": channel, "text": message }
```

#### Gmail
```python
# input_data가 TEXT인 경우:
#   { "type": "TEXT", "content": "메일 본문..." }
#   → content를 body로, config의 to/subject/action 사용
#
# input_data가 SINGLE_FILE인 경우:
#   { "type": "SINGLE_FILE", "filename": "report.pdf", "content": "base64...", "mime_type": "..." }
#   → 파일을 첨부하여 메일 전송
#
# config.action == "send" → 즉시 발송
# config.action == "draft" → 임시저장
```

#### Google Drive
```python
# input_data가 SINGLE_FILE인 경우:
#   → config.folder_id에 파일 업로드
#   → config.filename_template으로 파일명 생성 (없으면 원본 filename 사용)
#
# input_data가 FILE_LIST인 경우:
#   → items 각각을 folder_id에 업로드
#
# input_data가 TEXT인 경우:
#   → config.file_format (txt/docx/pdf)에 따라 파일 생성 후 업로드
#
# input_data가 SPREADSHEET_DATA인 경우:
#   → CSV 또는 Google Sheets 파일로 변환 후 업로드
```

#### Google Sheets
```python
# input_data가 SPREADSHEET_DATA인 경우:
#   → config.spreadsheet_id의 config.sheet_name 시트에
#   → config.write_mode == "append": 기존 데이터 아래에 행 추가
#   → config.write_mode == "overwrite": 시트 전체 덮어쓰기
#   → headers가 있으면 첫 행으로 사용
#
# input_data가 TEXT인 경우:
#   → 텍스트를 단일 셀 또는 파싱하여 행으로 변환
#
# input_data가 API_RESPONSE인 경우:
#   → data 객체를 테이블 형태로 변환 시도
```

#### Google Calendar
```python
# input_data가 SCHEDULE_DATA인 경우:
#   → items 각각을 config.calendar_id에 일정으로 생성/수정
#   → config.event_title_template으로 제목 생성
#   → config.action == "create": 새 일정 생성
#   → config.action == "update": 기존 일정 수정
#
# input_data가 TEXT인 경우:
#   → 텍스트에서 일정 정보 파싱 시도
```

#### Notion
```python
# input_data가 TEXT인 경우:
#   → config.target_type == "page": 페이지 본문으로 추가
#   → config.target_type == "database": DB 항목의 content 속성에 저장
#
# input_data가 SPREADSHEET_DATA인 경우:
#   → database 항목으로 행 단위 생성
#
# input_data가 API_RESPONSE인 경우:
#   → JSON을 페이지 블록 또는 DB 항목으로 변환
```

### 6.5 구현 구조 (Python 참조)

```python
class OutputNodeStrategy:

    SINK_HANDLERS = {
        "slack": SlackSinkHandler,
        "gmail": GmailSinkHandler,
        "notion": NotionSinkHandler,
        "google_drive": GoogleDriveSinkHandler,
        "google_sheets": GoogleSheetsSinkHandler,
        "google_calendar": GoogleCalendarSinkHandler,
    }

    def execute(self, node: dict, input_data: dict, service_tokens: dict) -> dict:
        runtime_sink = node["runtime_sink"]
        service = runtime_sink["service"]
        sink_config = runtime_sink["config"]

        handler_class = self.SINK_HANDLERS.get(service)
        if not handler_class:
            raise UnsupportedRuntimeSinkError(service)

        token = service_tokens.get(service)
        handler = handler_class(token=token)
        result = handler.send(config=sink_config, input_data=input_data)

        return {"status": "sent", "service": service, "detail": result}
```

---

## 7. LLMNodeStrategy / LoopNodeStrategy / IfElseNodeStrategy

### 7.1 LLMNodeStrategy

```json
{
  "runtime_type": "llm",
  "runtime_config": {
    "node_type": "summarize",
    "output_data_type": "TEXT",
    "action": "summarize",
    "style": "concise"
  }
}
```

- `node_type`: AI 작업 유형 (`summarize`, `translate`, `classify`, `extract`, `custom`)
- `output_data_type`: 출력 canonical type
- `action` + 기타 필드: node.config의 전체 내용이 병합됨
- 입력: 이전 노드의 canonical payload
- 출력: `output_data_type`에 맞는 canonical payload

### 7.2 IfElseNodeStrategy

```json
{
  "runtime_type": "if_else",
  "runtime_config": {
    "node_type": "CONDITION_BRANCH",
    "output_data_type": "...",
    "condition": "..."
  }
}
```

- 입력 데이터를 조건에 따라 평가
- true/false에 따라 다음 노드 분기 (edge에서 구분)

### 7.3 LoopNodeStrategy

```json
{
  "runtime_type": "loop",
  "runtime_config": {
    "node_type": "LOOP",
    "output_data_type": "...",
    "max_iterations": 10
  }
}
```

- 리스트형 입력(FILE_LIST, EMAIL_LIST 등)의 각 항목에 대해 하위 노드 반복 실행

---

## 8. Canonical Payload Schema 전체 정의

> Spring의 `schema_types.json` 기반. 모든 payload에 `"type"` discriminator 필수.

### SINGLE_FILE

```json
{
  "type": "SINGLE_FILE",
  "filename": "report.pdf",
  "content": "base64-encoded-or-text-content...",
  "mime_type": "application/pdf",
  "url": "https://drive.google.com/file/d/xxx"
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"SINGLE_FILE"` 고정 |
| `filename` | string | O | 파일명 |
| `content` | string | X | 파일 내용 (base64 또는 텍스트) |
| `mime_type` | string | X | MIME 타입 |
| `url` | string | X | 원본 파일 URL |

### FILE_LIST

```json
{
  "type": "FILE_LIST",
  "items": [
    { "filename": "doc1.pdf", "mime_type": "application/pdf", "size": 1024, "url": "..." },
    { "filename": "img.png", "mime_type": "image/png", "size": 2048, "url": "..." }
  ]
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"FILE_LIST"` 고정 |
| `items` | array | O | 파일 객체 배열 |
| `items[*].filename` | string | O | 파일명 |
| `items[*].mime_type` | string | X | MIME 타입 |
| `items[*].size` | number | X | 파일 크기 (bytes) |
| `items[*].url` | string | X | 파일 URL |

### SINGLE_EMAIL

```json
{
  "type": "SINGLE_EMAIL",
  "subject": "Meeting reminder",
  "from": "sender@example.com",
  "date": "2026-04-21T09:00:00Z",
  "body": "Don't forget the meeting at 3pm.",
  "attachments": [
    { "filename": "agenda.pdf", "mime_type": "application/pdf", "size": 512 }
  ]
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"SINGLE_EMAIL"` 고정 |
| `subject` | string | O | 제목 |
| `from` | string | O | 보낸 사람 |
| `date` | datetime | O | 날짜 (ISO8601) |
| `body` | string | O | 본문 |
| `attachments` | array | X | 첨부파일 목록 |

### EMAIL_LIST

```json
{
  "type": "EMAIL_LIST",
  "items": [
    { "subject": "Weekly report", "from": "team@example.com", "date": "2026-04-20T10:00:00Z", "body": "..." }
  ]
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"EMAIL_LIST"` 고정 |
| `items` | array | O | 이메일 객체 배열 |
| `items[*].subject` | string | O | 제목 |
| `items[*].from` | string | O | 보낸 사람 |
| `items[*].date` | datetime | O | 날짜 |
| `items[*].body` | string | X | 본문 |

### SPREADSHEET_DATA

```json
{
  "type": "SPREADSHEET_DATA",
  "headers": ["이름", "점수", "등급"],
  "rows": [
    ["홍길동", 95, "A"],
    ["김철수", 82, "B"]
  ],
  "sheet_name": "Sheet1"
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"SPREADSHEET_DATA"` 고정 |
| `rows` | array[array] | O | 행 데이터 (2차원 배열) |
| `headers` | array[string] | X | 열 헤더 |
| `sheet_name` | string | X | 시트 이름 |

### SCHEDULE_DATA

```json
{
  "type": "SCHEDULE_DATA",
  "items": [
    {
      "title": "팀 미팅",
      "start_time": "2026-04-21T14:00:00+09:00",
      "end_time": "2026-04-21T15:00:00+09:00",
      "location": "회의실 A",
      "description": "주간 진행상황 공유"
    }
  ]
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"SCHEDULE_DATA"` 고정 |
| `items` | array | O | 일정 객체 배열 |
| `items[*].title` | string | O | 일정 제목 |
| `items[*].start_time` | datetime | O | 시작 시간 (ISO8601) |
| `items[*].end_time` | datetime | X | 종료 시간 |
| `items[*].location` | string | X | 장소 |
| `items[*].description` | string | X | 설명 |

### API_RESPONSE

```json
{
  "type": "API_RESPONSE",
  "data": {
    "videos": [{ "title": "How to...", "url": "https://youtube.com/..." }]
  },
  "source": "youtube"
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"API_RESPONSE"` 고정 |
| `data` | object | O | 응답 데이터 (서비스별 자유 형식) |
| `source` | string | X | 데이터 출처 서비스명 |

### TEXT

```json
{
  "type": "TEXT",
  "content": "Slack #general 채널의 최근 메시지..."
}
```
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | O | `"TEXT"` 고정 |
| `content` | string | O | 텍스트 내용 |

---

## 9. 서비스별 외부 API 호출 가이드

### 9.1 Google Drive

**인증:** `Authorization: Bearer {service_tokens["google_drive"]}`
**Base URL:** `https://www.googleapis.com/drive/v3`

| mode | API 호출 | 설명 |
|------|---------|------|
| `single_file` | `GET /files/{target}?alt=media` + `GET /files/{target}?fields=name,mimeType` | target = file ID |
| `file_changed` | `GET /files/{target}?fields=name,mimeType,modifiedTime` | 변경 감지 후 파일 내용 조회 |
| `new_file` | `GET /files?q='{target}'+in+parents&orderBy=createdTime+desc&pageSize=1` | target = folder ID |
| `folder_new_file` | `GET /files?q='{target}'+in+parents&orderBy=createdTime+desc&pageSize=1` | target = folder ID |
| `folder_all_files` | `GET /files?q='{target}'+in+parents&fields=files(id,name,mimeType,size)` | target = folder ID |

### 9.2 Gmail

**인증:** `Authorization: Bearer {service_tokens["gmail"]}`
**Base URL:** `https://gmail.googleapis.com/gmail/v1/users/me`

| mode | API 호출 |
|------|---------|
| `single_email` | `GET /messages/{target}?format=full` |
| `new_email` | `GET /messages?maxResults=1&labelIds=INBOX` → `GET /messages/{id}?format=full` |
| `sender_email` | `GET /messages?q=from:{target}&maxResults=1` → `GET /messages/{id}?format=full` |
| `starred_email` | `GET /messages?labelIds=STARRED&maxResults=1` → `GET /messages/{id}?format=full` |
| `label_emails` | `GET /messages?labelIds={target}` → 각각 `GET /messages/{id}?format=full` |
| `attachment_email` | `GET /messages?q=has:attachment&maxResults=1` → 첨부파일 추출 |

**Gmail 발송 (sink):**
- `POST /messages/send` (action=send)
- `POST /drafts` (action=draft)
- MIME 메시지 형식으로 body 구성

### 9.3 Google Sheets

**인증:** `Authorization: Bearer {service_tokens["google_sheets"]}`
**Base URL:** `https://sheets.googleapis.com/v4/spreadsheets`

| mode | API 호출 |
|------|---------|
| `sheet_all` | `GET /{target}/values/{sheetName}` |
| `new_row` | `GET /{target}/values/{sheetName}` → 마지막 행 감지 |
| `row_updated` | `GET /{target}/values/{sheetName}` → 변경 감지 |

**Sheets 쓰기 (sink):**
- `POST /{spreadsheet_id}/values/{sheet_name}:append` (write_mode=append)
- `PUT /{spreadsheet_id}/values/{sheet_name}` (write_mode=overwrite)

### 9.4 Slack

**인증:** `Authorization: Bearer {service_tokens["slack"]}`
**Base URL:** `https://slack.com/api`

| mode/동작 | API 호출 |
|----------|---------|
| `channel_messages` (source) | `GET /conversations.history?channel={target}&limit=20` |
| 메시지 전송 (sink) | `POST /chat.postMessage` body: `{ "channel": config.channel, "text": content }` |

### 9.5 Google Calendar (Phase 2지만 sink는 Phase 1)

**인증:** `Authorization: Bearer {service_tokens["google_calendar"]}`
**Base URL:** `https://www.googleapis.com/calendar/v3`

| 동작 | API 호출 |
|------|---------|
| 일정 생성 (sink, action=create) | `POST /calendars/{calendar_id}/events` |
| 일정 수정 (sink, action=update) | `PUT /calendars/{calendar_id}/events/{eventId}` |

### 9.6 Notion (Phase 2 source, Phase 1 sink)

**인증:** `Authorization: Bearer {service_tokens["notion"]}`, `Notion-Version: 2022-06-28`
**Base URL:** `https://api.notion.com/v1`

| 동작 | API 호출 |
|------|---------|
| 페이지 생성 (sink, target_type=page) | `POST /pages` |
| DB 항목 생성 (sink, target_type=database) | `POST /pages` (parent: database_id) |

---

## 10. 에러 처리 규칙

### 10.1 미지원 서비스/모드 에러

Phase 1 범위 밖 서비스를 수신했을 때:

```json
// HTTP 400
{
  "error_code": "UNSUPPORTED_RUNTIME_SOURCE",
  "detail": "service=github, mode=new_pr is not supported in current runtime phase"
}
```

```json
// HTTP 400
{
  "error_code": "UNSUPPORTED_RUNTIME_SINK",
  "detail": "service=custom_webhook is not supported in current runtime phase"
}
```

> Spring preflight에서 1차 차단하므로 정상적으로는 발생하지 않지만, 방어적으로 구현해야 한다.

### 10.2 외부 API 호출 실패

```json
// HTTP 502
{
  "error_code": "EXTERNAL_SERVICE_ERROR",
  "detail": "Google Drive API returned 403: insufficient permissions",
  "service": "google_drive",
  "node_id": "n1"
}
```

### 10.3 토큰 만료

```json
// HTTP 401
{
  "error_code": "TOKEN_EXPIRED",
  "detail": "OAuth token for google_drive has expired",
  "service": "google_drive"
}
```

### 10.4 노드 실행 중 실패

```json
// HTTP 500
{
  "error_code": "NODE_EXECUTION_FAILED",
  "detail": "Failed to execute node n2: LLM response parsing error",
  "node_id": "n2"
}
```

### 10.5 Spring 측 에러 코드 매핑

| FastAPI 응답 | Spring 처리 |
|-------------|------------|
| HTTP 2xx | 성공 — `execution_id` 추출 |
| HTTP 4xx | `BusinessException(FASTAPI_UNAVAILABLE)` → 클라이언트 502 |
| HTTP 5xx | `BusinessException(FASTAPI_UNAVAILABLE)` → 클라이언트 502 |
| 네트워크 오류 | `BusinessException(FASTAPI_UNAVAILABLE)` → 클라이언트 502 |
| `execution_id` 없음 | `BusinessException(EXECUTION_FAILED)` → 클라이언트 500 |

---

## 11. 실행 이력 저장 (MongoDB)

### 11.1 컬렉션: `workflow_executions`

FastAPI가 직접 MongoDB에 기록해야 한다. Spring은 읽기만 수행한다.

```json
{
  "_id": "exec_a1b2c3d4",
  "workflowId": "workflow-123",
  "userId": "user-abc",
  "state": "running",
  "nodeLogs": [
    {
      "nodeId": "n1",
      "status": "success",
      "inputData": null,
      "outputData": {
        "type": "SINGLE_FILE",
        "filename": "report.pdf",
        "mime_type": "application/pdf"
      },
      "snapshot": {
        "capturedAt": "2026-04-21T10:00:01Z",
        "stateData": { "file_id": "xyz" }
      },
      "error": null,
      "startedAt": "2026-04-21T10:00:00Z",
      "finishedAt": "2026-04-21T10:00:01Z"
    },
    {
      "nodeId": "n2",
      "status": "running",
      "inputData": { "type": "SINGLE_FILE", "filename": "report.pdf" },
      "outputData": null,
      "snapshot": null,
      "error": null,
      "startedAt": "2026-04-21T10:00:01Z",
      "finishedAt": null
    }
  ],
  "errorMessage": null,
  "startedAt": "2026-04-21T10:00:00Z",
  "finishedAt": null
}
```

### 11.2 state 값

| state | 의미 | 전이 조건 |
|-------|------|----------|
| `running` | 실행 중 | execute 호출 시 |
| `completed` | 성공 완료 | 모든 노드 success |
| `failed` | 실패 | 노드 실행 중 에러 발생 |
| `stopped` | 사용자 중지 | stop API 호출 시 |
| `rollback_available` | 롤백 가능 | snapshot이 있는 상태에서 실패 |

### 11.3 nodeLog.status 값

| status | 의미 |
|--------|------|
| `pending` | 대기 중 |
| `running` | 실행 중 |
| `success` | 성공 |
| `failed` | 실패 |
| `skipped` | 이전 노드 실패로 건너뜀 |

### 11.4 롤백 조건

Spring의 `SnapshotService`는 `state`가 `"rollback_available"` 또는 `"failed"`일 때만 롤백을 허용한다.
`snapshot.stateData`에 충분한 복원 정보가 있어야 한다.

---

## 12. Pydantic 모델 참조 구현

```python
from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from enum import Enum


class RuntimeType(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    LLM = "llm"
    IF_ELSE = "if_else"
    LOOP = "loop"


class CanonicalType(str, Enum):
    SINGLE_FILE = "SINGLE_FILE"
    FILE_LIST = "FILE_LIST"
    SINGLE_EMAIL = "SINGLE_EMAIL"
    EMAIL_LIST = "EMAIL_LIST"
    SPREADSHEET_DATA = "SPREADSHEET_DATA"
    SCHEDULE_DATA = "SCHEDULE_DATA"
    API_RESPONSE = "API_RESPONSE"
    TEXT = "TEXT"


class RuntimeSource(BaseModel):
    service: str
    mode: str
    target: str = ""
    canonical_input_type: str


class RuntimeSink(BaseModel):
    service: str
    config: dict[str, Any] = {}


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    node_type: str
    output_data_type: str = ""
    action: str = ""


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0


class RuntimeNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    category: Optional[str] = None
    type: Optional[str] = None
    label: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    position: Optional[Position] = None

    # camelCase fields from Spring Jackson
    dataType: Optional[str] = None          # 입력 데이터 타입
    outputDataType: Optional[str] = None    # 출력 데이터 타입
    role: Optional[str] = None              # "start", "end", null
    authWarning: bool = False

    # snake_case runtime fields from WorkflowTranslator
    runtime_type: Optional[RuntimeType] = None
    runtime_source: Optional[RuntimeSource] = None
    runtime_sink: Optional[RuntimeSink] = None
    runtime_config: Optional[RuntimeConfig] = None


class Edge(BaseModel):
    id: Optional[str] = None
    source: str
    target: str


class TriggerConfig(BaseModel):
    type: str
    config: dict[str, Any] = {}


class RuntimeWorkflow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    userId: str
    nodes: list[RuntimeNode]
    edges: list[Edge]
    trigger: Optional[TriggerConfig] = None


class ExecuteRequest(BaseModel):
    workflow: RuntimeWorkflow
    service_tokens: dict[str, str] = {}


class ExecuteResponse(BaseModel):
    execution_id: str
```

---

## 13. Validation 규칙

### 13.1 InputNodeStrategy validate()

```python
def validate_input_node(node: RuntimeNode):
    rs = node.runtime_source
    if not rs:
        raise ValueError(f"Node {node.id}: runtime_source is required for input nodes")
    if not rs.service:
        raise ValueError(f"Node {node.id}: runtime_source.service is required")
    if not rs.mode:
        raise ValueError(f"Node {node.id}: runtime_source.mode is required")

    # Phase 1 지원 여부 확인
    SUPPORTED_SOURCES = {
        "google_drive": {"single_file", "file_changed", "new_file", "folder_new_file", "folder_all_files"},
        "gmail": {"single_email", "new_email", "sender_email", "starred_email", "label_emails", "attachment_email"},
        "google_sheets": {"sheet_all", "new_row", "row_updated"},
        "slack": {"channel_messages"},
    }

    supported_modes = SUPPORTED_SOURCES.get(rs.service)
    if supported_modes is None:
        raise UnsupportedRuntimeSourceError(rs.service, rs.mode)
    if rs.mode not in supported_modes:
        raise UnsupportedRuntimeSourceError(rs.service, rs.mode)
```

### 13.2 OutputNodeStrategy validate()

```python
def validate_output_node(node: RuntimeNode):
    rk = node.runtime_sink
    if not rk:
        raise ValueError(f"Node {node.id}: runtime_sink is required for output nodes")
    if not rk.service:
        raise ValueError(f"Node {node.id}: runtime_sink.service is required")

    SUPPORTED_SINKS = {"slack", "gmail", "notion", "google_drive", "google_sheets", "google_calendar"}
    if rk.service not in SUPPORTED_SINKS:
        raise UnsupportedRuntimeSinkError(rk.service)

    # config 필수 필드 검증
    REQUIRED_CONFIG = {
        "slack": ["channel"],
        "gmail": ["to", "subject", "action"],
        "notion": ["target_type", "target_id"],
        "google_drive": ["folder_id"],
        "google_sheets": ["spreadsheet_id", "write_mode"],
        "google_calendar": ["calendar_id", "event_title_template", "action"],
    }
    required = REQUIRED_CONFIG.get(rk.service, [])
    for field in required:
        if field not in rk.config or not rk.config[field]:
            raise ValueError(f"Node {node.id}: runtime_sink.config.{field} is required for {rk.service}")
```

### 13.3 input_type 호환성 검증 (OutputNodeStrategy)

```python
ACCEPTED_INPUT_TYPES = {
    "slack": {"TEXT"},
    "gmail": {"TEXT", "SINGLE_FILE", "FILE_LIST"},
    "notion": {"TEXT", "SPREADSHEET_DATA", "API_RESPONSE"},
    "google_drive": {"TEXT", "SINGLE_FILE", "FILE_LIST", "SPREADSHEET_DATA"},
    "google_sheets": {"TEXT", "SPREADSHEET_DATA", "API_RESPONSE"},
    "google_calendar": {"TEXT", "SCHEDULE_DATA"},
}

def validate_input_type_compatibility(service: str, input_data: dict):
    data_type = input_data.get("type")
    accepted = ACCEPTED_INPUT_TYPES.get(service, set())
    if data_type not in accepted:
        raise ValueError(
            f"Sink '{service}' does not accept input type '{data_type}'. "
            f"Accepted: {accepted}"
        )
```

---

## 14. Transition Policy

### 14.1 현재 상태

| 필드 | 역할 | FastAPI 사용법 |
|------|------|---------------|
| `runtime_type` | 전략 선택 **PRIMARY** | 반드시 이 값으로 전략 선택 |
| `runtime_source` | input 노드 정보 **PRIMARY** | service, mode, target, canonical_input_type 사용 |
| `runtime_sink` | output 노드 정보 **PRIMARY** | service, config 사용 |
| `runtime_config` | middle 노드 정보 **PRIMARY** | node_type, output_data_type, action 등 사용 |
| `type`, `category`, `role` | **FALLBACK** | runtime_type 없을 때만 사용 |
| `config` | 원본 설정 **하위 호환** | runtime_source/runtime_sink에 같은 정보가 구조화되어 있음 |

### 14.2 Fallback 규칙

Spring은 항상 `runtime_type`과 `runtime_source`/`runtime_sink`를 생성한다.
하지만 transition 기간 동안 이 필드가 없는 payload가 올 수도 있으므로:

1. `runtime_type` 있으면 → 그대로 사용
2. `runtime_type` 없으면 → `role` + `type` 기반으로 추론 (섹션 4.2 참조)
3. `runtime_source` 있으면 → 그대로 사용
4. `runtime_source` 없으면 → `config["source_mode"]`, `config["target"]` 으로 fallback

### 14.3 전환 일정

1. **즉시:** `runtime_type` 기반 전략 선택 구현
2. **Phase 1 완료:** `runtime_source`/`runtime_sink` 기반 validate/execute 완전 전환
3. **Phase 1 검증 후:** old fallback 코드 제거 가능

---

## 15. 테스트 체크리스트

### 15.1 End-to-End 최소 검증 (Slack source → Slack sink)

```bash
# 1. Spring에서 실행 요청
POST /api/workflows/{id}/execute

# 2. FastAPI가 수신하는 payload 확인
#    - runtime_type: "input" (start node)
#    - runtime_source.service: "slack"
#    - runtime_source.mode: "channel_messages"
#    - service_tokens["slack"]: "xoxb-..."

# 3. FastAPI가 Slack API 호출
#    - conversations.history → TEXT payload 생성

# 4. 다음 노드로 TEXT payload 전달

# 5. output 노드에서 Slack API 호출
#    - chat.postMessage → 메시지 전송

# 6. MongoDB에 실행 결과 기록
#    - state: "completed"
#    - nodeLogs: 각 노드 success
```

### 15.2 서비스별 InputNodeStrategy 단위 테스트

| 테스트 | 검증 항목 |
|--------|----------|
| `google_drive` + `single_file` | SINGLE_FILE payload 반환, filename/content/mime_type 존재 |
| `google_drive` + `folder_all_files` | FILE_LIST payload 반환, items 배열 존재 |
| `gmail` + `single_email` | SINGLE_EMAIL payload 반환, subject/from/date/body 존재 |
| `gmail` + `label_emails` | EMAIL_LIST payload 반환, items 배열 존재 |
| `gmail` + `attachment_email` | FILE_LIST payload 반환 (첨부파일 추출) |
| `google_sheets` + `sheet_all` | SPREADSHEET_DATA payload 반환, rows 존재 |
| `slack` + `channel_messages` | TEXT payload 반환, content 존재 |

### 15.3 서비스별 OutputNodeStrategy 단위 테스트

| 테스트 | 검증 항목 |
|--------|----------|
| `slack` + TEXT 입력 | Slack chat.postMessage 호출 성공 |
| `gmail` + TEXT 입력 (action=send) | 메일 발송 성공 |
| `gmail` + TEXT 입력 (action=draft) | 임시저장 성공 |
| `google_drive` + SINGLE_FILE 입력 | 파일 업로드 성공 |
| `google_sheets` + SPREADSHEET_DATA (append) | 행 추가 성공 |
| `google_sheets` + SPREADSHEET_DATA (overwrite) | 시트 덮어쓰기 성공 |
| `google_calendar` + SCHEDULE_DATA (create) | 일정 생성 성공 |
| `notion` + TEXT 입력 (target_type=page) | 페이지 생성 성공 |

### 15.4 에러 핸들링 테스트

| 테스트 | 기대 결과 |
|--------|----------|
| 미지원 서비스 수신 | `UNSUPPORTED_RUNTIME_SOURCE` 에러 반환 |
| 토큰 만료 상태에서 API 호출 | `TOKEN_EXPIRED` 에러 + nodeLog에 기록 |
| 중간 노드 실패 | 이후 노드 `skipped`, state=`failed` |
| stop API 호출 | 즉시 중단, state=`stopped` |
| 이미 중지된 실행에 stop 재호출 | 멱등하게 2xx 반환 |

### 15.5 Capability API (선택)

```
GET /api/runtime/capabilities
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

> 이 API는 선택사항이다. 구현하면 Spring이 preflight에서 FastAPI 지원 범위를 동적으로 검증할 수 있다.
