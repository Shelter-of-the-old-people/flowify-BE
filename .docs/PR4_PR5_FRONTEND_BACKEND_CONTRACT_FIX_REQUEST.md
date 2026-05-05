# PR4/PR5 병합 이후 프론트-백엔드 계약 검토 및 수정 요청

> 작성일: 2026-05-05  
> 대상: Spring backend, FastAPI runtime backend  
> 관련 문서:
> - `docs/backend/PR5_MERGE_REPORT.md`
> - `docs/backend/MERGE_REPORT_PR4_FILE_UPLOAD_AUTO_SHARE.md`
> - `docs/backend/PR5_DRIVE_SINGLE_FILE_METADATA_FIX_REQUEST.md`
> - `docs/WORKFLOW_SOURCE_TARGET_PICKER_UX_CONSOLIDATION_DESIGN.md`
> - `docs/NODE_SETUP_WIZARD_DESIGN.md`

## 1. 검토 목적

PR4 파일 업로드 자동 공유 템플릿, PR5 메일 요약 전달 템플릿 병합 이후 프론트 최신 코드와 백엔드 최신 코드를 함께 대조했습니다.

대부분의 핵심 기능은 정상적으로 이어져 있습니다.

- 파일 업로드 자동 공유 템플릿 3종은 Spring `TemplateSeeder`에 반영되어 있습니다.
- 메일 목록 요약 템플릿은 `EMAIL_LIST` 기반 일괄 요약 흐름으로 반영되어 있습니다.
- Gmail `maxResults`, LLM `EMAIL_LIST` 포맷, Notion `title_template`, `SPREADSHEET_DATA` 지원은 FastAPI에 유지되어 있습니다.
- Spring source/sink target option API와 프론트 picker API 계약은 현재 형태로 맞습니다.
- Slack, Notion, Google Drive folder picker는 프론트에서 백엔드 API를 재사용하는 구조로 구현되어 있습니다.

다만 실제 사용자 흐름에서 아래 4개 지점은 아직 계약이 완전히 맞지 않거나, 문서상 완료 내용과 실제 코드가 어긋납니다.

## 2. 수정 요청 요약

| 우선순위 | 대상 | 요청 |
| --- | --- | --- |
| P0 | Spring | 노드 설정 완료 판정에서 빈 문자열 placeholder를 설정 완료로 보지 않도록 보강 |
| P1 | FastAPI | Google Drive `single_file` payload에도 `created_time`, `modified_time` 포함 |
| P1 | Spring | Google Sheets가 Google Drive OAuth 토큰을 공유한다면 연결 상태 API와 scope 검증에도 alias 정책 반영 |
| P2 | Spring | catalog의 picker 타입과 실제 target option provider 지원 범위 정합성 정리 |

## 3. 요청 1. 노드 설정 완료 판정 보강

### 문제 상황

Spring `NodeLifecycleService`는 현재 required config를 값이 아니라 key 존재 여부 중심으로 판단합니다.

현재 코드 기준:

- start node는 `config.source_mode`, `config.target` key가 있으면 설정된 것으로 볼 수 있습니다.
- end node는 sink catalog의 required field key가 있으면 설정된 것으로 볼 수 있습니다.
- 값이 `""`인 경우도 configured/executable로 판정될 수 있습니다.

이 때문에 템플릿 placeholder 값이 들어간 노드가 실제로는 미설정 상태여도 백엔드 status에서 `configured=true`, `executable=true`로 내려올 수 있습니다.

예시:

```json
{
  "source_mode": "folder_new_file",
  "target": "",
  "target_label": "",
  "isConfigured": false
}
```

```json
{
  "service": "google_sheets",
  "spreadsheet_id": "",
  "write_mode": "append",
  "sheet_name": "Sheet1",
  "isConfigured": false
}
```

프론트는 `config.isConfigured=false`를 저장하고 있지만, `BaseNode` 렌더링에서는 백엔드 `nodeStatus.configured`가 우선될 수 있습니다. 따라서 백엔드가 빈 placeholder를 완료로 판단하면 UI에서도 노드가 설정 완료처럼 보일 위험이 있습니다.

### 요청 사항

Spring `NodeLifecycleService`의 설정 완료 판정을 값 기반으로 보강해 주세요.

1. start node
   - `type`은 non-blank이어야 합니다.
   - `config.source_mode`는 non-blank이어야 합니다.
   - `outputDataType`은 non-blank이어야 합니다.
   - `target`은 source mode의 `target_schema`가 비어 있지 않은 경우에만 필수로 봅니다.
   - `target_schema`가 필요한 mode라면 `config.target`은 non-blank이어야 합니다.
   - `target_schema`가 `{}`인 mode는 `target`이 없어도 설정 가능해야 합니다.
   - 구현 편의를 위해 `CatalogService`에 `findSourceMode(serviceKey, sourceModeKey)` 또는 `isSourceTargetRequired(serviceKey, sourceModeKey)` 같은 helper를 추가하는 방향을 권장합니다.
   - 현재 `CatalogService.getSinkRequiredFields()`는 sink required field만 제공하므로, source mode의 target 필수 여부를 판단하는 helper가 별도로 필요합니다.

2. end node
   - sink catalog에서 `required: true`인 field는 key 존재만으로 통과시키지 말고 의미 있는 값이 있어야 합니다.
   - 문자열은 `trim()` 후 빈 값이면 missing 처리합니다.
   - 배열, 객체는 비어 있으면 missing 처리합니다.
   - 숫자/boolean은 field 성격에 맞게 허용하되, null은 missing 처리합니다.

3. `config.isConfigured`
   - 서버는 최종적으로 값 기반 검증을 수행해야 합니다.
   - 단, 프론트가 명시적으로 `isConfigured=false`를 보낸 경우에는 configured를 true로 뒤집지 않는 방향을 권장합니다.
   - 오래된 데이터처럼 `isConfigured`가 없는 경우에는 값 기반으로만 계산하면 됩니다.

4. `missingFields`
   - 기존 형식처럼 `config.target`, `config.folder_id`, `config.spreadsheet_id` 형태로 내려주면 됩니다.
   - 프론트는 이미 missing field를 사람이 읽을 수 있는 문구로 표시하는 구조를 가지고 있습니다.

### 검증 요청

아래 케이스에 대한 단위 테스트를 추가해 주세요.

- Google Drive start node `source_mode=folder_new_file`, `target=""` -> configured false
- Google Drive start node `source_mode=single_file`, `target=""` -> configured false
- Gmail start node `source_mode=new_email`, `target` 없음 -> target schema가 비어 있으므로 target 때문에 실패하지 않음
- Slack sink `channel=""` -> configured false
- Gmail sink `to=""` 또는 `subject=""` -> configured false
- Notion sink `target_id=""` -> configured false
- Google Drive sink `folder_id=""` -> configured false
- Google Sheets sink `spreadsheet_id=""` -> configured false

## 4. 요청 2. Google Drive `single_file` metadata 정합성 보강

### 문제 상황

`PR5_MERGE_REPORT.md`에는 Google Drive `SINGLE_FILE`에 `file_id`, `created_time`, `modified_time`이 포함된 것으로 설명되어 있습니다.

실제 FastAPI 코드를 보면 `folder_new_file`, `new_file`, `file_changed`, `folder_all_files` 경로에는 생성/수정 시간이 포함되지만, 직접 파일을 선택하는 `single_file` 경로에는 포함되지 않습니다.

현재 `single_file` payload:

```json
{
  "type": "SINGLE_FILE",
  "file_id": "file_123",
  "filename": "example.pdf",
  "content": "...",
  "mime_type": "application/pdf",
  "url": "https://drive.google.com/file/d/file_123"
}
```

프론트 입출력 패널과 LLM context는 같은 canonical type이면 가능한 한 같은 metadata를 기대합니다. 선택 경로에 따라 같은 `SINGLE_FILE`의 metadata shape가 달라지면 UI 분기와 테스트가 불필요하게 복잡해집니다.

### 요청 사항

FastAPI Google Drive `single_file` 경로에도 아래 field를 포함해 주세요.

```json
{
  "created_time": "2026-05-04T12:00:00Z",
  "modified_time": "2026-05-04T12:10:00Z"
}
```

구현 방향:

1. `GoogleDriveService.download_file()` metadata 조회 fields에 `createdTime`, `modifiedTime` 추가
2. `download_file()` 반환값에 `createdTime`, `modifiedTime` 포함
3. `InputNodeStrategy._fetch_google_drive()`의 `mode == "single_file"` 반환 payload에 추가
   - `created_time: file_data.get("createdTime", "")`
   - `modified_time: file_data.get("modifiedTime", "")`
4. 기존 `folder_new_file` 등 list 기반 경로는 현재 구현 유지

### 검증 요청

- `tests/test_input_node.py::test_google_drive_single_file`에 `created_time`, `modified_time` assertion 추가
- `tests/test_llm_node.py::test_extract_text_from_single_file_includes_metadata`가 direct `single_file` payload 기준으로도 통과하는지 확인

## 5. 요청 3. Google Sheets OAuth alias 연결 상태 반영

### 문제 상황

Spring `OAuthTokenService`에는 아래 alias가 있습니다.

```java
private static final Map<String, String> TOKEN_SERVICE_ALIASES = Map.of(
        "google_sheets", "google_drive"
);
```

따라서 실행 시 `getDecryptedToken(userId, "google_sheets")`는 `google_drive` 토큰을 찾아 사용할 수 있습니다.

하지만 `/api/oauth-tokens`의 `getConnectedServices()`는 DB에 저장된 실제 token service만 반환합니다. 사용자가 Google Drive만 연결한 경우 응답에는 `google_drive`만 있고 `google_sheets`는 없을 가능성이 큽니다.

프론트는 이 응답을 기준으로 서비스 연결 여부를 판단합니다.

- `connectedServiceKeys.has(service.key)`
- service key가 `google_sheets`인 노드는 `google_sheets`가 응답에 없으면 미연결로 보일 수 있습니다.

즉 실행 backend는 Google Sheets를 Google Drive 토큰으로 실행할 수 있는데, 프론트는 Google Sheets가 연결되지 않았다고 판단할 수 있습니다.

### 요청 사항

백엔드 정책을 명확히 정하고 API 응답에 반영해 주세요.

권장 방향:

1. Google Sheets가 Google Drive OAuth 토큰을 공유하는 정책이라면 `/api/oauth-tokens` 응답에도 alias service를 포함합니다.
2. 사용자가 `google_drive`를 연결했고 scope에 `https://www.googleapis.com/auth/spreadsheets`가 포함되어 있으면 아래처럼 `google_sheets`도 connected로 반환합니다.

예시:

```json
[
  {
    "service": "google_drive",
    "connected": true,
    "expiresAt": "2026-05-05T10:00:00Z"
  },
  {
    "service": "google_sheets",
    "connected": true,
    "expiresAt": "2026-05-05T10:00:00Z",
    "aliasOf": "google_drive",
    "disconnectable": false
  }
]
```

3. scope가 부족하면 `google_sheets`를 connected로 반환하지 않거나, `connected=false`, `reason=OAUTH_SCOPE_INSUFFICIENT`처럼 명확히 표현해 주세요.
4. 실행 경로에서도 같은 scope 정책을 적용해 주세요.
   - 현재 `getDecryptedToken(userId, "google_sheets")`는 alias를 통해 `google_drive` 토큰을 찾아올 수 있습니다.
   - 하지만 Google Drive token에 spreadsheets scope가 없으면 Google Sheets 실행은 실패해야 합니다.
   - 따라서 `getDecryptedToken(userId, "google_sheets")` 또는 별도 token 조회 helper에서 `https://www.googleapis.com/auth/spreadsheets` scope를 검증하고, 부족하면 `OAUTH_SCOPE_INSUFFICIENT` 계열 오류를 반환하는 방향을 요청합니다.
5. alias 항목의 연결 해제 정책을 명확히 해 주세요.
   - 권장안은 alias service인 `google_sheets` 응답에 `disconnectable=false`를 포함하는 것입니다.
   - 프론트는 이 값을 기준으로 alias service의 직접 연결 해제 버튼을 숨길 수 있습니다.
   - 대안으로 `DELETE /oauth-tokens/google_sheets`를 원본 `google_drive` 삭제로 처리할 수도 있지만, 이 경우 사용자가 Google Sheets만 끊는다고 생각했는데 Drive까지 끊기는 UX가 될 수 있어 권장하지 않습니다.

대안 방향:

- alias를 프론트에서만 처리하게 할 수도 있습니다.
- 다만 실행 backend가 alias 정책을 이미 가지고 있으므로, 연결 상태 API도 같은 정책을 갖는 편이 사용자 경험과 디버깅에 더 안전합니다.

### 검증 요청

- Google Drive token만 저장되어 있고 spreadsheets scope가 있을 때 `/api/oauth-tokens`에 `google_sheets` 연결 상태가 노출되는지 테스트
- spreadsheets scope가 없을 때 Google Sheets 연결 상태가 잘못 connected로 표시되지 않는지 테스트
- spreadsheets scope가 없을 때 `getDecryptedToken(userId, "google_sheets")` 또는 Google Sheets 실행 token 조회 경로가 scope 부족 오류를 반환하는지 테스트
- `google_sheets` alias 응답에 `aliasOf`, `disconnectable` 정책이 일관되게 내려오는지 테스트
- `getDecryptedToken(userId, "google_sheets")` 기존 alias 조회 동작 유지 확인

## 6. 요청 4. catalog picker 타입과 provider 지원 범위 정리

### 문제 상황

Spring catalog에는 다양한 picker 타입이 이미 노출되어 있습니다.

source catalog:

- `file_picker`
- `folder_picker`
- `email_picker`
- `label_picker`
- `sheet_picker`
- `course_picker`
- `term_picker`
- `channel_picker`
- `page_picker`

sink catalog:

- `channel_picker`
- `page_picker`
- `folder_picker`
- `sheet_picker`
- `calendar_picker`

현재 구현된 provider와 프론트 연결 범위는 그보다 좁습니다.

현재 확인된 실사용 가능 범위:

- source: Canvas course/term, Google Drive file/folder
- sink: Slack channel, Notion page, Google Drive folder

아직 provider 또는 프론트 연결이 부족한 타입:

- Gmail `email_picker`, `label_picker`
- Google Sheets `sheet_picker`
- Google Calendar `calendar_picker`
- 일부 source side `channel_picker`, `page_picker`

이 상태 자체가 당장 오류는 아닙니다. 또한 이번 P0/P1 수정의 필수 범위는 아닙니다. 다만 catalog가 picker 타입을 노출하면 프론트는 장기적으로 “선택형 입력 가능”으로 해석하게 됩니다. provider가 없는 상태에서 picker 타입만 먼저 노출되면 사용자는 선택 UI 대신 수동 입력이나 에러를 마주하게 됩니다.

### 요청 사항

아래 중 하나로 정책을 정리해 주세요.

1. provider를 단계적으로 구현
   - Gmail label list provider
   - Google Sheets spreadsheet list provider
   - Google Calendar calendar list provider
   - 필요 시 Slack/Notion source target provider

2. 아직 provider가 없는 picker는 catalog type을 임시로 text 계열로 변경
   - 예: `sheet_picker` -> `text_input`
   - 예: `calendar_picker` -> `text_input`
   - provider 구현 후 다시 picker 타입으로 승격

3. catalog에 `picker_supported: false` 또는 `rollout` 같은 명시적 metadata를 추가
   - 프론트가 동일한 catalog를 보더라도 fallback UI를 의도적으로 선택할 수 있습니다.

권장 방향은 1번과 3번의 조합입니다. 장기적으로 선택형 UX를 유지하되, provider가 없는 타입은 프론트가 명시적으로 fallback할 수 있어야 합니다.

## 7. 프론트 영향

위 요청 중 프론트 수정이 바로 필요한 항목은 제한적입니다.

- 요청 1이 반영되면 프론트는 기존 `nodeStatus` 표시를 그대로 사용할 수 있습니다.
- 요청 2가 반영되면 입출력 데이터 패널에서 `SINGLE_FILE` metadata 렌더링이 더 일관됩니다.
- 요청 3이 반영되면 프론트의 `connectedServiceKeys` 로직을 크게 바꾸지 않아도 Google Sheets 연결 상태가 자연스럽게 맞습니다.
- alias 응답에 `disconnectable=false`가 포함되면 프론트는 Google Sheets 직접 연결 해제 버튼을 숨기고, Google Drive 연결 해제만 실제 token 삭제로 처리할 수 있습니다.
- 요청 4는 백엔드 catalog/provider rollout 정책에 맞춰 프론트 picker 지원 범위를 확장하면 됩니다.

프론트에서 별도로 주의할 부분:

- Google Sheets alias를 백엔드가 응답하지 않는다면 프론트에서 `google_sheets -> google_drive` alias mapping을 추가해야 합니다.
- picker provider가 없는 타입은 현재처럼 수동 입력 fallback이 필요합니다.

## 8. 최종 요청 우선순위

1. P0: Spring `NodeLifecycleService` 값 기반 required validation
   - 사용자에게 “미설정 노드가 완료처럼 보이는 문제”와 실행 실패를 직접 유발할 수 있습니다.

2. P1: FastAPI Google Drive `single_file` metadata 보강
   - PR5 병합 보고서와 실제 구현의 불일치입니다.
   - canonical payload 일관성을 위해 빠르게 맞추는 편이 좋습니다.

3. P1: Spring Google Sheets OAuth alias 연결 상태 반영
   - Google Sheets 템플릿과 실행 계약은 이미 들어와 있으므로 연결 상태 UX와 실행 scope 검증이 같은 정책으로 맞아야 합니다.

4. P2: picker catalog/provider 지원 범위 정리
   - 당장 blocking은 아니지만 선택형 설정 UX 확장을 위해 추적이 필요합니다.

## 9. 완료 기준

백엔드 완료 판단 기준은 아래와 같습니다.

- 빈 placeholder 값을 가진 템플릿 노드는 `configured=false`, `executable=false`로 내려온다.
- Google Drive `single_file` 실행 결과에도 `created_time`, `modified_time`이 포함된다.
- Google Drive OAuth 연결 후 spreadsheets scope가 있으면 Google Sheets 연결 상태가 프론트에서 확인 가능하다.
- Google Drive OAuth 연결 후 spreadsheets scope가 없으면 Google Sheets 연결 상태 또는 실행 token 조회가 scope 부족으로 명확히 실패한다.
- Google Sheets alias 응답은 직접 연결 해제 가능 여부를 명확히 표현한다.
- catalog에 노출된 picker 타입과 실제 target option provider 지원 범위가 문서 또는 metadata로 명확히 구분된다.
- Spring/FastAPI 관련 단위 테스트가 추가되고 통과한다.
