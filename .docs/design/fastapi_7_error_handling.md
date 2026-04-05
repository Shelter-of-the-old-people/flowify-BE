# 7. 에러 핸들링 설계

> Spring Boot `ErrorCode`, `BusinessException`, `GlobalExceptionHandler` 대응 문서
> FastAPI 서버의 구조화된 에러 처리 체계를 정의합니다.

---

## 7.1 에러 응답 형식

모든 에러 응답은 다음 형식을 따릅니다:

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

---

## 7.2 에러 코드 체계 (ErrorCode Enum)

Spring Boot의 `ErrorCode` enum과 1:1 대응되는 FastAPI 에러 코드입니다.

| 에러 코드 | HTTP Status | 메시지 | 관련 EXR | 설명 |
|-----------|-------------|--------|---------|------|
| `INTERNAL_ERROR` | 500 | 내부 서버 오류가 발생했습니다 | - | 미처리 예외 |
| `INVALID_REQUEST` | 400 | 잘못된 요청입니다 | - | 요청 유효성 검증 실패 |
| `UNAUTHORIZED` | 401 | 인증되지 않은 요청입니다 | - | X-Internal-Token 불일치 |
| `WORKFLOW_NOT_FOUND` | 404 | 워크플로우를 찾을 수 없습니다 | - | 존재하지 않는 워크플로우 |
| `EXECUTION_NOT_FOUND` | 404 | 실행 이력을 찾을 수 없습니다 | - | 존재하지 않는 실행 ID |
| `INVALID_STATE_TRANSITION` | 400 | 잘못된 상태 전환입니다 | - | WorkflowState 잘못된 전환 |
| `NODE_EXECUTION_FAILED` | 500 | 노드 실행에 실패했습니다 | EXR-06 | 노드 execute() 예외 |
| `LLM_API_ERROR` | 502 | LLM API 호출에 실패했습니다 | EXR-03 | OpenAI API 타임아웃/에러 |
| `LLM_GENERATION_FAILED` | 422 | 워크플로우 자동 생성에 실패했습니다 | EXR-04 | JSON 파싱 실패 등 |
| `EXTERNAL_API_ERROR` | 502 | 외부 서비스 연결에 실패했습니다 | EXR-01 | Google/Slack/Notion API 오류 |
| `OAUTH_TOKEN_INVALID` | 400 | 서비스 인증 토큰이 유효하지 않습니다 | EXR-02 | 만료/잘못된 OAuth 토큰 |
| `CRAWL_FAILED` | 502 | 웹 수집에 실패했습니다 | EXR-07 | 크롤링 대상 접근 불가 |
| `DATA_CONVERSION_FAILED` | 422 | 데이터 변환에 실패했습니다 | EXR-08 | 이기종 데이터 변환 실패 |
| `ROLLBACK_UNAVAILABLE` | 400 | 롤백할 수 없는 상태입니다 | - | rollback_available이 아닌 상태 |

---

## 7.3 예외 클래스 구조

```python
class FlowifyException(Exception):
    """Flowify 비즈니스 예외 기본 클래스"""
    def __init__(self, error_code: ErrorCode, detail: str = None, context: dict = None):
        self.error_code = error_code
        self.detail = detail or error_code.message
        self.context = context or {}
```

### 사용 예시

```python
# 노드 실행 실패
raise FlowifyException(
    ErrorCode.NODE_EXECUTION_FAILED,
    detail="node_2 (llm) 실행 중 오류가 발생했습니다.",
    context={"node_id": "node_2", "node_type": "llm"}
)

# LLM API 오류
raise FlowifyException(
    ErrorCode.LLM_API_ERROR,
    detail="OpenAI API rate limit exceeded",
    context={"model": "gpt-4o", "retry_count": 2}
)

# 외부 서비스 오류
raise FlowifyException(
    ErrorCode.EXTERNAL_API_ERROR,
    detail="Google Drive API 접속에 실패했습니다.",
    context={"service": "google_drive", "status_code": 503}
)
```

---

## 7.4 전역 예외 핸들러

`app/main.py`에서 FastAPI 앱에 등록합니다:

```python
app.add_exception_handler(FlowifyException, flowify_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
```

### flowify_exception_handler

```python
async def flowify_exception_handler(request: Request, exc: FlowifyException):
    return JSONResponse(
        status_code=exc.error_code.http_status,
        content={
            "success": False,
            "error_code": exc.error_code.name,
            "message": exc.detail,
            "detail": exc.context
        }
    )
```

### generic_exception_handler

```python
async def generic_exception_handler(request: Request, exc: Exception):
    # 운영 환경에서는 스택 트레이스를 숨기고, 개발 환경에서만 노출
    detail = {"stack_trace": traceback.format_exc()} if settings.APP_DEBUG else None
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": "내부 서버 오류가 발생했습니다.",
            "detail": detail
        }
    )
```

---

## 7.5 예외 요구사항 대응 매핑 (EXR-01 ~ EXR-08)

### EXR-01: 외부 서비스 API 연결 오류

| 항목 | 내용 |
|------|------|
| **발생 조건** | Google Drive, Slack, Notion 등 외부 API 호출 실패 |
| **에러 코드** | `EXTERNAL_API_ERROR` (502) |
| **재시도 정책** | 최대 3회, Exponential Backoff (1s → 2s → 4s) |
| **시스템 응답** | 재시도 모두 실패 시 해당 노드 FAILED 처리 → 워크플로우 FAILED |
| **처리 위치** | `InputNodeStrategy`, `OutputNodeStrategy`, 각 Integration Service |

### EXR-02: OAuth 토큰 만료/무효

| 항목 | 내용 |
|------|------|
| **발생 조건** | Spring Boot로부터 전달받은 토큰이 만료되었거나 유효하지 않은 경우 |
| **에러 코드** | `OAUTH_TOKEN_INVALID` (400) |
| **시스템 응답** | 해당 노드 FAILED 처리 → Spring Boot에 토큰 갱신 필요 알림 |
| **참고** | FastAPI는 토큰 갱신을 수행하지 않음. Spring Boot가 Lazy Refresh 담당 |

### EXR-03: LLM API 호출 오류

| 항목 | 내용 |
|------|------|
| **발생 조건** | OpenAI API 타임아웃, Rate Limit, 서버 오류 |
| **에러 코드** | `LLM_API_ERROR` (502) |
| **재시도 정책** | Rate Limit → 대기 후 재시도 (1회), 서버 오류 → 최대 2회 재시도 |
| **시스템 응답** | 재시도 실패 시 해당 노드 FAILED |
| **처리 위치** | `LLMService` |

### EXR-04: LLM 자동 생성 실패

| 항목 | 내용 |
|------|------|
| **발생 조건** | LLM이 유효한 워크플로우 JSON 구조를 생성하지 못한 경우 |
| **에러 코드** | `LLM_GENERATION_FAILED` (422) |
| **시스템 응답** | 즉시 에러 반환. 재시도 없음 (사용자가 프롬프트 수정 후 재요청) |
| **처리 위치** | `LLMService.generate_workflow` |

### EXR-05: 워크플로우 유효성 검증 실패

| 항목 | 내용 |
|------|------|
| **발생 조건** | 순환 참조, 고립 노드, 필수 설정 누락 등 |
| **참고** | Spring Boot의 `WorkflowValidator`가 실행 전 검증. FastAPI는 수신된 정의를 신뢰 |
| **에러 코드** | `INVALID_REQUEST` (400) — 기본 구조 유효성만 확인 |

### EXR-06: 워크플로우 실행 중 노드 오류

| 항목 | 내용 |
|------|------|
| **발생 조건** | 워크플로우 실행 중 개별 노드의 execute()에서 예외 발생 |
| **에러 코드** | `NODE_EXECUTION_FAILED` (500) |
| **시스템 응답** | 해당 노드 FAILED → 이후 노드 SKIPPED → 워크플로우 FAILED → ROLLBACK_AVAILABLE |
| **스냅샷** | 실패 노드의 직전 스냅샷이 저장되어 롤백 가능 |
| **처리 위치** | `WorkflowExecutor._execute_node` |

### EXR-07: 웹 수집 오류

| 항목 | 내용 |
|------|------|
| **발생 조건** | 크롤링 대상 사이트 접근 불가, 구조 변경, 타임아웃 |
| **에러 코드** | `CRAWL_FAILED` (502) |
| **재시도 정책** | 최대 2회 재시도 |
| **처리 위치** | `WebCrawlerService`, `InputNodeStrategy._fetch_from_web_crawl` |

### EXR-08: 이기종 데이터 변환 오류

| 항목 | 내용 |
|------|------|
| **발생 조건** | 노드 간 데이터 타입 불일치로 변환 불가 |
| **에러 코드** | `DATA_CONVERSION_FAILED` (422) |
| **시스템 응답** | 해당 노드 FAILED 처리 |
| **참고** | 현재 FastAPI는 dict 기반 느슨한 스키마를 사용하여 대부분의 변환이 암묵적으로 수행됨. 명시적 변환 실패 시에만 발생 |

---

## 7.6 재시도 정책 요약

| 대상 | 최대 재시도 | 백오프 전략 | 적용 위치 |
|------|-----------|-----------|-----------|
| 외부 서비스 API (EXR-01) | 3회 | Exponential (1s → 2s → 4s) | Integration Services |
| LLM Rate Limit (EXR-03) | 1회 | 고정 대기 (API 헤더의 Retry-After) | LLMService |
| LLM 서버 오류 (EXR-03) | 2회 | Exponential (1s → 2s) | LLMService |
| 웹 크롤링 (EXR-07) | 2회 | Exponential (1s → 2s) | WebCrawlerService |
| LLM 생성 실패 (EXR-04) | 0회 | 없음 (즉시 실패) | LLMService |
