# Flowify 성능 지표 및 측정 계획

> 비기능 요구사항(SPR-01~04)과 인수 시험(PT-01~07)에 대응하는 성능 측정 전략을 정의합니다.
> FastAPI 서버(AI/실행 엔진)와 Spring Boot 서버(메인 BE) 양쪽을 모두 포함하되, 본 문서는 FastAPI 서버 중심으로 작성합니다.

---

## 1. 성능 지표 총괄표

| 지표 ID | 카테고리 | 지표명 | 목표값 | 관련 요구사항 | 관련 시험 | 측정 대상 |
|---------|---------|--------|--------|-------------|----------|----------|
| PM-01 | 응답 시간 | API 응답 시간 (일반) | 평균 500ms 이내 | SPR-01 | PT-01 | FastAPI + Spring Boot |
| PM-02 | 응답 시간 | LLM 처리 응답 시간 | 최대 30초 이내 | SPR-01 | PT-02 | FastAPI (LLMService) |
| PM-03 | 응답 시간 | 트리거 실행 시작 지연 | 감지 후 3초 이내 | SPR-01 | PT-07 | FastAPI (SchedulerService) |
| PM-04 | 응답 시간 | 외부 서비스 API 호출 | 개별 15초 이내 | SPR-01 | - | FastAPI (Integration Services) |
| PM-05 | 동시 처리 | 동시 접속 사용자 | 최소 50명 | SPR-02 | PT-03 | Spring Boot + FastAPI |
| PM-06 | 동시 처리 | 동시 워크플로우 실행 | 최소 20개 | SPR-02 | PT-04 | FastAPI (WorkflowExecutor) |
| PM-07 | 동시 처리 | LLM 동시 요청 | 최대 10건 | SPR-02 | - | FastAPI (LLMService) |
| PM-08 | 자원 사용률 | CPU 사용률 | 평균 70% 이하 | SPR-03 | - | FastAPI 컨테이너 |
| PM-09 | 자원 사용률 | 메모리 사용률 | 평균 80% 이하 | SPR-03 | - | FastAPI 컨테이너 |
| PM-10 | 자원 사용률 | LLM 호출 당 메모리 | 200MB 이하 | SPR-03 | - | FastAPI 프로세스 |

---

## 2. 측정 도구 및 환경

### 2.1 도구 선정

| 도구 | 용도 | 적용 지표 |
|------|------|----------|
| **Locust** | 부하 테스트 (Python 기반, FastAPI와 동일 생태계) | PM-01, PM-05, PM-06 |
| **pytest + httpx** | API 단위 성능 테스트 | PM-01, PM-02, PM-03, PM-04 |
| **time.perf_counter** | 코드 레벨 실행 시간 측정 (미들웨어/데코레이터) | PM-01~04 |
| **psutil** | CPU/메모리 사용률 모니터링 | PM-08, PM-09, PM-10 |
| **Docker stats** | 컨테이너 자원 모니터링 | PM-08, PM-09 |
| **FastAPI Middleware** | 요청별 응답 시간 자동 로깅 | PM-01 |

### 2.2 측정 환경

| 환경 | 구성 | 비고 |
|------|------|------|
| **로컬 테스트** | Docker Compose (FastAPI + MongoDB) | 개발 중 단위 성능 검증 |
| **스테이징** | Cloudtype 배포 환경 (Spring Boot + FastAPI + MongoDB) | 통합 성능 검증 |
| **부하 테스트** | Locust 클라이언트 → 스테이징 환경 | 동시 접속/실행 검증 |

---

## 3. 지표별 측정 방법

### 3.1 PM-01: API 응답 시간 (일반)

**대상 엔드포인트:**

| 엔드포인트 | 예상 소요 | 비고 |
|-----------|----------|------|
| `GET /api/v1/health` | < 50ms | 기준 벤치마크 |
| `GET /api/v1/executions/{id}/status` | < 200ms | MongoDB 단건 조회 |
| `GET /api/v1/executions/{id}/logs` | < 500ms | MongoDB 조회 + 직렬화 |
| `GET /api/v1/triggers` | < 200ms | 메모리 기반 조회 |

**측정 방법:**

```python
# FastAPI 미들웨어로 자동 측정
@app.middleware("http")
async def add_performance_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    # 로그 기록 (운영 환경에서는 샘플링)
    if duration_ms > 500:
        logger.warning(f"Slow API: {request.url.path} took {duration_ms:.2f}ms")
    return response
```

**합격 기준:** 100회 연속 호출 시 평균 응답 시간 **500ms 이내**, p95 **1000ms 이내**

---

### 3.2 PM-02: LLM 처리 응답 시간

**대상 엔드포인트:**

| 엔드포인트 | 예상 소요 | 비고 |
|-----------|----------|------|
| `POST /api/v1/llm/process` | 3~15초 | 동기 응답 |
| `POST /api/v1/llm/generate-workflow` | 5~25초 | JSON 파싱 포함 |
| 워크플로우 내 LLM 노드 | 3~20초 | 비동기 실행 (폴링) |

**측정 방법:**

```python
# LLMService 내부 측정
async def process(self, prompt: str, context: str = None) -> str:
    start = time.perf_counter()
    result = await self._chain.ainvoke({"prompt": prompt, "context": context})
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(f"LLM process: {duration_ms:.0f}ms, tokens: {len(result.split())}")
    return result
```

**합격 기준:**
- 10회 실행 시 **전체 최대 30초 이내** 완료
- 진행 상태 폴링 시 **1초 이내** 상태 응답

---

### 3.3 PM-03: 트리거 실행 시작 지연

**측정 방법:**

```python
# SchedulerService에서 측정
async def _trigger_workflow(self, workflow_id: str, ...):
    triggered_at = datetime.utcnow()  # APScheduler가 job을 시작한 시각
    execution = await executor.execute(workflow_definition, credentials)
    started_at = execution.started_at  # 실제 실행 시작 시각
    delay_ms = (started_at - triggered_at).total_seconds() * 1000
    logger.info(f"Trigger delay for {workflow_id}: {delay_ms:.0f}ms")
```

**합격 기준:** 트리거 감지 후 워크플로우 첫 노드 실행 시작까지 **3초 이내**

---

### 3.4 PM-04: 외부 서비스 API 호출 시간

**측정 대상:**

| 서비스 | 호출 | 타임아웃 |
|--------|------|---------|
| GoogleDriveService | list_files, download_file | 15초 |
| GmailService | list_messages, send_message | 15초 |
| GoogleSheetsService | read_range, write_range | 15초 |
| GoogleCalendarService | list_events, create_event | 15초 |
| SlackService | send_message | 10초 |
| NotionService | create_page | 10초 |
| WebCrawlerService | crawl | 15초 |
| OpenAI (LLMService) | chat.completions | 30초 |

**측정 방법:**

```python
# httpx 클라이언트에 타임아웃 + 로깅
async with httpx.AsyncClient(timeout=15.0) as client:
    start = time.perf_counter()
    response = await client.get(url, headers=headers)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(f"External API [{service}]: {duration_ms:.0f}ms, status={response.status_code}")
```

**합격 기준:** 개별 호출 당 **15초 이내** (LLM은 30초), 재시도 포함 시 **45초 이내**

---

### 3.5 PM-05/06: 동시 처리 성능

**Locust 테스트 시나리오:**

```python
# locustfile.py
from locust import HttpUser, task, between

class FlowifyUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.headers = {
            "X-Internal-Token": "test-secret",
            "X-User-ID": f"user_{self.environment.runner.user_count}"
        }

    @task(3)
    def check_health(self):
        self.client.get("/api/v1/health")

    @task(2)
    def check_execution_status(self):
        self.client.get("/api/v1/executions/test_exec_001/status", headers=self.headers)

    @task(1)
    def execute_workflow(self):
        self.client.post(
            "/api/v1/workflows/wf_test/execute",
            json={"workflow_id": "wf_test", "user_id": "usr_test", ...},
            headers=self.headers
        )
```

**테스트 구성:**

| 시나리오 | 동시 사용자 | 지속 시간 | 합격 기준 |
|---------|-----------|----------|----------|
| 동시 접속 (PM-05) | 50명 | 5분 | 요청 실패율 < 1%, p95 응답 < 2초 |
| 동시 워크플로우 (PM-06) | 20개 동시 실행 | 3분 | 전체 실행 완료, 교착 상태 없음 |

---

### 3.6 PM-08/09/10: 자원 사용률

**측정 방법:**

```bash
# Docker stats 기반 모니터링 (1초 간격, 5분간)
docker stats flowify-fastapi --format "{{.CPUPerc}}\t{{.MemUsage}}" --no-stream
```

```python
# psutil 기반 인-프로세스 모니터링 (테스트 코드 내)
import psutil

def get_resource_usage():
    process = psutil.Process()
    return {
        "cpu_percent": process.cpu_percent(interval=1),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "memory_percent": process.memory_percent()
    }
```

**합격 기준:**

| 시나리오 | CPU | 메모리 | 비고 |
|---------|-----|--------|------|
| 유휴 상태 | < 5% | < 200MB | 기본 프로세스 + MongoDB 연결 |
| 단일 워크플로우 실행 | < 30% | < 400MB | LLM 노드 포함 |
| 20개 동시 실행 (피크) | < 70% | < 80% | SPR-03 합격 기준 |
| LLM 호출 1건 | - | +200MB 이내 | 호출 전후 메모리 증분 |

---

## 4. 테스트 실행 계획

### 4.1 단위 성능 테스트 (pytest 기반)

```
tests/
├── performance/
│   ├── test_api_response_time.py      # PM-01: 엔드포인트별 응답 시간
│   ├── test_llm_performance.py        # PM-02: LLM 처리 시간
│   ├── test_trigger_latency.py        # PM-03: 트리거 지연
│   ├── test_external_api_timeout.py   # PM-04: 외부 API 타임아웃
│   └── test_resource_usage.py         # PM-08~10: 자원 사용률
```

**실행 방법:**

```bash
# 전체 성능 테스트
pytest tests/performance/ -v --tb=short

# 특정 지표만
pytest tests/performance/test_api_response_time.py -v
```

### 4.2 부하 테스트 (Locust 기반)

```bash
# 동시 접속 테스트 (50명, 5분)
locust -f tests/load/locustfile.py --users 50 --spawn-rate 10 --run-time 5m --host http://localhost:8000

# 동시 워크플로우 테스트 (20개)
locust -f tests/load/locust_workflow.py --users 20 --spawn-rate 5 --run-time 3m --host http://localhost:8000
```

### 4.3 실행 일정

| 단계 | 시기 | 대상 테스트 | 비고 |
|------|------|-----------|------|
| Phase B 완료 후 | 핵심 기능 구현 후 | PM-01, PM-02, PM-03 | API/LLM/트리거 기본 성능 |
| Phase C 완료 후 | 외부 연동 구현 후 | PM-04 | 외부 서비스 호출 성능 |
| 통합 테스트 | 전체 기능 완료 후 | PM-05, PM-06, PM-08~10 | 부하 + 자원 사용률 |
| 최종 검증 | 배포 전 | 전체 (PM-01~10) | 인수 시험 대응 |

---

## 5. 성능 로깅 및 모니터링 설계

### 5.1 실행 로그 내 성능 데이터

워크플로우 실행 시 MongoDB에 저장되는 `NodeLog`에 이미 `duration_ms` 필드가 포함되어 있습니다.

```json
{
  "execution_id": "exec_abc123",
  "node_logs": [
    {
      "node_id": "node_1",
      "status": "success",
      "duration_ms": 1200,
      "started_at": "...",
      "finished_at": "..."
    }
  ]
}
```

이 데이터를 활용하여 다음을 추적합니다:
- **노드별 평균 실행 시간**: 병목 노드 식별
- **워크플로우 전체 실행 시간**: E2E 성능 추적
- **노드 타입별 성능 분포**: LLM 노드 vs 일반 노드 비교

### 5.2 성능 응답 헤더

모든 FastAPI 응답에 다음 헤더를 포함합니다:

| 헤더 | 값 | 용도 |
|------|-----|------|
| `X-Response-Time-Ms` | 처리 시간 (ms) | 클라이언트 측 성능 모니터링 |
| `X-Request-ID` | UUID | 요청 추적 |

---

## 6. 인수 시험(PT) 대응 매트릭스

| 인수 시험 ID | 시험 내용 | 성능 지표 | 측정 도구 | 합격 기준 |
|-------------|----------|----------|----------|----------|
| PT-01 | API 응답 시간 | PM-01 | pytest + httpx | 100회 평균 500ms 이내 |
| PT-02 | LLM 처리 시간 | PM-02 | pytest + 타이머 | 10회 최대 30초 이내 |
| PT-03 | 동시 접속 처리 | PM-05 | Locust (50명) | 실패율 < 1%, p95 < 2초 |
| PT-04 | 동시 워크플로우 | PM-06 | Locust (20개) | 전체 정상 완료 |
| PT-05 | FE 초기 로딩 | - | Lighthouse | LCP 3초 이내 (FE 담당) |
| PT-06 | 캔버스 렌더링 | - | Chrome DevTools | 50 노드 60fps (FE 담당) |
| PT-07 | 트리거 지연 | PM-03 | pytest + 타이머 | 감지 후 3초 이내 |

---

## 7. 성능 개선 전략 (병목 발생 시)

| 병목 유형 | 증상 | 개선 방안 |
|-----------|------|----------|
| LLM 응답 지연 | PM-02 > 30초 | 스트리밍 응답 전환, 프롬프트 최적화, 모델 경량화 (gpt-4o-mini) |
| MongoDB 조회 느림 | PM-01 > 500ms | 인덱스 추가 (workflow_id, execution_id), 쿼리 프로젝션 |
| 동시 실행 교착 | PM-06 실패 | asyncio.Semaphore로 동시성 제어, 커넥션 풀 크기 조정 |
| 메모리 초과 | PM-10 > 200MB | LLM 스트리밍 응답, 대용량 데이터 페이지네이션 |
| 외부 API 타임아웃 | PM-04 > 15초 | 타임아웃 단축 + 빠른 실패, 캐싱 (반복 호출 시) |
| 트리거 지연 | PM-03 > 3초 | APScheduler 스레드 풀 크기 조정, 워크플로우 정의 캐싱 |
