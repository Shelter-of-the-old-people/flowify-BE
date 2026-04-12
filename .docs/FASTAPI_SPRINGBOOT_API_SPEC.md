# FastAPI ↔ Spring Boot 통신 명세서

> 작성일: 2026-04-13
> 대상: FastAPI 서버 개발자
> 목적: Spring Boot가 FastAPI에 보내는 요청과, FastAPI가 반드시 돌려줘야 하는 응답 형식을 정확하게 정리한다.

---

## 1. 통신 기본 구조

### 인증 헤더

Spring Boot는 FastAPI로 보내는 **모든 요청**에 아래 두 헤더를 포함한다.

| 헤더 | 값 | 설명 |
|------|----|------|
| `X-Internal-Token` | `${INTERNAL_API_SECRET}` | 서버 간 공유 비밀 토큰. 환경변수로 주입. FastAPI는 이 값을 검증해야 한다. |
| `X-User-ID` | `"<mongoDB ObjectId 문자열>"` | 현재 요청을 트리거한 사용자 ID (Spring Boot JWT에서 추출). |

### 환경 변수 참조

| Spring Boot 변수 | 기본값 | 설명 |
|-----------------|--------|------|
| `FASTAPI_URL` | `http://localhost:8000` | FastAPI 베이스 URL |
| `INTERNAL_API_SECRET` | (필수, 기본값 없음) | 서버 간 인증 토큰 |

---

## 2. API 엔드포인트 목록

### 2-1. 워크플로우 실행

**Spring Boot가 FastAPI를 호출하는 시점:** 사용자가 `POST /api/workflows/{id}/execute` 요청 시.

```
POST {FASTAPI_URL}/api/v1/workflows/{workflowId}/execute
```

**요청 헤더:**
```
X-Internal-Token: <INTERNAL_API_SECRET>
X-User-ID: <userId>
Content-Type: application/json
```

**요청 바디:**
```json
{
  "workflow": {
    "id": "string",
    "name": "string",
    "description": "string | null",
    "userId": "string",
    "sharedWith": ["userId1", "userId2"],
    "isTemplate": false,
    "templateId": "string | null",
    "nodes": [
      {
        "id": "node_abc12345",
        "category": "trigger | service | logic | output",
        "type": "string",
        "label": "string | null",
        "config": { "key": "value" },
        "position": { "x": 100.0, "y": 200.0 },
        "dataType": "string | null",
        "outputDataType": "string | null",
        "role": "start | end | null",
        "authWarning": false
      }
    ],
    "edges": [
      {
        "id": "edge_abc12345",
        "source": "node_abc12345",
        "target": "node_def67890"
      }
    ],
    "trigger": {
      "type": "manual | schedule | webhook",
      "config": { "key": "value" }
    },
    "active": true,
    "createdAt": "2026-04-13T00:00:00Z",
    "updatedAt": "2026-04-13T00:00:00Z"
  },
  "service_tokens": {
    "gmail": "ya29.a0...",
    "slack": "xoxb-..."
  }
}
```

> **주의:** `workflow` 객체는 Spring Boot의 `Workflow` 엔티티가 Jackson 직렬화된 결과다.
> - `boolean isActive` 필드 → JSON 키는 **`"active"`** (Lombok + Jackson 규칙)
> - `boolean isTemplate` 필드 → JSON 키는 **`"template"`**
> - `service_tokens`: `category == "service"` 인 노드의 `type`을 키로, 해당 서비스의 OAuth 액세스 토큰을 값으로 갖는다. 서비스 미연결 시 Spring Boot에서 400 오류를 반환하고 FastAPI 호출 자체가 발생하지 않는다.

**FastAPI 응답 (필수):**
```json
{
  "execution_id": "string"
}
```

Spring Boot는 `response["execution_id"]`를 읽어 클라이언트에 반환한다. 이 키가 없으면 `EXECUTION_FAILED` 에러가 발생한다.

---

### 2-2. AI 워크플로우 자동 생성

**Spring Boot가 FastAPI를 호출하는 시점:** 사용자가 `POST /api/workflows/generate` 요청 시.

```
POST {FASTAPI_URL}/api/v1/workflows/generate
```

**요청 헤더:**
```
X-Internal-Token: <INTERNAL_API_SECRET>
X-User-ID: <userId>
Content-Type: application/json
```

**요청 바디:**
```json
{
  "prompt": "매일 오전 9시에 Gmail 받은 편지함을 확인해서 Slack으로 요약 전달"
}
```

**FastAPI 응답 (필수):**

FastAPI는 Spring Boot의 `WorkflowCreateRequest` 구조와 호환되는 JSON을 반환해야 한다.

```json
{
  "name": "string (필수, @NotBlank)",
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
  "edges": [
    {
      "id": "edge_abc12345",
      "source": "node_abc12345",
      "target": "node_def67890"
    }
  ],
  "trigger": {
    "type": "manual | schedule | webhook",
    "config": {}
  }
}
```

> Spring Boot는 이 응답을 `ObjectMapper.convertValue()`로 `WorkflowCreateRequest`에 매핑한 후 MongoDB에 저장한다. `name` 필드가 없거나 비어 있으면 저장에 실패한다.

---

### 2-3. 실행 롤백

**Spring Boot가 FastAPI를 호출하는 시점:** 사용자가 `POST /api/workflows/{id}/executions/{execId}/rollback` 요청 시.

```
POST {FASTAPI_URL}/api/v1/executions/{executionId}/rollback
```

**요청 헤더:**
```
X-Internal-Token: <INTERNAL_API_SECRET>
X-User-ID: <userId>
Content-Type: application/json
```

**요청 바디:**
```json
{
  "node_id": "string | null"
}
```

> `node_id`는 롤백 기준 노드 ID. Spring Boot에서 `null`을 보낼 수 있으므로 FastAPI는 `null`을 허용해야 한다.

**FastAPI 응답 (필수):**

HTTP 2xx 응답이면 성공으로 처리한다. 응답 바디는 무시한다 (`bodyToMono(Void.class)`).

---

## 3. FastAPI → Spring Boot 방향 콜백 (있을 경우)

현재 Spring Boot 코드에 FastAPI로부터 비동기 콜백을 받는 엔드포인트는 **구현되어 있지 않다.**

워크플로우 실행이 완료되거나 실패했을 때 FastAPI가 Spring Boot에 상태를 알려야 한다면, 아래 방식 중 하나를 협의 후 구현해야 한다.

| 방식 | 설명 |
|------|------|
| **웹훅 콜백** | FastAPI가 완료 시 `POST /api/internal/executions/{execId}/complete` 호출 |
| **폴링** | 프론트가 `GET /api/workflows/{id}/executions/{execId}` 주기적 호출 |

현재는 폴링 방식만 지원 가능하다 (`GET /api/workflows/{id}/executions/{execId}` 구현됨).

---

## 4. Spring Boot 에러 코드

FastAPI에서 HTTP 4xx/5xx 응답 시 Spring Boot가 반환하는 에러:

| 상황 | Spring Boot ErrorCode | HTTP 상태 |
|------|-----------------------|-----------|
| FastAPI 호출 실패 (4xx/5xx) | `FASTAPI_UNAVAILABLE` | 502 |
| FastAPI 응답에 `execution_id` 없음 | `EXECUTION_FAILED` | 500 |
| 실행할 수 없는 상태에서 롤백 요청 | `EXECUTION_FAILED` | 400 |

---

## 5. Spring Boot가 FastAPI에 전달하는 데이터 타입 상세

### NodeDefinition (노드)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `String` | `"node_"` + UUID 8자리. 예: `"node_a1b2c3d4"` |
| `category` | `String` | `"trigger"`, `"service"`, `"logic"`, `"output"` |
| `type` | `String` | 서비스 종류. 예: `"gmail"`, `"slack"`, `"condition"` |
| `label` | `String \| null` | 사용자가 지정한 노드 제목 |
| `config` | `Map<String, Object>` | 노드 설정. 내용은 type별로 다름 |
| `position` | `{ x: number, y: number }` | 캔버스 좌표 |
| `dataType` | `String \| null` | 입력 데이터 타입 |
| `outputDataType` | `String \| null` | 출력 데이터 타입 |
| `role` | `String \| null` | `"start"`, `"end"`, `null` |
| `authWarning` | `boolean` | OAuth 토큰 미연결 경고 여부 |

### EdgeDefinition (엣지)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `String` | `"edge_"` + UUID 8자리. 예: `"edge_a1b2c3d4"` |
| `source` | `String` | 출발 노드 ID |
| `target` | `String` | 도착 노드 ID |

### TriggerConfig (트리거)

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | `String` | `"manual"`, `"schedule"`, `"webhook"` |
| `config` | `Map<String, Object>` | 트리거 설정. 예: `{ "cron": "0 9 * * *" }` |

### service_tokens (서비스 토큰 맵)

```json
{
  "<service_type>": "<decrypted_oauth_access_token>"
}
```

- 키: `NodeDefinition.type` (`category == "service"` 인 노드만 포함)
- 값: MongoDB에 암호화 저장된 OAuth 액세스 토큰을 복호화한 평문 값

---

## 6. Spring Boot ↔ FastAPI 데이터 플로우 요약

```
[사용자]
  │
  ▼ POST /api/workflows/{id}/execute
[Spring Boot]
  ├─ Workflow 조회 (MongoDB)
  ├─ 유효성 검사 (workflowValidator.validate)
  ├─ 서비스 토큰 수집 (OAuthTokenService → 복호화)
  └─ FastApiClient.execute() 호출
       │
       ▼ POST /api/v1/workflows/{id}/execute
       │   Body: { workflow, service_tokens }
       │   Header: X-Internal-Token, X-User-ID
[FastAPI]
       │
       ▼ { "execution_id": "..." }
[Spring Boot]
  └─ executionId를 클라이언트에 반환
       │
       ▼ ApiResponse<String> { "success": true, "data": "exec_xxx" }
[사용자]
```

```
[사용자]
  │
  ▼ POST /api/workflows/generate
[Spring Boot]
  └─ FastApiClient.generateWorkflow() 호출
       │
       ▼ POST /api/v1/workflows/generate
       │   Body: { "prompt": "..." }
       │   Header: X-Internal-Token, X-User-ID
[FastAPI]
       │
       ▼ WorkflowCreateRequest 호환 JSON
[Spring Boot]
  ├─ ObjectMapper로 WorkflowCreateRequest 변환
  └─ MongoDB에 워크플로우 저장 후 WorkflowResponse 반환
```

---

## 7. Spring Boot 실행 이력 저장 구조

FastAPI가 `execution_id`를 반환한 후 Spring Boot는 이를 클라이언트에 바로 전달한다. 현재 Spring Boot는 **실행 상태를 자체적으로 저장하지 않는다**. 실행 결과 조회 (`GET /api/workflows/{id}/executions/{execId}`) 시 MongoDB의 `workflow_executions` 컬렉션을 읽는다.

FastAPI가 실행 결과를 MongoDB에 직접 저장해야 한다면, 아래 스키마를 따라야 한다.

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
      "snapshot": {
        "capturedAt": "ISO8601",
        "stateData": {}
      },
      "error": {
        "code": "string",
        "message": "string",
        "stackTrace": "string | null"
      },
      "startedAt": "ISO8601",
      "finishedAt": "ISO8601"
    }
  ],
  "startedAt": "ISO8601",
  "finishedAt": "ISO8601 | null"
}
```

> **롤백 조건:** Spring Boot `SnapshotService`는 `state`가 `"rollback_available"` 또는 `"failed"`일 때만 롤백을 허용한다. FastAPI는 이 두 값 중 하나로 상태를 설정해야 롤백이 가능하다.

---

## 8. 로컬 개발 환경 설정

Spring Boot `application-dev.yml` 기준:

```yaml
app:
  fastapi:
    base-url: http://localhost:8000
    internal-token: dev-internal-api-secret
```

FastAPI 로컬 서버는 `http://localhost:8000`에서 실행되어야 하며, `X-Internal-Token: dev-internal-api-secret` 헤더를 수락해야 한다.

도커 환경에서는 `docker-compose.yml`의 환경변수로 주입된다:
```yaml
FASTAPI_URL: http://fastapi:8000
INTERNAL_API_SECRET: <공유된 비밀값>
```

---

## 9. 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-04-13 | 최초 작성. execute, generate, rollback 3개 엔드포인트 전체 명세 완성. |
| 2026-04-13 | `NodeDefinition.label`, `EdgeDefinition.id` 필드 추가 반영. |
