# Git 충돌 방지 & 작업자 병렬 작업 계획

> 작성일: 2026-04-23 | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17
> 전제: v2 runtime contract 구현 완료, 작업자 3명 병렬 작업 시작

---

## Context

v2 런타임 컨트랙트 통합이 완료되어 코드베이스가 크게 변경됨. 작업자 A/B/C가 남은 작업을 병렬로 진행할 때 git 충돌을 최소화하고, 각 작업자가 v2 패턴에 맞는 코드를 쉽게 작성할 수 있도록 환경을 정비해야 함.

**핵심 발견**: 탐색 결과 TASK 문서에 TODO로 표시된 많은 항목이 이미 구현되어 있음:
- `trigger.py` (111줄, full CRUD), `main.py` 스케줄러 초기화, `router.py` 등록 — 모두 완료
- `snapshot.py` DB 조회 메서드 (`get_snapshot_from_db`, `get_last_success_snapshot`) — 완료
- `execution.py` rollback 개선 (`errorMessage`, `finishedAt` 초기화) — 완료

따라서 실제 남은 작업량은 예상보다 훨씬 적고, 파일 겹침도 거의 없음.

---

## 1. 실제 남은 작업 & 파일 소유권

### Worker A (노드 테스트 + 버그 수정)

| 파일 | 작업 | 충돌 위험 |
|------|------|----------|
| `app/services/integrations/rest_api.py` | 재시도 로직 우회 버그 수정 | 🟢 없음 — A 전용 |
| `tests/test_input_node.py` | **신규 생성** | 🟢 없음 |
| `tests/test_output_node.py` | **신규 생성** | 🟢 없음 |

### Worker B (스케줄러 고도화 + 테스트)

| 파일 | 작업 | 충돌 위험 |
|------|------|----------|
| `app/services/scheduler_service.py` | MongoDB jobstore 추가 (6/17) | 🟢 없음 — B 전용 |
| `tests/test_loop_node.py` | **신규 생성** | 🟢 없음 |
| `tests/test_scheduler.py` | **신규 생성** | 🟢 없음 |

### Worker C (VectorService + 테스트)

| 파일 | 작업 | 충돌 위험 |
|------|------|----------|
| `app/services/vector_service.py` | 전면 구현 (현재 17줄 스켈레톤) | 🟢 없음 — C 전용 |
| `tests/test_vector_service.py` | **신규 생성** | 🟢 없음 |
| `tests/test_snapshot.py` | DB 조회 테스트 추가 | 🟢 없음 — C 전용 |
| `pyproject.toml` | chromadb 의존성 추가 | 🟡 낮음 — 아래 참조 |

### 🔒 Frozen 파일 (절대 수정 금지)

아래 파일들은 v2 구현 완료 상태이므로 어떤 작업자도 수정하지 않음:

```
app/core/nodes/base.py          # v2 시그니처 확정
app/core/nodes/input_node.py    # runtime_source 라우팅 완료
app/core/nodes/output_node.py   # runtime_sink 라우팅 완료
app/core/nodes/llm_node.py      # canonical payload 처리 완료
app/core/nodes/logic_node.py    # v2 IfElse/Loop 완료
app/core/nodes/factory.py       # create_from_node_def 완료
app/core/engine/executor.py     # canonical payload 데이터 흐름 완료
app/core/engine/snapshot.py     # DB 조회 메서드 완료
app/models/workflow.py          # runtime 필드 + EdgeDefinition label 완료
app/models/canonical.py         # 8종 canonical payload 완료
app/models/requests.py          # ExecutionResult 간소화 완료
app/common/errors.py            # v2 에러 코드 완료
app/api/v1/endpoints/workflow.py
app/api/v1/endpoints/execution.py  # rollback 개선 완료
app/api/v1/endpoints/trigger.py    # full CRUD 완료
app/api/v1/router.py               # trigger 등록 완료
app/main.py                        # 스케줄러 초기화 완료
```

---

## 2. 충돌 위험 분석 결과

**결론: 소스 파일 충돌 위험 사실상 제로.**

모든 소스 파일 수정이 작업자별로 완전히 분리되어 있고, 신규 파일은 이름이 겹치지 않음.

유일한 잠재적 충돌 지점:
- **`pyproject.toml`** — C가 `chromadb` 의존성을 추가할 때. 해결: C가 먼저 작은 PR로 의존성만 추가하거나, 머지 순서 조정.
- **`tests/conftest.py`** — 공유 fixture 추가 시. 해결: 각 작업자가 자기 테스트 파일 내에 로컬 fixture 정의.

---

## 3. 추천 전략: 스켈레톤 스텁 + 파일 소유권

### 3-1. TASK 문서 업데이트 (먼저 수행)

TASK_A/B/C 문서에서 이미 완료된 항목 반영:
- B-4 (trigger.py), B-5 (main.py 스케줄러, router 등록) → ✅ 완료 표시
- C-1 (snapshot DB 조회), C-2 (rollback 개선) → ✅ 완료 표시

### 3-2. 테스트 스켈레톤 파일 생성 (6개)

작업자가 v2 시그니처와 패턴을 바로 파악할 수 있도록 빈 테스트 파일을 미리 생성.
각 파일에 올바른 import, 사용할 fixture, v2 시그니처 예시를 포함.

#### `tests/test_input_node.py` (Worker A)

```python
"""InputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_source 기반 라우팅. canonical payload 반환.
conftest.py의 service_tokens fixture 사용 가능.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.core.nodes.input_node import InputNodeStrategy


# ── 테스트 헬퍼 ──

def _source_node(service: str, mode: str, target: str = "") -> dict:
    """runtime_source가 설정된 노드 dict 생성."""
    return {
        "runtime_source": {
            "service": service,
            "mode": mode,
            "target": target,
            "canonical_input_type": "TEXT",
        }
    }


# ── Google Drive ──

# TODO: test_google_drive_single_file
# TODO: test_google_drive_folder_all_files

# ── Gmail ──

# TODO: test_gmail_new_email
# TODO: test_gmail_label_emails

# ── Slack ──

# TODO: test_slack_channel_messages

# ── Google Sheets ──

# TODO: test_sheets_sheet_all

# ── 에러 케이스 ──

# TODO: test_missing_token_raises_oauth_error
# TODO: test_unsupported_source_raises

# ── validate ──

# TODO: test_validate_supported_source_returns_true
# TODO: test_validate_unknown_source_returns_false
# TODO: test_validate_no_runtime_source_returns_false
```

#### `tests/test_output_node.py` (Worker A)

```python
"""OutputNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
runtime_sink 기반 라우팅. canonical payload 소비.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.common.errors import FlowifyException
from app.core.nodes.output_node import OutputNodeStrategy


# ── 테스트 헬퍼 ──

def _sink_node(service: str, **config) -> dict:
    """runtime_sink가 설정된 노드 dict 생성."""
    return {"runtime_sink": {"service": service, "config": config}}


# ── Slack ──

# TODO: test_slack_send_text

# ── Gmail ──

# TODO: test_gmail_send_text
# TODO: test_gmail_send_single_email_type

# ── Notion ──

# TODO: test_notion_create_page_text

# ── 에러 케이스 ──

# TODO: test_unsupported_sink_raises
# TODO: test_incompatible_input_type_raises
# TODO: test_missing_token_raises

# ── validate ──

# TODO: test_validate_supported_sink_returns_true
# TODO: test_validate_missing_required_config_returns_false
```

#### `tests/test_loop_node.py` (Worker B)

```python
"""LoopNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
canonical payload 타입별 items 추출 (FILE_LIST→items, SPREADSHEET_DATA→rows).
"""
import pytest

from app.core.nodes.logic_node import LoopNodeStrategy


# TODO: test_file_list_iteration
# TODO: test_spreadsheet_rows_iteration
# TODO: test_max_iterations_limit
# TODO: test_empty_input_returns_zero_iterations
# TODO: test_transform_field_extracts_values
# TODO: test_validate
```

#### `tests/test_scheduler.py` (Worker B)

```python
"""SchedulerService 테스트."""
import pytest

from app.services.scheduler_service import SchedulerService


# TODO: test_scheduler_start_stop
# TODO: test_add_cron_job_and_get_job
# TODO: test_add_interval_job
# TODO: test_remove_job
# TODO: test_get_jobs_returns_list
```

#### `tests/test_vector_service.py` (Worker C)

```python
"""VectorService 테스트.

ChromaDB + OpenAI Embedding 모킹 패턴.
"""
from unittest.mock import MagicMock, patch

import pytest


# TODO: test_add_documents
# TODO: test_search_returns_results
# TODO: test_search_empty_collection
# TODO: test_delete_document
```

### 3-3. pyproject.toml 의존성 선행 추가

C의 chromadb 의존성을 지금 바로 추가하여 충돌 가능성을 제거:

```toml
# pyproject.toml dependencies 리스트에 추가
"chromadb>=0.4.0",
```

---

## 4. 브랜치 & 머지 전략

### 브랜치 규칙

```
main ← 모든 PR의 base
  ├─ fix/rest-api-retry        (Worker A)
  ├─ test/input-output-nodes   (Worker A)
  ├─ feat/scheduler-jobstore   (Worker B, 6/17 전)
  ├─ test/loop-scheduler       (Worker B)
  ├─ feat/vector-service       (Worker C)
  └─ test/vector-snapshot      (Worker C)
```

각 작업자는 1~2개 브랜치 사용. 단일 브랜치로 합쳐도 무방 (파일 겹침 없으므로).

### 머지 순서 (권장)

1. **스켈레톤 + pyproject.toml 선행 커밋** → main에 즉시 머지
2. **Worker A 머지** — rest_api.py 버그 수정 + 테스트
3. **Worker B 머지** — 테스트 (jobstore는 6/17)
4. **Worker C 머지** — vector_service.py + 테스트
   - 마지막 머지 시 main 최신 상태 rebase

실제로는 순서 무관하게 머지 가능 — 파일 겹침이 없으므로.

---

## 5. 타임라인

```
4/23 (오늘):
  - 스켈레톤 테스트 파일 6개 생성 + pyproject.toml chromadb 추가
  - TASK_A/B/C 문서에 이미 완료된 항목(trigger, snapshot, rollback) 반영
  - main에 커밋 & 푸시 → 작업자들에게 공유

4/24-26 (병렬 작업):
  - A: rest_api.py 버그 수정 + test_input_node.py, test_output_node.py 구현
  - B: test_loop_node.py, test_scheduler.py 구현
  - C: vector_service.py 전면 구현 + test_vector_service.py, test_snapshot.py 보강

4/27: PR 리뷰 & 머지

4/28: 통합 테스트 (120+ 전체 pytest 통과 확인)

4/29: 중간 발표
```

---

## 6. 실행 단계

### Step 1. 스켈레톤 파일 생성
- `tests/test_input_node.py` — Worker A 전용
- `tests/test_output_node.py` — Worker A 전용
- `tests/test_loop_node.py` — Worker B 전용
- `tests/test_scheduler.py` — Worker B 전용
- `tests/test_vector_service.py` — Worker C 전용

### Step 2. pyproject.toml 의존성 추가
- `"chromadb>=0.4.0"` 추가

### Step 3. TASK 문서 업데이트
- TASK_B: B-4 (trigger.py), B-5 (main.py, router.py) → ✅ 완료 표시
- TASK_C: C-1 (snapshot DB 조회), C-2 (rollback 개선) → ✅ 완료 표시
- TASK_SUMMARY: 해당 항목 완료 반영, 구현율 업데이트

### Step 4. 커밋 & 공유
- 단일 커밋으로 스켈레톤 + 문서 업데이트 + 의존성 추가
- 작업자들에게 pull 요청

---

## 7. 검증

- `python -m pytest tests/ -x --tb=short -q` — 스켈레톤 파일에 테스트가 없으므로 기존 120개 통과 확인
- 각 작업자가 구현 완료 후 개별 테스트 실행
- 최종 통합 시 전체 테스트 실행
