# Flowify FastAPI — 3인 작업 분담 종합 요약

> 작성일: 2026-04-17 | **v2 업데이트: 2026-04-23** | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17  
> 기반 분석: 코드베이스 전수 조사 (2026-04-17) + v2 런타임 컨트랙트 통합 (2026-04-23)

---

## 현재 프로젝트 상태

```
FastAPI 백엔드 구현율: 약 85%  (v2 컨트랙트 + 스케줄러/스냅샷/롤백 반영 후)
──────────────────────────────────────────────────────
✅ 완료된 부분
   - 핵심 실행 엔진 (executor — v2 canonical payload, runtime_type 기반)
   - 노드 전략 패턴 (input/output/llm/if_else/loop — v2 시그니처)
   - NodeFactory (create_from_node_def + runtime_type 추론 fallback)
   - Canonical Payload 모델 8종 (SINGLE_FILE, FILE_LIST, SINGLE_EMAIL, ...)
   - 노드 서비스 연결 (Input: 4 서비스 15 모드, Output: 6 서비스)
   - LLM 서비스 (LangChain LCEL, 재시도 로직)
   - 통합 서비스 클래스 8개 (Gmail, Slack, Notion, Drive, Sheets, Calendar, REST API, WebCrawler)
   - API 엔드포인트 (실행, 로그, 롤백, 중지, LLM 처리, 워크플로우 생성)
   - 인증 미들웨어 (X-Internal-Token, X-User-ID)
   - Dual naming convention (camelCase editor + snake_case runtime)
   - EdgeDefinition label 필드 + label 기반 IfElse 분기
   - Stop race condition 보호 (조건부 upsert)
   - MongoDB 인덱스 필드명 수정
   - 스케줄러 API (trigger.py CRUD + main.py 초기화 + router 등록)
   - Snapshot DB 조회 메서드 (get_snapshot_from_db, get_last_success_snapshot)
   - Rollback 응답 개선 (errorMessage/finishedAt 초기화)
   - 테스트 120개 통과 (18개 파일)

⚠️ 미완성 부분 (TODO 남음)
   - VectorService/RAG 기능

🐛 남은 버그
   - rest_api.py 공개 API 재시도 로직 우회
```

---

## v2 런타임 컨트랙트 변경 핵심 요약

모든 작업자가 인지해야 하는 v2 변경:

| 변경 사항 | 설명 |
|-----------|------|
| **노드 시그니처** | `execute(input_data)` → `execute(node, input_data, service_tokens)` |
| **validate 시그니처** | `validate()` → `validate(node: dict)` |
| **데이터 흐름** | flat dict 누적 → **canonical payload** (per-node, `type` 필드 필수) |
| **토큰 전달** | `input_data["credentials"]` → `service_tokens` 별도 파라미터 |
| **입력 라우팅** | `config["source"]` → `node["runtime_source"]` (service + mode) |
| **출력 라우팅** | `config["target"]` → `node["runtime_sink"]` (service + config) |
| **팩토리** | `factory.create(type, config)` → `factory.create_from_node_def(node_def)` |
| **IfElse 분기** | 모든 2-outgoing 노드 → **if_else 노드만** + label 기반 우선 |

---

## 3인 작업 분담

| 작업자 | 역할 | 핵심 가치 | v2 후 남은 작업 |
|--------|------|---------|---------------|
| **A** | 노드 통합 & 서비스 연동 | 실제 워크플로우 E2E 데모 가능하게 함 | rest_api.py 버그 수정, 테스트 작성 |
| **B** | 실행 엔진 안정화 & 스케줄러 | 스케줄 기능 추가 | trigger.py 생성, 스케줄러 초기화, 테스트 작성 |
| **C** | 스냅샷/롤백 & 고급 기능 | 안정성 개선 + RAG 기능 | snapshot DB 조회, rollback 개선, VectorService |

---

## 전체 작업 목록 (우선순위 순)

### ✅ 완료 항목 (v2 컨트랙트 통합으로 해결)

| 파일 | 작업 | 담당 | 상태 |
|------|------|------|------|
| `app/db/mongodb.py` | 인덱스 필드명 camelCase 수정 | B | ✅ 883bec5 |
| `app/core/engine/executor.py` | _build_branch_map IfElse 필터링 | B | ✅ v2 |
| `app/core/nodes/input_node.py` | 서비스 연결 (4 서비스, 15 모드) | A | ✅ v2 |
| `app/core/nodes/output_node.py` | 서비스 연결 (6 서비스) | A | ✅ v2 |
| `app/core/nodes/factory.py` | ValueError → FlowifyException + create_from_node_def | A | ✅ v2 |
| `app/core/nodes/logic_node.py` | LoopNode canonical payload + 타임아웃 | B | ✅ v2 |
| `app/core/engine/executor.py` | Stop race condition 보호 | B | ✅ v2 |
| `app/models/workflow.py` | EdgeDefinition label 필드 | C | ✅ v2 |
| `app/core/nodes/base.py` | v2 시그니처 (node, input_data, service_tokens) | 공통 | ✅ v2 |
| `app/models/canonical.py` | Canonical Payload 8종 모델 | 공통 | ✅ v2 |
| `app/models/requests.py` | ExecutionResult 간소화 (execution_id만) | 공통 | ✅ v2 |
| `app/api/v1/endpoints/trigger.py` | 스케줄러 API CRUD (POST/GET/DELETE) | B | ✅ 구현 완료 |
| `app/main.py` | SchedulerService 초기화 + app.state 등록 | B | ✅ 구현 완료 |
| `app/api/v1/router.py` | trigger 라우터 등록 | B | ✅ 구현 완료 |
| `app/core/engine/snapshot.py` | DB 조회 메서드 (get_snapshot_from_db, get_last_success_snapshot) | C | ✅ 구현 완료 |
| `app/api/v1/endpoints/execution.py` | rollback 개선 (errorMessage/finishedAt 초기화) | C | ✅ 구현 완료 |

### 중간 발표 (4/29) 전 완료 필수

> 중간 발표 전 필수 구현 항목은 모두 완료됨. 아래는 테스트 작성만 남은 상태.

없음 — 모든 중간 발표 필수 항목 완료.

### 최종 제출 (6/17) 전 완료

| 파일 | 작업 | 담당 |
|------|------|------|
| `app/services/integrations/rest_api.py` | 재시도 로직 우회 수정 | **A** |
| `tests/test_input_node.py` (신규) | Input 노드 테스트 (v2 시그니처) | **A** |
| `tests/test_output_node.py` (신규) | Output 노드 테스트 (v2 시그니처) | **A** |
| `app/services/scheduler_service.py` | MongoDB jobstore 설정 | **B** |
| `tests/test_loop_node.py` (신규) | Loop 노드 테스트 (v2 시그니처) | **B** |
| `tests/test_scheduler.py` (신규) | 스케줄러 테스트 | **B** |
| `app/services/vector_service.py` | ChromaDB + OpenAI Embedding 구현 | **C** |
| `docker-compose.yml` | chroma_data volume 추가 | **C** |
| `tests/test_vector_service.py` (신규) | VectorService 테스트 | **C** |
| `tests/test_snapshot.py` | DB 조회 메서드 테스트 추가 | **C** |

---

## 의존 관계

```
[v2 완료] ───────────────────────────────→ 노드 E2E 데모 가능
   input/output/llm/logic 서비스 연결 완료
   canonical payload 기반 데이터 흐름 구현

B-5 (main.py 스케줄러 초기화) ──────────→ B-4 (trigger.py API) 동작 가능

C-1 (snapshot DB 조회) ────────────────→ C-2 (rollback 개선) 정확한 복원점 제공

C-4 (VectorService) ───────────────────→ LLMService.generate_workflow()와 연동
                                          (RAG 기반 워크플로우 생성 고도화)
```

---

## 팀 공통 확인 사항

### ✅ 해결 완료 (v2 컨트랙트에서 확정)

| 확인 항목 | 상태 |
|----------|------|
| `service_tokens`의 정확한 키 구조 | ✅ 서비스 타입 키 (`google_drive`, `gmail`, `slack` 등) |
| 노드 `type` 값의 실제 문자열 명세 | ✅ `runtime_type` 필드로 해결 (input, llm, if_else, loop, output) |
| edge에 label 필드 포함 여부 | ✅ 포함됨 |

### 아직 확인 필요

| 확인 항목 | 중요도 | 영향 파일 |
|----------|--------|---------|
| 롤백 후 재실행 흐름 (자동 vs 수동) | 🟡 High | `execution.py`, `snapshot.py` |

---

## 각 작업자 문서 링크

| 문서 | 내용 |
|------|------|
| [TASK_A_NODE_INTEGRATION.md](TASK_A_NODE_INTEGRATION.md) | 작업자 A 상세 — 노드 통합 & 서비스 연동 |
| [TASK_B_ENGINE_SCHEDULER.md](TASK_B_ENGINE_SCHEDULER.md) | 작업자 B 상세 — 실행 엔진 & 스케줄러 |
| [TASK_C_SNAPSHOT_ADVANCED.md](TASK_C_SNAPSHOT_ADVANCED.md) | 작업자 C 상세 — 스냅샷/롤백 & 고급 기능 |

---

## 남은 버그 목록

| # | 파일 | 버그 내용 | 심각도 | 담당 |
|---|------|---------|--------|------|
| 1 | `app/services/integrations/rest_api.py` | 공개 API 재시도 로직 우회 | 🟡 High | A |

### 해결된 버그 (v2)

| # | 파일 | 버그 내용 | 해결 방식 |
|---|------|---------|---------|
| ~~1~~ | `app/db/mongodb.py` | 인덱스 필드명 snake_case | camelCase로 수정 (883bec5) |
| ~~2~~ | `app/core/engine/executor.py` | _build_branch_map 모든 노드 대상 | if_else 노드만 + label 기반 |
| ~~4~~ | `app/core/engine/executor.py` | Stop 후 SUCCESS 덮어쓰기 | 조건부 upsert |
| ~~5~~ | `app/core/nodes/factory.py` | ValueError 500 에러 노출 | FlowifyException |
| ~~6~~ | `app/models/workflow.py` | EdgeDefinition label 없음 | label 필드 추가 |

---

## 테스트 현황

```
현재 테스트: 120개 통과 (18개 파일)
──────────────────────────────────
있음: test_errors, test_execution_api, test_executor, test_health,
      test_integrations/{base,gmail,notion,slack,web_crawler},
      test_llm_api, test_llm_node, test_llm_service,
      test_middleware, test_models, test_snapshot, test_state

없음 (신규 작성 필요):
  A 담당: test_input_node, test_output_node
  B 담당: test_loop_node, test_scheduler
  C 담당: test_vector_service
```
