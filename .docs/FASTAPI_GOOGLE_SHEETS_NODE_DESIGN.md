# FastAPI Google Sheets Node Design

> 작성일: 2026-05-11
> 대상 저장소: `flowify-BE`
> 범위: FastAPI runtime 기준 Google Sheets 노드 실행 설계
> 관련 저장소: `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 Google Sheets 노드에 대해 FastAPI가 런타임에서 맡아야 하는 책임과 실행 규칙을 정의한다.

FastAPI는 picker UI나 생성 오케스트레이션을 담당하지 않고, 실제 실행 엔진 역할을 맡는다.

Google Sheets는 아래 세 역할을 모두 지원해야 한다.

- 시작 노드
- 중간 노드
- 끝 노드

---

## 2. 런타임 목표

FastAPI는 아래와 같은 대표 자동화를 안정적으로 지원해야 한다.

- 시트 전체 읽기
- 특정 범위 읽기
- 키워드 검색
- 기준 컬럼으로 한 행 조회
- 마지막 성공 실행 이후 새로 추가된 행만 방출
- 마지막 성공 실행 이후 수정된 행만 방출
- 결과를 시트에 추가 저장
- 선택 범위를 덮어쓰기
- 기준 컬럼으로 기존 행 부분 수정
- 기준 컬럼으로 업서트

---

## 3. 책임 경계

### 3.1 FastAPI가 담당하는 것

- Google Sheets API 읽기와 쓰기 실행
- 범위 읽기
- 검색과 조회 실행
- `new_row` diff 계산
- `row_updated` diff 계산
- 부분 수정과 업서트 갱신 경로의 행 병합
- 성공 실행 후 `node_state_update` 계산

### 3.2 FastAPI가 담당하지 않는 것

- 스프레드시트 생성 UI
- 시트 생성 UI
- picker 목록 조회
- durable node state 영속화
- 저장 시점 검증의 최종 owner 역할

위 항목은 `flowify-BE-spring`과 `flowify-FE`가 담당한다.

---

## 4. 런타임 계약

### 4.1 RuntimeSource

Google Sheets 시작 노드는 `RuntimeSource`를 통해 실행된다.

필수 필드:

- `service = google_sheets`
- `mode`
- `target = spreadsheet_id`
- `config`

Google Sheets source config 예시:

- `sheet_name`
- `range_a1`
- `header_row`
- `data_start_row`
- `initial_sync_mode`
- `key_column`

### 4.2 RuntimeAction

Google Sheets 중간 노드는 구조화된 액션 설정으로 실행된다.

지원 액션:

- `read_range`
- `search_text`
- `lookup_row_by_key`

### 4.3 Runtime sink

Google Sheets 끝 노드는 sink config를 통해 실행된다.

지원 저장 방식:

- `append_rows`
- `overwrite_range`
- `update_row_by_key`
- `upsert_row_by_key`

---

## 5. 시작 노드 동작

### 5.1 `sheet_all`

동작:

- 선택한 시트 또는 범위를 읽는다.
- 헤더와 데이터 행을 정규화한다.
- 구조화된 표 형태로 반환한다.

### 5.2 `new_row`

동작:

- 현재 행을 읽는다.
- 이전 성공 실행에서 저장된 상태와 비교한다.
- 마지막 기준점 이후 새로 추가된 행만 방출한다.

사용 상태값:

- `last_seen_row_index`
- `header_signature`

첫 실행 모드:

- `skip_existing`
  - 현재 데이터를 기준점으로만 저장하고 결과는 비운다.
- `emit_existing`
  - 첫 실행에서 현재 행도 함께 방출한다.

### 5.3 `row_updated`

동작:

- 현재 행을 읽는다.
- `key_column` 기준으로 행 맵을 만든다.
- 각 행의 해시를 계산한다.
- 이전 스냅샷과 비교해 변경된 행만 방출한다.

사용 상태값:

- `row_snapshot`
- `header_signature`

중요 규칙:

- `key_column`은 필수다.

Mongo-safe 상태 규칙:

- 이메일처럼 `.`가 들어간 키는 그대로 Mongo map key로 저장하면 안 된다.
- 저장 전 escape하고, 읽을 때 다시 복원해야 한다.

### 5.4 시작 노드 source preview

Google Sheets 시작 노드는 실행 전 preview도 지원해야 한다.

preview 목표:

- 사용자가 어떤 헤더와 행이 들어오는지 실행 전에 확인한다.
- preview는 실제 실행 기록이나 `node_state_update`를 만들지 않는다.
- preview 결과는 기존 실행 payload와 같은 `SPREADSHEET_DATA` 계열을 유지한다.

모드별 preview 규칙:

- `sheet_all`
  - 현재 시트에서 앞쪽 `limit`행 sample을 반환한다.
- `new_row`
  - event source의 성격을 보여주기 위해 현재 시트의 최근 `limit`행 sample을 반환한다.
  - preview에서는 첫 실행 `skip_existing` 상태를 commit하거나 변경하지 않는다.
- `row_updated`
  - `key_column` 검증은 그대로 수행한다.
  - preview에서는 실제 diff commit 대신 현재 시트의 최근 `limit`행 sample을 반환한다.

preview payload 규칙:

- `headers`는 현재 헤더를 그대로 반환한다.
- `rows`는 sample 행만 반환한다.
- `metadata.total_rows`로 실제 전체 행 수를 함께 반환한다.
- `metadata.truncated`와 top-level `truncated`로 sample 생략 여부를 표시한다.
- `metadata.sample_strategy`로 `head`/`tail` sample 방식을 구분한다.

---

## 6. 중간 노드 동작

### 6.1 `read_range`

동작:

- 선택한 범위를 읽는다.
- 헤더와 데이터 행이 있는 표 형태로 반환한다.

### 6.2 `search_text`

동작:

- 선택한 컬럼 또는 전체 행을 대상으로 텍스트를 검색한다.
- exact 또는 contains를 지원한다.
- 대소문자 구분 여부를 지원한다.
- 고정 값 또는 입력 필드 바인딩을 검색값 소스로 지원한다.

유효한 검색 설정은 아래 둘 중 하나를 만족해야 한다.

- `search_value`가 있다.
- `search_source = input_field` 이고 `search_field`가 있다.

둘 다 없으면 런타임에서 거부해야 한다.

### 6.3 `lookup_row_by_key`

동작:

- `key_column` 기준으로 한 행을 찾는다.
- 고정 값 또는 입력 필드 바인딩을 조회값 소스로 지원한다.
- 매칭된 행과 메타데이터를 반환한다.

중요 규칙:

- `key_column`은 대상 시트 헤더에 실제로 존재해야 한다.

---

## 7. 끝 노드 동작

### 7.1 `append_rows`

동작:

- 기존 데이터 아래에 새 행을 추가한다.
- 옵션에 따라 헤더를 초기화할 수 있다.

### 7.2 `overwrite_range`

범위 해석 규칙:

- `range_a1`가 `A1`, `A1:B10`처럼 시트 이름 없는 형태이면 선택된 `sheet_name`을 앞에 붙여 해석한다.
- 예:
  - `sheet_name = MailSubset`, `range_a1 = A1` -> `MailSubset!A1`
- `range_a1`에 이미 시트 이름이 포함돼 있으면 그 값을 그대로 사용한다.

동작:

- 선택한 범위를 새 결과 표로 교체한다.

### 7.3 `update_row_by_key`

동작:

- `key_column`으로 기존 행 하나를 찾는다.
- 들어온 컬럼만 기존 행에 병합한다.
- 입력에 없는 컬럼은 유지한다.
- 병합된 전체 행을 다시 쓴다.

중요 규칙:

- 이 동작은 부분 수정이어야 한다.
- 전달되지 않은 컬럼을 빈 문자열로 지우면 안 된다.

### 7.4 `upsert_row_by_key`

동작:

- 같은 키의 행이 있으면 기존 행에 병합한다.
- 없으면 새 행을 추가한다.

중요 규칙:

- update 경로는 `update_row_by_key`와 같은 부분 수정 규칙을 사용해야 한다.

---

## 8. 출력 의미

Google Sheets 노드는 다음 노드가 재사용할 수 있는 구조화된 출력을 반환해야 한다.

주요 필드:

- `headers`
- `rows`
- `rowCount`
- `metadata`

쓰기 동작은 추가로 아래 요약값을 반환할 수 있다.

- 영향을 받은 행 수
- insert/update 요약

상태를 가지는 시작 노드는 성공 시 아래도 계산해야 한다.

- `node_state_update`

이 상태 업데이트는 FastAPI가 계산하지만, 실제 commit은 Spring이 callback 이후 수행한다.

---

## 9. 검증 기대사항

FastAPI는 아래와 같은 잘못된 설정을 런타임에서 막아야 한다.

- `key_column`이 빠진 update, lookup, row_updated
- `key_column`이 실제 헤더에 없는 경우
- `search_text`인데 검색값 소스가 없는 경우
- 필요한 범위 설정이 빠진 경우

Spring 쪽 저장 시점 검증이 있더라도, FastAPI도 런타임 보호막 역할을 해야 한다.

---

## 10. 실제 사용 시나리오 대응 범위

현재 런타임 설계는 아래 시나리오를 염두에 둔다.

- Gmail 메일을 Google Sheets staging 시트로 적재
- Gmail 메일을 sender 또는 message id 기준으로 upsert
- 시트 전체를 읽어 보고서 생성
- 키워드 검색 결과를 다른 탭에 저장
- 정책표 lookup
- `new_row` 기반 대기열 처리
- `row_updated` 기반 사람 개입 후속 처리

---

## 11. 테스트 기대사항

아래가 충족되면 FastAPI 동작이 올바르다고 본다.

- `search_text`가 contains, exact, case-sensitive, case-insensitive, input binding을 지원한다.
- `lookup_row_by_key`가 매치/미매치 모두 올바르게 처리된다.
- `new_row`가 `skip_existing`, `emit_existing`를 지원한다.
- `row_updated`가 변경된 행만 감지한다.
- `update_row_by_key`가 전달되지 않은 컬럼을 유지한다.
- `upsert_row_by_key`가 update 시 부분 수정, insert 시 신규 추가를 수행한다.
- 모든 경로가 Spring callback 흐름 안에서 정상 동작한다.

---

## 12.1 공통 표 가공 경로

Google Sheets 저장 흐름은 메일 전용 시나리오가 아니라, 어떤 입력이든 `SPREADSHEET_DATA`로 정리한 뒤 시트에 쓰는 공통 경로를 포함해야 한다.
FastAPI는 이 공통 표 가공 경로에서 `DATA_FILTER`가 만든 표형 payload를 안정적으로 받아 Google Sheets start/middle/end 노드와 이어지게 해야 한다.

대표 입력 타입:

- `SINGLE_EMAIL`
- `SINGLE_FILE`
- `SPREADSHEET_DATA`

대표 표 가공 액션:

- `filter_fields_table`
  - 선택한 필드만 골라 표 컬럼으로 정리한다.
- `filter_metadata_table`
  - 파일 메타데이터를 표 컬럼으로 정리한다.

셀 직렬화 규칙:

- 문자열, 숫자, 불리언은 그대로 사용한다.
- 리스트는 사람이 읽을 수 있는 문자열로 평탄화한다.
- 딕셔너리 리스트는 `name`, `filename`, `title`, `email`, `id` 우선 순위로 대표 값을 뽑아 쉼표로 연결한다.
- 예:
  - 수신자 목록 `[{email: a}, {email: b}]` -> `a, b`
  - 라벨 목록 `["INBOX", "IMPORTANT"]` -> `INBOX, IMPORTANT`
  - 첨부 목록 `[{filename: agenda.pdf}]` -> `agenda.pdf`

실사용 의미:

- Gmail 메일을 시트 로그용 표로 정리할 수 있다.
- 파일 메타데이터를 시트 자산 목록으로 정리할 수 있다.
- 기존 시트 데이터를 다시 골라 다른 시트용 표로 재정리할 수 있다.

## 12.2 향후 보완점

FastAPI 런타임은 Google Sheets 중간 노드 기능을 계속 지원한다.

지원 대상:

- `read_range`
- `search_text`
- `lookup_row_by_key`

다만 현재 제품 사용자 흐름에서는 FE 에디터가 공통 `data-process` 외의 중간 노드 타입을 직접 생성하지 못하므로, 위 기능은 현재 사용자 경로에서는 직접 노출되지 않는다.

따라서 이번 이슈에서는 런타임 지원을 유지하되, 기능 노출은 보류 상태로 두고 문서에만 향후 보완점으로 남긴다.

향후 FE 에디터에서 중간 노드 타입 확장이 열리면, FastAPI의 현재 중간 노드 실행 경로를 그대로 연결해 재사용한다.

또한 현재 시작 노드의 `new_row`, `row_updated`는 Google Sheets 변경을 외부 push event로 즉시 받는 구조가 아니라, 워크플로우 실행 시점에 시트를 다시 읽고 durable state와 비교하는 polling 기반 감지로 동작한다.

이번 이슈 범위에서는 자동화 요구를 충족하지만, 향후 "시트가 바뀌면 즉시 실행"에 가까운 제품 요구가 생기면 별도 watch 등록, event ingestion, 기준점 갱신 규칙을 포함한 실시간 감지 설계를 추가해야 한다.

끝 노드도 현재는 실제 쓰기 전 결과를 계산만 해보는 dry-run preview를 제공하지 않는다.

향후 보완 시에는 아래 정보를 실제 write 없이 계산해서 preview payload로 내려줄 수 있어야 한다.

- 대상 `spreadsheet_id`와 `sheet_name`
- 적용될 `write_mode`
- sample 기준으로 실제로 써질 row
- `update`/`upsert`일 때 key 기준 insert/update 예상 요약
- `overwrite_range`일 때 영향 범위 요약

이 기능은 실행 로직을 재사용하되, 외부 시트에 commit하지 않는 no-write preview 경로로 분리하는 것이 안전하다.

## 12. 결정 요약

FastAPI는 Google Sheets 실행 엔진이다.

반드시 제대로 해야 하는 일:

- 읽기
- 검색
- 조회
- diff 계산
- 추가 저장
- 덮어쓰기
- 부분 수정
- 업서트

직접 owner가 아닌 일:

- picker 생성 UX
- durable state 영속화 오케스트레이션
- 스프레드시트/시트 생성 UI
