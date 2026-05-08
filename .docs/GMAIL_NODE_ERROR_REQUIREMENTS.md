# Gmail 노드 오류 확인 및 수정 요구사항

> 작성일: 2026-05-08
> 브랜치: `9-gmail-node-error-fix`
> 관련 이슈: Gmail 노드 오류 수정
> 목적: Gmail 노드에서 발생 중인 오류를 확인하고 수정하기 위해 필요한 요구사항, 확인 범위, FE/BE 계약, 완료 기준을 정리한다.

---

## 1. 배경

현재 Flowify FE는 Gmail을 source와 sink 양쪽에서 사용할 수 있는 서비스로 노출하고 있다.

- source: Gmail 메일을 가져오는 시작 노드
- sink: Gmail로 메일을 보내거나 초안을 만드는 도착 노드
- OAuth: Gmail 계정 연결

하지만 기존 문서와 현재 코드 사이에 지원 범위가 맞지 않는 부분이 있다. 특히 `docs/backend/BACKEND_INTEGRATION_CHECK_REPORT.md`는 Gmail connector를 미구현 상태로 기록하고 있고, 동시에 다른 문서에서는 Gmail sink 카탈로그와 Gmail API 발송 가능성을 언급한다.

이후 백엔드 최신 상태 확인 결과, 이번 이슈의 제품 요구는 Gmail을 임시로 닫는 것이 아니라 **Gmail source와 sink를 모두 유지하는 선택지 C**로 전환한다. Spring Boot 쪽 수정은 `label_emails` target-options와 OAuth scope 검증을 먼저 정렬하는 단계이며, FastAPI 쪽은 Gmail source 실행 payload, source preview schema, Gmail sink result canonical 계약 반영이 완료된 상태로 본다.

따라서 이번 이슈는 단순 UI 버그 수정이 아니라, 아래를 먼저 분명히 해야 한다.

1. Gmail source/sink/OAuth를 신규 노드 추가 흐름에서 유지하기 위해 FE가 어떤 보정을 해야 하는지
2. Spring Boot의 OAuth, scope, catalog, target picker 계약과 FE 저장 계약이 서로 같은 구조를 바라보는지
3. FastAPI runtime/source preview payload가 FE data preview와 downstream node에서 안정적으로 처리되는지
4. 아직 완료되지 않은 Spring/FE status, target-options, error mapping 영역은 어떤 완료 기준과 후속 검증으로 닫을지

---

## 2. 관련 문서에서 확인한 기준

### 2.1 Gmail source/sink 제품 기준

`docs/WORKFLOW_SOURCE_SINK_FLOW_DESIGN.md` 기준으로 Gmail은 다음 역할을 가진다.

Gmail source mode:

| mode 의미 | canonical type |
| --- | --- |
| 특정 메일 사용 | `SINGLE_EMAIL` |
| 새 메일 도착 | `SINGLE_EMAIL` |
| 특정 보낸 사람의 메일 도착 | `SINGLE_EMAIL` |
| 별표/중요 메일 사용 | `SINGLE_EMAIL` |
| 라벨 메일 목록 사용 | `EMAIL_LIST` |
| 첨부파일 있는 메일 | `FILE_LIST` |

Gmail sink 역할:

| sink service | 기본 역할 | 마지막 단계 설정 |
| --- | --- | --- |
| `Gmail` | 이메일 발송/초안 저장 | 수신자, 제목, 본문 포맷 |

### 2.2 백엔드 OAuth 지원 현황 문서

`docs/backend/BACKEND_INTEGRATION_CHECK_REPORT.md` 기준:

- `gmail` connector는 미구현으로 기록되어 있다.
- FE에서 Gmail OAuth 연결을 시도하면 `지원하지 않는 서비스: gmail` 오류가 발생할 수 있다고 되어 있다.
- Gmail 소스 노드는 테스트 불가/보류 시나리오로 분류되어 있다.

### 2.3 Gmail sink 가능성 문서

`docs/backend/LMS_TO_DRIVE_AUTOMATION_ANALYSIS.md` 기준:

- Gmail sink는 카탈로그에 정의되어 있다고 언급된다.
- `to`, `subject`, `body_format(html)`, `action(send)` 설정을 지원한다고 되어 있다.
- 단, Gmail sink 사용 시 Google OAuth에 `https://www.googleapis.com/auth/gmail.send` scope가 필요하다고 되어 있다.

이 문서는 Gmail sink의 가능성을 말하지만, OAuth connector가 실제로 준비되었는지는 별도 확인이 필요하다.

### 2.4 Gmail preview 관련 기준

`docs/WORKFLOW_NODE_PREVIEW_DRY_RUN_DESIGN.md` 기준:

- 실행 후 데이터 UI는 `EMAIL_LIST`, `SINGLE_EMAIL` 타입을 사용자 친화적으로 표시해야 한다.
- source metadata preview 범위에는 Gmail source preview가 포함되어 있다.
- 시작 노드에서 Gmail label의 예상 입력 목록이 보이는 것을 목표로 한다.
- Gmail sink preview는 실제 발송 없이 수신자, 제목, 본문, 첨부를 보여주는 no-write preview가 목표다.

이번 이슈에서 preview 전체를 구현할 필요는 없지만, Gmail 오류가 preview/source picker와 연결되어 있다면 계약 확인 범위에 포함해야 한다.

### 2.5 source target picker 기준

`docs/WORKFLOW_SOURCE_TARGET_PICKER_FRONTEND_DESIGN.md`와 `docs/WORKFLOW_SOURCE_TARGET_PICKER_UX_CONSOLIDATION_DESIGN.md` 기준:

- source target option API는 아래 형태다.

```http
GET /api/editor-catalog/sources/{serviceKey}/target-options
```

- 선택값 저장 계약은 다음 형태다.

```json
{
  "target": "resource-id",
  "target_label": "사용자에게 보여줄 이름",
  "target_meta": {}
}
```

- 기존 후속 이슈 목록에는 Gmail picker 확장이 별도 항목으로 남아 있다.

---

## 3. 현재 FE 코드 상태

### 3.1 Gmail OAuth 연결 가능 처리

`src/entities/oauth-token/model/oauth-connect-support.ts`

```ts
export const OAUTH_CONNECT_SUPPORTED_SERVICES = [
  "slack",
  "gmail",
  "google_drive",
  "notion",
  "github",
  "canvas_lms",
] as const;
```

현재 FE는 Gmail을 OAuth 연결 가능한 서비스로 판단한다.

요구사항:

- 선택지 C에서는 Gmail을 OAuth 연결 가능 서비스로 유지한다.
- `/api/oauth-tokens/gmail/connect` 연결 시작, callback, token 저장이 정상 동작해야 한다.
- Gmail source/sink 기능별 scope 부족 상태가 `oauth_scope_insufficient` 또는 동등한 표준 상태로 표현되어야 한다.
- Gmail OAuth connector가 일시적으로 실패하더라도 FE가 raw backend error를 그대로 노출하면 안 된다.

### 3.2 Gmail source 노출

`src/features/add-node/model/source-rollout.ts`

```ts
gmail: [
  "single_email",
  "new_email",
  "sender_email",
  "starred_email",
  "label_emails",
  "attachment_email",
],
```

현재 FE는 Gmail source mode를 모두 노출한다.

요구사항:

- 선택지 C에서는 Gmail source rollout을 유지한다.
- Spring catalog 기준 6개 mode만 FE allowlist에 둔다.
- 각 mode의 target schema, output type, OAuth scope, 실행 가능 여부가 Spring/FastAPI 계약과 일치해야 한다.

### 3.3 Gmail sink 노출

`src/features/add-node/model/sink-rollout.ts`

```ts
const SINK_SERVICE_ROLLOUT_ALLOWLIST = [
  "slack",
  "gmail",
  "notion",
  "google_drive",
  "google_sheets",
  "google_calendar",
] as const;
```

현재 FE는 Gmail sink를 노출한다.

요구사항:

- 선택지 C에서는 Gmail sink rollout을 유지한다.
- `gmail.send` scope 보유 여부와 부족 시 node status가 정확히 표시되어야 한다.
- sink schema의 required field와 FE 입력 UI가 일치해야 한다.

### 3.4 Gmail label picker 불일치

최초 노드 추가 위자드:

`src/features/add-node/model/source-target-picker.ts`

```ts
const REMOTE_TARGET_SCHEMA_TYPES = new Set([
  "course_picker",
  "term_picker",
  "file_picker",
  "folder_picker",
]);
```

기존 노드 재설정 패널:

`src/features/configure-node/model/source-target-schema.ts`

```ts
const REMOTE_SOURCE_TARGET_SCHEMA_TYPES = new Set([
  "calendar_picker",
  "channel_picker",
  "course_picker",
  "file_picker",
  "folder_picker",
  "label_picker",
  "page_picker",
  "sheet_picker",
  "term_picker",
]);
```

현재 최초 노드 추가 위자드는 `label_picker`를 remote picker로 처리하지 않지만, 재설정 패널은 처리한다.

요구사항:

- Gmail `label_emails`가 `label_picker`를 사용한다면 최초 추가 위자드도 `label_picker`를 remote picker로 처리해야 한다.
- `SourceTargetPicker`는 option type `label`에 적절한 아이콘과 라벨을 표시해야 한다.
- 선택 시 `target`, `target_label`, `target_meta`가 저장되어야 한다.
- Google Drive 전용 문구인 `내 드라이브`가 Gmail label picker에 부적절하게 보이지 않아야 한다.

---

## 4. 이번 이슈의 핵심 요구사항

### 4.1 지원 범위 확정 요구사항

이번 이슈에서 가장 먼저 결정해야 하는 것은 Gmail 지원 범위다.

초기 검토에서는 아래 셋 중 하나를 선택지로 두었지만, 최신 요구사항 기준 최종 선택지는 C다.

### 폐기된 선택지 A: Gmail 전체 임시 비활성화

조건:

- 백엔드 Gmail OAuth connector가 없거나
- Gmail source/sink 실행이 아직 보장되지 않거나
- 이번 이슈 범위가 FE 방어 수정에 한정될 때

요구사항:

- Gmail source 노출 제거
- Gmail sink 노출 제거
- Gmail OAuth 연결 가능 목록에서 제거
- 템플릿/시나리오에서 Gmail 필요 서비스가 있더라도 노드 추가 UI에서는 진입하지 않도록 처리
- 사용자가 `지원하지 않는 서비스: gmail` 오류를 직접 보지 않게 해야 한다.

### 폐기된 선택지 B: Gmail sink만 유지

조건:

- Gmail 발송/초안 기능은 백엔드와 FastAPI에서 동작하지만
- Gmail source는 아직 미구현 또는 불안정할 때

요구사항:

- Gmail source rollout 제거
- Gmail sink rollout 유지
- Gmail OAuth connect 지원 확인
- `gmail.send` scope 확인
- scope 부족 시 `oauth_scope_insufficient`가 사용자 문구 `권한 부족`으로 표시되어야 한다.
- sink 설정 패널에서 required field를 저장하면 `isConfigured=true`가 되어야 한다.

### 선택지 C: Gmail source와 sink 모두 유지

조건:

- Gmail OAuth connector가 있고
- source target options와 실행이 준비되어 있고
- sink 발송 scope도 준비되어 있을 때

요구사항:

- Gmail OAuth 연결이 성공해야 한다.
- Gmail source mode별 target schema가 FE와 일치해야 한다.
- `label_emails`는 label picker로 선택 가능해야 한다.
- Gmail source preview 또는 실행 후 data panel에서 `EMAIL_LIST`, `SINGLE_EMAIL`, `FILE_LIST`가 올바르게 표시되어야 한다.
- Gmail sink schema와 node lifecycle이 정상 동작해야 한다.

이번 이슈의 확정 선택지는 **선택지 C: Gmail source와 sink 모두 유지**다.

선택지 C로 전환하는 이유:

- Gmail 노드에서 다른 사용자에게 메일을 발송하는 기능이 필수 요구사항이다.
- 특정 발송인 기준 메일 필터링은 Gmail source `sender_email` mode와 직접 연결된다.
- `label_emails` target-options와 OAuth scope 검증은 Spring Boot에서 우선 정렬 중이다.
- FastAPI는 Gmail source runtime payload와 preview schema를 canonical 계약에 맞춰 정렬해야 하며, Spring은 FastAPI error code를 Spring API error shape로 변환해야 한다.

따라서 FE는 Gmail을 다시 닫는 방식이 아니라, Gmail source/sink/OAuth를 열어두되 `label_picker`, schema 저장, status/error 표시, data preview 호환성을 보정하는 방향으로 진행한다.

단, 선택지 C의 완료는 한 번에 끝났다고 보지 않는다. FastAPI는 source 실행 payload와 source preview schema를 canonical 계약으로 맞춘 상태이며, Spring Boot는 target-options와 scope 검증, FastAPI error 변환을 맞춘 뒤 FE 수동 검증으로 최종 완료를 판단한다.

---

## 5. 확인해야 할 백엔드/API 계약

### 5.1 OAuth connector 계약

확인 endpoint:

```http
POST /api/oauth-tokens/gmail/connect
GET /api/oauth-tokens
DELETE /api/oauth-tokens/gmail
```

확인 항목:

- `gmail` service key로 connector가 매칭되는가
- 응답이 redirect 방식인지 direct connect 방식인지
- callback 후 token이 `service: "gmail"`로 저장되는가
- Gmail source/sink에 필요한 scope가 저장/검증되는가
- 미지원 상태라면 FE가 연결 버튼을 보여주면 안 된다.

### 5.2 source catalog 계약

확인 endpoint:

```http
GET /api/editor-catalog/sources
```

확인 항목:

- Gmail service가 내려오는가
- `auth_required` 값은 무엇인가
- source mode key가 FE allowlist와 일치하는가
- 각 mode의 `canonical_input_type`이 FE data type 변환과 일치하는가
- 각 mode의 `target_schema.type`이 무엇인가

특히 확인할 mode:

- `single_email`
- `new_email`
- `sender_email`
- `starred_email`
- `label_emails`
- `attachment_email`

### 5.3 Gmail target options 계약

확인 endpoint:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=label_emails
```

필요 시 mode별 확인:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=single_email
GET /api/editor-catalog/sources/gmail/target-options?mode=starred_email
```

확인 항목:

- endpoint가 존재하는가
- 인증/권한 부족 시 표준 API error shape를 따르는가
- label option의 `type`은 `label`인가
- option item은 `{ id, label, description, type, metadata }` 형태인가
- pagination `nextCursor`가 정상 동작하는가
- FE가 저장해야 하는 값은 label id인지 query 문자열인지 명확한가

### 5.4 sink catalog/schema 계약

확인 endpoint:

```http
GET /api/editor-catalog/sinks
GET /api/editor-catalog/sinks/gmail/schema?inputType=TEXT
GET /api/editor-catalog/sinks/gmail/schema?inputType=EMAIL_LIST
GET /api/editor-catalog/sinks/gmail/schema?inputType=SINGLE_EMAIL
GET /api/editor-catalog/sinks/gmail/schema?inputType=FILE_LIST
```

확인 항목:

- Gmail sink가 어떤 input type을 받는가
- schema field key가 FE 상태 라벨과 일치하는가
- required field는 무엇인가
- `to`와 `recipient` 중 어떤 key가 authoritative인지
- `subject`, `body_format`, `action`, `message/body` field 계약이 무엇인지
- scope 부족 시 node status가 어떻게 내려오는가

### 5.5 node status 계약

확인 항목:

- Gmail 토큰 없음: `missingFields`에 `oauth_token`이 내려오는가
- Gmail scope 부족: `missingFields`에 `oauth_scope_insufficient`가 내려오는가
- 설정값 누락과 실행 조건 부족이 구분되는가
- `configured=true`, `executable=false` 상태가 UI에서 보이는가

현재 FE에는 다음 라벨이 존재한다.

- `oauth_token` -> `인증 연결`
- `oauth_scope_insufficient` -> `권한 부족`

---

## 6. FE 수정 요구사항

### 6.1 노출 제어

Gmail의 실제 지원 범위에 따라 FE allowlist를 조정해야 한다.

수정 후보:

- `src/features/add-node/model/source-rollout.ts`
- `src/features/add-node/model/sink-rollout.ts`
- `src/entities/oauth-token/model/oauth-connect-support.ts`

요구사항:

- 지원되지 않는 Gmail 기능은 노드 추가 UI에 노출하지 않는다.
- 연결할 수 없는 서비스에 “계정 인증하기” 버튼이 뜨지 않아야 한다.
- 문서와 코드의 지원 범위가 어긋나지 않아야 한다.

### 6.2 Gmail label picker

Gmail source를 유지한다면 `label_picker`를 최초 노드 추가 위자드에서도 지원해야 한다.

수정 후보:

- `src/features/add-node/model/source-target-picker.ts`
- `src/features/add-node/ui/SourceTargetPicker.tsx`

요구사항:

- `REMOTE_TARGET_SCHEMA_TYPES`에 `label_picker` 추가
- `TARGET_OPTION_ICON_MAP`에 `label` option type 추가
- Gmail picker의 root/search/empty 문구가 Drive 전용으로 보이지 않도록 정리
- 선택값은 `target`, `target_label`, `target_meta`로 저장
- 검색, pagination, retry가 기존 `RemoteOptionPicker` 패턴과 동일하게 동작

### 6.3 Gmail sink 설정

Gmail sink를 유지한다면 sink schema 기반 설정 저장이 안정적으로 동작해야 한다.

확인/수정 후보:

- `src/features/configure-node/ui/panels/SinkNodePanel.tsx`
- `src/features/configure-node/model/sink-node-draft.ts`
- `src/entities/workflow/lib/node-status.ts`

요구사항:

- 이메일 필드는 `email_input`이면 `<input type="email">`로 렌더링
- required field가 모두 채워지면 `isConfigured=true`
- number/select/text/email field validation이 schema와 일치
- missing field raw key가 UI에 그대로 노출되지 않음
- Gmail scope 부족은 `권한 부족`으로 표시

### 6.4 Data preview 표시

Gmail source 실행 결과 또는 preview 결과가 FE에 들어오면 타입별 UI가 정상 표시되어야 한다.

확인 후보:

- `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx`

요구사항:

- `EMAIL_LIST`: 메일 목록, 제목, 발신자, 날짜, 본문 일부 표시
- `SINGLE_EMAIL`: 제목, 발신자, 본문, 첨부 표시
- 빈 목록/누락 필드에도 UI가 깨지지 않아야 한다.

---

## 7. 에러 재현 요구사항

이번 이슈에서 최소한 아래 시나리오를 확인해야 한다.

### 7.1 Gmail OAuth 연결 오류

절차:

1. 로그인된 브라우저에서 시작 노드 추가
2. Gmail 선택
3. 인증 단계에서 연결 시작

기대 확인:

- 미지원이면 FE에서 진입 자체가 막혀야 한다.
- 지원이면 redirect 또는 direct connect가 정상 동작해야 한다.
- 오류가 난다면 API response와 화면 문구를 기록한다.

### 7.2 Gmail source 추가 오류

절차:

1. Gmail source mode 선택
2. target schema 확인
3. target 입력 또는 picker 선택
4. 시작 노드 생성
5. 저장된 config 확인

기대 확인:

- `service`, `source_mode`, `canonical_input_type`, `trigger_kind` 저장
- target이 필요한 mode는 `target` 저장
- remote option 기반 mode는 `target_label`, `target_meta` 저장
- source target/options 또는 runtime 오류가 있으면 node status/preflight/error UI에서 사용자 조치로 안내

### 7.3 Gmail label picker 오류

절차:

1. Gmail `label_emails` mode 선택
2. 라벨 선택 UI 확인
3. 라벨 선택 후 노드 생성

기대 확인:

- 텍스트 입력이 아니라 라벨 목록 picker가 떠야 한다.
- option type `label`이 깨지지 않아야 한다.
- Drive 전용 breadcrumb/root 문구가 노출되지 않아야 한다.

### 7.4 Gmail sink 설정 오류

절차:

1. Gmail sink 추가
2. sink schema 조회
3. required field 입력
4. 설정 저장
5. node status 확인

기대 확인:

- schema 조회 실패 시 사용자에게 이해 가능한 오류 표시
- 설정 완료 시 `isConfigured=true`
- OAuth 토큰 없음 또는 scope 부족 시 실행 조건 메시지 표시

### 7.5 Gmail 실행/preview 데이터 표시

절차:

1. Gmail source 또는 Gmail sink가 포함된 워크플로우 실행
2. 노드 데이터 패널 확인

기대 확인:

- `EMAIL_LIST`, `SINGLE_EMAIL`이 타입별 UI로 표시
- 발송/초안 생성 같은 write 작업 preview가 있다면 실제 write가 발생하지 않음

---

## 8. 완료 기준

이번 이슈의 완료 기준은 선택지 C, 즉 Gmail source/sink/OAuth를 모두 유지하는 방향을 기준으로 한다.

### 공통 완료 기준

- Gmail 관련 오류 원인이 문서화되어 있다.
- Gmail 지원 범위가 source/sink/OAuth 단위로 명확하다.
- FE 노출 범위와 백엔드 실제 지원 범위가 일치한다.
- 사용자가 Gmail 기능으로 진입했을 때 인증, 권한, target 선택, schema 저장, 실행 조건이 일관된 상태로 표시된다.
- 권한/인증 관련 raw key가 UI에 그대로 노출되지 않는다.
- 변경 후 수동 검증 절차가 문서에 남아 있다.

### Gmail source/sink 모두 유지 완료 기준

- Gmail OAuth 연결이 정상 동작한다.
- Gmail OAuth token의 source/sink 기능별 scope 부족이 사용자 문구로 표시된다.
- Gmail source mode별 target schema가 FE 최초 노드 추가 위자드와 기존 노드 설정 패널에서 동일하게 처리된다.
- `label_emails` mode의 `label_picker`가 remote picker로 동작하고 `target`, `target_label`, `target_meta` 저장 계약을 지킨다.
- Gmail sink schema 조회, 필수값 입력, 설정 저장, node status가 정상 동작한다.
- Gmail source 실행 또는 preview 결과가 `EMAIL_LIST`, `SINGLE_EMAIL`, `FILE_LIST`로 표시된다.
- Gmail sink send 결과가 성공/실패 상태와 함께 사용자에게 이해 가능한 형태로 표시된다.
- Gmail required template은 더 이상 “준비 중”으로 막지 않고, OAuth/scope/status 흐름으로 진입한다.

### 백엔드 단계별 완료 기준

Spring Boot 완료 기준:

- Gmail OAuth connector가 `gmail` service key로 동작한다.
- Gmail source/sink 기능별 required scope가 정리되어 node lifecycle/status에 반영된다.
- `label_emails` target-options가 Gmail label id/name/meta를 반환한다.
- scope 부족, token 없음, target-options 실패가 표준 API error shape로 내려온다.
- Gmail source runtime payload와 source preview schema는 FastAPI 계약 반영이 완료되었고, Spring/FE는 error mapping과 status/preflight 표시를 이어서 맞춘다.

FastAPI 완료 기준:

- Spring source catalog의 Gmail mode key와 동일한 mode만 runtime에서 처리한다.
- `SINGLE_EMAIL`, `EMAIL_LIST`, `FILE_LIST`, `SEND_RESULT` canonical payload가 문서와 일치한다.
- Gmail source preview가 runtime source와 같은 payload schema를 사용한다.
- OAuth/scope/external API/runtime unsupported 오류가 구분 가능한 error code로 내려온다.
- keyword search mode는 이번 범위에서 FE가 임의 추가하지 않고, 별도 catalog 확장 또는 중간 filter 노드 조합으로 처리한다.

현재 반영 상태:

- FastAPI payload/schema 정렬은 반영 완료로 본다.
- 선택지 C에서는 Gmail을 숨기지 않기 때문에, Spring Boot의 `FastApiClient`는 FastAPI error body를 파싱해 Spring API error shape로 변환해야 한다.
- 이번 PR은 “선택지 C 서버 계약 완성” 범위로 보고 FastAPI error mapping 구현과 테스트까지 포함한다.
- FastAPI error mapping은 `OAUTH_SCOPE_INSUFFICIENT`, token invalid/missing, external API/rate limit, unsupported runtime 계열을 구분한다.

---

## 9. 이번 PR에서 권장하는 작업 순서

1. 요구사항과 설계 문서를 선택지 C 기준으로 갱신한다.
2. Gmail source/sink/OAuth allowlist를 선택지 C 기준으로 복구한다.
3. 최초 노드 추가 위자드에서 `label_picker`를 remote picker로 처리한다.
4. Gmail picker의 label icon/문구/empty state가 Drive 전용 표현을 쓰지 않도록 보정한다.
5. Gmail sink schema 저장과 node status 표시가 기존 패널에서 정상 동작하는지 확인한다.
6. Gmail required template의 “준비 중” 차단을 제거하고 OAuth/status 흐름으로 진입하게 한다.
7. `EMAIL_LIST`, `SINGLE_EMAIL`, `FILE_LIST`, `SEND_RESULT` data preview 호환성을 확인한다.
8. Spring Boot/FastAPI 문서의 남은 서버 작업을 PR description에 명시한다.
9. 수동 검증 결과를 PR description 또는 후속 문서에 기록한다.

---

## 10. 후속 이슈 후보

- Gmail keyword search source mode를 Spring catalog/FastAPI runtime에 추가할지 결정
- Gmail source metadata preview 고도화
- Gmail sink no-write preview 구현
- Gmail draft action 노출 여부 결정
- Gmail fetch 개수 설정화
- Gmail attachment content download/전달 계약 확정
- Gmail template 목록에서 OAuth/scope 필요 상태를 배지로 표시할지 결정
