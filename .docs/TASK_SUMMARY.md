# Flowify FastAPI — 3인 작업 분담 종합 요약

> 작성일: 2026-04-17 | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17  
> 기반 분석: 코드베이스 전수 조사 (2026-04-17)

---

## 현재 프로젝트 상태

```
FastAPI 백엔드 구현율: 약 65%
──────────────────────────────────────────────────────
✅ 완료된 부분
   - 핵심 실행 엔진 (executor, snapshot, state)
   - LLM 서비스 (LangChain LCEL, 재시도 로직)
   - 통합 서비스 클래스 8개 (Gmail, Slack, Notion, Drive, Sheets, Calendar, REST API, WebCrawler)
   - API 엔드포인트 (실행, 로그, 롤백, 중지, LLM 처리, 워크플로우 생성)
   - 인증 미들웨어 (X-Internal-Token, X-User-ID)
   - 테스트 18개 파일

⚠️ 미완성 부분 (TODO 남음)
   - Input/Output 노드의 실제 서비스 호출 연결
   - Loop 노드 서브플로우 실행
   - 스케줄러 API 엔드포인트 (trigger.py 없음)
   - VectorService/RAG 기능

🐛 발견된 버그
   - MongoDB 인덱스 필드명 전부 snake_case (실제는 camelCase) → 쿼리 인덱스 미적용
   - executor IfElse 분기 맵이 IfElse 아닌 노드도 처리 가능
```

---

## 3인 작업 분담

| 작업자 | 역할 | 핵심 가치 |
|--------|------|---------|
| **A** | 노드 통합 & 서비스 연동 | 실제 워크플로우 E2E 데모 가능하게 함 |
| **B** | 실행 엔진 안정화 & 스케줄러 | 버그 수정 + 스케줄 기능 추가 |
| **C** | 스냅샷/롤백 & 고급 기능 | 안정성 개선 + RAG 기능 |

---

## 전체 작업 목록 (우선순위 순)

### 즉시 수정 (Critical Bugs)

| 파일 | 문제 | 담당 | 예상 시간 |
|------|------|------|---------|
| `app/db/mongodb.py:48-54` | 인덱스 필드명 snake_case → camelCase 수정 | **B** | 30분 |
| `app/core/engine/executor.py:320-335` | `_build_branch_map()` IfElse 타입 미확인 | **B** | 반나절 |

### 중간 발표 (4/29) 전 완료 필수

| 파일 | 작업 | 담당 | 예상 시간 |
|------|------|------|---------|
| `app/core/nodes/input_node.py` | 서비스 연결 구현 (Gmail, Drive, Sheets, WebCrawl) | **A** | 2일 |
| `app/core/nodes/output_node.py` | 서비스 연결 구현 (Slack, Notion, Gmail) | **A** | 2일 |
| `app/core/nodes/logic_node.py` | LoopNodeStrategy 타임아웃 + 단순 변환 구현 | **B** | 1일 |
| `app/api/v1/endpoints/trigger.py` (신규) | 스케줄러 API 엔드포인트 생성 | **B** | 1.5일 |
| `app/main.py` | SchedulerService 초기화 추가 | **B** | 1시간 |
| `app/api/v1/router.py` | trigger 라우터 등록 | **B** | 10분 |
| `app/core/engine/snapshot.py` | DB 조회 메서드 추가 | **C** | 반나절 |
| `app/api/v1/endpoints/execution.py` | rollback 응답 개선 (errorMessage 초기화) | **C** | 1시간 |

### 최종 제출 (6/17) 전 완료

| 파일 | 작업 | 담당 | 예상 시간 |
|------|------|------|---------|
| `app/services/integrations/rest_api.py` | 재시도 로직 우회 수정 | **A** | 반나절 |
| `app/core/nodes/factory.py` | ValueError → FlowifyException | **A** | 1시간 |
| `tests/test_input_node.py` (신규) | Input 노드 테스트 | **A** | 반나절 |
| `tests/test_output_node.py` (신규) | Output 노드 테스트 | **A** | 반나절 |
| `app/core/engine/executor.py` | Stop 엔드포인트 race condition 수정 | **B** | 1일 |
| `app/services/scheduler_service.py` | MongoDB jobstore 설정 | **B** | 1일 |
| `tests/test_loop_node.py` (신규) | Loop 노드 테스트 | **B** | 반나절 |
| `tests/test_scheduler.py` (신규) | 스케줄러 테스트 | **B** | 반나절 |
| `app/models/workflow.py` | EdgeDefinition label 필드 추가 | **C** | 1시간 |
| `app/services/vector_service.py` | ChromaDB + OpenAI Embedding 구현 | **C** | 3일 |
| `docker-compose.yml` | chroma_data volume 추가 | **C** | 30분 |
| `tests/test_vector_service.py` (신규) | VectorService 테스트 | **C** | 반나절 |
| `tests/test_snapshot.py` | DB 조회 메서드 테스트 추가 | **C** | 반나절 |

---

## 의존 관계

```
B-1 (인덱스 수정) ─────────────────→ 쿼리 성능 즉시 개선
                                        ↓
B-2 (branch_map 수정) ──────────────→ IfElse 워크플로우 정확히 동작
                                        ↓
C-3 (EdgeDefinition label 추가) ────→ B-2와 연동하여 더 정확한 분기

A-1 + A-2 (노드 연결) ──────────────→ 실제 워크플로우 E2E 데모 가능
                                        (서비스 클래스는 이미 완성됨)

B-5 (main.py 스케줄러 초기화) ──────→ B-4 (trigger.py API) 동작 가능

C-4 (VectorService) ────────────────→ LLMService.generate_workflow()와 연동
                                        (RAG 기반 워크플로우 생성 고도화)
```

---

## 팀 공통 확인 사항

### 즉시 확인 필요 (Spring Boot 담당자와)

| 확인 항목 | 중요도 | 영향 파일 |
|----------|--------|---------|
| `service_tokens`의 정확한 키 구조 | 🔴 Critical | `input_node.py`, `output_node.py` |
| 노드 `type` 값의 실제 문자열 명세 | 🔴 Critical | `factory.py` |
| 롤백 후 재실행 흐름 (자동 vs 수동) | 🟡 High | `execution.py`, `snapshot.py` |
| edge에 label 필드 포함 여부 | 🟠 Medium | `workflow.py`, `executor.py` |

### 확인 방법

`.docs/FASTAPI_SPRINGBOOT_API_SPEC.md` 내 `service_tokens` 섹션 확인:
- 현재 명세가 최신인지 확인
- Spring Boot 측 `FastApiClient.java`의 요청 body 생성 코드 직접 확인 권장

---

## 각 작업자 문서 링크

| 문서 | 내용 |
|------|------|
| [TASK_A_NODE_INTEGRATION.md](TASK_A_NODE_INTEGRATION.md) | 작업자 A 상세 — 노드 통합 & 서비스 연동 |
| [TASK_B_ENGINE_SCHEDULER.md](TASK_B_ENGINE_SCHEDULER.md) | 작업자 B 상세 — 실행 엔진 & 스케줄러 |
| [TASK_C_SNAPSHOT_ADVANCED.md](TASK_C_SNAPSHOT_ADVANCED.md) | 작업자 C 상세 — 스냅샷/롤백 & 고급 기능 |

---

## 발견된 주요 버그 목록 (전수 조사 결과)

| # | 파일 | 버그 내용 | 심각도 | 담당 |
|---|------|---------|--------|------|
| 1 | `app/db/mongodb.py:48` | 인덱스 필드명 snake_case (실제: camelCase) | 🔴 Critical | B |
| 2 | `app/core/engine/executor.py:320` | `_build_branch_map()` 모든 노드 타입 대상 | 🔴 Critical | B |
| 3 | `app/services/integrations/rest_api.py` | 공개 API 재시도 로직 우회 | 🟡 High | A |
| 4 | `app/core/engine/executor.py` | Stop 후 SUCCESS 저장 race condition | 🟡 High | B |
| 5 | `app/core/nodes/factory.py:22` | `ValueError` 미래 500 에러 노출 | 🟠 Medium | A |
| 6 | `app/models/workflow.py` | EdgeDefinition label 필드 없음 | 🟠 Medium | C |

---

## 테스트 현황

```
현재 테스트 파일 18개
──────────────────────────────────
있음: test_errors, test_execution_api, test_executor, test_health,
      test_integrations/{base,gmail,notion,slack,web_crawler},
      test_llm_api, test_llm_node, test_llm_service,
      test_middleware, test_models, test_snapshot, test_state

없음 (신규 작성 필요):
  A 담당: test_input_node, test_output_node
  B 담당: test_loop_node, test_scheduler
  C 담당: test_vector_service
  공통: test_if_else_node (선택적)
```
