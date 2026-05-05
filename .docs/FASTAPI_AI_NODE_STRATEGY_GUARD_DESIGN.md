# FastAPI AI 노드 실행 보강 설계

> 작성일: 2026-05-05  
> 대상: `flowify-BE` FastAPI 실행 엔진  
> 관련 이슈: AI 처리 노드가 빈 프롬프트로 실행되어 일반 안내 문구만 반환하는 문제

---

## 1. 배경

Spring 서버에서 AI 노드의 기본 프롬프트 조합을 담당하도록 보강되었다. FastAPI는 Spring이 전달한 `runtime_config.prompt`를 사용해 LLM을 호출한다.

현재 FastAPI 실행 엔진은 `runtime_type=llm`인 중간 노드를 모두 `LLMNodeStrategy`로 처리한다. 이 구조에서는 다음 문제가 발생한다.

- `prompt`가 비어 있어도 LLM 호출이 실행된다.
- `PASSTHROUGH`처럼 LLM 호출이 필요 없는 처리도 LLM 전략으로 들어간다.
- `DATA_FILTER`처럼 결정적 변환이 가능한 처리도 빈 프롬프트 LLM 호출로 흘러갈 수 있다.
- 결과적으로 사용자가 기대한 처리 결과 대신 “어떤 요청을 도와드릴까요?” 같은 일반 응답이 반환된다.

---

## 2. 현재 계약과 제약

### 2.1 기존 runtime contract

`.docs/FASTAPI_CONTRACT_SPEC.md`의 현재 매핑은 다음과 같다.

| runtime_type | 현재 FastAPI 전략 |
| --- | --- |
| `input` | `InputNodeStrategy` |
| `output` | `OutputNodeStrategy` |
| `llm` | `AI`, `DATA_FILTER`, `AI_FILTER`, `PASSTHROUGH` |
| `if_else` | `IfElseNodeStrategy` |
| `loop` | `LoopNodeStrategy` |

즉, Spring은 아직 `AI`, `DATA_FILTER`, `PASSTHROUGH`를 별도 `runtime_type`으로 보내지 않고 `runtime_type=llm` 하위 의미로 전달한다.

### 2.2 FastAPI 컨벤션

이번 변경은 `.docs/CONVENTION.md`를 따른다.

- 새 실행 단위는 `app/core/nodes/{타입}_node.py`에 `NodeStrategy`로 구현한다.
- public class/method에는 한국어 docstring과 타입 힌트를 작성한다.
- 비즈니스 오류는 `FlowifyException`으로 반환한다.
- 새 전략은 `NodeFactory`에서 등록한다.
- 테스트는 `tests/test_{대상}.py`에 작성한다.
- `ruff format .`, `ruff check .`, `pytest tests/`를 통과해야 한다.

---

## 3. 설계 원칙

1. 외부 계약은 당장 변경하지 않는다.
   - Spring이 보내는 `runtime_type=llm`은 그대로 수용한다.

2. 내부 실행 전략은 의미 단위로 분리한다.
   - `PASSTHROUGH`는 LLM 호출 없이 입력 payload를 그대로 반환한다.
   - `DATA_FILTER`는 지원 가능한 범위에서 결정적 필드 추출만 수행한다.
   - `AI`, `AI_FILTER`는 LLM 기반 처리로 유지한다.

3. 전환기 라우팅은 `NodeFactory`에만 둔다.
   - `WorkflowExecutor`에는 `node_type` 분기 로직을 추가하지 않는다.
   - 전략 선택 책임은 `NodeFactory`에 고정한다.

4. 빈 프롬프트 LLM 호출은 실행 전 차단한다.
   - process 계열 action에서 `prompt`가 없으면 `INVALID_REQUEST`를 발생시킨다.
   - `SPREADSHEET_DATA`처럼 JSON 출력을 요구하는 LLM 처리도 prompt가 필요하다.

5. 범위를 넘는 기능은 명시적으로 실패시킨다.
   - 복잡한 조건 필터, AI 판단 필터 결과 구조화는 이번 범위에서 제외한다.
   - 지원하지 않는 `DATA_FILTER` 설정은 조용히 통과시키지 않고 `INVALID_REQUEST`로 실패시킨다.

---

## 4. 구현 설계

### 4.1 `NodeFactory` 전환기 전략 선택

`runtime_type`은 계속 primary key로 읽는다. 단, `runtime_type=llm`인 경우에 한해 `runtime_config.node_type`을 보조 키로 사용한다.

```text
runtime_type != llm
  -> 기존 runtime_type 그대로 전략 선택

runtime_type == llm
  -> runtime_config.node_type == PASSTHROUGH  -> passthrough 전략
  -> runtime_config.node_type == DATA_FILTER  -> data_filter 전략
  -> 그 외                                  -> llm 전략
```

보조 키 사용은 전환기 호환 로직이다. 향후 Spring이 `runtime_type=passthrough`, `runtime_type=data_filter`를 직접 내려주면 이 fallback을 제거하거나 단순화한다.

권장 헬퍼:

```python
def resolve_strategy_key(node_def) -> str:
    """NodeDefinition에서 실제 실행 전략 키를 결정합니다."""
```

### 4.2 `LLMNodeStrategy` 프롬프트 guard

`LLMNodeStrategy.execute()`에서 LLM 호출 직전에 prompt를 검증한다.

검증 대상:

- `action in {"process", "extract", "translate", "custom"}`
- `output_data_type == "SPREADSHEET_DATA"`
- action이 비어 있고 기본값으로 `process`가 적용되는 경우

예외:

- `summarize`: 입력 텍스트만으로 수행 가능
- `classify`: categories 기반 처리 가능. 단, categories 누락 검증은 별도 보강 가능

실패 응답:

```python
raise FlowifyException(
    ErrorCode.INVALID_REQUEST,
    detail="AI 처리 프롬프트가 없어 노드를 실행할 수 없습니다.",
    context={"node_id": node.get("id"), "action": action},
)
```

### 4.3 `PassthroughNodeStrategy`

파일: `app/core/nodes/passthrough_node.py`

역할:

- 입력 canonical payload를 변경하지 않고 반환한다.
- 입력이 없으면 실행할 수 없으므로 실패한다.

동작:

```text
input_data 존재 -> input_data 그대로 반환
input_data 없음 -> INVALID_REQUEST
```

주의:

- `credentials` 같은 실행 보조 데이터가 payload에 섞여 있으면 반환하지 않는다.
- 현재 executor는 `input_data`와 `service_tokens`를 분리해 전달하므로 payload만 반환하면 된다.

### 4.4 `DataFilterNodeStrategy`

파일: `app/core/nodes/data_filter_node.py`

이번 범위에서는 **명확한 필드 선택 기반 projection**만 지원한다.

Spring/프론트의 현재 설정 구조는 다음과 같다.

```json
{
  "choiceActionId": "filter_fields",
  "choiceSelections": {
    "follow_up": ["subject", "sender"]
  },
  "node_type": "DATA_FILTER",
  "output_data_type": "TEXT"
}
```

따라서 FastAPI는 `choiceSelections.follow_up`을 우선 읽어야 한다. `selected_fields` 같은 별도 키는 현재 공식 계약이 아니므로 하위 호환 fallback으로만 둔다.

지원 입력:

- `TEXT`
- `SINGLE_FILE`
- `SINGLE_EMAIL`
- `SPREADSHEET_DATA`
- `SCHEDULE_DATA`
- `FILE_LIST`
- `EMAIL_LIST`
- `API_RESPONSE`

필드 선택 후보:

- `runtime_config.choiceSelections.follow_up`
- `runtime_config.choice_selections.follow_up`
- `runtime_config.selected_fields`
- `config.selected_fields`

출력 정책:

- `runtime_config.output_data_type`을 우선 따른다.
- `output_data_type=TEXT`이면 선택 필드를 사람이 읽을 수 있는 텍스트로 직렬화한다.
- `output_data_type=SPREADSHEET_DATA`이면 선택 필드를 `headers`로, 값 목록을 `rows`로 반환한다.
- `output_data_type=API_RESPONSE`이면 선택 필드를 `data` 또는 `items`에 담아 반환한다.
- `output_data_type`이 없으면 기존 canonical type을 가능한 범위에서 유지한다.

단일 객체 예시:

```json
{
  "type": "TEXT",
  "content": "제목: 메일 제목\n발신자: sender@example.com"
}
```

목록 객체를 `SPREADSHEET_DATA`로 변환하는 예시:

```json
{
  "type": "SPREADSHEET_DATA",
  "headers": ["subject", "from"],
  "rows": [["메일 제목", "sender@example.com"]]
}
```

지원하지 않는 설정:

- 조건식 필터
- 정렬/집계
- AI 판단 필터
- 중첩 경로 필드 선택
- 자유 텍스트에서 “중요 문장만”, “핵심만”처럼 의미 판단이 필요한 추출

위 항목은 이번 범위에서 `INVALID_REQUEST`로 반환한다.

`choiceActionId`별 1차 지원 범위:

| choiceActionId | 처리 |
| --- | --- |
| `filter_fields` | 지원. `choiceSelections.follow_up` 필드 projection |
| `filter_metadata` | 지원. 파일 메타데이터 필드 projection |
| `filter_condition` | 보류. 조건 연산자 계약 필요 |
| `filter_type` | 보류. 일정/도메인별 predicate 계약 필요 |
| `filter_content` | 보류. 의미 판단이 필요하므로 AI 처리 또는 별도 계약 필요 |

### 4.5 `AI_FILTER` 처리

`AI_FILTER`는 LLM 판단이 필요하므로 이번에는 `LLMNodeStrategy`에 남긴다.

다만 현재 출력 payload 구조가 명확하지 않으므로 FastAPI에서 임의로 필터 결과 구조를 만들지 않는다. Spring이 `runtime_config.prompt`를 제공하면 기존 LLM 처리 경로를 사용한다.

후속 협의가 필요한 항목:

- AI 필터 결과가 boolean인지, 원본 payload 유지인지, 필터링된 목록인지
- 여러 item 입력 시 item별 판단을 반복해야 하는지
- 실패/보류 결과를 어떤 payload로 표현할지

---

## 5. 테스트 설계

### 5.1 `test_llm_node.py`

추가 케이스:

- process action에서 prompt가 없으면 `INVALID_REQUEST`
- extract/translate/custom action에서 prompt가 없으면 `INVALID_REQUEST`
- `SPREADSHEET_DATA` 출력인데 prompt가 없으면 `INVALID_REQUEST`
- summarize action은 prompt 없이 실행 가능

### 5.2 `test_node_factory.py`

추가 케이스:

- `runtime_type=llm`, `node_type=PASSTHROUGH`이면 `PassthroughNodeStrategy`
- `runtime_type=llm`, `node_type=DATA_FILTER`이면 `DataFilterNodeStrategy`
- `runtime_type=llm`, `node_type=AI`이면 `LLMNodeStrategy`
- `runtime_type`이 없으면 기존 fallback 유지

### 5.3 `test_passthrough_node.py`

추가 케이스:

- 입력 payload를 그대로 반환
- 입력 payload가 없으면 `INVALID_REQUEST`

### 5.4 `test_data_filter_node.py`

추가 케이스:

- `SINGLE_EMAIL`에서 선택 필드만 추출
- `SINGLE_FILE`에서 파일 메타데이터 필드 추출
- `FILE_LIST`에서 각 item projection
- 선택 필드가 없으면 `INVALID_REQUEST`
- 지원하지 않는 조건 필터 설정이면 `INVALID_REQUEST`

---

## 6. 구현 단계

### Step 1. LLM prompt guard

- `LLMNodeStrategy` docstring 한국어 정리
- prompt 필요 여부 helper 추가
- prompt 누락 시 `FlowifyException(INVALID_REQUEST)` 발생
- 관련 테스트 추가

검증:

```bash
python -m pytest tests/test_llm_node.py
```

커밋 예시:

```text
fix(LLM노드): 빈 프롬프트 실행 차단
```

### Step 2. Passthrough 전략 추가

- `PassthroughNodeStrategy` 추가
- `NodeFactory` registry 등록
- `resolve_strategy_key()`에서 전환기 라우팅 처리
- 관련 테스트 추가

검증:

```bash
python -m pytest tests/test_passthrough_node.py tests/test_node_factory.py
```

커밋 예시:

```text
feat(노드전략): 패스스루 실행 전략 추가
```

### Step 3. DataFilter 전략 추가

- `DataFilterNodeStrategy` 추가
- 필드 선택 projection 구현
- `NodeFactory` 전환기 라우팅 추가
- 관련 테스트 추가

검증:

```bash
python -m pytest tests/test_data_filter_node.py tests/test_node_factory.py
```

커밋 예시:

```text
feat(노드전략): 데이터 필터 실행 전략 추가
```

### Step 4. 전체 검증

```bash
ruff format .
ruff check .
python -m pytest tests/
```

---

## 7. 백엔드 간 합의가 필요한 후속 항목

이번 구현은 현재 Spring 계약을 깨지 않는 전환기 보강이다. 다만 장기적으로는 다음 중 하나로 계약을 정리해야 한다.

### A안. runtime_type 확장

Spring이 다음 값을 직접 내려준다.

- `runtime_type=passthrough`
- `runtime_type=data_filter`
- `runtime_type=ai_filter`

FastAPI는 `runtime_type`만 보고 전략을 선택한다.

### B안. runtime_type 유지 + subtype 명시

Spring은 계속 `runtime_type=llm`을 내려주되, `runtime_config.node_type`을 공식 subtype으로 문서화한다.

FastAPI는 `runtime_type + runtime_config.node_type` 조합으로 전략을 선택한다.

현재 구현은 B안에 가까운 전환기 처리다. 다만 runtime contract의 “primary key는 runtime_type” 원칙을 유지하려면 장기적으로는 A안이 더 명확하다.

---

## 8. 완료 기준

- 빈 prompt로 LLM이 호출되지 않는다.
- `PASSTHROUGH`는 LLM 호출 없이 입력 payload를 그대로 넘긴다.
- `DATA_FILTER`는 지원 가능한 필드 projection만 수행한다.
- 지원하지 않는 필터 설정은 조용히 잘못된 결과를 만들지 않고 실패한다.
- `WorkflowExecutor`에는 노드 subtype 분기가 추가되지 않는다.
- FastAPI 컨벤션의 docstring, 타입 힌트, 에러 처리, 테스트 규칙을 만족한다.
