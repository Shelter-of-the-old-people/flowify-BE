# Gmail 노드 오류 확인 및 수정 요구사항

> 작성일: 2026-05-08  
> 브랜치: `feat#145-gmail-error-check-and-fix&update`  
> 관련 이슈: Gmail 노드 오류 수정  
> 목적: Gmail 노드에서 발생 중인 오류를 확인하고 수정하기 위해 필요한 요구사항, 확인 범위, FE/BE 계약, 완료 기준을 정리한다.

---

## 1. 배경

현재 Flowify FE는 Gmail을 source와 sink 양쪽에서 사용할 수 있는 서비스로 노출하고 있다.

- source: Gmail 메일을 가져오는 시작 노드
- sink: Gmail로 메일을 보내거나 초안을 만드는 도착 노드
- OAuth: Gmail 계정 연결

하지만 기존 문서와 현재 코드 사이에 지원 범위가 맞지 않는 부분이 있다. 특히 `docs/backend/BACKEND_INTEGRATION_CHECK_REPORT.md`는 Gmail connector를 미구현 상태로 기록하고 있고, 동시에 다른 문서에서는 Gmail sink 카탈로그와 Gmail API 발송 가능성을 언급한다.

따라서 이번 이슈는 단순 UI 버그 수정이 아니라, 아래를 먼저 분명히 해야 한다.

1. Gmail이 현재 실제 지원 대상인지
2. 지원 대상이라면 source와 sink 중 어느 범위까지 동작해야 하는지
3. OAuth connector, Google scope, catalog, target picker, node status가 서로 같은 계약을 바라보는지
4. 지원되지 않는 범위는 FE에서 숨기거나 “준비 중”으로 막아야 하는지

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

- 백엔드가 `/api/oauth-tokens/gmail/connect`를 지원하지 않는다면 Gmail은 연결 가능 서비스에서 제외되어야 한다.
- 백엔드가 지원한다면 연결 시작, callback, token 저장, scope 부족 상태가 정상 동작해야 한다.

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

- Gmail source가 실제 동작하지 않는다면 source rollout에서 닫아야 한다.
- 일부 mode만 동작한다면 mode 단위로 allowlist를 조정해야 한다.
- Gmail source를 유지한다면 각 mode의 target schema, output type, OAuth scope, 실행 가능 여부가 확인되어야 한다.

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

- Gmail sink가 실제로 동작하지 않는다면 sink rollout에서 닫아야 한다.
- Gmail sink가 동작한다면 `gmail.send` scope 보유 여부와 부족 시 node status가 정확히 표시되어야 한다.
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

아래 셋 중 하나로 명확히 정해야 한다.

### 선택지 A: Gmail 전체 임시 비활성화

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

### 선택지 B: Gmail sink만 유지

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

현재 문서 기준으로는 선택지 A가 가장 안전하지만, 백엔드가 최신 브랜치에서 Gmail connector를 이미 구현했을 수 있으므로 실제 API 확인 후 최종 결정한다.

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
- source 미지원이면 노드 생성 전 UI에서 차단

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

이번 이슈의 완료 기준은 선택한 지원 범위에 따라 달라진다.

### 공통 완료 기준

- Gmail 관련 오류 원인이 문서화되어 있다.
- Gmail 지원 범위가 source/sink/OAuth 단위로 명확하다.
- FE 노출 범위와 백엔드 실제 지원 범위가 일치한다.
- 사용자가 미지원 Gmail 기능으로 진입해 백엔드 예외를 직접 보지 않는다.
- 권한/인증 관련 raw key가 UI에 그대로 노출되지 않는다.
- 변경 후 수동 검증 절차가 문서에 남아 있다.

### Gmail 비활성화 선택 시 완료 기준

- Gmail source가 새 노드 추가 UI에서 보이지 않는다.
- Gmail sink가 새 노드 추가 UI에서 보이지 않는다.
- Gmail OAuth 연결 버튼이 노출되지 않는다.
- 기존 Gmail 템플릿/시나리오가 있다면 현재 미지원 상태를 별도 후속 이슈로 남긴다.

### Gmail sink만 유지 선택 시 완료 기준

- Gmail source는 노출되지 않는다.
- Gmail sink는 schema 조회와 설정 저장이 가능하다.
- Gmail OAuth 연결과 `gmail.send` scope가 확인된다.
- scope 부족 시 `권한 부족` 상태가 표시된다.

### Gmail source/sink 모두 유지 선택 시 완료 기준

- Gmail OAuth 연결이 정상 동작한다.
- Gmail source mode별 target schema가 FE에서 정상 처리된다.
- `label_emails` mode의 label picker가 정상 동작한다.
- Gmail sink 설정 저장과 node status가 정상 동작한다.
- Gmail 관련 data preview UI가 깨지지 않는다.

---

## 9. 이번 PR에서 권장하는 작업 순서

1. 로그인 세션에서 Gmail OAuth/API 실제 상태 확인
2. Gmail 지원 범위 결정
3. 결정된 범위에 맞춰 FE allowlist 수정
4. Gmail source 유지 시 `label_picker` 최초 생성 위자드 보정
5. Gmail sink 유지 시 schema/status 저장 흐름 확인
6. 수동 검증 결과를 PR description 또는 후속 문서에 기록

현재 문서만 기준으로는 Gmail 전체를 임시 비활성화하는 방어 수정이 가장 안전하다. 다만 최신 백엔드에서 Gmail connector가 구현되어 있다면, 실제 API 확인 결과에 따라 Gmail sink만 유지하거나 source/sink 모두 유지하는 방향으로 전환한다.

---

## 10. 후속 이슈 후보

- Gmail OAuth connector 및 Google Cloud scope 정리
- Gmail source target-options API 구현
- Gmail label/email picker UX 고도화
- Gmail source metadata preview 구현
- Gmail sink no-write preview 구현
- Gmail 템플릿의 실제 지원 범위와 설명 문구 정렬
- Gmail fetch 개수 설정화
- Gmail attachment payload와 `FILE_LIST` 변환 계약 확정
