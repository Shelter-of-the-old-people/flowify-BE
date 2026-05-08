# Gmail 노드 오류 수정 설계

> 작성일: 2026-05-08
> 브랜치: `9-gmail-node-error-fix`
> 관련 문서: `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`
> 관련 이슈: Gmail 노드 오류 수정
> 목적: Gmail 노드 오류의 원인 후보를 바탕으로 FE 수정 방향, API 확인 절차, 지원 범위별 구현 설계를 정리한다.

---

## 1. 설계 요약

이번 이슈의 핵심 문제는 두 가지다.

1. FE는 Gmail을 source/sink/OAuth 연결 가능 대상으로 노출하고 있지만, 기존 백엔드 점검 문서 기준으로 Gmail connector는 미구현 상태다.
2. Gmail `label_picker`가 최초 노드 추가 위자드에서는 remote picker로 처리되지 않아 라벨 선택 UX와 저장 계약이 어긋날 수 있다.

따라서 이번 설계는 아래 원칙을 따른다.

- Gmail source/sink/OAuth를 모두 유지하는 선택지 C를 구현 기준으로 둔다.
- Gmail을 열어두는 대신 source/sink/OAuth/picker/status/error 계약을 함께 맞춘다.
- `label_picker` 보정은 Gmail source 유지의 필수 구현으로 본다.
- Gmail source 실행 payload와 preview schema는 FastAPI 계약 반영 이후 완료로 보고, FastAPI error mapping은 Spring `FastApiClient` 변환 작업으로 이번 PR에 포함한다.
- 아직 서버 runtime이 완전히 닫히지 않은 영역은 FE에서 임의 mode를 추가하지 않고, 문서화된 mode와 canonical payload만 처리한다.

이번 변경의 확정안은 **선택지 C: Gmail source/sink 모두 유지**다. 기존 방어 설계는 Gmail 미지원 가능성을 기준으로 신규 진입을 닫는 방향이었지만, 지금 제품 요구는 Gmail 발송과 발송인/라벨 기반 메일 조회 기능을 반드시 제공하는 것이다.

이 판단의 근거는 다음과 같다.

- Spring Boot 수정은 FastAPI runtime 구현이 아니라 `label_emails` target-options, OAuth scope 검증, FastAPI error 변환을 정렬하는 단계다.
- FastAPI 문서는 Gmail source 6개 mode의 canonical payload와 Gmail sink send 결과 계약을 정렬하는 방향으로 업데이트되었다.
- Gmail 발송 기능은 `gmail.send` scope가 필요하다.
- 발송인 기반 필터링은 현재 Gmail source `sender_email` mode와 맞는다.
- 키워드 기반 필터링은 현재 catalog에 명시적 search mode가 없으므로 FE가 임의 mode를 만들지 않고 중간 filter 노드 또는 후속 catalog 확장으로 처리한다.

따라서 이번 PR의 설계 판단은 선택지 C로 전환한다. FE는 Gmail source/sink/OAuth allowlist를 복구하고, 최초 노드 추가 위자드의 `label_picker` 처리, Gmail picker UX, Gmail required template 차단 해제, source/sink status/error 표시를 함께 보정한다.

---

## 2. 목표

### 2.1 사용자 관점 목표

- 사용자가 아직 지원되지 않는 Gmail 노드를 추가하려다 백엔드 예외를 마주하지 않는다.
- Gmail이 노출되는 경우에는 인증, 대상 선택, 설정 저장, 실행 조건 표시가 일관되게 동작한다.
- Gmail 라벨을 선택해야 하는 흐름에서는 텍스트 입력 대신 목록 기반 선택 UI가 제공된다.
- Gmail 권한 부족이나 미연결 상태가 raw key가 아닌 사용자 친화적인 문구로 보인다.

### 2.2 개발 관점 목표

- Gmail 노출 정책을 source/sink/OAuth 연결 가능 여부와 일치시킨다.
- Gmail 관련 allowlist가 백엔드 실제 지원 범위와 어긋나지 않게 한다.
- 최초 노드 추가 위자드와 기존 노드 설정 패널의 source target picker 처리 기준을 맞춘다.
- Gmail 지원 범위가 바뀌어도 수정 지점이 명확하도록 한다.

---

## 3. 비목표

이번 FE 설계에서 바로 구현 대상으로 보지 않는 것:

- Gmail OAuth connector 백엔드 구현
- Google Cloud Console scope 설정 변경
- FastAPI Gmail source 실행 로직 구현
- FastAPI Gmail sink 발송/초안 생성 로직 구현
- FastAPI Gmail source preview executor 구현
- Gmail sink no-write preview 구현
- Gmail 템플릿 전체 UX 개편
- Gmail fetch 개수 설정화
- Gmail attachment payload 변환 계약 확정

위 항목은 FE 저장소 밖의 백엔드 작업 또는 후속 UX 고도화로 분리한다. 다만 FE는 해당 계약이 들어왔을 때 깨지지 않도록 canonical payload 표시와 error/status mapping을 확인한다.

---

## 4. 현재 문제 구조

### 4.1 Gmail OAuth 노출 문제

현재 FE는 Gmail을 OAuth 연결 가능한 서비스로 취급한다.

대상 파일:

- `src/entities/oauth-token/model/oauth-connect-support.ts`

현재 구조:

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

문제:

- 백엔드에 Gmail connector가 없다면 `/api/oauth-tokens/gmail/connect` 호출은 실패한다.
- 그럼에도 FE는 Gmail을 “연결 시작” 가능한 서비스로 보여준다.
- 사용자는 UI상 가능해 보이는 작업을 수행하다가 백엔드 예외를 만난다.

설계 방향:

- 선택지 C에서는 Gmail을 OAuth connect supported list에 포함한다.
- Gmail 미연결 상태에서는 “연결 시작”이 가능해야 한다.
- scope 부족은 미지원이 아니라 권한 부족 상태로 보여야 한다.
- Spring Boot가 기능별 scope 검증을 내려주면 FE는 `oauth_scope_insufficient`를 `권한 부족`으로 표시한다.
- OAuth connect API 자체가 실패하는 경우에는 raw error 대신 표준 에러/토스트/상태 문구로 처리한다.

### 4.2 Gmail source rollout 문제

대상 파일:

- `src/features/add-node/model/source-rollout.ts`

현재 구조:

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

문제:

- 백엔드 Gmail source 실행 또는 OAuth가 준비되지 않았는데 FE가 Gmail source mode를 모두 노출한다.
- `ServiceSelectionPanel`은 source catalog에서 내려온 Gmail service를 rollout allowlist 기준으로 표시한다.
- 결과적으로 사용자가 Gmail source 노드 생성 흐름에 진입할 수 있다.

설계 방향:

- Gmail source 미지원 상태라면 `SOURCE_SERVICE_ROLLOUT_ALLOWLIST`에서 Gmail entry를 제거한다.
- 일부 mode만 지원하는 경우에는 mode 단위 allowlist로 제한한다.
- source 전체 지원이 확인되기 전에는 `label_emails`를 포함한 Gmail source mode를 열지 않는다.

### 4.3 Gmail sink rollout 문제

대상 파일:

- `src/features/add-node/model/sink-rollout.ts`

현재 구조:

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

문제:

- 문서상 Gmail sink는 가능하다는 언급이 있지만 `gmail.send` scope와 connector가 필요하다.
- connector/scope가 준비되지 않았으면 Gmail sink도 실행 단계에서 실패할 수 있다.

설계 방향:

- Gmail sink 지원이 확인되지 않으면 sink rollout에서 Gmail을 제거한다.
- Gmail sink만 지원되는 것으로 확인되면 sink rollout에는 Gmail을 유지하고 source rollout에서만 제거한다.
- Gmail sink 유지 시 OAuth supported list도 Gmail을 포함해야 한다.

### 4.4 Gmail label picker 문제

최초 노드 추가 위자드 대상 파일:

- `src/features/add-node/model/source-target-picker.ts`
- `src/features/add-node/ui/SourceTargetPicker.tsx`

기존 노드 재설정 패널 대상 파일:

- `src/features/configure-node/model/source-target-schema.ts`
- `src/features/configure-node/ui/panels/SourceTargetForm.tsx`

문제:

- 기존 노드 재설정 패널은 `label_picker`를 remote picker로 처리한다.
- 최초 노드 추가 위자드는 `label_picker`를 remote picker로 처리하지 않는다.
- 같은 Gmail `label_emails` source라도 생성 시점과 재설정 시점의 UX가 달라진다.
- 최초 생성 시 텍스트 입력으로 저장하면 백엔드가 기대하는 label id와 다를 수 있다.

설계 방향:

- Gmail source를 유지하는 경우, 최초 노드 추가 위자드도 `label_picker`를 remote picker로 처리한다.
- `SourceTargetPicker`에 option type `label` 표시를 추가한다.
- Gmail picker에서 Drive 전용 root label인 `내 드라이브`가 보이지 않게 한다.
- 선택값 저장은 기존 remote picker 계약인 `target`, `target_label`, `target_meta`를 따른다.

---

## 5. 지원 범위 결정 설계

구현 전 API 확인 결과에 따라 아래 셋 중 하나를 선택한다.

이번 설계의 판단은 다음과 같이 보정한다.

| 선택지 | 이번 PR 기본 판단 | 이유 |
| --- | --- | --- |
| A. Gmail 전체 임시 비활성화 | 폐기 | 필수 Gmail 기능 요구와 맞지 않는다. |
| B. Gmail sink만 유지 | 폐기 | 메일 발송은 가능하지만 발송인/라벨 기반 source 요구를 충족하지 못한다. |
| C. Gmail source/sink 모두 유지 | 확정 | Gmail 발송, 라벨 메일 조회, 발송인 기준 필터링을 모두 지원하기 위한 기준안이다. |

즉, 이번 작업은 A/B로 축소하지 않고 C를 구현 기준으로 둔다.
API 확인이 불명확한 영역은 Gmail 진입을 닫는 방식이 아니라 Spring/FastAPI의 status, preflight, error mapping으로 사용자에게 명확히 보여주는 방향으로 처리한다.

### 5.1 폐기된 대안 A: Gmail 전체 임시 비활성화

초기 백엔드 점검 문서만 기준으로 검토했던 방어안이다. 현재 필수 Gmail 기능 요구와 맞지 않으므로 이번 구현 기준에서 제외한다.

적용 조건:

- `/api/oauth-tokens/gmail/connect`가 미지원이거나
- Gmail connector가 없거나
- Gmail source/sink 실행 가능 여부가 불명확하거나
- 이번 PR을 FE 방어 수정으로 제한할 때

FE 변경:

| 파일 | 변경 |
| --- | --- |
| `src/features/add-node/model/source-rollout.ts` | Gmail source entry 제거 |
| `src/features/add-node/model/sink-rollout.ts` | Gmail sink 제거 |
| `src/entities/oauth-token/model/oauth-connect-support.ts` | Gmail 제거 |

동작 결과:

- 새 시작 노드 서비스 목록에서 Gmail이 보이지 않는다.
- 새 도착 노드 서비스 목록에서 Gmail이 보이지 않는다.
- 새 Gmail OAuth 연결 버튼이 노출되지 않는다.
- 기존에 이미 존재하는 Gmail 노드는 삭제하지 않는다.

기존 Gmail 노드 처리:

- 기존 workflow/template에 Gmail 노드가 이미 있다면 FE가 노드를 임의 삭제하지 않는다.
- 백엔드 node status가 내려주는 `oauth_token`, `oauth_scope_insufficient`, config missing field를 표시한다.
- 기존 노드 패널에서 Gmail이 catalog에 남아 있다면 OAuth unsupported 상태가 사용자에게 보일 수 있다.
- 기존 Gmail 노드 실행 실패까지 FE가 해결하지는 않는다.

장점:

- 가장 작은 변경으로 사용자 오류 진입을 줄인다.
- 백엔드 지원 상태와 FE 노출 상태의 불일치를 즉시 줄인다.

주의:

- Gmail 템플릿이 있다면 템플릿 인스턴스화나 상세 진입에서 별도 미지원 처리가 필요할 수 있다.
- 선택지 A에서는 템플릿 상세의 인스턴스화 버튼 방어까지 포함한다.
- 템플릿 목록 표시 고도화는 후속 이슈로 분리한다.

### 5.2 폐기된 대안 B: Gmail sink만 유지

Gmail sink만 먼저 여는 절충안이다. 현재 요구사항에는 발송인/라벨 기반 Gmail source 기능이 포함되므로 이번 구현 기준에서 제외한다.

적용 조건:

- `/api/oauth-tokens/gmail/connect`가 지원된다.
- Gmail OAuth token에 `gmail.send` scope가 포함되거나 scope 부족을 감지할 수 있다.
- Gmail sink schema가 안정적으로 내려온다.
- Gmail source catalog/target-options/실행은 아직 준비되지 않았다.

FE 변경:

| 파일 | 변경 |
| --- | --- |
| `src/features/add-node/model/source-rollout.ts` | Gmail source entry 제거 |
| `src/features/add-node/model/sink-rollout.ts` | Gmail sink 유지 |
| `src/entities/oauth-token/model/oauth-connect-support.ts` | Gmail 유지 |
| `src/entities/workflow/lib/node-status.ts` | scope/missing field 라벨 확인 |
| `src/features/configure-node/ui/panels/SinkNodePanel.tsx` | schema 기반 입력 저장 확인 |

동작 결과:

- Gmail source는 새 노드 추가 UI에서 보이지 않는다.
- Gmail sink는 accepted input type이 맞을 때 도착 서비스로 보인다.
- Gmail sink 설정 패널에서 required field 입력 후 저장할 수 있다.
- OAuth 미연결/권한 부족은 node status로 표시한다.

추가 확인:

- Gmail sink schema field key가 FE 라벨과 맞는지 확인한다.
- `to`와 `recipient` 중 어떤 key가 authoritative인지 확인한다.
- `body_format`, `action`, `subject`의 required 여부를 확인한다.

### 5.3 선택지 C: Gmail source/sink 모두 유지

Gmail을 실제 지원 기능으로 확정할 때 선택한다.

적용 조건:

- `/api/oauth-tokens/gmail/connect`가 지원된다.
- Gmail source modes가 source catalog에 안정적으로 존재한다.
- Gmail target-options API가 필요한 mode에서 동작한다.
- Gmail source 실행 또는 preview가 준비되어 있다.
- Gmail sink schema와 실행이 준비되어 있다.

FE 변경:

| 파일 | 변경 |
| --- | --- |
| `src/features/add-node/model/source-rollout.ts` | Gmail source 유지 또는 지원 mode만 제한 |
| `src/features/add-node/model/sink-rollout.ts` | Gmail sink 유지 |
| `src/entities/oauth-token/model/oauth-connect-support.ts` | Gmail 유지 |
| `src/features/add-node/model/source-target-picker.ts` | `label_picker` remote 처리 추가 |
| `src/features/add-node/ui/SourceTargetPicker.tsx` | label icon, Gmail 문구 보정 |
| `src/features/configure-node/ui/panels/SourceTargetForm.tsx` | 기존 동작과 최초 생성 위자드 동작 정렬 확인 |
| `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx` | Gmail data type 표시 확인 |

동작 결과:

- Gmail source와 sink 모두 신규 노드 추가 UI에 노출된다.
- `label_emails` mode는 라벨 목록 picker로 target을 선택한다.
- remote picker 선택값은 `target`, `target_label`, `target_meta`로 저장된다.
- 실행 결과 또는 preview 데이터가 `EMAIL_LIST`, `SINGLE_EMAIL`, `FILE_LIST`로 표시된다.

---

## 6. API 확인 설계

설계 적용 전 브라우저 로그인 세션 또는 인증 토큰이 있는 API 클라이언트로 확인한다.

현재 Codex 실행 환경에서는 로그인된 브라우저 세션의 access token을 알 수 없으므로 API를 완전히 확정할 수 없다. 다만 제품 요구와 백엔드 최신 상태를 반영해 설계상 확정 판단은 선택지 C로 둔다.

1. 로그인 세션으로 실제 API를 확인할 수 있으면 그 결과를 검증 결과에 기록한다.
2. Spring Boot 최신 상태는 OAuth/scope/`label_emails` target-options 정렬 단계로 본다.
3. FastAPI 최신 상태는 Gmail source runtime payload, source preview schema, Gmail sink result schema 정렬이 반영된 상태로 본다. 남은 서버 의존성은 Spring의 FastAPI error body parsing, Spring error code 변환, FE 사용자 문구 mapping이다.
4. FE는 Gmail source/sink/OAuth 진입을 열고, 미완료 runtime 영역은 status/error mapping으로 사용자에게 명확히 보여준다.

이 기준에 따르면 현재 설계 판단은 선택지 C다.

### 6.1 OAuth 확인

확인 endpoint:

```http
POST /api/oauth-tokens/gmail/connect
GET /api/oauth-tokens
```

판정:

| 결과 | 선택 |
| --- | --- |
| `지원하지 않는 서비스: gmail` 계열 오류 | 선택지 A |
| endpoint가 인증 후에도 404/400/미지원 오류 | 선택지 A |
| connect 가능하지만 `gmail.send` scope만 확인됨 | 선택지 B |
| connect 가능하고 source/sink scope 모두 확인됨 | 선택지 C 후보 |
| 인증은 가능하지만 scope 부족 상태가 내려옴 | B 또는 C, node status 보정 확인 |

확인할 응답:

- `kind: "redirect"` 또는 `authUrl`
- direct connect 응답 여부
- token list의 `service`
- `connected`
- `accountEmail`
- scope 부족 판단 방식

미래 기능 기준 scope 판단:

| 기능 | 필요한 Gmail API 권한 성격 | 선택지 영향 |
| --- | --- | --- |
| 다른 사용자에게 메일 발송 | send 권한, 예: `gmail.send` | B 이상 필요 |
| 특정 발송인 기준 메일 조회 | read/search 권한 | C 필요 |
| 특정 키워드 기준 메일 조회 | read/search 권한 | C 또는 중간 filter 대체 |
| 라벨 메일 목록 조회 | label/message read 권한 | C 필요 |

### 6.2 source catalog 확인

확인 endpoint:

```http
GET /api/editor-catalog/sources
```

확인 항목:

- Gmail service 존재 여부
- `auth_required`
- source mode key
- `canonical_input_type`
- `trigger_kind`
- `target_schema.type`

판정:

| 결과 | 선택 |
| --- | --- |
| Gmail service 없음 | source rollout 제거 |
| Gmail service는 있으나 OAuth 미지원 | 선택지 A |
| Gmail service/mode는 있으나 target schema 불완전 | source rollout 제거 또는 mode 제한 |
| Gmail service/mode/target schema 정상 | 선택지 C 후보 |

### 6.3 target-options 확인

확인 endpoint:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=label_emails
```

필요 시:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=single_email
GET /api/editor-catalog/sources/gmail/target-options?mode=starred_email
```

확인 항목:

- option item shape
- `type: "label"` 여부
- `id`가 실행에 필요한 label id인지
- `label`이 UI 표시용 이름인지
- `metadata` 유무
- `nextCursor` 동작
- 권한 부족/토큰 없음 error shape

판정:

| 결과 | 설계 |
| --- | --- |
| endpoint 없음 | 선택지 C blocker. Gmail source는 숨기지 않고 provider 구현 또는 표준 error/status 표시를 우선한다. |
| endpoint 있음, label option 정상 | `label_picker` 보정 적용 |
| endpoint error shape 불안정 | picker error handling 후속 이슈 |

키워드/발송인 필터링 관련 판정:

- `sender_email` mode가 존재하므로 발송인 기준 조회는 기존 Spring catalog key를 우선 사용한다.
- 키워드 기준 조회는 현재 Spring catalog key 목록에 별도 `search_email` mode가 없으므로 FE가 임의 mode key를 만들지 않는다.
- 키워드 필터링은 1차로 Gmail source 이후의 `filter`/`condition`/`data-process` 노드에서 처리하는 방향을 우선한다.
- 백엔드가 향후 키워드 검색 source mode를 추가하면 source catalog에 새 mode가 내려온 뒤 FE rollout allowlist에 추가한다.
- 문서상 과거 예시인 `search_email`은 실제 Spring catalog key가 아니므로 이번 설계에서 사용하지 않는다.

### 6.4 sink schema 확인

확인 endpoint:

```http
GET /api/editor-catalog/sinks
GET /api/editor-catalog/sinks/gmail/schema?inputType=TEXT
GET /api/editor-catalog/sinks/gmail/schema?inputType=EMAIL_LIST
GET /api/editor-catalog/sinks/gmail/schema?inputType=SINGLE_EMAIL
GET /api/editor-catalog/sinks/gmail/schema?inputType=FILE_LIST
```

확인 항목:

- Gmail sink accepted input type
- schema field key
- schema field type
- required field
- `email_input` 사용 여부
- `select` options
- `to`/`recipient` key 차이

판정:

| 결과 | 설계 |
| --- | --- |
| Gmail sink 없음 | 선택지 A |
| Gmail sink 있음, OAuth 미지원 | 선택지 A |
| Gmail sink 있음, OAuth/scope 지원 | 선택지 B 이상 |
| schema key가 FE 라벨과 다름 | `node-status.ts` 라벨 보강 |

---

## 7. FE 구현 설계

### 7.0 Gmail capability 정책

선택지 C에서 Gmail은 source와 sink를 모두 지원 대상으로 둔다. 따라서 FE는 “Gmail이라는 서비스명 하나”를 기준으로 숨기지 않고, 아래 capability 단위로 인증/권한/target/status를 판단한다.

| capability | 의미 | 필요한 확인 |
| --- | --- | --- |
| `gmail.oauth` | Gmail 계정 연결 가능 | `/oauth-tokens/gmail/connect` |
| `gmail.send` | Gmail sink 발송/초안 가능 | OAuth send scope, sink schema, runtime |
| `gmail.read` | Gmail source 조회 가능 | read/search scope, source catalog, runtime |
| `gmail.labels` | Gmail label picker 가능 | target-options label response |
| `gmail.filter.sender` | 발송인 기준 source 조회 가능 | `sender_email` mode 계약 |
| `gmail.filter.keyword` | 키워드 기준 source 조회 가능 | 기존 filter 노드 또는 향후 source mode |

이번 코드베이스에는 capability registry가 아직 없으므로 1차 구현에서는 기존 allowlist 파일을 capability의 대리 지점으로 사용한다.

- source rollout: `gmail.read`, `gmail.labels`, `gmail.filter.sender`와 연결
- sink rollout: `gmail.send`와 연결
- OAuth supported list: `gmail.oauth`와 연결
- template instantiate 방어: requiredServices의 Gmail 사용 가능 여부와 연결

향후 Gmail 기능이 확장되면 정적 배열 세 곳을 각각 고치는 대신, `gmail-capability` 또는 `service-capability` 모델로 합치는 리팩터링을 검토한다.

### 7.1 Gmail 노출 정책

Gmail 노출 정책은 다음 세 축을 항상 함께 맞춘다.

1. source rollout
2. sink rollout
3. OAuth connect supported service

세 축이 어긋나면 아래 문제가 생긴다.

- source/sink는 보이는데 인증 연결이 실패한다.
- 인증은 가능해 보이는데 노드 추가가 막힌다.
- 노드는 만들 수 있는데 실행 조건이 충족되지 않는다.

#### 선택지 A 구현

`src/features/add-node/model/source-rollout.ts`

```ts
export const SOURCE_SERVICE_ROLLOUT_ALLOWLIST = {
  canvas_lms: ["course_files", "course_new_file", "term_all_files"],
  google_drive: [
    "single_file",
    "file_changed",
    "new_file",
    "folder_new_file",
    "folder_all_files",
  ],
  google_sheets: ["sheet_all", "new_row", "row_updated"],
  slack: ["channel_messages"],
} as const satisfies Record<string, readonly string[]>;
```

`src/features/add-node/model/sink-rollout.ts`

```ts
const SINK_SERVICE_ROLLOUT_ALLOWLIST = [
  "slack",
  "notion",
  "google_drive",
  "google_sheets",
  "google_calendar",
] as const;
```

`src/entities/oauth-token/model/oauth-connect-support.ts`

```ts
export const OAUTH_CONNECT_SUPPORTED_SERVICES = [
  "slack",
  "google_drive",
  "notion",
  "github",
  "canvas_lms",
] as const;
```

주의:

- Gmail 관련 display mapping, icon mapping, data preview는 제거하지 않는다.
- 기존 workflow나 향후 백엔드 응답에서 Gmail node가 들어와도 화면이 깨지지 않게 유지한다.
- 새 노드 추가 진입만 막는다.

#### 선택지 B 구현

source만 제거하고 sink/OAuth는 유지한다.

```ts
// source-rollout.ts
// gmail 제거

// sink-rollout.ts
"gmail" 유지

// oauth-connect-support.ts
"gmail" 유지
```

추가 확인:

- Gmail sink를 선택한 후 `SinkNodePanel`에서 schema 조회가 실패하지 않아야 한다.
- OAuth scope 부족 시 node status가 `권한 부족`으로 보인다.

#### 선택지 C 구현

Gmail source/sink/OAuth를 유지하고 `label_picker` 보정을 적용한다.

```ts
// source-rollout.ts
gmail: [
  "single_email",
  "new_email",
  "sender_email",
  "starred_email",
  "label_emails",
  "attachment_email",
],

// sink-rollout.ts
"gmail" 유지

// oauth-connect-support.ts
"gmail" 유지
```

추가 필수:

- `label_picker` remote picker 처리
- Gmail option type 표시
- Gmail picker 문구 보정

### 7.2 `label_picker` 처리 설계

대상:

- `src/features/add-node/model/source-target-picker.ts`

변경:

```ts
const REMOTE_TARGET_SCHEMA_TYPES = new Set([
  "course_picker",
  "term_picker",
  "file_picker",
  "folder_picker",
  "label_picker",
]);
```

기대:

- 최초 노드 추가 위자드에서 `target_schema.type === "label_picker"`이면 `SourceTargetPicker`를 렌더링한다.
- 사용자는 라벨 id를 직접 입력하지 않고 목록에서 선택한다.

### 7.3 Gmail option icon 설계

대상:

- `src/features/add-node/ui/SourceTargetPicker.tsx`

현재:

```ts
const TARGET_OPTION_ICON_MAP = {
  course: MdSchool,
  file: MdInsertDriveFile,
  folder: MdFolder,
  term: MdCalendarMonth,
};
```

변경:

```ts
import { MdLabel } from "react-icons/md";

const TARGET_OPTION_ICON_MAP = {
  course: MdSchool,
  file: MdInsertDriveFile,
  folder: MdFolder,
  label: MdLabel,
  term: MdCalendarMonth,
};
```

기대:

- Gmail label option이 folder 아이콘으로 fallback되지 않는다.
- 기존 노드 재설정 패널의 `SourceTargetForm`과 표시 방식이 맞춰진다.

### 7.4 picker 문구 설계

현재 `SourceTargetPicker`는 remote picker의 root label을 고정값으로 사용한다.

```tsx
rootLabel="내 드라이브"
```

문제:

- Gmail label picker에서 `내 드라이브`는 부적절하다.
- `label_picker`는 folder browse가 아니므로 root/breadcrumb가 필요하지 않을 수 있다.

설계:

```ts
const getPickerRootLabel = (schemaType: string, serviceKey: string) => {
  if (serviceKey === "google_drive") {
    return "내 드라이브";
  }

  if (serviceKey === "gmail" && schemaType === "label_picker") {
    return "Gmail 라벨";
  }

  return undefined;
};
```

적용:

- `path`는 folder picker일 때만 넘긴다.
- `rootLabel`은 `getPickerRootLabel()` 결과가 있을 때만 넘긴다.
- `label_picker`는 browse 기능 없이 검색/선택만 제공한다.

주의:

- `RemoteOptionPicker`가 `rootLabel` optional을 허용하는지 확인한다.
- optional이 아니라면 기본값을 `getTargetSchemaLabel(mode.target_schema)` 기반으로 준다.

### 7.5 선택값 저장 설계

기존 `buildSourceTargetConfig()` 계약을 유지한다.

대상:

- `src/features/add-node/ui/ServiceSelectionPanel.tsx`

현재 remote option 선택 시:

```ts
return {
  target: targetValue.option.id,
  target_label: targetValue.option.label,
  target_meta: targetValue.option.metadata,
};
```

설계:

- Gmail label picker도 동일 계약을 사용한다.
- 별도 Gmail 전용 config key를 만들지 않는다.
- 백엔드가 `target`을 실행용 id로 사용하고, `target_label`, `target_meta`는 UI 표시용으로 본다.

### 7.6 기존 노드 설정 패널과 정렬

기존 노드 설정 패널은 이미 `label_picker`를 remote picker로 처리한다.

대상:

- `src/features/configure-node/model/source-target-schema.ts`
- `src/features/configure-node/ui/panels/SourceTargetForm.tsx`

설계:

- 선택지 C에서는 최초 생성 위자드의 동작을 이 구현과 맞춘다.
- 중복된 picker 처리 로직은 이번 이슈에서 당장 공용화하지 않는다.
- 다만 향후 `SourceTargetPicker`와 `SourceTargetForm`의 중복 제거는 후속 리팩터링 후보로 남긴다.

### 7.7 node status 표시 설계

대상:

- `src/entities/workflow/lib/node-status.ts`

현재 필요한 라벨은 이미 있다.

```ts
oauth_scope_insufficient: "권한 부족",
oauth_token: "인증 연결",
```

설계:

- Gmail 미연결 상태는 `인증 연결`로 표시한다.
- Gmail scope 부족은 `권한 부족`으로 표시한다.
- 새 raw key가 백엔드에서 내려오면 라벨 매핑을 추가한다.
- Gmail sink schema field key가 `to`, `recipient`, `body`, `message` 등으로 다르면 missing field label을 보강한다.

### 7.8 data preview 유지 설계

대상:

- `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx`

설계:

- 선택지 C에서는 Gmail source/sink를 유지하므로 `EMAIL_LIST`, `SINGLE_EMAIL`, `FILE_LIST`, `SEND_RESULT` preview/data UI를 수동 검증 대상으로 포함한다.
- 기존 실행 결과 또는 다른 서비스가 email data type을 사용할 수 있으므로 email data type 표시 로직은 제거하지 않는다.
- FastAPI payload가 `email`/`emails`/`files` canonical field와 `items` alias를 함께 제공하므로 FE data preview는 두 형태를 모두 안전하게 읽을 수 있어야 한다.

---

## 8. 템플릿 영향 설계

선택지 C에서는 Gmail을 새 노드 추가 UI에서 유지하고, Gmail required template도 막지 않는다.

관련 예:

- 메일 요약 후 전달 템플릿
- Google Drive 문서 요약 후 Gmail 전달
- 새 파일 업로드 알림 메일 발송

추가 코드 확인 결과, 템플릿 상세 화면은 `requiredServices`를 표시하고 `useInstantiateTemplateMutation()`으로 바로 `/templates/{id}/instantiate`를 호출한다. 즉, 새 노드 추가 UI에서 Gmail을 막아도 Gmail required template을 통해 Gmail 노드가 포함된 workflow가 생성될 수 있다.

대상 파일:

- `src/entities/template/api/types.ts`
- `src/entities/template/model/template-presentation.ts`
- `src/pages/template-detail/TemplateDetailPage.tsx`
- `src/pages/template-detail/ui/TemplateInfoPanel.tsx`
- `src/pages/template-detail/ui/TemplateRequiredServices.tsx`

기존 선택지 A에서는 템플릿 경로도 방어 대상으로 봤지만, 선택지 C에서는 Gmail required template을 차단하지 않는다. 템플릿은 OAuth/status/preflight 흐름으로 진입한다.

### 8.1 선택지 C 기준: 템플릿 인스턴스화 허용

설계:

- Gmail required template의 “가져오기” 버튼을 활성화한다.
- 상세 화면의 필요한 서비스 영역에서 Gmail을 일반 required service로 표시한다.
- 목록에서 템플릿 자체를 숨기지는 않는다.
- 템플릿 설명과 미리보기를 유지하고, 인스턴스화 이후 OAuth/status 흐름으로 진입한다.

장점:

- 사용자가 Gmail 템플릿을 통해 필수 Gmail workflow를 만들 수 있다.
- 템플릿 목록 데이터나 백엔드 API를 변경하지 않는다.
- 미연결/scope 부족/실행 전 검증은 node status와 preflight에서 일관되게 처리한다.

구현 후보:

- `src/entities/template/model/template-service-support.ts` 제거 또는 Gmail unsupported set 비활성화
- `TemplateInfoPanel`의 Gmail unsupported message/disabled 조건 제거
- `TemplateRequiredServices`의 Gmail “현재 준비 중” 표시 제거

### 8.2 2차 후보: 템플릿 목록 표시 보정

설계:

- 목록에서는 Gmail required template을 숨기지 않는다.
- 다만 row나 detail에 OAuth/scope 필요 상태 배지를 표시할지는 별도 UX로 결정한다.
- 목록 숨김은 사용자가 템플릿 존재 자체를 알 수 없게 하므로 1차 방어로는 과하다.

이번 문서의 권장:

- 선택지 A를 적용한다면 템플릿 상세의 인스턴스화 버튼 방어까지 포함한다.
- 선택지 B를 적용한다면 Gmail source가 포함된 템플릿과 Gmail sink만 포함된 템플릿을 구분해야 하므로 template nodes까지 검사하는 추가 설계가 필요하다.
- 선택지 C를 적용한다면 템플릿 방어는 필요하지 않지만 OAuth/scope 부족 상태는 기존 연결 안내로 처리한다.

### 8.3 선택지 B에서의 템플릿 주의점

Gmail sink만 유지하는 선택지 B에서는 `requiredServices: ["gmail"]`만으로 템플릿 사용 가능 여부를 판단할 수 없다.

이유:

- 어떤 템플릿은 Gmail source를 사용한다.
- 어떤 템플릿은 Gmail sink만 사용한다.
- `requiredServices`는 source/sink 역할을 구분하지 않는다.

설계:

- 선택지 B에서 템플릿 방어를 정확히 하려면 `TemplateDetail.nodes`를 검사해 Gmail node의 `role` 또는 edge 위치를 확인한다.
- 목록의 `TemplateSummary`만으로는 정확한 판정이 어렵다.
- 이번 PR에서 선택지 B를 적용하더라도 템플릿 source/sink 구분 방어는 후속으로 분리할 수 있다.

---

## 9. 에러 처리 설계

### 9.1 새 노드 추가 UI

Gmail이 allowlist에서 제거되면 서비스 목록에 표시되지 않는다.

기대:

- 사용자는 Gmail을 클릭할 수 없다.
- OAuth 연결 단계로 진입하지 않는다.
- `지원하지 않는 서비스: gmail` API 오류가 발생하지 않는다.

### 9.2 기존 Gmail 노드

기존 workflow에 Gmail 노드가 있으면 다음이 가능하다.

- 노드는 캔버스에 계속 표시된다.
- node status가 있으면 `필수 설정` 또는 `실행 조건` 메시지를 표시한다.
- OAuth 미연결 또는 scope 부족 상태면 연결/재승인 안내를 표시한다.

주의:

- 기존 Gmail 노드 제거는 데이터 손실 가능성이 있으므로 하지 않는다.
- 기존 Gmail 노드 실행 실패는 백엔드/런타임 지원 범위의 문제이므로 이번 FE 방어 수정만으로 완전히 해결하지 않는다.

### 9.3 picker API 오류

선택지 C에서 Gmail picker를 유지하는 경우:

- token 없음
- scope 부족
- target-options 미구현
- 외부 Google API 실패

위 오류는 `RemoteOptionPicker`의 기존 error UI로 표시한다.

추가 설계:

- error message는 `getApiErrorMessage(error)`를 사용한다.
- OAuth 재연결 버튼을 picker 내부에 추가하는 것은 후속 이슈로 둔다.

---

## 10. 검증 설계

### 10.1 폐기된 대안 A 검증

전제:

- Gmail 전체 임시 비활성화

검증:

1. 시작 placeholder 클릭
2. source service 목록 확인
3. Gmail이 보이지 않아야 한다.
4. 도착 placeholder 클릭
5. sink service 목록 확인
6. Gmail이 보이지 않아야 한다.
7. Gmail OAuth 연결 버튼이 신규 노드 추가 흐름에서 나타나지 않아야 한다.
8. 기존 Gmail node가 있는 workflow가 깨지지 않는지 확인한다.
9. Gmail required template 상세에서 가져오기 버튼이 비활성화되는지 확인한다.
10. Gmail required template을 통해 `/templates/{id}/instantiate`가 호출되지 않는지 확인한다.

통과 기준:

- 신규 Gmail 노드 생성 경로가 없다.
- console runtime error가 없다.
- 백엔드 `지원하지 않는 서비스: gmail` 오류가 발생하지 않는다.
- 템플릿 인스턴스화 경로로도 새 Gmail workflow가 생성되지 않는다.

주의:

- 이 검증은 현재 선택지 C 구현 기준에서는 수행하지 않는 폐기된 대안 검증이다.
- 선택지 C 검증은 `10.3 선택지 C 검증`을 기준으로 한다.

### 10.2 선택지 B 검증

전제:

- Gmail sink만 유지

검증:

1. source service 목록에서 Gmail이 보이지 않는다.
2. sink service 목록에서 Gmail이 조건에 맞게 보인다.
3. Gmail sink 선택 시 OAuth 연결이 가능하다.
4. Gmail sink schema가 조회된다.
5. required field를 입력하고 저장한다.
6. `isConfigured=true`가 된다.
7. scope 부족 상태에서 `권한 부족`이 표시된다.

통과 기준:

- Gmail source 진입 경로가 없다.
- Gmail sink 설정 저장이 가능하다.
- OAuth/scope 문제는 node status로 표현된다.

### 10.3 선택지 C 검증

전제:

- Gmail source/sink 모두 유지

검증:

1. Gmail OAuth 연결이 가능하다.
2. Gmail source mode가 목록에 표시된다.
3. `label_emails` mode 선택 시 라벨 picker가 표시된다.
4. 라벨 option이 label icon으로 표시된다.
5. Drive 전용 `내 드라이브` 문구가 Gmail label picker에 보이지 않는다.
6. 선택 후 시작 노드 생성 시 `target`, `target_label`, `target_meta`가 저장된다.
7. Gmail sink schema 조회와 설정 저장이 가능하다.
8. Gmail source 실행 결과가 `EMAIL_LIST` 또는 `SINGLE_EMAIL` UI로 표시된다.
9. 발송인 기준 필터링은 `sender_email` mode 또는 중간 filter 노드로 동작한다.
10. 키워드 기준 필터링은 현재 catalog에 없는 mode를 FE가 만들지 않고, 중간 filter 노드 또는 백엔드 신규 mode 추가 후 동작한다.
11. Gmail sink로 다른 사용자 이메일 주소를 입력하고 설정 저장이 가능하다.

통과 기준:

- 최초 생성과 기존 설정 패널의 label picker 동작이 일치한다.
- Gmail OAuth/source/sink/status가 한 계약으로 동작한다.
- 미래 발송/필터링 기능을 위해 존재하지 않는 source mode key를 FE가 하드코딩하지 않는다.

### 10.4 정적 검증

가능하면 아래 명령을 사용한다.

```bash
pnpm run lint
pnpm run tsc
pnpm run build
```

현재 작업 환경에서 `pnpm`이 없으면 실행하지 못한 사실을 PR에 기록한다.

---

## 11. 구현 순서

### Step 1. 선택지 C 기준 문서 정렬

확인:

- 요구사항 문서가 선택지 C를 최종 선택지로 명시하는가
- 설계 문서의 파일별 변경 계획이 Gmail source/sink/OAuth 유지 기준인가
- Spring Boot 문서가 `label_emails` target-options와 OAuth scope 검증을 우선 단계로 설명하는가
- FastAPI 문서가 source runtime payload/schema 완료와 error mapping 미완료/후속 여부를 분리해서 설명하는가

산출:

- 선택지 C 확정 근거
- FE 구현 범위와 백엔드 미완료 범위 분리
- PR description에 들어갈 서버 의존성 목록
- FastAPI error mapping 구현 및 테스트 포함 여부 확인

### Step 2. Gmail 노출 정책 복구

선택지 C 기준으로 수정:

- source rollout
- sink rollout
- OAuth supported list
- template instantiate 방어 제거

기대 결과:

- Gmail source mode가 신규 노드 추가 UI에 보인다.
- Gmail sink가 도착 노드 목록에 보인다.
- Gmail OAuth 연결 버튼이 준비 중이 아니라 연결 가능 상태로 보인다.
- Gmail required template이 가져오기 가능 상태로 돌아온다.

### Step 3. `label_picker` 최초 생성 위자드 보정

수정:

- add-node `REMOTE_TARGET_SCHEMA_TYPES`에 `label_picker` 추가
- Gmail label option icon 보정
- picker root/search/empty 문구에서 Drive 전용 표현 제거
- 선택값 저장 계약 유지: `target`, `target_label`, `target_meta`

주의:

- 기존 노드 설정 패널은 이미 `label_picker`를 remote picker로 처리하므로 최초 생성 위자드와 같은 기준으로 맞춘다.
- `label_picker`를 추가하더라도 Gmail 외 서비스의 picker UX가 깨지지 않아야 한다.

### Step 4. Gmail sink 설정 확인

확인:

- sink schema
- required field 저장
- node status
- missing field label
- `to`, `subject`, `body`, `body_format`, `action` key

필요 시:

- `node-status.ts` field label 보강
- schema field label mapping 보강

### Step 5. Gmail source data preview/status 확인

확인:

- `SINGLE_EMAIL` 결과가 subject/from/date/body preview 중심으로 표시되는지
- `EMAIL_LIST` 결과가 list 형태로 표시되는지
- `FILE_LIST` 결과가 attachment metadata를 깨뜨리지 않는지
- source preview/runtime error가 raw key로 노출되지 않는지

필요 시:

- `DataPreviewBlock` email payload normalizing 보강
- source runtime/preview error message mapping 보강

### Step 6. 미래 발송/필터링 경로 확인

발송:

- Gmail sink schema에서 다른 사용자 이메일 주소를 입력할 수 있는지 확인한다.
- field key가 `to`인지 `recipient`인지 확인한다.
- `gmail.send` scope 부족 상태가 node status로 표현되는지 확인한다.

필터링:

- 발송인 기준은 기존 `sender_email` mode 또는 중간 filter 노드로 처리한다.
- 키워드 기준은 현재 존재하지 않는 mode key를 FE에서 만들지 않는다.
- 키워드 필터링이 source-level 검색이어야 한다면 백엔드 source catalog에 새 mode가 추가된 뒤 FE rollout에 추가한다.

### Step 7. 수동 검증

선택지 C 검증 시나리오를 수행한다.

### Step 8. 문서 갱신

선택지 C 구현 결과와 검증 결과를 아래 중 하나에 반영한다.

- `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`
- PR description
- 별도 follow-up 문서

---

## 12. 파일별 변경 계획

### 12.1 필수 변경

| 파일 | 선택지 C 변경 |
| --- | --- |
| `src/features/add-node/model/source-rollout.ts` | Gmail source mode 복구: `single_email`, `new_email`, `sender_email`, `starred_email`, `label_emails`, `attachment_email` |
| `src/features/add-node/model/sink-rollout.ts` | Gmail sink 복구 |
| `src/entities/oauth-token/model/oauth-connect-support.ts` | Gmail OAuth connect 지원 복구 |
| `src/features/add-node/model/source-target-picker.ts` | `label_picker` remote type 추가 |
| `src/features/add-node/ui/SourceTargetPicker.tsx` | Gmail label option icon/문구 보정 |
| `src/entities/template/model/template-service-support.ts` | 선택지 A용 Gmail unsupported 차단 제거 또는 비활성화 |
| `src/pages/template-detail/ui/TemplateInfoPanel.tsx` | Gmail required template 가져오기 차단 제거 |
| `src/pages/template-detail/ui/TemplateRequiredServices.tsx` | Gmail “현재 준비 중” 표시 제거 또는 capability 상태와 분리 |

### 12.2 조건부 후보

| 파일 | 조건 | 변경 |
| --- | --- | --- |
| `src/entities/workflow/lib/node-status.ts` | B/C에서 새 raw key 확인 시 | field label 추가 |
| `src/features/configure-node/ui/panels/SinkNodePanel.tsx` | B/C에서 schema 저장 문제 확인 시 | validation/save 보정 |
| `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx` | C에서 data 표시 문제 확인 시 | email preview 보정 |

### 12.3 이번 설계에서 직접 수정하지 않는 후보

| 파일/영역 | 사유 |
| --- | --- |
| template list row 숨김/필터링 | 선택지 C에서는 숨기지 않는다. OAuth/scope 상태 배지는 후속 UX 결정 |
| FastAPI runtime | FE 저장소 범위를 벗어나며 별도 백엔드 이슈 |
| OAuth backend connector | FE 저장소 범위를 벗어남 |
| Google Cloud scope 설정 | 운영/백엔드 설정 영역 |

---

## 13. 리스크와 대응

### 13.1 Gmail을 비활성화하면 템플릿과 충돌할 수 있음

리스크:

- 기존 선택지 A처럼 Gmail 신규 진입만 닫으면 template detail에서 Gmail node가 포함된 workflow가 생성되는 우회 경로가 생길 수 있다.

대응:

- 이번 선택지 C에서는 Gmail template을 막지 않는다.
- Gmail required template은 OAuth/status/preflight 검증 흐름으로 통일한다.
- 따라서 선택지 A용 unsupported template helper는 제거하거나 비활성화한다.

### 13.2 Gmail sink는 가능하지만 source만 막아야 할 수 있음

리스크:

- Gmail 전체 비활성화가 실제 가능한 sink 기능까지 숨길 수 있다.

대응:

- OAuth와 sink schema 확인 후 선택지 B로 전환한다.
- `gmail.send` scope와 node status 계약 확인을 완료 기준에 넣는다.
- Gmail required template은 source/sink 구분 없이 `requiredServices`만으로 판단하면 오차가 생기므로, 선택지 B에서는 상세 nodes 검사 또는 후속 이슈로 분리한다.

### 13.3 문서가 오래되어 백엔드 최신 상태와 다를 수 있음

리스크:

- 기존 점검 문서에는 Gmail connector 미구현으로 되어 있지만 최신 백엔드는 다를 수 있다.

대응:

- 설계상 API 확인 Step 1을 필수로 둔다.
- 문서 판단만으로 최종 코드를 확정하지 않는다.

### 13.4 `label_picker`만 고쳐도 OAuth 오류는 해결되지 않음

리스크:

- UI picker 문제를 고쳐도 Gmail connector 미지원이면 인증/실행 오류가 계속 난다.

대응:

- `label_picker` 보정은 선택지 C의 필수 작업으로 둔다.
- picker 보정만으로 OAuth/scope/FastAPI error 문제가 해결되는 것은 아니므로, Spring status/preflight와 FastAPI error mapping을 함께 검증한다.

### 13.5 FastAPI error mapping 미완료 위험

리스크:

- 선택지 C에서는 Gmail source/sink/OAuth를 숨기지 않으므로 preview/runtime 실패가 사용자에게 직접 보일 수 있다.
- Spring `FastApiClient`가 FastAPI error body의 `error_code`를 파싱하지 않으면 `OAUTH_SCOPE_INSUFFICIENT`, 외부 API 실패, runtime unsupported가 모두 `FASTAPI_UNAVAILABLE`처럼 보일 수 있다.

대응:

- 이번 PR 범위를 “선택지 C 서버 계약 완성”으로 잡고 FastAPI error mapping 구현과 테스트를 포함한다.
- PR description에는 FastAPI error mapping이 포함되었고 어떤 error code를 Spring `ErrorCode`로 변환하는지 명시한다.

### 13.6 기존 Gmail 노드 데이터 손상 위험

리스크:

- Gmail 비활성화를 구현하면서 기존 workflow의 Gmail node config를 지우면 데이터 손실이 발생한다.

대응:

- rollout allowlist와 OAuth supported list만 조정한다.
- 기존 node hydrate/display/data preview mapping은 유지한다.
- 기존 workflow의 Gmail node는 읽기/표시 가능하게 둔다.

### 13.7 미래 키워드 필터링을 잘못된 source mode로 열 위험

리스크:

- 과거 문서 예시의 `search_email` 같은 mode를 FE가 먼저 하드코딩하면 Spring catalog와 불일치한다.

대응:

- 현재 catalog key 기준으로는 `sender_email`, `label_emails`, `new_email` 등만 사용한다.
- 키워드 필터링은 우선 중간 filter/condition 노드에서 처리한다.
- source-level Gmail search가 필요하면 백엔드 catalog에 실제 mode가 추가된 후 FE allowlist를 연다.

### 13.8 미래 발송 기능을 과도하게 막을 위험

리스크:

- 선택지 A를 적용하면 Gmail sink 발송 기능도 일시적으로 숨겨진다.

대응:

- Gmail 관련 display/data type mapping은 유지한다.
- sink rollout은 `gmail.send` capability가 확인되는 즉시 선택지 B로 복구할 수 있게 변경 범위를 작게 유지한다.
- Gmail sink schema와 OAuth scope 확인 절차를 설계에 남겨 재활성화 기준을 명확히 한다.

---

## 14. 권장 최종안

현재 요구사항, 백엔드 최신 상태, 필수 Gmail 기능 요구를 기준으로 최종안은 **선택지 C: Gmail source/sink 모두 유지**다.

구현 판단:

1. Gmail source/sink/OAuth 신규 진입을 다시 연다.
2. `label_emails`의 `label_picker`를 최초 노드 추가 위자드에서 지원한다.
3. Gmail required template 인스턴스화 차단을 제거한다.
4. OAuth 미연결과 scope 부족은 미지원이 아니라 인증/권한 상태로 표시한다.
5. Gmail source runtime payload와 source preview schema는 FastAPI canonical contract 반영이 완료되었으며, Spring/FE는 error mapping과 사용자 상태 표시를 이어서 맞춘다.
6. FE는 Spring/FastAPI가 확정한 mode key만 사용하고 임의 Gmail search mode를 만들지 않는다.

미래 기능 관점의 최종 판단:

- “Gmail 노드에서 다른 사용자에게 메일을 발송하는 기능”은 Gmail sink `send` schema, `gmail.send` scope, FastAPI send runtime을 기준으로 구현한다.
- “특정 발송인을 기준으로 메일을 필터링하는 기능”은 Gmail source `sender_email` mode를 우선 사용한다.
- “특정 키워드를 기준으로 메일을 필터링하는 기능”은 현재 catalog에 명시적 source mode가 없으므로, 1차에서는 중간 filter/condition/AI 노드 조합으로 처리한다.
- 발송인 기준은 현재 catalog의 `sender_email` mode와 잘 맞는다.
- source-level keyword search가 필요하면 Spring catalog와 FastAPI runtime에 새 mode를 추가한 뒤 FE rollout에 반영한다.

---

## 15. 설계 완료 기준

이 설계는 아래 조건을 만족하면 선택지 C 구현 단계로 넘어갈 수 있다.

- Gmail 지원 범위가 선택지 C, 즉 source/sink/OAuth 유지로 확정되어 있다.
- 선택지 C의 FE 변경 파일과 검증 시나리오가 정리되어 있다.
- `label_picker` 문제가 Gmail source 유지의 필수 작업으로 정의되어 있다.
- Spring Boot 완료 범위와 FastAPI 완료 범위가 분리되어 있다.
- Gmail source runtime/preview 완료 기준이 canonical payload/schema와 Spring `FastApiClient` error mapping으로 분리되어 있다.
- Gmail keyword filtering의 1차 처리 방식과 후속 source mode 확장 조건이 분리되어 있다.
