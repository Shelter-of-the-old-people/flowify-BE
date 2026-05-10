# FastAPI Google Sheets Node Design

> **작성일** 2026-05-11
> **대상 저장소** `flowify-BE`
> **범위** FastAPI runtime 관점의 Google Sheets 노드 설계
> **관련 저장소** `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 Google Sheets를 `시작 노드`, `중간 노드`, `끝 노드`로 사용할 때 FastAPI가 맡아야 하는 실행 책임을 정의한다.

이번 설계의 핵심은 아래와 같다.

- FastAPI는 실제 시트 읽기, 검색, lookup, diff 계산, 쓰기를 수행한다.
- 스프레드시트/시트 생성은 설정 단계의 책임이며, Spring이 관리한다.
- FastAPI는 생성 UI나 생성 API의 owner가 아니다.
- `new_row`, `row_updated`는 상태 기반 diff를 계산하되, durable state commit은 Spring이 맡는다.

---

## 2. 사용자 자동화 기준

FastAPI가 안정적으로 지원해야 하는 대표 시나리오는 아래와 같다.

- 시트 전체를 읽어 요약 또는 보고서 생성
- 특정 단어가 포함된 행만 검색
- 특정 key 행을 lookup 해서 후속 판단
- 새 행이 들어왔을 때만 처리
- 수정된 행만 처리
- 결과를 append, overwrite, update, upsert

즉 이 저장소의 Google Sheets 책임은 `실행 시점에 데이터를 정확히 읽고 계산하고 쓰는 것`이다.

---

## 3. FastAPI 책임 범위

### 3.1 FastAPI가 하는 일

- Google Sheets API 호출
- 시트 범위 읽기
- 텍스트 검색
- key 기반 lookup
- `new_row`, `row_updated` diff 계산
- append / overwrite / update / upsert 실행
- 다음 성공 실행에 반영할 `node_state_update` 계산

### 3.2 FastAPI가 하지 않는 일

- 스프레드시트 파일 생성
- 시트 탭 생성
- picker 목록 관리
- durable state 저장
- schedule 등록

이 기능들은 Spring과 FE의 설정 단계에서 처리한다.

---

## 4. 런타임 계약

### 4.1 RuntimeSource

Google Sheets 시작 노드는 아래 정보를 받아야 한다.

```python
class RuntimeSource(BaseModel):
    service: str
    mode: str
    target: str = ""
    canonical_input_type: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] | None = None
```

Google Sheets source config 예시:

```json
{
  "service": "google_sheets",
  "mode": "row_updated",
  "target": "spreadsheet_123",
  "canonical_input_type": "SPREADSHEET_DATA",
  "config": {
    "spreadsheet_id": "spreadsheet_123",
    "sheet_name": "Responses",
    "range_a1": "Responses!A:Z",
    "header_row": 1,
    "data_start_row": 2,
    "key_column": "submission_id",
    "initial_sync_mode": "skip_existing"
  },
  "state": {
    "last_seen_row_index": 201,
    "row_snapshot": {
      "sub_001": "hash-a"
    }
  }
}
```

### 4.2 RuntimeAction

Google Sheets 중간 노드는 service action 형태를 사용한다.

```python
class RuntimeAction(BaseModel):
    service: str
    action: str
    config: dict[str, Any] = Field(default_factory=dict)
```

지원 액션:

- `read_range`
- `search_text`
- `lookup_row_by_key`

### 4.3 RuntimeSink

Google Sheets 끝 노드는 아래 쓰기 모드를 지원한다.

- `append_rows`
- `overwrite_range`
- `update_row_by_key`
- `upsert_row_by_key`

---

## 5. 역할별 동작

### 5.1 시작 노드

지원 모드:

- `sheet_all`
- `new_row`
- `row_updated`

동작 요약:

- `sheet_all`: 현재 범위를 그대로 읽어 `SPREADSHEET_DATA` 반환
- `new_row`: 마지막 성공 실행 이후 새로 추가된 행만 반환
- `row_updated`: `key_column` 기준으로 수정된 행만 반환

### 5.2 중간 노드

지원 액션:

- `read_range`
- `search_text`
- `lookup_row_by_key`

동작 요약:

- `read_range`: 지정 범위를 읽어 그대로 반환
- `search_text`: 지정 컬럼 또는 전체 컬럼에서 검색
- `lookup_row_by_key`: key에 맞는 단일 행을 찾아 `API_RESPONSE`로 반환

### 5.3 끝 노드

지원 쓰기 방식:

- `append_rows`
- `overwrite_range`
- `update_row_by_key`
- `upsert_row_by_key`

동작 요약:

- append: 새 행 누적
- overwrite: 범위 전체 덮어쓰기
- update: key가 있는 행만 갱신
- upsert: key가 있으면 갱신, 없으면 추가

---

## 6. 상태 기반 diff

### 6.1 new_row

- 현재 row count를 읽는다.
- `last_seen_row_index` 이후 행만 추출한다.
- 첫 실행에서 `skip_existing`이면 현재 마지막 행만 기준점으로 저장하고 결과는 비운다.

### 6.2 row_updated

- `key_column`은 필수다.
- 현재 행을 key 기준 map으로 정규화한다.
- row hash를 계산한다.
- 이전 `row_snapshot`과 비교해 hash가 바뀐 key만 반환한다.

### 6.3 node_state_update

FastAPI는 성공 후보 상태만 계산해 callback payload로 보낸다.

예시:

```json
{
  "nodeStateUpdates": [
    {
      "nodeId": "node_start_sheet",
      "service": "google_sheets",
      "state": {
        "last_seen_row_index": 205,
        "row_snapshot": {
          "sub_001": "hash-b"
        }
      }
    }
  ]
}
```

실제 commit은 Spring이 한다.

---

## 7. 생성 기능과의 관계

이번 설계에서 생성 기능은 `설정 단계 생성`만 포함한다.

- 사용자가 목록에 원하는 스프레드시트가 없으면 FE -> Spring 생성 API로 새 파일을 만든다.
- 사용자가 선택한 스프레드시트에 원하는 탭이 없으면 FE -> Spring 생성 API로 새 시트를 만든다.
- FastAPI는 이미 선택된 `spreadsheet_id`, `sheet_name`을 받아 실행만 한다.

즉 FastAPI에는 `create_spreadsheet`, `create_sheet` 런타임 책임을 넣지 않는다.

---

## 8. 검증 계획

- `sheet_all` source 테스트
- `new_row` first-run / follow-up 테스트
- `row_updated` 수정 감지 테스트
- `search_text` static / input binding 테스트
- `lookup_row_by_key` 테스트
- `append_rows`, `overwrite_range`, `update_row_by_key`, `upsert_row_by_key` 테스트
- executor가 `nodeStateUpdates`를 callback에 실어 보내는지 테스트

---

## 9. V1 범위

이번 V1에 포함:

- `sheet_all`
- `new_row`
- `row_updated`
- `read_range`
- `search_text`
- `lookup_row_by_key`
- `append_rows`
- `overwrite_range`
- `update_row_by_key`
- `upsert_row_by_key`
- `RuntimeSource.config/state`
- `RuntimeAction`
- `nodeStateUpdates`

이번 V1에서 제외:

- row deletion event
- regex / fuzzy search
- 다중 spreadsheet join
- Apps Script / push webhook 기반 실시간 이벤트
- 런타임 자동 생성

---

## 10. 결정 요약

- FastAPI는 Google Sheets의 실행 엔진이다.
- 생성은 설정 단계에서 Spring이 처리하고, FastAPI는 이미 결정된 대상에 대해서만 읽기/검색/쓰기/차이 계산을 수행한다.
- `new_row`, `row_updated`는 상태 기반 diff로 정식 지원한다.
- 사용자가 자주 원하는 `전체 읽기`, `검색`, `lookup`, `upsert` 중심으로 V1을 고정한다.
