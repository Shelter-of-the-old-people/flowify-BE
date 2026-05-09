# FastAPI 파일 종류 다중 분기 실행 설계

> 작성일: 2026-05-08
> 대상: `flowify-BE` FastAPI runtime
> 목적: Spring이 생성한 `branch_by_file_type` 분기 계약을 FastAPI 실행 엔진에서 실제 edge별 데이터 흐름으로 처리한다.

---

## 1. 배경

프론트/스프링에서는 파일 목록을 파일 종류별로 분기하는 UX를 준비한다.

예상 흐름은 다음과 같다.

```text
Google Drive 또는 Canvas LMS
  -> FILE_LIST
  -> 파일 종류 분기
     -> pdf 경로
     -> image 경로
     -> other 경로
```

사용자가 `pdf`, `image`, `other` 세 가지 branch를 만들면 FastAPI는 각 경로에 해당 파일만 전달해야 한다.

현재 FastAPI는 `if_else`를 `true/false` 이진 분기로만 처리한다. 따라서 파일 종류별 다중 분기를 실행하려면 다음 두 가지가 필요하다.

- 분기 노드가 `FILE_LIST.items`를 branch별 `FILE_LIST`로 나눈다.
- executor가 branch별 결과를 outgoing edge별 input으로 전달한다.

---

## 2. 현재 코드 기준 문제

### 2.1 EdgeDefinition이 Spring edge metadata를 보존하지 않음

현재 `app/models/workflow.py`의 `EdgeDefinition`은 다음 필드만 가진다.

```python
id: str | None = None
source: str
target: str
label: str | None = None
```

Spring은 분기 edge에 `label`, `sourceHandle`, `targetHandle`을 전달할 수 있다. 하지만 FastAPI 모델에는 `sourceHandle`, `targetHandle`이 없어 해당 정보가 버려진다.

### 2.2 IfElseNodeStrategy는 true/false 조건만 처리

현재 `app/core/nodes/logic_node.py`의 `IfElseNodeStrategy`는 다음 방식으로만 동작한다.

- `runtime_config.condition_field` 조회
- 입력 payload에서 해당 필드 값 조회
- `expected_value`와 비교
- `branch: "true"` 또는 `"false"` 반환

`runtime_config.branch_type == "file_type"`과 `branch_rules`는 처리하지 않는다.

### 2.3 WorkflowExecutor는 node별 output만 저장

현재 `WorkflowExecutor.execute()`는 다음 방식으로 다음 노드 input을 결정한다.

```python
prev_node_ids = self._get_predecessors(node_id, edges)
if prev_node_ids:
    input_data = node_outputs.get(prev_node_ids[0])
```

즉, 같은 분기 노드에서 여러 edge가 나가도 모든 다음 노드는 동일한 `node_outputs[branch_node_id]`를 받는다. 파일 종류별로 다른 payload를 전달할 수 없다.

### 2.4 skip 로직도 true/false 전용

현재 branch skip은 `output_data["branch"]`가 `"true"` 또는 `"false"`일 때 반대쪽 경로를 skip하는 방식이다. `pdf`, `image`, `other` 같은 다중 branch key는 처리할 수 없다.

---

## 3. Spring -> FastAPI 계약

Spring은 `branch_by_file_type` 선택 시 condition node를 다음 runtime 계약으로 보낸다.

```json
{
  "runtime_type": "if_else",
  "runtime_config": {
    "node_type": "CONDITION_BRANCH",
    "output_data_type": "FILE_LIST",
    "choiceActionId": "branch_by_file_type",
    "branch_type": "file_type",
    "branch_rules": [
      {
        "key": "pdf",
        "label": "PDF",
        "matcher": {
          "type": "file_type",
          "extensions": ["pdf"],
          "mime_types": ["application/pdf"],
          "mime_prefixes": []
        }
      }
    ],
    "fallback_branch": {
      "key": "other",
      "label": "기타"
    }
  }
}
```

분기 edge는 다음 형태를 받을 수 있다.

```json
{
  "source": "node_branch",
  "target": "node_pdf",
  "label": "pdf",
  "sourceHandle": "pdf",
  "targetHandle": "input"
}
```

FastAPI의 branch key 해석 우선순위는 다음으로 고정한다.

```text
edge.label -> edge.source_handle
```

`target_handle`은 현재 실행 routing에는 사용하지 않고 계약 보존만 한다.

---

## 4. 목표

- `branch_type == "file_type"`인 `if_else` 노드를 파일 종류 다중 분기로 실행한다.
- branch별 payload는 기존 canonical type인 `FILE_LIST`를 유지한다.
- downstream node는 자기 edge key에 맞는 `FILE_LIST`만 받는다.
- 파일이 없는 branch target은 실행하지 않고 `skipped` 처리한다.
- 기존 `true/false` if_else, loop one_by_one, source/sink/LLM 실행 흐름을 깨지 않는다.

---

## 5. 비목표

- 일반 조건식 분기 엔진 구현
- 발신자별, 내용별, 임의 필드별 다중 분기 구현
- branch merge 입력 병합 구현
- 새 canonical type 추가
- 프론트 UI 변경
- Spring 계약 추가 변경

---

## 6. 설계 원칙

### 6.1 기존 이진 분기와 다중 분기를 분리한다

기존 이진 분기는 다음 조건에서만 실행한다.

```python
output_data.get("branch") in ("true", "false")
```

새 다중 분기는 다음 조건에서만 실행한다.

```python
isinstance(output_data.get("branch_outputs"), dict)
```

두 로직을 같은 `branch` 문자열만 보고 처리하지 않는다.

### 6.2 다중 분기는 edge별 payload를 우선한다

다음 노드 input 우선순위는 다음과 같다.

```text
edge_outputs[(prev, current)] -> node_outputs[prev]
```

edge별 payload가 있으면 그것을 사용하고, 없으면 기존 node output fallback을 사용한다.

### 6.3 canonical payload를 유지한다

branch별 output은 모두 기존 `FILE_LIST` 형태를 사용한다.

```json
{
  "type": "FILE_LIST",
  "items": []
}
```

새 type인 `PDF_LIST`, `IMAGE_LIST` 같은 값은 만들지 않는다.

### 6.4 빈 branch는 실행하지 않는다

분기 edge가 있어도 해당 branch payload의 `items`가 비어 있으면 target node는 skip한다.

### 6.5 merge node는 실수로 skip하지 않는다

inactive branch target의 descendants를 무조건 skip하면 다음 구조가 깨질 수 있다.

```text
branch
  -> pdf node
  -> image node
pdf node, image node -> common sink
```

따라서 inactive descendants 중 active target에서도 도달 가능한 노드는 skip 대상에서 제외한다.

---

## 7. 모델 설계

파일: `app/models/workflow.py`

`EdgeDefinition`을 Spring 계약에 맞게 확장한다.

```python
class EdgeDefinition(BaseModel):
    """워크플로우 edge 정의 모델."""

    model_config = {"populate_by_name": True}

    id: str | None = None
    source: str
    target: str
    label: str | None = None
    source_handle: str | None = Field(default=None, alias="sourceHandle")
    target_handle: str | None = Field(default=None, alias="targetHandle")
```

주의:

- 기존 `label` 기반 true/false 분기와 호환된다.
- `sourceHandle`, `targetHandle`은 Spring JSON 수신을 위해 명시 alias를 둔다.
- `target_handle`은 지금 실행 로직에는 쓰지 않는다.

---

## 8. IfElseNodeStrategy 설계

파일: `app/core/nodes/logic_node.py`

### 8.1 execute 분기

```python
async def execute(...):
    runtime_config = node.get("runtime_config") or {}
    if self._is_file_type_branch(runtime_config):
        return self._execute_file_type_branch(runtime_config, input_data)

    return self._execute_boolean_branch(runtime_config, input_data)
```

### 8.2 file_type branch 조건

```python
def _is_file_type_branch(runtime_config: dict[str, Any]) -> bool:
    return runtime_config.get("branch_type") == "file_type"
```

`choiceActionId`는 보조 정보로만 보고, 실행 분기는 `branch_type`을 기준으로 한다.

### 8.3 입력 검증

`file_type` 분기는 `FILE_LIST` 입력만 허용한다.

```python
if not input_data or input_data.get("type") != "FILE_LIST":
    raise FlowifyException(
        ErrorCode.INVALID_REQUEST,
        detail="File type branch requires FILE_LIST input.",
    )
```

### 8.4 matcher 규칙

item에서 다음 필드를 본다.

```text
filename
mime_type
mimeType
```

우선순위:

1. MIME 정확 매칭: `mime_type in matcher.mime_types`
2. MIME prefix 매칭: `mime_type.startswith(prefix)`
3. 확장자 매칭: `filename` 마지막 확장자

첫 번째로 매칭된 rule에 item을 넣는다. 어떤 rule에도 매칭되지 않으면 `fallback_branch.key`, 기본값 `other`에 넣는다.

### 8.5 출력 형태

```json
{
  "type": "FILE_LIST",
  "items": "원본 items",
  "branch": "multi",
  "branch_outputs": {
    "pdf": {
      "type": "FILE_LIST",
      "items": []
    },
    "image": {
      "type": "FILE_LIST",
      "items": []
    },
    "other": {
      "type": "FILE_LIST",
      "items": []
    }
  },
  "branch_counts": {
    "pdf": 0,
    "image": 0,
    "other": 0
  }
}
```

`branch: "multi"`는 기존 true/false skip과 구분하기 위한 보조 값이다.

### 8.6 validate

```python
def validate(self, node: dict[str, Any]) -> bool:
    runtime_config = node.get("runtime_config") or {}
    if self._is_file_type_branch(runtime_config):
        fallback_branch = runtime_config.get("fallback_branch") or {}
        return bool(runtime_config.get("branch_rules")) or bool(fallback_branch.get("key"))
    return bool(runtime_config.get("condition_field") or self.config.get("condition_field"))
```

주의:

- Spring은 사용자가 `other`만 선택한 경우 `branch_rules`를 빈 배열로 보내고 `fallback_branch.key`만 유지한다.
- 따라서 `branch_rules`가 비어 있어도 `fallback_branch.key`가 있으면 유효한 파일 종류 분기로 본다.

---

## 9. WorkflowExecutor 설계

파일: `app/core/engine/executor.py`

### 9.1 edge output 저장소 추가

```python
edge_outputs: dict[tuple[str, str], dict[str, Any]] = {}
```

key는 `(source_node_id, target_node_id)`로 둔다.

### 9.2 input 결정 helper

```python
@staticmethod
def _resolve_input_data(
    node_id: str,
    edges: list[EdgeDefinition],
    node_outputs: dict[str, dict[str, Any]],
    edge_outputs: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    incoming_edges = [edge for edge in edges if edge.target == node_id]
    for edge in incoming_edges:
        edge_payload = edge_outputs.get((edge.source, edge.target))
        if edge_payload is not None:
            return edge_payload

    for edge in incoming_edges:
        node_payload = node_outputs.get(edge.source)
        if node_payload is not None:
            return node_payload

    return None
```

fallback은 "첫 번째 incoming edge"가 아니라 "실제로 output이 존재하는 첫 번째 predecessor"를 사용한다.

이유:

- merge node가 여러 incoming edge를 가질 때, 첫 번째 edge가 skipped branch에서 온 edge일 수 있다.
- 이 경우 단순히 `incoming_edges[0]`만 보면 active branch output이 있어도 `None`을 받을 수 있다.
- 단, 이번 범위에서는 여러 predecessor output을 병합하지 않는다. 여러 active predecessor가 있으면 첫 번째 available output만 사용한다.

### 9.3 branch key helper

```python
@staticmethod
def _get_branch_key(edge: EdgeDefinition) -> str | None:
    return edge.label or edge.source_handle
```

### 9.4 multi branch edge output 생성

```python
@classmethod
def _build_multi_branch_edge_outputs(
    cls,
    node_id: str,
    output_data: dict[str, Any],
    edges: list[EdgeDefinition],
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str], set[str]]:
    ...
```

반환:

- edge별 payload
- active target ids
- inactive target ids

규칙:

- `branch_outputs`가 dict가 아니면 빈 결과
- branch node outgoing edge만 본다.
- edge key가 없으면 `INVALID_REQUEST`
- edge key에 해당 payload가 없으면 inactive
- payload가 있어도 `items`가 비어 있으면 inactive
- payload `items`가 있으면 active

### 9.5 inactive branch skip

```python
@staticmethod
def _resolve_multi_branch_skipped_nodes(
    active_targets: set[str],
    inactive_targets: set[str],
    adjacency: dict[str, list[str]],
) -> set[str]:
    active_reachable = set(active_targets)
    for target in active_targets:
        active_reachable.update(WorkflowExecutor._get_descendants(target, adjacency))

    skipped = set()
    for target in inactive_targets:
        candidates = {target}
        candidates.update(WorkflowExecutor._get_descendants(target, adjacency))
        skipped.update(candidates - active_reachable)

    return skipped
```

이렇게 하면 active 경로에서도 도달 가능한 merge node는 skip하지 않는다.

### 9.6 execute 흐름 보강

기존:

```python
prev_node_ids = self._get_predecessors(node_id, edges)
input_data = node_outputs.get(prev_node_ids[0])
```

변경:

```python
input_data = self._resolve_input_data(node_id, edges, node_outputs, edge_outputs)
```

분기 노드 실행 후:

```python
output_data = node_outputs[node_id]
if runtime_type == "if_else":
    if isinstance(output_data.get("branch_outputs"), dict):
        new_edge_outputs, active_targets, inactive_targets = self._build_multi_branch_edge_outputs(
            node_id,
            output_data,
            edges,
        )
        edge_outputs.update(new_edge_outputs)
        skipped_nodes.update(
            self._resolve_multi_branch_skipped_nodes(
                active_targets,
                inactive_targets,
                adjacency,
            )
        )
    elif output_data.get("branch") in ("true", "false"):
        기존 true/false skip 처리
```

---

## 10. 영향 범위와 방어 설계

### 10.1 기존 true/false 분기 회귀 방지

위험:

- `branch: "multi"`를 기존 true/false 로직이 처리하면 잘못 skip될 수 있다.

방어:

- 기존 로직은 `branch in ("true", "false")`일 때만 실행한다.
- 다중 분기는 `branch_outputs`가 dict일 때만 실행한다.

### 10.2 loop 조합 회귀 방지

위험:

- `branch -> loop -> AI`에서 loop가 전체 `FILE_LIST`를 받을 수 있다.

방어:

- `_resolve_input_data()`가 edge payload를 node output보다 우선한다.
- branch edge payload가 있으면 loop는 branch별 `FILE_LIST`만 받는다.

### 10.3 merge node skip 방지

위험:

- inactive branch의 descendants를 모두 skip하면 active 경로와 합쳐지는 공통 node까지 skip될 수 있다.
- skip 대상에서 제외된 merge node가 input을 고를 때 skipped branch predecessor만 보면 `None`을 받을 수 있다.

방어:

- active reachable node는 inactive skip 후보에서 제외한다.
- merge node input fallback은 실제 `node_outputs`가 있는 predecessor를 순회해서 선택한다.
- 여러 active predecessor의 payload 병합은 이번 범위에서 구현하지 않는다.

### 10.4 branch key 누락 방지

위험:

- branch node outgoing edge에 `label`과 `sourceHandle`이 모두 없으면 routing이 불가능하다.

방어:

- `branch_outputs`가 있는 분기 노드에서 branch key 없는 outgoing edge를 만나면 `INVALID_REQUEST`로 실패한다.
- 이 실패는 Spring/FastAPI 계약 불일치를 빨리 드러내기 위한 의도적인 fail-fast다.

### 10.5 빈 branch 처리

위험:

- 빈 `FILE_LIST`가 AI/Loop로 전달되어 불필요한 실행이 발생할 수 있다.

방어:

- payload가 없거나 `items`가 비어 있으면 target을 inactive로 보고 skip한다.

---

## 11. 테스트 계획

### 11.1 모델 테스트

대상: `tests/test_models.py`

- `EdgeDefinition`이 `sourceHandle`, `targetHandle`을 수신한다.
- Python field name `source_handle`, `target_handle`로도 생성 가능하다.

### 11.2 IfElseNodeStrategy 테스트

대상: 신규 `tests/test_logic_node.py` 또는 기존 logic node 테스트 파일

필수 케이스:

- PDF 확장자 또는 MIME이 `pdf` branch로 분류된다.
- `image/` MIME prefix가 `image` branch로 분류된다.
- 매칭되지 않는 파일이 `other` branch로 분류된다.
- `branch_rules`가 비어 있고 `fallback_branch.key == "other"`인 경우 모든 파일이 `other` branch로 분류된다.
- `FILE_LIST`가 아닌 입력은 `INVALID_REQUEST`.
- 기존 `condition_field` true/false 분기는 그대로 동작한다.

### 11.3 Executor 테스트

대상: `tests/test_executor.py`

필수 케이스:

- `branch_outputs.pdf`가 pdf edge target에만 전달된다.
- `branch_outputs.image`가 image edge target에만 전달된다.
- 빈 branch target은 skipped 된다.
- active path에서 도달 가능한 merge node는 skipped 되지 않는다.
- merge node는 skipped branch가 아닌 실제 output이 있는 predecessor의 payload를 받는다.
- 기존 true/false if_else 테스트가 통과한다.
- 기존 loop one_by_one 테스트가 통과한다.

### 11.4 전체 회귀

```bash
ruff format .
ruff check .
pytest tests/
```

---

## 12. 구현 순서

### Step 1. EdgeDefinition 계약 보강

- `source_handle`, `target_handle` 필드 추가
- 모델 테스트 추가

커밋 예:

```text
feat(워크플로우): edge handle 계약 추가
```

### Step 2. IfElseNodeStrategy 파일 종류 분류 추가

- `branch_type=file_type` dispatch 추가
- matcher helper 추가
- branch output payload 생성
- logic node 테스트 추가

커밋 예:

```text
feat(분기노드): 파일 종류 분류 실행 추가
```

### Step 3. Executor edge별 payload 전달 추가

- `edge_outputs` 저장소 추가
- `_resolve_input_data()` 추가
- branch output -> edge output 변환 helper 추가
- branch별 input 전달 테스트 추가

커밋 예:

```text
feat(실행엔진): 분기 edge별 입력 전달 추가
```

### Step 4. 다중 분기 skip 보강

- inactive branch skip helper 추가
- merge node 보호 로직 추가
- skip/merge 테스트 추가

커밋 예:

```text
fix(실행엔진): 다중 분기 skip 처리 보정
```

### Step 5. 회귀 테스트와 문서 보강

- 기존 loop/if_else/source/output 테스트 확인
- 문서 최신화

커밋 예:

```text
test(분기실행): 파일 종류 분기 회귀 테스트 추가
```

---

## 13. 완료 기준

- FastAPI가 Spring의 `branch_by_file_type` runtime config를 해석한다.
- `pdf`, `image`, `other` 등 branch별로 다른 `FILE_LIST`가 다음 노드에 전달된다.
- 파일이 없는 branch는 실행되지 않는다.
- 기존 true/false if_else는 그대로 동작한다.
- 기존 loop one_by_one은 그대로 동작한다.
- `ruff format .`, `ruff check .`, `pytest tests/`가 통과한다.
