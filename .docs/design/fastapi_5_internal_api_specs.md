# 5. 내부 API 인터페이스 명세서

> Spring Boot가 FastAPI 서버를 호출할 때 사용하는 내부 API(Internal API) 전체 스펙을 정의합니다.

---

## 5.1 공통 헤더 규격 (Authentication)

FastAPI는 외부의 직접적인 접근을 차단하기 위해, Spring Boot와의 공유 시크릿 기반 인증 헤더를 요구합니다.

| 헤더 | 필수 | 설명 |
|------|------|------|
| `X-Internal-Token` | Y | Spring Boot와 FastAPI 간 약속된 시크릿 키. 불일치 시 401 반환 |
| `X-User-ID` | Y | 현재 요청을 발생시킨 사용자의 고유 ID. 컨텍스트 추적 및 격리에 사용 |

### 인증 실패 응답

```json
// X-Internal-Token 불일치 또는 누락
HTTP 401 Unauthorized
{
  "success": false,
  "error_code": "UNAUTHORIZED",
  "message": "유효하지 않은 내부 인증 토큰입니다.",
  "detail": null
}
```

---

## 5.2 공통 응답 형식

### 성공 응답

```json
{
  "success": true,
  "data": { ... },
  "message": null
}
```

### 에러 응답

```json
{
  "success": false,
  "error_code": "ERROR_CODE_HERE",
  "message": "사용자 친화적 에러 메시지",
  "detail": { ... }
}
```

---

## 5.3 API 엔드포인트 명세

### 5.3.1 헬스체크

**[GET]** `/api/v1/health`

> 인증 헤더 불필요 (헬스체크는 인프라 레벨에서 사용)

- **Description**: FastAPI 서버의 상태를 확인합니다.
- **Response** (HTTP 200 OK):
  ```json
  {
    "status": "ok",
    "service": "flowify-api",
    "mongodb": "connected",
    "timestamp": "2026-03-30T10:00:00Z"
  }
  ```

---

### 5.3.2 워크플로우 비동기 실행 (Trigger Workflow)

**[POST]** `/api/v1/workflows/{workflow_id}/execute`

- **Description**: 지정된 워크플로우의 파이프라인 실행을 요청합니다. 실행은 백그라운드 태스크로 전환되어 비동기로 진행됩니다.
- **Path Parameters**:
  | 파라미터 | 타입 | 설명 |
  |---------|------|------|
  | `workflow_id` | str | 워크플로우 고유 ID |

- **Request Body** (`fastapi_4_data_models.md` 4.1 참조):
  ```json
  {
    "workflow_id": "wf_12345abc",
    "user_id": "usr_987xyz",
    "credentials": {
      "google": "ya29.a0AfB_...",
      "slack": "xoxb-..."
    },
    "nodes": [ ... ],
    "edges": [ ... ]
  }
  ```

- **Response** (HTTP 200 OK):
  ```json
  {
    "execution_id": "exec_abc123",
    "workflow_id": "wf_12345abc",
    "status": "running",
    "message": "Workflow execution started asynchronously."
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 400 | `INVALID_REQUEST` | 요청 본문 유효성 검증 실패 |
  | 401 | `UNAUTHORIZED` | 내부 토큰 불일치 |
  | 500 | `NODE_EXECUTION_FAILED` | 실행 중 노드 오류 (비동기 실행 시 상태 폴링으로 확인) |

---

### 5.3.3 실행 상태 조회

**[GET]** `/api/v1/executions/{execution_id}/status`

- **Description**: 특정 워크플로우 실행의 현재 상태를 조회합니다. Spring Boot가 프론트엔드의 폴링 요청에 대응하기 위해 사용합니다.
- **Path Parameters**:
  | 파라미터 | 타입 | 설명 |
  |---------|------|------|
  | `execution_id` | str | 실행 고유 ID |

- **Response** (HTTP 200 OK):
  ```json
  {
    "execution_id": "exec_abc123",
    "workflow_id": "wf_12345abc",
    "status": "running",
    "current_node": "node_2",
    "progress": {
      "total_nodes": 3,
      "completed_nodes": 1
    },
    "started_at": "2026-03-30T10:00:00Z",
    "finished_at": null
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 404 | `EXECUTION_NOT_FOUND` | 해당 execution_id 없음 |

---

### 5.3.4 실행 로그 상세 조회

**[GET]** `/api/v1/executions/{execution_id}/logs`

- **Description**: 특정 실행의 노드별 상세 로그를 조회합니다. 실행 모니터링 화면(UC-E02)에서 사용됩니다.
- **Path Parameters**:
  | 파라미터 | 타입 | 설명 |
  |---------|------|------|
  | `execution_id` | str | 실행 고유 ID |

- **Response** (HTTP 200 OK):
  ```json
  {
    "execution_id": "exec_abc123",
    "workflow_id": "wf_12345abc",
    "status": "success",
    "started_at": "2026-03-30T10:00:00Z",
    "finished_at": "2026-03-30T10:00:15Z",
    "node_logs": [
      {
        "node_id": "node_1",
        "status": "success",
        "input_data": { "source": "google_drive" },
        "output_data": { "raw_files": [...], "data_type": "FILE_LIST" },
        "duration_ms": 1200,
        "started_at": "2026-03-30T10:00:01Z",
        "finished_at": "2026-03-30T10:00:02.2Z",
        "error": null
      },
      {
        "node_id": "node_2",
        "status": "success",
        "input_data": { "raw_files": [...] },
        "output_data": { "llm_result": "..." },
        "duration_ms": 8500,
        "started_at": "2026-03-30T10:00:02.3Z",
        "finished_at": "2026-03-30T10:00:10.8Z",
        "error": null
      }
    ]
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 404 | `EXECUTION_NOT_FOUND` | 해당 execution_id 없음 |

---

### 5.3.5 실행 롤백 요청

**[POST]** `/api/v1/executions/{execution_id}/rollback`

- **Description**: 실패한 워크플로우 실행을 마지막 성공 노드의 스냅샷으로 롤백합니다. `rollback_available` 상태인 실행에 대해서만 가능합니다.
- **Path Parameters**:
  | 파라미터 | 타입 | 설명 |
  |---------|------|------|
  | `execution_id` | str | 실행 고유 ID |

- **Request Body** (Optional):
  ```json
  {
    "target_node_id": "node_2"
  }
  ```
  > `target_node_id`를 지정하면 해당 노드의 스냅샷으로 롤백합니다. 미지정 시 마지막 성공 노드로 롤백합니다.

- **Response** (HTTP 200 OK):
  ```json
  {
    "execution_id": "exec_abc123",
    "status": "pending",
    "rollback_point": "node_2",
    "message": "Rolled back to node_2. Ready for re-execution."
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 400 | `ROLLBACK_UNAVAILABLE` | 롤백 불가능 상태 (success, pending 등) |
  | 404 | `EXECUTION_NOT_FOUND` | 해당 execution_id 없음 |

---

### 5.3.6 단일 LLM 처리

**[POST]** `/api/v1/llm/process`

- **Description**: 워크플로우 실행 외에, UI/UX(채팅형 워크플로우 자동 생성 등)에서 단일 프롬프트 처리를 위해 즉각적으로 호출할 수 있는 엔드포인트입니다.
- **Request Body**:
  ```json
  {
    "prompt": "다음 대화를 바탕으로 워크플로우를 구성해줘",
    "context": "사용자: 지메일에 메일이 오면 슬랙으로 요약해서 보내줘.",
    "max_tokens": 1024
  }
  ```

- **Response** (HTTP 200 OK):
  ```json
  {
    "result": "워크플로우 구성 제안: 1. Gmail 입력 노드...",
    "tokens_used": 256
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 502 | `LLM_API_ERROR` | LLM API 호출 실패 (타임아웃, Rate Limit 등) |

---

### 5.3.7 LLM 기반 워크플로우 자동 생성

**[POST]** `/api/v1/llm/generate-workflow`

- **Description**: 사용자의 자연어 프롬프트를 분석하여 워크플로우 구조(노드/엣지)를 자동 생성합니다. UC-W02(채팅형 워크플로우 자동 생성)의 핵심 엔드포인트입니다.
- **Request Body**:
  ```json
  {
    "prompt": "지메일에 메일이 오면 내용을 요약해서 슬랙 #general 채널에 보내줘",
    "context": null
  }
  ```

- **Response** (HTTP 200 OK):
  ```json
  {
    "result": {
      "nodes": [
        {
          "id": "node_1",
          "type": "input",
          "category": "communication",
          "config": { "source": "gmail" },
          "data_type": null,
          "output_data_type": "EMAIL_LIST",
          "role": "start"
        },
        {
          "id": "node_2",
          "type": "llm",
          "category": "ai",
          "config": { "action": "summarize" },
          "data_type": "EMAIL_LIST",
          "output_data_type": "TEXT",
          "role": "middle"
        },
        {
          "id": "node_3",
          "type": "output",
          "category": "communication",
          "config": { "target": "slack", "channel": "#general" },
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
  }
  ```

- **에러 응답**:
  | HTTP Status | error_code | 조건 |
  |------------|------------|------|
  | 422 | `LLM_GENERATION_FAILED` | LLM이 유효한 워크플로우 구조를 생성하지 못함 |
  | 502 | `LLM_API_ERROR` | LLM API 호출 자체 실패 |

---

### 5.3.8 트리거 등록

**[POST]** `/api/v1/triggers`

- **Description**: 워크플로우의 자동 실행 트리거를 등록합니다. APScheduler를 사용하여 cron 또는 interval 기반 스케줄을 등록합니다.
- **Request Body**:
  ```json
  {
    "workflow_id": "wf_12345abc",
    "user_id": "usr_987xyz",
    "type": "cron",
    "config": { "hour": 9, "minute": 0 },
    "workflow_definition": { "nodes": [...], "edges": [...] },
    "credentials": { "google": "ya29...", "slack": "xoxb-..." }
  }
  ```

- **Response** (HTTP 200 OK):
  ```json
  {
    "trigger_id": "trigger_abc123",
    "workflow_id": "wf_12345abc",
    "type": "cron",
    "status": "active",
    "next_run": "2026-03-31T09:00:00Z"
  }
  ```

---

### 5.3.9 트리거 삭제

**[DELETE]** `/api/v1/triggers/{trigger_id}`

- **Description**: 등록된 트리거를 삭제합니다.
- **Path Parameters**:
  | 파라미터 | 타입 | 설명 |
  |---------|------|------|
  | `trigger_id` | str | 트리거 고유 ID |

- **Response** (HTTP 200 OK):
  ```json
  {
    "trigger_id": "trigger_abc123",
    "status": "deleted",
    "message": "Trigger removed successfully."
  }
  ```

---

### 5.3.10 트리거 목록 조회

**[GET]** `/api/v1/triggers`

- **Description**: 등록된 모든 트리거의 목록을 조회합니다.
- **Query Parameters**:
  | 파라미터 | 타입 | 필수 | 설명 |
  |---------|------|------|------|
  | `workflow_id` | str | N | 특정 워크플로우의 트리거만 조회 |

- **Response** (HTTP 200 OK):
  ```json
  {
    "triggers": [
      {
        "trigger_id": "trigger_abc123",
        "workflow_id": "wf_12345abc",
        "type": "cron",
        "status": "active",
        "next_run": "2026-03-31T09:00:00Z"
      }
    ]
  }
  ```

---

## 5.4 엔드포인트 요약 테이블

| Method | Path | 설명 | 인증 | 관련 UC |
|--------|------|------|------|---------|
| GET | `/api/v1/health` | 헬스체크 | 불필요 | - |
| POST | `/api/v1/workflows/{id}/execute` | 워크플로우 비동기 실행 | 필수 | UC-E01 |
| GET | `/api/v1/executions/{id}/status` | 실행 상태 조회 | 필수 | UC-E02 |
| GET | `/api/v1/executions/{id}/logs` | 실행 로그 조회 | 필수 | UC-E02 |
| POST | `/api/v1/executions/{id}/rollback` | 롤백 요청 | 필수 | UC-E01, EXR-06 |
| POST | `/api/v1/llm/process` | 단일 LLM 처리 | 필수 | UC-A01 |
| POST | `/api/v1/llm/generate-workflow` | 워크플로우 자동 생성 | 필수 | UC-W02 |
| POST | `/api/v1/triggers` | 트리거 등록 | 필수 | UC-P01 |
| DELETE | `/api/v1/triggers/{id}` | 트리거 삭제 | 필수 | UC-P01 |
| GET | `/api/v1/triggers` | 트리거 목록 조회 | 필수 | UC-P01 |
