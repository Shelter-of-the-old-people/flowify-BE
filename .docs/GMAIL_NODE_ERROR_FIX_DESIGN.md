# Gmail 노드 오류 수정 설계

> 작성일: 2026-05-08  
> 브랜치: `feat#145-gmail-error-check-and-fix&update`  
> 관련 문서: `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`  
> 관련 이슈: Gmail 노드 오류 수정  
> 목적: Gmail 노드 오류의 원인 후보를 바탕으로 FE 수정 방향, API 확인 절차, 지원 범위별 구현 설계를 정리한다.

---

## 1. 설계 요약

이번 이슈의 핵심 문제는 두 가지다.

1. FE는 Gmail을 source/sink/OAuth 연결 가능 대상으로 노출하고 있지만, 기존 백엔드 점검 문서 기준으로 Gmail connector는 미구현 상태다.
2. Gmail `label_picker`가 최초 노드 추가 위자드에서는 remote picker로 처리되지 않아 라벨 선택 UX와 저장 계약이 어긋날 수 있다.

따라서 이번 설계는 아래 원칙을 따른다.

- Gmail 지원 여부를 FE가 임의로 낙관하지 않는다.
- 백엔드가 실제 지원하지 않는 Gmail 기능은 새 노드 추가 UI에서 진입을 막는다.
- Gmail을 유지해야 하는 경우에는 source/sink/OAuth/picker/status 계약을 함께 맞춘다.
- `label_picker` 보정은 Gmail source를 유지하는 경우에만 필수 구현으로 본다.
- preview와 실제 Gmail 실행 엔진 개선은 이번 이슈의 핵심 범위가 아니며, 후속 이슈로 분리한다.

현재 문서와 코드 기준의 권장 기본안은 **Gmail 전체 임시 비활성화**다. 다만 장기적으로는 Gmail 발송과 Gmail 메일 필터링 기능을 지원해야 하므로, 이번 설계는 Gmail 관련 display/data type mapping을 제거하지 않고 **신규 진입만 capability 기준으로 제어**하는 방향을 택한다.

이 판단의 근거는 다음과 같다.

- 백엔드 점검 문서에는 Gmail connector가 미구현으로 기록되어 있다.
- 현재 FE에는 Gmail을 실제 지원 가능 여부와 무관하게 여는 정적 allowlist가 있다.
- Gmail 발송 기능은 `gmail.send` scope가 필요하다.
- 특정 키워드/발송인 기반 필터링은 Gmail source query와 중간 filter 노드 중 어느 레이어에서 처리할지 계약이 더 필요하다.

따라서 이번 PR의 설계 판단은 **현재는 선택지 A를 기본 확정안으로 두고**, 실제 API 확인에서 Gmail OAuth와 sink schema가 검증된 경우에만 선택지 B로 좁혀 전환한다. Gmail source까지 여는 선택지 C는 `label_picker`, source target-options, source canonical payload, 필요한 Gmail read scope가 모두 확인된 뒤에만 적용한다.

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

이번 설계에서 바로 구현 대상으로 보지 않는 것:

- Gmail OAuth connector 백엔드 구현
- Google Cloud Console scope 설정 변경
- FastAPI Gmail source 실행 로직 구현
- FastAPI Gmail sink 발송/초안 생성 로직 구현
- Gmail source metadata preview 구현
- Gmail sink no-write preview 구현
- Gmail 템플릿 전체 UX 개편
- Gmail fetch 개수 설정화
- Gmail attachment payload 변환 계약 확정

위 항목은 현재 오류 원인 확인과 FE 방어 수정 이후 후속 이슈로 분리한다.

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

- 백엔드 Gmail connector가 확인되기 전까지 Gmail은 OAuth connect supported list에서 제외한다.
- 제외되면 `getOAuthConnectionUiState()`는 Gmail을 `unsupported`로 판단할 수 있다.
- 새 노드 추가 UI에서는 Gmail 자체가 allowlist에서 빠지므로 사용자가 새 Gmail 노드를 만들 수 없다.

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
| A. Gmail 전체 임시 비활성화 | 기본 적용 후보 | 현재 repo 문서 기준 Gmail connector 미구현 가능성이 가장 높다. |
| B. Gmail sink만 유지 | API 확인 후 조건부 전환 | Gmail 발송은 미래 핵심 기능이지만 `gmail.send` scope와 OAuth connector 확인이 필요하다. |
| C. Gmail source/sink 모두 유지 | 이번 PR에서는 보수적으로 제외 | 키워드/발송인 필터링까지 온전하게 열려면 read scope, target-options, source payload 계약이 모두 필요하다. |

즉, API 확인이 불가능하거나 확인 결과가 불명확하면 A로 간다.  
Gmail 발송 기능이 실제로 확인되면 B로 간다.  
Gmail 메일 조회/라벨/검색까지 확인되면 C로 확장할 수 있지만, C는 이번 이슈의 기본값으로 보지 않는다.

### 5.1 선택지 A: Gmail 전체 임시 비활성화

현재 문서 기준 권장 기본안이다.

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

### 5.2 선택지 B: Gmail sink만 유지

Gmail sink는 실제 동작하지만 Gmail source가 미지원일 때 선택한다.

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

현재 Codex 실행 환경에서는 로그인된 브라우저 세션의 access token을 알 수 없으므로 API를 완전히 확정할 수 없다. 따라서 설계상 확정 판단은 다음 우선순위를 따른다.

1. 로그인 세션으로 실제 API를 확인할 수 있으면 그 결과를 최우선으로 한다.
2. 실제 API 확인이 불가능하면 `docs/backend/BACKEND_INTEGRATION_CHECK_REPORT.md`의 Gmail connector 미구현 기록을 우선한다.
3. Gmail sink 가능성을 언급한 문서는 “기능 목표 또는 런타임 가능성”으로 보고, OAuth connector가 확인되기 전까지는 FE 노출 근거로 사용하지 않는다.

이 기준에 따르면 현재 문서 기반 판단은 선택지 A다.

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
| endpoint 없음 | Gmail source 비활성화 |
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

Gmail은 장기적으로 source와 sink를 모두 지원해야 하지만, 현재는 실제 지원 범위가 불명확하다. 따라서 FE는 “Gmail이라는 서비스명 하나”를 기준으로 열고 닫지 않고, 아래 capability 단위로 판단한다.

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

- Gmail을 비활성화하더라도 `EMAIL_LIST`, `SINGLE_EMAIL` preview UI는 유지한다.
- 기존 실행 결과 또는 다른 서비스가 email data type을 사용할 수 있기 때문이다.
- 이번 이슈에서 DataPreviewBlock을 수정하는 것은 필수 범위가 아니다.
- 단, Gmail source/sink 모두 유지하는 선택지 C에서는 수동 검증 대상으로 포함한다.

---

## 8. 템플릿 영향 설계

Gmail을 새 노드 추가 UI에서 비활성화하더라도 템플릿에는 Gmail required service가 남아 있을 수 있다.

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

따라서 Gmail 전체 비활성화 선택지 A를 적용한다면 템플릿 경로도 방어 대상으로 보는 것이 안전하다.

### 8.1 1차 권장: 템플릿 인스턴스화 방어

설계:

- Gmail이 현재 disabled capability라면 Gmail required template의 “가져오기” 버튼을 비활성화한다.
- 상세 화면의 필요한 서비스 영역에서 Gmail을 “현재 준비 중”으로 표시한다.
- 목록에서 템플릿 자체를 숨기지는 않는다.
- 템플릿 설명과 미리보기는 유지하되, 인스턴스화만 막는다.

장점:

- 사용자가 Gmail 템플릿을 통해 미지원 Gmail 노드를 생성하는 경로를 막는다.
- 템플릿 목록 데이터나 백엔드 API를 변경하지 않는다.
- 향후 Gmail capability가 켜지면 버튼을 다시 활성화하기 쉽다.

구현 후보:

- `src/entities/template/model/template-service-support.ts` 신규 추가
- `isTemplateBlockedByUnsupportedServices(template.requiredServices)` helper 추가
- `TemplateInfoPanel`에 `unsupportedServices` 또는 `instantiateDisabledReason` prop 추가
- Gmail disabled 상태에서는 버튼 disabled 및 안내 문구 표시

### 8.2 2차 후보: 템플릿 목록 표시 보정

설계:

- 목록에서는 Gmail required template을 숨기지 않는다.
- 다만 row나 detail에 “일부 서비스 준비 중” 배지를 표시할 수 있다.
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
- OAuth unsupported 상태면 연결 버튼을 막거나 준비 중 문구를 표시한다.

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

### 10.1 선택지 A 검증

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

### Step 1. 실제 Gmail API 지원 상태 확인

확인:

- OAuth connect
- source catalog
- target-options
- sink catalog/schema
- node status

산출:

- 선택지 A/B/C 중 하나 확정
- PR description에 확인 결과 기록

### Step 2. Gmail 노출 정책 수정

선택지에 따라 수정:

- source rollout
- sink rollout
- OAuth supported list
- template instantiate 방어

### Step 3. 선택지 A일 경우 템플릿 방어

수정:

- Gmail required template의 instantiate button disabled
- unsupported service 안내 문구
- `/templates/{id}/instantiate` 호출 차단

주의:

- 템플릿 목록 숨김은 하지 않는다.
- 기존 template preview graph는 유지한다.

### Step 4. 선택지 C일 경우 label picker 보정

수정:

- add-node `REMOTE_TARGET_SCHEMA_TYPES`
- add-node `TARGET_OPTION_ICON_MAP`
- picker root/search/empty 문구

### Step 5. 선택지 B/C일 경우 sink 설정 확인

확인:

- sink schema
- required field 저장
- node status
- missing field label

필요 시:

- `node-status.ts` field label 보강

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

선택지별 검증 시나리오를 수행한다.

### Step 8. 문서 갱신

최종 선택한 지원 범위와 검증 결과를 아래 중 하나에 반영한다.

- `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`
- PR description
- 별도 follow-up 문서

---

## 12. 파일별 변경 계획

### 12.1 필수 후보

| 파일 | 선택지 A | 선택지 B | 선택지 C |
| --- | --- | --- | --- |
| `src/features/add-node/model/source-rollout.ts` | Gmail 제거 | Gmail 제거 | Gmail 유지/제한 |
| `src/features/add-node/model/sink-rollout.ts` | Gmail 제거 | Gmail 유지 | Gmail 유지 |
| `src/entities/oauth-token/model/oauth-connect-support.ts` | Gmail 제거 | Gmail 유지 | Gmail 유지 |

### 12.2 조건부 후보

| 파일 | 조건 | 변경 |
| --- | --- | --- |
| `src/entities/template/model/template-service-support.ts` | 선택지 A | Gmail unsupported 판정 helper |
| `src/pages/template-detail/TemplateDetailPage.tsx` | 선택지 A | unsupported service 판정 전달 |
| `src/pages/template-detail/ui/TemplateInfoPanel.tsx` | 선택지 A | 가져오기 버튼 disabled 및 안내 |
| `src/pages/template-detail/ui/TemplateRequiredServices.tsx` | 선택지 A | Gmail 준비 중 표시 |
| `src/features/add-node/model/source-target-picker.ts` | 선택지 C | `label_picker` remote type 추가 |
| `src/features/add-node/ui/SourceTargetPicker.tsx` | 선택지 C | `MdLabel`, root label 문구 보정 |
| `src/entities/workflow/lib/node-status.ts` | B/C에서 새 raw key 확인 시 | field label 추가 |
| `src/features/configure-node/ui/panels/SinkNodePanel.tsx` | B/C에서 schema 저장 문제 확인 시 | validation/save 보정 |
| `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx` | C에서 data 표시 문제 확인 시 | email preview 보정 |

### 12.3 이번 설계에서 직접 수정하지 않는 후보

| 파일/영역 | 사유 |
| --- | --- |
| template list row 숨김/필터링 | 목록에서 숨길지 배지만 표시할지는 별도 UX 결정 필요 |
| FastAPI runtime | FE 저장소 범위를 벗어나며 별도 백엔드 이슈 |
| OAuth backend connector | FE 저장소 범위를 벗어남 |
| Google Cloud scope 설정 | 운영/백엔드 설정 영역 |

---

## 13. 리스크와 대응

### 13.1 Gmail을 비활성화하면 템플릿과 충돌할 수 있음

리스크:

- Gmail required template이 여전히 보일 수 있다.
- template detail에서 가져오기 버튼을 통해 Gmail node가 포함된 workflow가 생성될 수 있다.

대응:

- 선택지 A에서는 템플릿 상세의 인스턴스화 버튼까지 방어한다.
- 목록에서는 숨기지 않고 상세에서 준비 중 상태를 보여준다.
- 선택지 B에서는 source/sink 구분이 필요하므로 template nodes 검사 여부를 별도 판단한다.

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

- `label_picker` 보정은 선택지 C의 조건부 작업으로 둔다.
- 지원 범위가 확정되기 전에는 picker 보정만 단독 해결책으로 보지 않는다.

### 13.5 기존 Gmail 노드 데이터 손상 위험

리스크:

- Gmail 비활성화를 구현하면서 기존 workflow의 Gmail node config를 지우면 데이터 손실이 발생한다.

대응:

- rollout allowlist와 OAuth supported list만 조정한다.
- 기존 node hydrate/display/data preview mapping은 유지한다.
- 기존 workflow의 Gmail node는 읽기/표시 가능하게 둔다.

### 13.6 미래 키워드 필터링을 잘못된 source mode로 열 위험

리스크:

- 과거 문서 예시의 `search_email` 같은 mode를 FE가 먼저 하드코딩하면 Spring catalog와 불일치한다.

대응:

- 현재 catalog key 기준으로는 `sender_email`, `label_emails`, `new_email` 등만 사용한다.
- 키워드 필터링은 우선 중간 filter/condition 노드에서 처리한다.
- source-level Gmail search가 필요하면 백엔드 catalog에 실제 mode가 추가된 후 FE allowlist를 연다.

### 13.7 미래 발송 기능을 과도하게 막을 위험

리스크:

- 선택지 A를 적용하면 Gmail sink 발송 기능도 일시적으로 숨겨진다.

대응:

- Gmail 관련 display/data type mapping은 유지한다.
- sink rollout은 `gmail.send` capability가 확인되는 즉시 선택지 B로 복구할 수 있게 변경 범위를 작게 유지한다.
- Gmail sink schema와 OAuth scope 확인 절차를 설계에 남겨 재활성화 기준을 명확히 한다.

---

## 14. 권장 최종안

현재 요구사항, 추가 코드 확인 결과, 기존 백엔드 점검 문서 기준으로는 다음 순서를 권장한다.

1. API 확인을 먼저 수행한다.
2. Gmail connector 미지원이 확인되면 선택지 A를 적용한다.
3. 실제 API 확인이 불가능하면 문서 기준으로 선택지 A를 적용한다.
4. 선택지 A에서는 Gmail source/sink/OAuth 신규 진입을 모두 닫는다.
5. 선택지 A에서는 Gmail required template의 인스턴스화도 막는다.
6. 기존 Gmail node 표시와 email data preview는 유지한다.
7. Gmail runtime 지원은 후속 이슈로 분리한다.

단, API 확인 결과 Gmail sink가 이미 안정적으로 동작한다면 선택지 B로 전환한다. Gmail source와 target-options까지 안정적으로 확인되는 경우에만 선택지 C를 적용하고, 그때 `label_picker` 보정을 함께 구현한다.

미래 기능 관점의 최종 판단:

- “Gmail 노드에서 다른 사용자에게 메일을 발송하는 기능”은 선택지 B가 최소 필요 조건이다.
- “특정 키워드 또는 발송인을 기준으로 메일을 필터링하는 기능”은 선택지 C 또는 중간 filter 노드 조합이 필요하다.
- 발송인 기준은 현재 catalog의 `sender_email` mode와 잘 맞는다.
- 키워드 기준은 현재 catalog에 명시적 source mode가 없으므로, FE가 임의 mode를 만들지 않고 중간 filter 노드 또는 백엔드 catalog 확장 후 처리한다.

---

## 15. 설계 완료 기준

이 설계는 아래 조건을 만족하면 구현 단계로 넘어갈 수 있다.

- Gmail 지원 범위 선택지 A/B/C 중 하나를 구현 전 확정할 수 있다.
- 확정 기준이 API 확인 항목으로 정의되어 있다.
- 선택지별 변경 파일과 검증 시나리오가 정리되어 있다.
- `label_picker` 문제는 Gmail source 유지 시 필수 작업으로 분리되어 있다.
- Gmail preview/runtime/template 목록 UX 확장은 후속 범위로 분리되어 있다.
