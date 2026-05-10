# FastAPI Workflow Trigger Settings Design

> **작성일:** 2026-05-10
> **대상 저장소:** `flowify-BE`
> **범위:** FastAPI runtime 관점의 trigger settings 설계
> **관련 저장소:** `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 새로 도입할 workflow trigger settings 기능에서 FastAPI가 담당할 역할을 다시 정의한다.

이번 문서의 핵심은 다음과 같다.

- 스케줄 소유권은 Spring에 두고, FastAPI는 실행 엔진 역할에 집중한다.
- 기존 `/api/v1/triggers` API와 새 editor 기반 workflow trigger 기능의 경계를 분명히 한다.
- Spring이 전달하는 `workflow.trigger`를 runtime metadata로 안정적으로 수용한다.

---

## 2. 현재 상태 요약

### 2.1 이미 존재하는 것

- `WorkflowDefinition` 모델은 `trigger` 필드를 이미 받을 수 있다.
- `/api/v1/workflows/{workflow_id}/execute`는 `workflow + service_tokens` 구조를 받아 비동기 실행한다.
- 별도의 `SchedulerService`와 `/api/v1/triggers` CRUD가 존재한다.
- `tests/test_trigger_api.py`, `tests/test_scheduler.py`도 존재한다.

### 2.2 현재 구조의 한계

현재 FastAPI의 trigger API는 editor 저장 기반 워크플로우 트리거와는 결이 다르다.

- client가 `workflow_definition` 전체를 직접 넘겨야 한다.
- client가 `service_tokens`까지 직접 넘기는 구조다.
- 스케줄 등록 주체가 Spring이 아니라 FastAPI처럼 보인다.
- 현재 3-repo 구조에서 authoritative workflow 저장소는 Spring이므로 책임 경계가 맞지 않는다.

---

## 3. 이번 기능의 아키텍처 결정

### 3.1 Trigger 소유권

새 trigger settings 기능의 source of truth는 Spring `Workflow.trigger`다.

- FE는 Spring workflow update API만 사용한다.
- Spring이 trigger 저장, 검증, schedule 등록과 해제를 담당한다.
- FastAPI는 실제 실행이 시작될 때만 workflow 정의를 전달받는다.

### 3.2 FastAPI의 책임

FastAPI는 trigger를 아래 용도로만 사용한다.

- 현재 실행이 수동인지 스케줄인지 runtime metadata로 보존
- 필요 시 노드 실행 전략이 trigger 정보를 참고할 수 있는 기반 제공
- 로그와 디버깅과 추적 정보에 활용

즉 FastAPI는 기다리거나 예약하지 않는다.

### 3.3 source mode의 `trigger_kind`와의 관계

FastAPI는 `source_mode.trigger_kind`와 `workflow.trigger`를 별도 계층으로 해석한다.

- `trigger_kind`는 source mode 성격이다.
- `workflow.trigger`는 이번 실행이 어떤 정책으로 시작됐는지 나타낸다.

즉 schedule workflow라도 source mode는 기존 mode key 기준으로 그대로 해석하며, FastAPI가 `trigger_kind`를 보고 별도 스케줄러처럼 행동하지는 않는다.

### 3.4 legacy null trigger 해석

- `workflow.trigger == null`이어도 실행은 깨지지 않아야 한다.
- FastAPI 내부에서는 null을 manual처럼 취급한다.
- Spring이 이후 canonical manual payload를 보내더라도 추가 분기 없이 수용 가능해야 한다.

---

## 4. V1 범위

V1에서 FastAPI가 고려하는 trigger 타입은 아래 두 가지다.

- `manual`
- `schedule`

`webhook`은 후속 범위다.

FastAPI에서 필요한 보장은 다음뿐이다.

- `workflow.trigger == null`이어도 실행이 깨지지 않아야 한다.
- `workflow.trigger.type == schedule`이어도 실행 엔진이 별도 대기 로직을 요구하지 않아야 한다.
- manual과 schedule 모두 동일한 execute 엔드포인트로 들어와야 한다.

---

## 5. Runtime Contract 설계

### 5.1 Spring -> FastAPI 전달 기준

FastAPI는 아래 구조를 그대로 받는다.

```json
{
  "workflow": {
    "id": "wf_123",
    "name": "메일 요약 전달",
    "userId": "user_1",
    "trigger": {
      "type": "schedule",
      "config": {
        "schedule_mode": "interval",
        "cron": "0 */4 * * *",
        "timezone": "Asia/Seoul",
        "interval_hours": 4,
        "skip_if_running": true
      }
    },
    "nodes": [],
    "edges": []
  },
  "service_tokens": {
    "gmail": "ya29..."
  }
}
```

### 5.2 FastAPI 해석 원칙

- `trigger.type`은 실행 진입 정책이 아니라 metadata다.
- schedule workflow도 execute 시점에는 일반 workflow와 동일하게 실행한다.
- `config.cron`, `config.timezone`은 FastAPI가 스케줄링하지 않는다.
- trigger 정보는 로그, 디버깅, 향후 node-level 활용을 위해 유지한다.

### 5.3 Optional metadata

추후 Spring이 아래 값을 추가하더라도 FastAPI는 그대로 수용 가능해야 한다.

- `triggered_by`: `manual` | `schedule`
- `triggered_at`: ISO datetime

이 값들은 V1 필수는 아니지만 설계상 허용한다.

---

## 6. 기존 `/api/v1/triggers` API의 위치 재정의

### 6.1 이번 기능에서의 판단

새 editor trigger settings 기능은 `/api/v1/triggers`를 사용하지 않는다.

이유:

- workflow 저장 권한과 OAuth 토큰 해석은 Spring이 이미 가지고 있다.
- FastAPI trigger API는 current architecture 기준으로 user-facing public contract가 아니다.
- 같은 스케줄을 Spring과 FastAPI 양쪽이 동시에 소유하면 중복 실행과 책임 혼선이 생긴다.

### 6.2 처리 방침

V1에서는 아래 기준으로 정리한다.

- 유지하되 legacy/internal API로 간주
- editor 경로에서는 호출하지 않음
- 문서와 테스트에서 새 기능의 기준 경로가 아님을 명시

즉 새 기능 구현 때문에 FastAPI scheduler를 새 source of truth로 승격하지 않는다.

### 6.3 과거 trigger 문서와의 관계

기존 `.docs/TASK_B_ENGINE_SCHEDULER.md`와 Spring 쪽 `TRIGGER_INTEGRATION_SPEC`는 FastAPI scheduler 자체를 중심으로 한 과거 문맥을 포함한다.

이번 기능 구현에서는 아래를 우선 기준으로 삼는다.

- workflow 저장과 스케줄 등록의 source of truth는 Spring
- FastAPI trigger CRUD는 새 editor 기능의 공식 경로가 아님

---

## 7. FastAPI 구현 범위

### 7.1 유지

- `WorkflowDefinition.trigger`
- `POST /api/v1/workflows/{workflow_id}/execute`
- preview와 generate 흐름
- callback과 node log 저장 흐름

### 7.2 보강

- Spring 스타일 schedule payload를 받아도 깨지지 않는 테스트 추가
- manual 기본값 유지
- 필요 시 trigger metadata를 읽는 공통 helper 추가
- null/manual/schedule payload가 서로 다른 workflow 실행에서 섞이지 않도록 regression test 보강

### 7.3 이번 범위에서 하지 않는 것

- editor에서 직접 FastAPI trigger CRUD 호출
- FastAPI가 cron을 등록하고 주기적으로 대기하는 구조로 전환
- scheduler owner를 Spring에서 FastAPI로 되돌리는 작업

---

## 8. 검증 전략

이번 기능은 FastAPI가 trigger를 소유하지 않는다는 전제를 지키면서도, schedule payload가 들어와도 런타임이 안전하게 실행되는지 확인해야 한다.

### 8.1 단위 및 모델 테스트

- `WorkflowDefinition.trigger`가 null, manual, schedule payload를 모두 수용한다.
- trigger metadata helper가 누락값과 예상치 못한 보조 필드가 있어도 안전하게 동작한다.

### 8.2 API 실행 테스트

- Spring 스타일 `workflow.trigger.schedule` payload로 execute 호출 시 정상 실행된다.
- `trigger == null` 또는 `trigger.type == manual`에서도 동일하게 정상 실행된다.
- schedule payload가 들어와도 FastAPI가 별도 대기 로직 없이 즉시 background execution으로 넘어간다.

### 8.3 legacy 비회귀 테스트

- `/api/v1/triggers` 기존 테스트는 유지하되, 새 editor 공식 경로가 아님을 문서로 분명히 한다.
- legacy scheduler API가 남아 있어도 workflow execute 경로 동작에는 영향을 주지 않아야 한다.

### 8.4 다중 workflow 시나리오 테스트

- 서로 다른 workflow id와 서로 다른 trigger payload를 연속 실행해도 상태가 섞이지 않는다.
- manual workflow와 schedule workflow가 섞여 들어와도 같은 execute path에서 독립적으로 처리된다.
- 하나의 workflow 실행 실패가 다른 workflow의 trigger metadata 처리에 영향을 주지 않는다.
- callback, node log, execution state 저장이 workflow 단위로 분리되어 유지된다.

### 8.5 Spring 연동 회귀 테스트

- Spring이 보내는 최신 runtime payload fixture로 execute API를 검증한다.
- `workflow.trigger`가 포함된 payload와 포함되지 않은 payload를 모두 확인한다.
- source mode의 `trigger_kind` 값이 달라도 FastAPI 실행 분기에는 영향이 없음을 확인한다.

### 8.6 실행 커맨드 기준

- `python -m pytest`
- 필요 시 `tests/test_execution_api.py`, `tests/test_trigger_api.py`, `tests/test_scheduler.py`를 부분 실행한다.

---

## 9. 구현 후보 파일

### 9.1 확인/수정 대상

- `app/models/workflow.py`
- `app/api/v1/endpoints/workflow.py`
- `tests/test_trigger_api.py`
- `tests/test_scheduler.py`
- `tests/test_execution_api.py`

### 9.2 선택적 정리 대상

- `app/api/v1/endpoints/trigger.py`
- `app/services/scheduler_service.py`

선택적 정리는 삭제가 아니라 legacy 경로임을 명확히 하는 수준을 우선한다.

---

## 10. 한 줄 요약

이번 FastAPI 작업의 핵심은 스케줄을 소유하지 않고도 workflow trigger metadata를 안정적으로 수용하는 실행 엔진 역할로 경계를 다시 고정하는 것이다.
