# FastAPI Loop one_by_one 실행 설계

> 작성일: 2026-05-05  
> 대상: FastAPI runtime, Spring WorkflowTranslator  
> 목적: `one_by_one` 처리 방식이 실제 실행 시 항목별 반복 처리로 동작하도록 FastAPI 실행 엔진 설계를 정리한다.

---

## 1. 배경

현재 워크플로우 생성 화면에서 사용자가 목록형 데이터를 받은 뒤 `하나씩 처리(one_by_one)`를 선택하면 Spring은 중간 노드를 `LOOP`로 생성한다.

예상되는 사용자 기대 흐름은 다음과 같다.

```text
Canvas LMS(FILE_LIST)
 -> Loop(one_by_one, item type SINGLE_FILE)
 -> AI(TEXT)
 -> Google Drive
```

실행 시에는 다음처럼 동작해야 한다.

```text
Canvas LMS 1회 실행
Loop 1회 실행: FILE_LIST에서 items 추출
AI N회 실행: 각 item을 SINGLE_FILE로 받아 처리
AI 결과 N개 집계
Google Drive 1회 실행: 집계 결과 저장
```

하지만 현재 FastAPI는 `Loop` 이후 노드를 항목 수만큼 반복 실행하지 않고, 그래프의 모든 노드를 위상정렬 순서대로 1회씩만 실행한다.

---

## 2. 현재 코드 기준 문제

### 2.1 Spring 계약

Spring의 `mapping_rules.json`은 `one_by_one`을 다음처럼 정의한다.

```json
{
  "id": "one_by_one",
  "node_type": "LOOP",
  "output_data_type": "SINGLE_FILE"
}
```

`WorkflowTranslator`는 `LOOP` 타입을 FastAPI runtime type `loop`로 변환한다.

```java
if (LOOP_TYPES.contains(upperType)) {
    return "loop";
}
```

즉 Spring 계약상 `one_by_one`은 “목록형 입력을 단일 항목 단위로 처리하는 loop”다.

### 2.2 FastAPI 실행기

FastAPI `WorkflowExecutor`는 현재 다음 방식으로 동작한다.

- edges 기반 위상정렬을 수행한다.
- `execution_order`를 순회하며 각 노드를 1회 실행한다.
- 현재 노드의 입력은 첫 번째 predecessor의 `node_outputs`를 사용한다.
- `if_else`만 branch skip 특수 처리를 한다.
- `loop`에 대한 downstream 반복 실행 처리는 없다.

### 2.3 LoopNodeStrategy

`LoopNodeStrategy`는 현재 목록형 canonical payload에서 items를 추출하고 다시 목록 형태로 반환한다.

```python
return {
    "type": input_data.get("type", "TEXT") if input_data else "TEXT",
    "items": results,
    "loop_results": results,
    "iterations": len(results),
}
```

이 구조에서는 다음 노드가 `SINGLE_FILE` 또는 `SINGLE_EMAIL`을 N번 받지 않는다. 다음 노드는 `FILE_LIST` 또는 `EMAIL_LIST` 전체를 1번만 받는다.

---

## 3. 설계 원칙

FastAPI 프로젝트 컨벤션을 기준으로 다음 원칙을 지킨다.

1. `runtime_type`은 전략 선택의 primary key로 유지한다.
2. 노드 간 데이터는 기존 canonical payload 형식을 유지한다.
3. `NodeStrategy`는 자기 노드의 실행 책임만 가진다.
4. 그래프 실행 순서, skip, 반복 orchestration은 `WorkflowExecutor` 책임이다.
5. 에러는 `FlowifyException`과 기존 `ErrorCode`를 사용한다.
6. MongoDB `nodeLogs`는 Spring 조회 계약을 고려해 그래프 노드당 1개를 유지한다.
7. 새 canonical type은 v1에서 추가하지 않는다.

---

## 4. 목표와 비목표

### 4.1 목표

- `one_by_one`으로 생성된 `loop`가 실제로 다음 처리 노드를 항목별로 반복 실행한다.
- `FILE_LIST -> LOOP -> AI` 흐름에서 AI가 각 파일을 `SINGLE_FILE`로 N회 처리한다.
- `EMAIL_LIST -> LOOP -> AI` 흐름에서 AI가 각 메일을 `SINGLE_EMAIL`로 N회 처리한다.
- 반복 결과는 기존 canonical payload로 집계해 이후 노드가 1회 실행되도록 한다.
- Spring의 기존 `nodeLogs` 조회와 프론트의 노드 입출력 데이터 조회가 깨지지 않도록 한다.

### 4.2 비목표

- v1에서는 loop block, loop end, nested loop를 구현하지 않는다.
- v1에서는 loop body를 여러 노드로 확장하지 않는다.
- v1에서는 `TEXT_LIST`, `SUMMARY_LIST` 같은 새 canonical type을 만들지 않는다.
- v1에서는 부분 성공 정책을 복잡하게 만들지 않는다. body 실행 중 실패하면 workflow 실패로 처리한다.

---

## 5. Loop v1 실행 범위

v1에서 loop body는 **Loop 노드의 첫 번째 outgoing target 노드 1개**로 정의한다.

예:

```text
source -> loop -> ai -> sink
```

이 경우 반복 대상 body는 `ai` 하나다.

제약:

- loop outgoing edge가 0개면 `INVALID_REQUEST`.
- loop outgoing edge가 2개 이상이면 v1에서는 `INVALID_REQUEST`.
- body node가 없거나 node map에 존재하지 않으면 `INVALID_REQUEST`.
- body node가 다시 loop이거나 if_else인 경우 v1에서는 지원하지 않는 방향을 권장한다.

이 제약은 현재 그래프에 loop scope 또는 loop end 개념이 없기 때문이다.

---

## 6. FastAPI 구현 설계

### 6.1 책임 분리

#### LoopNodeStrategy

`LoopNodeStrategy`는 기존 역할을 유지한다.

- 입력 canonical payload에서 반복 대상 items를 추출한다.
- `max_iterations`, timeout, `transform_field`를 적용한다.
- downstream 노드를 직접 실행하지 않는다.
- 반환 payload에는 `items`, `loop_results`, `iterations`를 포함한다.

#### WorkflowExecutor

`WorkflowExecutor`에 loop-aware 실행 흐름을 추가한다.

역할:

- `runtime_type == "loop"` 감지
- loop node 1회 실행
- loop body node 탐색
- loop items를 item canonical payload로 변환
- body node를 item 수만큼 내부 반복 실행
- body 결과 집계
- body node log 1개 생성
- body node가 일반 순회에서 다시 실행되지 않도록 skip 처리

### 6.2 실행 흐름

의사 코드는 다음과 같다.

```python
handled_nodes: set[str] = set()

for node_id in execution_order:
    if node_id in handled_nodes:
        continue

    node_def = node_map[node_id]
    runtime_type = node_def.runtime_type or node_def.type

    if runtime_type == "loop":
        loop_log = await self._execute_node(...)
        execution.nodeLogs.append(loop_log)

        if loop_log.status == "failed":
            fail_workflow()

        loop_output = loop_log.outputData or {}
        body_node_id = self._resolve_loop_body_node_id(node_id, edges)
        body_node_def = node_map[body_node_id]

        aggregate_log = await self._execute_loop_body(
            loop_node_def=node_def,
            body_node_def=body_node_def,
            loop_output=loop_output,
            service_tokens=service_tokens,
            snapshot_manager=snapshot_manager,
        )

        execution.nodeLogs.append(aggregate_log)

        if aggregate_log.status == "failed":
            fail_workflow()

        node_outputs[node_id] = loop_output
        node_outputs[body_node_id] = aggregate_log.outputData or {}
        handled_nodes.add(body_node_id)
        continue

    # 기존 일반 노드 실행
```

### 6.3 body node log 정책

Spring의 `ExecutionService.buildNodeDataResponse()`는 `nodeLogs`에서 `nodeId`가 일치하는 첫 로그를 반환한다.

따라서 body node를 N회 실행하더라도 `nodeLogs`에 같은 `nodeId`를 N개 추가하지 않는다.

v1 정책:

- loop node log 1개
- body node aggregate log 1개
- body node log의 `inputData`는 loop input 요약 또는 loop items summary
- body node log의 `outputData`는 aggregate payload
- 반복별 상세 결과는 `outputData.loop_results` 또는 `outputData.items`에 포함

예:

```json
{
  "nodeId": "node_ai",
  "status": "success",
  "inputData": {
    "type": "FILE_LIST",
    "items": [
      { "filename": "a.pdf" },
      { "filename": "b.pdf" }
    ],
    "iterations": 2
  },
  "outputData": {
    "type": "TEXT",
    "content": "1. a.pdf 요약...\n\n2. b.pdf 요약...",
    "loop_results": [
      { "type": "TEXT", "content": "a.pdf 요약..." },
      { "type": "TEXT", "content": "b.pdf 요약..." }
    ],
    "iterations": 2
  }
}
```

### 6.4 item payload 변환 규칙

Loop node의 `runtime_config.output_data_type`을 item type으로 사용한다.

| loop input type | item output type | 변환 |
| --- | --- | --- |
| `FILE_LIST` | `SINGLE_FILE` | item dict에 `type: SINGLE_FILE` 부여 |
| `EMAIL_LIST` | `SINGLE_EMAIL` | item dict에 `type: SINGLE_EMAIL` 부여 |
| `SPREADSHEET_DATA` | `SPREADSHEET_DATA` | row 1개를 `rows: [row]`로 감싸고 headers 유지 |
| `SCHEDULE_DATA` | `SCHEDULE_DATA` | item 1개를 `items: [item]`로 감쌈 |

지원하지 않는 조합은 `FlowifyException(ErrorCode.INVALID_REQUEST)`로 실패 처리한다.

예:

```python
def _to_loop_item_payload(
    self,
    source_type: str,
    item_type: str,
    item: dict[str, Any] | list[Any],
    loop_input: dict[str, Any],
) -> dict[str, Any]:
    ...
```

### 6.5 결과 집계 규칙

body 결과는 기존 canonical type으로 집계한다.

| body output type | aggregate output type | 집계 |
| --- | --- | --- |
| `TEXT` | `TEXT` | `content` 문자열 결합 |
| `SINGLE_FILE` | `FILE_LIST` | `items` 배열로 결합 |
| `SINGLE_EMAIL` | `EMAIL_LIST` | `items` 배열로 결합 |
| `SPREADSHEET_DATA` | `SPREADSHEET_DATA` | headers 유지, rows 병합 |
| 동일하지 않은 혼합 타입 | `API_RESPONSE` 또는 실패 | v1은 실패 권장 |

v1에서는 혼합 타입을 `INVALID_REQUEST`로 실패시키는 것이 단순하고 안전하다.

TEXT 집계 예:

```json
{
  "type": "TEXT",
  "content": "1. a.pdf\n...\n\n---\n\n2. b.pdf\n...",
  "loop_results": [
    { "type": "TEXT", "content": "a.pdf 요약" },
    { "type": "TEXT", "content": "b.pdf 요약" }
  ],
  "iterations": 2
}
```

### 6.6 실패 처리

body node 반복 실행 중 한 번이라도 실패하면 workflow 전체를 실패 처리한다.

정책:

- aggregate body log status는 `failed`
- error에는 실패한 iteration index, body node id, 원본 에러를 context로 포함
- 이후 노드는 기존 실패 처리와 동일하게 skipped
- state는 기존 executor 실패 흐름을 따른다.

---

## 7. Spring 계약 보강

Spring의 현재 구현은 필수 계약 대부분을 이미 제공한다.

- `one_by_one -> LOOP`
- `output_data_type -> SINGLE_FILE` 또는 `SINGLE_EMAIL`
- `runtime_type -> loop`
- `runtime_config.output_data_type`

추가 보강은 선택 사항이다.

권장 metadata:

```json
{
  "loop_mode": "for_each",
  "body_scope": "next_node",
  "aggregation": "auto"
}
```

이 값은 FastAPI가 없어도 동작할 수 있지만, 추후 loop 정책을 명시적으로 구분하는 데 도움이 된다.

---

## 8. 프론트 영향

이 설계는 우선 백엔드 런타임 수정이다. 프론트는 다음 계약이 유지되면 큰 수정이 필요 없다.

- 노드 ID는 기존 graph node ID 유지
- `nodeLogs`는 그래프 노드당 1개 유지
- body node의 최종 `outputData`는 기존 canonical payload
- 반복 상세는 `loop_results`, `iterations` 같은 추가 필드로 제공

프론트의 “들어오는 데이터 / 나가는 데이터” 패널은 body node output의 aggregate payload를 그대로 표시할 수 있다.

---

## 9. 테스트 계획

### 9.1 FastAPI 단위 테스트

대상:

- `tests/test_loop_node.py`
- `tests/test_executor.py`

필수 케이스:

1. `FILE_LIST -> loop -> llm`
   - loop input items 2개
   - llm strategy 2회 실행
   - 각 llm input type은 `SINGLE_FILE`
   - body node log는 1개
   - body output type은 `TEXT`
   - `iterations == 2`

2. `EMAIL_LIST -> loop -> llm`
   - llm input type은 `SINGLE_EMAIL`
   - body output은 `TEXT`

3. `max_iterations = 1`
   - body node는 1회만 실행
   - aggregate output `iterations == 1`

4. loop outgoing edge 없음
   - `INVALID_REQUEST`

5. loop outgoing edge 2개 이상
   - `INVALID_REQUEST`

6. body node 실패
   - workflow state는 실패 계열
   - 이후 노드는 skipped

7. body node 중복 실행 방지
   - topological order에서 body node가 다시 실행되지 않음

### 9.2 Spring 연동 확인

Spring에서는 다음을 확인한다.

1. `one_by_one` 선택 시 loop node의 `outputDataType`이 `SINGLE_FILE` 또는 `SINGLE_EMAIL`로 저장되는지
2. `WorkflowTranslator`가 `runtime_config.output_data_type`을 FastAPI로 넘기는지
3. 실행 후 `GET /api/workflows/{id}/executions/latest/nodes/{nodeId}/data`가 body node aggregate data를 반환하는지

---

## 10. 수용 기준

- 사용자가 `하나씩 처리`를 선택한 워크플로우를 실행하면 다음 처리 노드가 항목별로 반복 실행된다.
- AI 처리 노드는 목록 전체가 아니라 단일 항목 payload를 입력으로 받는다.
- 최종 sink 노드는 반복 결과가 집계된 payload를 1회 받는다.
- nodeLogs에는 같은 graph node id가 중복으로 여러 개 생성되지 않는다.
- 기존 `if_else` branch skip 동작은 깨지지 않는다.
- 기존 단일 노드 실행, source, sink, llm 테스트는 통과한다.
- `ruff format .`, `ruff check .`, `pytest tests/`가 통과한다.

---

## 11. 구현 순서

1. `WorkflowExecutor`에 loop body 탐색 helper 추가
   - `_resolve_loop_body_node_id()`
   - outgoing edge 수 검증

2. item payload 변환 helper 추가
   - `_to_loop_item_payload()`
   - canonical type 조합 검증

3. body 반복 실행 helper 추가
   - `_execute_loop_body()`
   - 내부 반복 중 body node 실행
   - 실패 시 aggregate failed log 반환

4. 결과 집계 helper 추가
   - `_aggregate_loop_outputs()`
   - 기존 canonical type만 사용

5. main execute loop에 `runtime_type == "loop"` 분기 추가
   - loop node 1회 실행
   - body node aggregate 실행
   - `handled_nodes`로 body node 재실행 방지

6. 테스트 추가 및 기존 테스트 보정
   - `test_loop_node.py`
   - `test_executor.py`

7. 문서 보강
   - FastAPI `.docs` 쪽 runtime guide 또는 loop 관련 설계 문서에 반영

---

## 12. 백엔드 에이전트에게 전달할 핵심 요청

FastAPI 쪽에서 `one_by_one` loop를 단순 list passthrough가 아니라 executor-level 반복 실행으로 구현해 주세요.

핵심은 다음입니다.

- `LoopNodeStrategy`가 아니라 `WorkflowExecutor`가 downstream 반복 실행을 제어합니다.
- loop body는 v1에서 loop의 첫 번째 outgoing target 1개로 제한합니다.
- body node는 item 개수만큼 내부 실행하되 `nodeLogs`에는 aggregate log 1개만 남깁니다.
- item input은 `runtime_config.output_data_type` 기준으로 `SINGLE_FILE`, `SINGLE_EMAIL` 등 기존 canonical payload로 변환합니다.
- body 결과도 기존 canonical payload로 집계합니다.
- 새 canonical type은 만들지 않습니다.
- 실패 시 기존 `FlowifyException`/`ErrorCode.INVALID_REQUEST`/executor 실패 흐름을 사용합니다.
