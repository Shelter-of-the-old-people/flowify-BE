# PR4/PR5 프론트-백엔드 계약 수정 완료 보고서 (Spring)

> 작성일: 2026-05-05
> 대상: Spring backend
> 원본 요청: `src/main/resources/docs/PR4_PR5_FRONTEND_BACKEND_CONTRACT_FIX_REQUEST.md`

## 수정 요약

| 우선순위 | 요청 | 상태 | 비고 |
| --- | --- | --- | --- |
| P0 | NodeLifecycleService 값 기반 required validation | 완료 | 빈 문자열/null 값을 미설정으로 판정 |
| P1 | FastAPI Google Drive single_file metadata 보강 | Spring 대상 아님 | FastAPI 별도 처리 필요 |
| P1 | Google Sheets OAuth alias 연결 상태 반영 | 완료 | scope 검증, aliasOf, disconnectable 포함 |
| P2 | catalog picker/provider 지원 범위 정리 | 완료 | picker_supported 메타데이터 추가 |

---

## 1. P0: NodeLifecycleService 값 기반 required validation

### 수정 파일

- `src/main/java/org/github/flowify/catalog/service/NodeLifecycleService.java`
- `src/main/java/org/github/flowify/catalog/service/CatalogService.java`

### 변경 내용

#### CatalogService 신규 helper

- `findSourceMode(serviceKey, sourceModeKey)`: source catalog에서 특정 서비스의 source mode를 검색합니다.
- `isSourceTargetRequired(serviceKey, sourceModeKey)`: source mode의 `target_schema`가 비어 있는지(`{}`) 확인하여 target 필수 여부를 판단합니다. 알 수 없는 mode는 안전하게 필수로 간주합니다.

#### NodeLifecycleService 개선 사항

**Start Node**
- `type`: non-blank 필수
- `config.source_mode`: key 존재만이 아닌 non-blank 값 필수
- `outputDataType`: non-blank 필수
- `config.target`: `CatalogService.isSourceTargetRequired()`로 target_schema가 비어 있지 않은 mode에서만 필수. target_schema가 `{}`인 mode(예: Gmail `new_email`, `starred_email`)는 target 없이도 설정 완료 가능

**End Node**
- sink catalog의 `required: true` 필드에 대해 **값 기반 검증** 수행:
  - 문자열: `trim()` 후 빈 값이면 missing
  - Collection: 비어 있으면 missing
  - Map: 비어 있으면 missing
  - null: missing
  - 숫자/boolean: 값이 있으면 유효

**isConfigured 존중**
- 프론트가 명시적으로 `config.isConfigured=false`를 보낸 경우, 서버 값 기반 검증이 통과하더라도 configured를 true로 뒤집지 않습니다.
- `isConfigured` 키가 없는 경우(오래된 데이터)에는 값 기반으로만 계산합니다.

**missingFields 형식**
- 기존 형식 유지: `config.target`, `config.folder_id`, `config.spreadsheet_id` 등

### 테스트 추가

`src/test/java/org/github/flowify/catalog/NodeLifecycleServiceTest.java` (신규)

| 테스트 케이스 | 기대 결과 |
| --- | --- |
| Google Drive start node `source_mode=folder_new_file`, `target=""` | configured=false |
| Google Drive start node `source_mode=single_file`, `target=""` | configured=false |
| Gmail start node `source_mode=new_email`, target 없음 | target 때문에 실패하지 않음 (target_schema 비어 있음) |
| 빈 source_mode | configured=false |
| 프론트 `isConfigured=false` 전송 시 | configured=false 유지 |
| 빈 outputDataType | configured=false |
| Slack sink `channel=""` | configured=false |
| Gmail sink `to=""` | configured=false |
| Gmail sink `subject=""` | configured=false |
| Notion sink `target_id=""` | configured=false |
| Google Drive sink `folder_id=""` | configured=false |
| Google Sheets sink `spreadsheet_id=""` | configured=false |
| 모든 필수 필드 유효한 값 | configured=true |
| 필수 필드 null | configured=false |

---

## 2. P1: Google Sheets OAuth alias 연결 상태 반영

### 수정 파일

- `src/main/java/org/github/flowify/oauth/service/OAuthTokenService.java`

### 변경 내용

#### alias 서비스 scope 정책 선언

```java
private static final Map<String, List<String>> ALIAS_REQUIRED_SCOPES = Map.of(
    "google_sheets", List.of("https://www.googleapis.com/auth/spreadsheets")
);
```

#### getConnectedServices() 개선

- 실제 저장된 토큰 외에 alias 서비스도 응답에 포함합니다.
- 원본 토큰(`google_drive`)이 있고 필요한 scope(`spreadsheets`)가 포함되어 있으면:

```json
{
  "service": "google_sheets",
  "connected": true,
  "expiresAt": "2026-05-05T10:00:00Z",
  "aliasOf": "google_drive",
  "disconnectable": false
}
```

- scope가 부족하면:

```json
{
  "service": "google_sheets",
  "connected": false,
  "expiresAt": "2026-05-05T10:00:00Z",
  "aliasOf": "google_drive",
  "disconnectable": false,
  "reason": "OAUTH_SCOPE_INSUFFICIENT"
}
```

#### getDecryptedToken() scope 검증

- alias 서비스(`google_sheets`)로 토큰을 조회할 때, 원본 토큰에 필요한 scope가 있는지 검증합니다.
- scope가 부족하면 `ErrorCode.OAUTH_SCOPE_INSUFFICIENT` 예외를 발생시킵니다.
- 기존 alias 조회 동작(google_sheets -> google_drive 토큰 반환)은 유지됩니다.

#### deleteToken() alias 보호

- alias 서비스(`google_sheets`)를 직접 삭제하려고 하면 `ErrorCode.INVALID_REQUEST` 예외가 발생합니다.
- 프론트는 `disconnectable=false`를 기준으로 alias 서비스의 직접 연결 해제 버튼을 숨길 수 있습니다.

### 테스트 추가

`src/test/java/org/github/flowify/oauth/OAuthTokenServiceTest.java` (기존 파일에 추가)

| 테스트 케이스 | 기대 결과 |
| --- | --- |
| Google Drive 토큰 + spreadsheets scope -> getConnectedServices | google_sheets connected=true, aliasOf=google_drive |
| Google Drive 토큰 - spreadsheets scope -> getConnectedServices | google_sheets connected=false, reason=OAUTH_SCOPE_INSUFFICIENT |
| google_sheets 토큰 조회 + scope 충분 | google_drive 토큰 반환 성공 |
| google_sheets 토큰 조회 + scope 부족 | OAUTH_SCOPE_INSUFFICIENT 예외 |
| google_sheets 직접 삭제 시도 | INVALID_REQUEST 예외 |
| alias 메타데이터 일관성 (aliasOf, disconnectable) | 항상 포함 |
| 기존 alias 조회 동작 유지 | google_sheets -> google_drive 토큰 반환 |

---

## 3. P2: catalog picker/provider 지원 범위 정리

### 수정 파일

- `src/main/resources/catalog/source_catalog.json`
- `src/main/resources/catalog/sink_catalog.json`

### 변경 내용

catalog version을 `1.1.0`으로 올리고, picker 타입을 가진 target_schema와 config field에 `picker_supported` 메타데이터를 추가했습니다.

#### Source catalog picker_supported 현황

| 서비스 | picker 타입 | picker_supported | 비고 |
| --- | --- | --- | --- |
| Google Drive | file_picker | true | provider 구현됨 |
| Google Drive | folder_picker | true | provider 구현됨 |
| Gmail | email_picker | false | provider 미구현 |
| Gmail | label_picker | false | provider 미구현 |
| Google Sheets | sheet_picker | false | provider 미구현 |
| Google Calendar | time_picker | false | provider 미구현 |
| Google Calendar | day_picker | false | provider 미구현 |
| Canvas LMS | course_picker | true | provider 구현됨 |
| Canvas LMS | term_picker | true | provider 구현됨 |
| Slack | channel_picker | false | source side provider 미구현 |
| Notion | page_picker | false | source side provider 미구현 |

#### Sink catalog picker_supported 현황

| 서비스 | 필드 | picker 타입 | picker_supported | 비고 |
| --- | --- | --- | --- | --- |
| Slack | channel | channel_picker | true | provider 구현됨 |
| Notion | target_id | page_picker | true | provider 구현됨 |
| Google Drive | folder_id | folder_picker | true | provider 구현됨 |
| Google Sheets | spreadsheet_id | sheet_picker | false | provider 미구현 |
| Google Calendar | calendar_id | calendar_picker | false | provider 미구현 |

### 프론트 활용 방법

- `picker_supported: true` -> 선택형 picker UI 사용
- `picker_supported: false` -> 수동 입력 fallback UI 사용
- `picker_supported` 없음 (text_input, select 등) -> 기존 입력 방식 유지

---

## 4. 프론트 영향 정리

| 요청 | 프론트 수정 필요 여부 | 설명 |
| --- | --- | --- |
| P0 NodeLifecycleService | 불필요 | 기존 nodeStatus 표시 그대로 사용 가능 |
| P1 OAuth alias | 최소 수정 | connectedServiceKeys 로직 변경 불필요. `disconnectable=false`인 서비스의 연결 해제 버튼 숨김 권장 |
| P2 picker_supported | 선택적 | `picker_supported: false`인 picker에 수동 입력 fallback 추가 권장 |

---

## 5. 미해결 항목

| 항목 | 상태 | 담당 |
| --- | --- | --- |
| FastAPI Google Drive single_file metadata 보강 (P1) | 미반영 | FastAPI 별도 수정 필요 |
| Gmail label list provider 구현 | 미구현 | 후속 작업 |
| Google Sheets spreadsheet list provider 구현 | 미구현 | 후속 작업 |
| Google Calendar calendar list provider 구현 | 미구현 | 후속 작업 |
| Source side Slack channel/Notion page provider | 미구현 | 후속 작업 |

---

## 6. 검증 결과

```
BUILD SUCCESSFUL
전체 테스트 통과
```

모든 기존 테스트와 신규 테스트(NodeLifecycleServiceTest 14건, OAuthTokenServiceTest alias 7건)가 통과했습니다.
