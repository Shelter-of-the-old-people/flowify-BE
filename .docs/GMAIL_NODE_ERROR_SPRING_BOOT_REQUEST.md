# Gmail 노드 오류 관련 Spring Boot 확인 및 수정 요청

> 작성일: 2026-05-08
> 브랜치: `9-gmail-node-error-fix`
> 관련 FE 문서: `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`, `docs/GMAIL_NODE_ERROR_FIX_DESIGN.md`
> 대상: Spring Boot 개발 팀
> 목적: Gmail 노드 오류 원인 확인과 FE 노출 정책 확정을 위해 Spring Boot 쪽 OAuth, catalog, schema, node lifecycle 계약을 정리하고 요청 사항을 전달한다.

---

## 1. 배경

현재 FE는 Gmail을 source/sink/OAuth 연결 가능 대상으로 노출하고 있다.

하지만 기존 백엔드 점검 문서 기준으로는 Gmail connector가 미구현으로 기록되어 있고, FE에서 Gmail OAuth 연결을 시도하면 `지원하지 않는 서비스: gmail` 계열 오류가 발생할 수 있다고 되어 있다.

이 상태에서 FE가 Gmail을 계속 열어두면 사용자는 아래 단계에서 오류를 만날 수 있다.

- Gmail 계정 연결
- Gmail source 노드 생성
- Gmail label target-options 조회
- Gmail sink schema 조회 또는 저장
- Gmail 포함 템플릿 인스턴스화
- 워크플로우 실행 전 node status 평가

FE 쪽 최신 설계 판단은 선택지 C다.

- Gmail OAuth 연결을 유지한다.
- Gmail source와 sink 신규 추가를 유지한다.
- Gmail required template 인스턴스화를 막지 않는다.
- Spring Boot는 OAuth/scope/target-options/status/preflight를 정렬해 Gmail 기능 진입 후 실패 원인을 명확히 보여줘야 한다.

---

## 2. 로컬 서버 확인 결과

현재 FE 작업 환경에서 확인한 서버 상태:

- `8080`: Spring Boot 서버로 추정되는 Java 프로세스가 LISTEN 중
- `8000`: Python/FastAPI 계열 프로세스가 LISTEN 중

터미널에서 브라우저 로그인 세션은 자동 공유되지 않으므로, 아래 결과는 비인증 요청 기준이다.

### 2.1 Spring API 비인증 응답

```http
GET http://127.0.0.1:8080/api/editor-catalog/sources
```

응답:

```json
{
  "success": false,
  "message": "인증이 필요합니다.",
  "errorCode": "AUTH_REQUIRED"
}
```

아래 endpoint도 모두 동일하게 `AUTH_REQUIRED`를 반환했다.

```http
POST /api/oauth-tokens/gmail/connect
GET /api/oauth-tokens
GET /api/editor-catalog/sources/gmail/target-options?mode=label_emails
GET /api/editor-catalog/sinks/gmail/schema?inputType=TEXT
```

따라서 Gmail 지원 여부 자체는 로그인된 세션 또는 JWT로 Spring 팀에서 추가 확인이 필요하다.

---

## 3. Spring Boot 쪽 핵심 확인 요청

### 3.1 Gmail OAuth connector 지원 여부

확인 endpoint:

```http
POST /api/oauth-tokens/gmail/connect
GET /api/oauth-tokens
DELETE /api/oauth-tokens/gmail
```

확인해 주실 항목:

- `gmail` service key가 OAuth connector map에 등록되어 있는가
- connect 응답이 redirect 방식인지 direct 방식인지
- OAuth callback 이후 token이 `service: "gmail"`로 저장되는가
- `GET /api/oauth-tokens`에서 Gmail 연결 상태가 내려오는가
- `accountEmail`, `expiresAt`, `connected` 값이 정상인가
- scope 부족 상태를 Spring에서 판정할 수 있는가

FE가 기대하는 connect 응답 shape:

```ts
type RawOAuthConnectResponse =
  | { authUrl: string }
  | { connected: "true"; service: string };
```

현재 FE는 위 응답을 다음 형태로 정규화한다.

```ts
type OAuthConnectResult =
  | { kind: "redirect"; authUrl: string }
  | { kind: "direct"; service: string; connected: true };
```

요청:

- Gmail connector가 미구현이면 명확한 표준 error code/message로 내려달라.
- 가능하면 `UNSUPPORTED_SERVICE` 또는 이에 준하는 error code를 사용해 달라.
- 단순 `IllegalArgumentException` stack trace가 사용자에게 노출되지 않게 처리해 달라.

---

### 3.2 Gmail OAuth scope 계약

미래 기능을 고려해 Gmail scope를 기능별로 분리해서 확인해야 한다.

| 기능 | 필요 권한 성격 | FE 지원 범위 판단 |
| --- | --- | --- |
| 다른 사용자에게 메일 발송 | Gmail send 권한, 예: `gmail.send` | Gmail sink 유지 가능 |
| Gmail 메일 목록/단일 메일 조회 | Gmail read 권한 | Gmail source 유지 가능 |
| Gmail 라벨 목록 조회 | label read 권한 | `label_picker` 유지 가능 |
| 특정 발송인 기준 조회 | read/search 권한 | `sender_email` mode 유지 가능 |
| 특정 키워드 기준 조회 | read/search 권한 또는 후처리 filter | 별도 source mode 또는 filter 조합 필요 |

요청:

- Gmail token 저장 시 어떤 scope가 실제 발급되는지 문서화해 달라.
- node lifecycle에서 scope 부족을 판정할 수 있다면 `missingFields`에 `oauth_scope_insufficient`를 내려달라.
- 토큰 자체가 없으면 `oauth_token`을 내려달라.

FE는 이미 아래 라벨을 가지고 있다.

```ts
oauth_token -> "인증 연결"
oauth_scope_insufficient -> "권한 부족"
```

---

### 3.3 Source catalog 계약

확인 endpoint:

```http
GET /api/editor-catalog/sources
```

Gmail이 source로 지원된다면 Spring catalog는 실제 runtime이 지원하는 mode만 내려줘야 한다.

현재 FE 문서상 Gmail source mode 후보:

| mode key | 의미 | canonical input type |
| --- | --- | --- |
| `single_email` | 특정 메일 사용 | `SINGLE_EMAIL` |
| `new_email` | 새 메일 도착 | `SINGLE_EMAIL` |
| `sender_email` | 특정 발송인 메일 | `SINGLE_EMAIL` 또는 구현 정책에 따른 타입 |
| `starred_email` | 별표/중요 메일 | `SINGLE_EMAIL` |
| `label_emails` | 라벨 메일 목록 | `EMAIL_LIST` |
| `attachment_email` | 첨부파일 있는 메일 | `FILE_LIST` |

요청:

- 실제 지원하지 않는 Gmail source mode는 catalog에서 제외하거나 FE와 협의해 unsupported status/preflight로 표현할 수 있게 알려달라.
- 존재하지 않는 mode key를 문서나 응답 예시에 사용하지 말아달라.
- 과거 문서에 있던 `search_email`은 현재 Spring catalog key가 아니므로, 키워드 검색 source를 지원하려면 새 mode 추가를 명시적으로 협의해 달라.

---

### 3.4 Gmail target-options 계약

확인 endpoint:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=label_emails
```

필요 시:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=single_email
GET /api/editor-catalog/sources/gmail/target-options?mode=starred_email
```

FE가 기대하는 응답:

```ts
interface SourceTargetOptionItemResponse {
  id: string;
  label: string;
  description: string | null;
  type: string;
  metadata: Record<string, unknown>;
}

interface SourceTargetOptionsResponse {
  items: SourceTargetOptionItemResponse[];
  nextCursor: string | null;
}
```

`label_emails`의 라벨 option 예시:

```json
{
  "id": "Label_123",
  "label": "뉴스레터",
  "description": null,
  "type": "label",
  "metadata": {
    "messageCount": 42
  }
}
```

요청:

- Gmail 라벨 picker를 지원한다면 option `type`은 `label`로 내려달라.
- `id`는 FastAPI 실행에 전달 가능한 Gmail label id여야 한다.
- `label`은 사용자 표시명이어야 한다.
- 인증 없음, scope 부족, Google API 실패가 표준 API error shape로 내려오게 해 달라.
- endpoint가 미구현이면 FE가 target 선택 실패 상태를 명확히 표시할 수 있도록 표준 error shape로 알려달라.

---

### 3.5 Sink catalog/schema 계약

확인 endpoint:

```http
GET /api/editor-catalog/sinks
GET /api/editor-catalog/sinks/gmail/schema?inputType=TEXT
GET /api/editor-catalog/sinks/gmail/schema?inputType=EMAIL_LIST
GET /api/editor-catalog/sinks/gmail/schema?inputType=SINGLE_EMAIL
GET /api/editor-catalog/sinks/gmail/schema?inputType=FILE_LIST
```

확인 요청:

- Gmail sink가 어떤 input type을 받는가
- schema field key가 무엇인가
- required field가 무엇인가
- `to`와 `recipient` 중 어느 key가 authoritative인가
- `subject`, `body_format`, `action`, `body/message` 필드 계약이 무엇인가
- `email_input`, `select`, `text` field type을 FE가 그대로 렌더링해도 되는가

FE의 현재 sink schema field 처리:

- `email_input` -> `<input type="email">`
- `number` -> number input
- `select` -> options button
- 그 외 -> text input

요청:

- 다른 사용자에게 메일 발송 기능을 위해 수신자 필드는 명확히 하나의 key로 확정해 달라.
- 복수 수신자를 지원한다면 구분자 또는 field type을 명확히 알려달라.
- send/draft action을 둘 다 지원한다면 `action` options를 내려달라.
- Gmail sink가 준비되지 않았다면 catalog 또는 schema에서 노출하지 않는 방향을 권장한다.

---

### 3.6 Node lifecycle/status 계약

Gmail node 상태가 FE에서 사용자에게 보이려면 node status 계약이 필요하다.

확인 요청:

| 상황 | 기대 `missingFields` |
| --- | --- |
| Gmail OAuth token 없음 | `["oauth_token"]` |
| Gmail scope 부족 | `["oauth_scope_insufficient"]` |
| Gmail source target 누락 | `["config.target"]` 또는 현행 규칙 |
| Gmail sink 수신자 누락 | `["config.to"]` 또는 authoritative field key |
| Gmail sink 제목 누락 | `["config.subject"]` |

요청:

- `configured`와 `executable`을 분리해 달라.
- 설정값은 다 찼지만 scope가 부족한 경우는 `configured=true`, `executable=false`가 자연스럽다.
- `missingFields` raw key가 FE 라벨 매핑 가능한 형태로 내려오게 해 달라.

---

### 3.7 Template instantiate 및 preflight 관련 요청

FE 코드 확인 결과, 템플릿 상세 화면은 `requiredServices`를 표시하고 곧바로 아래 API를 호출한다.

```http
POST /api/templates/{id}/instantiate
```

선택지 C 이전에는 FE에서 새 노드 추가 UI의 Gmail을 닫아도 Gmail required template 경로로 Gmail node가 생성될 수 있다는 우회 위험이 있었다.

선택지 C 기준 FE 설계:

- Gmail required template의 “가져오기” 버튼을 막지 않는다.
- 목록에서 템플릿 자체를 숨기지 않는다.
- instantiate 이후 OAuth 미연결, scope 부족, target 누락은 node lifecycle/status/preflight에서 표시한다.

Spring 팀 확인 요청:

- `TemplateSummary.requiredServices`만으로는 Gmail source와 sink를 구분할 수 없다.
- 선택지 C에서는 Gmail source/sink를 모두 허용하므로 template detail의 `nodes`를 기준으로 차단하지 않는다.
- 서버에서 template instantiate 이후 node lifecycle/status가 OAuth token, scope, target, required config 누락을 정확히 내려주는지 확인해 달라.
- FE 방어가 있더라도 API 차원에서 실행 전 preflight가 Gmail 실패 원인을 명확히 내려주면 더 안전하다.

요청 후보:

- `POST /api/templates/{id}/instantiate`는 Gmail required template을 허용
- workflow 실행/preview/preflight 단계에서 token 없음, scope 부족, target 누락, runtime 오류를 표준 error code로 반환
- template detail/summary에는 향후 OAuth/scope 필요 상태 배지를 추가할 수 있음

---

## 4. FE 지원 범위 확정에 필요한 Spring 답변

아래 항목에 답을 주시면 FE에서 Gmail 노출 정책을 확정할 수 있다.

| 질문 | 선택지 C 기준 Spring/FE 처리 |
| --- | --- |
| `/oauth-tokens/gmail/connect`가 동작하는가? | Gmail OAuth는 유지한다. 실패 시 표준 error code와 사용자 문구로 표시한다. |
| Gmail token에 `gmail.send` scope가 있는가? | Gmail sink status/preflight에서 부족 시 `oauth_scope_insufficient`로 표시한다. |
| Gmail sink schema가 안정적으로 내려오는가? | `to`, `subject`, `action` 저장 계약을 유지하고 FastAPI `SEND_RESULT`와 맞춘다. |
| Gmail read/label/search scope가 있는가? | Gmail source status/preflight에서 read scope 부족을 표시한다. |
| Gmail source catalog mode들이 실제 runtime과 일치하는가? | Spring catalog 6개 mode와 FastAPI runtime 6개 mode를 일치시킨다. |
| `label_emails` target-options가 동작하는가? | `GmailTargetOptionProvider`를 구현하고 `label_picker`를 remote picker로 지원한다. |
| 키워드 검색 source mode가 필요한가? | 이번 범위에서는 추가하지 않고 중간 filter/condition/AI 노드 또는 후속 catalog 확장으로 처리한다. |
| template instantiate에서 unsupported Gmail을 막을 수 있는가? | 선택지 C에서는 Gmail template을 막지 않고 OAuth/scope/status/preflight 흐름으로 진입한다. |

---

## 5. FE 선택지 C 전환 판단

최신 요구사항 기준 FE는 Gmail source/sink/OAuth를 모두 유지하는 선택지 C로 전환한다.

1. Gmail source 신규 추가 허용
2. Gmail sink 신규 추가 허용
3. Gmail OAuth 신규 연결 허용
4. Gmail required template 상세에서 가져오기 버튼 활성화
5. 기존 Gmail node와 email data type 표시 로직 유지

따라서 Spring Boot는 Gmail을 숨기는 방향이 아니라 아래 계약을 맞추는 방향으로 수정한다.

- Gmail OAuth/source/sink scope 부족을 `oauth_scope_insufficient`로 표현
- `label_emails` target-options provider 구현
- Gmail source/sink node lifecycle status 정렬
- FastAPI error body를 Spring API error shape로 변환
- template instantiate 이후 OAuth/status/preflight 흐름에서 실패 원인 표시

---

## 6. FastAPI 서버 측 재검토 결과 및 수정 진행 계획

> 작성일: 2026-05-08
> 기준 문서: `.docs/GMAIL_NODE_ERROR_FASTAPI_REQUEST.md`, `.docs/GMAIL_NODE_ERROR_SPRING_BOOT_REQUEST.md`
> 목적: Spring Boot 팀이 OAuth/catalog/schema/node lifecycle을 정리할 때 FastAPI runtime 지원 범위와 수정 방향을 함께 참고할 수 있도록 한다.

FastAPI 서버 측 코드를 확인한 결과, Gmail connector는 완전 미구현 상태가 아니라 source/sink runtime 코드가 일부 존재한다. 다만 현재 payload shape가 FE/Spring 문서에서 기대하는 canonical schema와 맞지 않는 부분이 있어, FastAPI 측에서는 아래 방향으로 수정한다.

### 6.1 FastAPI Gmail runtime 지원 범위

FastAPI는 Spring source catalog에 없는 mode key를 임의로 추가하지 않는다. 현재 Spring 문서에 있는 mode 후보만 기준으로 삼는다.

| mode key | FastAPI 처리 계획 | canonical output type |
| --- | --- | --- |
| `single_email` | `target`을 Gmail message id로 보고 단일 메일 조회 | `SINGLE_EMAIL` |
| `new_email` | 최신 메일 1건 조회 | `SINGLE_EMAIL` |
| `sender_email` | `from:{target}` query로 최신 1건 조회 | `SINGLE_EMAIL` |
| `starred_email` | `is:starred` query로 최신 1건 조회 | `SINGLE_EMAIL` |
| `label_emails` | `label:{target}` query로 메일 목록 조회 | `EMAIL_LIST` |
| `attachment_email` | `has:attachment` query로 첨부 metadata 조회 | `FILE_LIST` |

`sender_email`, `starred_email`은 여러 메일이 매칭될 수 있지만 1차 구현에서는 Spring catalog 기대와 기존 runtime 흐름을 고려해 최신 1건 `SINGLE_EMAIL`로 고정한다. 목록 반환이 필요하면 Spring catalog canonical type 변경 또는 별도 mode 추가를 협의해야 한다.

`search_email`, `search_emails`, `keyword_emails` 같은 키워드 검색 source mode는 이번 범위에서 FastAPI가 임의로 추가하지 않는다. 키워드 필터링은 1차로 Gmail source 이후 filter/condition/AI 등 중간 노드에서 처리하는 방향을 유지한다.

### 6.2 FastAPI source payload 수정 설계

FastAPI는 Gmail source payload를 아래 canonical schema에 맞춘다.

`SINGLE_EMAIL`:

```json
{
  "type": "SINGLE_EMAIL",
  "email": {
    "id": "msg-123",
    "threadId": "thread-123",
    "subject": "메일 제목",
    "from": "sender@example.com",
    "sender": "sender@example.com",
    "to": ["user@example.com"],
    "date": "2026-05-08T10:00:00Z",
    "body": "본문",
    "bodyPreview": "본문 일부",
    "labels": ["INBOX"],
    "attachments": []
  }
}
```

`EMAIL_LIST`:

```json
{
  "type": "EMAIL_LIST",
  "emails": [],
  "items": [],
  "metadata": {
    "count": 0,
    "truncated": false,
    "sourceMode": "label_emails"
  }
}
```

`FILE_LIST`:

```json
{
  "type": "FILE_LIST",
  "files": [],
  "items": [],
  "metadata": {
    "count": 0,
    "truncated": false
  }
}
```

정책:

- authoritative sender field는 `from`이다.
- `sender`는 FE 호환 alias로 제공한다.
- `EMAIL_LIST`의 canonical field는 `emails`지만, 기존 runtime/downstream 호환을 위해 `items` alias도 당분간 유지한다.
- `FILE_LIST`의 canonical field는 `files`지만, 기존 Google Drive sink 등 downstream 호환을 위해 `items` alias도 당분간 유지한다.
- Gmail attachment는 1차 metadata only로 반환한다. attachment content download 및 Drive sink로의 직접 전달은 후속 범위로 둔다.

### 6.3 FastAPI sink 수정 설계

FastAPI output node에는 Gmail `send`와 `draft` 호출 코드가 존재한다. 다만 Spring/FE 1차 노출 정책과 맞추기 위해 FastAPI 측 계약은 아래처럼 정리한다.

| 항목 | FastAPI 수정/응답 계획 |
| --- | --- |
| service key | `gmail` |
| 수신자 key | `to` |
| 수신자 형태 | 1차 단일 email string |
| 제목 key | `subject` |
| 본문 | `config.body` 우선, 없으면 이전 `TEXT.content` |
| action | FastAPI는 `send`, `draft` 처리 가능. Spring/FE 노출은 `send` 우선 권장 |
| cc/bcc | 후속 범위 |
| 복수 수신자 | 후속 범위 |
| attachment send | 후속 범위로 판단 |

Gmail send 결과는 기존 output node wrapper를 유지하면서 `detail` 안에 canonical `SEND_RESULT`를 담는 방식으로 수정한다.

```json
{
  "status": "sent",
  "service": "gmail",
  "detail": {
    "type": "SEND_RESULT",
    "service": "gmail",
    "status": "sent",
    "messageId": "gmail-sent-message-id",
    "threadId": "thread-id",
    "to": ["recipient@example.com"],
    "subject": "발송 제목"
  }
}
```

draft action을 Spring/FE에서 노출하기로 결정하면 FastAPI는 아래와 같은 형태로 응답을 정렬한다.

```json
{
  "status": "sent",
  "service": "gmail",
  "detail": {
    "type": "SEND_RESULT",
    "service": "gmail",
    "status": "drafted",
    "draftId": "gmail-draft-id",
    "messageId": "gmail-draft-message-id",
    "threadId": "thread-id",
    "to": ["recipient@example.com"],
    "subject": "초안 제목"
  }
}
```

### 6.4 FastAPI preview 수정 설계

FastAPI Gmail source preview는 runtime source와 같은 canonical schema를 사용하도록 정렬한다.

- source preview는 write side effect 없이 동작한다.
- `limit`, `include_content`를 반영한다.
- `include_content=false`면 `body`는 비우거나 생략하고 `bodyPreview`는 유지한다.
- `label_emails` preview는 `emails`, `items`, `metadata.truncated`를 반환한다.
- Gmail sink no-write preview는 이번 1차 수정 범위에는 포함하지 않고, payload builder와 sender 분리 작업이 필요할 때 별도로 진행한다.

### 6.5 FastAPI 인증 및 error code 계획

FastAPI 내부 인증은 이미 `X-Internal-Token`으로 동작한다. Spring에서 FastAPI를 호출할 때 필요한 내부 인증 계약은 아래와 같다.

| 항목 | 값 |
| --- | --- |
| 내부 인증 헤더 | `X-Internal-Token` |
| 사용자 식별 헤더 | `X-User-ID` |
| 내부 인증 실패 error code | `UNAUTHORIZED` |

Gmail OAuth/API 실패는 아래처럼 구분하는 방향으로 정리한다.

| 상황 | FastAPI 응답 계획 |
| --- | --- |
| Gmail token 없음 | 현재 `OAUTH_TOKEN_INVALID`, 필요 시 `OAUTH_TOKEN_MISSING` 추가 검토 |
| Gmail API 401 | `OAUTH_TOKEN_INVALID` |
| Gmail API 403 scope 부족 | 가능하면 `OAUTH_SCOPE_INSUFFICIENT` 추가 |
| Gmail API rate limit | 가능하면 `EXTERNAL_RATE_LIMITED` 추가 |
| 기타 Gmail API 실패 | `EXTERNAL_API_ERROR` |
| runtime mode 미지원 | `UNSUPPORTED_RUNTIME_SOURCE` 또는 `UNSUPPORTED_RUNTIME_SINK` |

Spring API error shape로 최종 변환하는 것은 Spring Boot 담당 범위이므로, FastAPI는 구분 가능한 error code와 사용자에게 노출 가능한 sanitized detail을 제공하는 방향으로 수정한다.

### 6.6 FastAPI 코드 수정 대상

FastAPI 측 예상 수정 파일은 아래와 같다.

| 파일 | 수정 내용 |
| --- | --- |
| `app/services/integrations/gmail.py` | Gmail message/header/attachment normalization 보강 |
| `app/core/nodes/input_node.py` | Gmail source payload를 `email`/`emails`/`files` canonical schema로 변경하고 `items` alias 유지 |
| `app/core/engine/preview_executor.py` | Gmail source preview schema를 runtime source와 동일하게 정렬 |
| `app/core/nodes/output_node.py` | Gmail send/draft 결과를 `SEND_RESULT` detail로 정규화 |
| `app/common/errors.py` | scope/rate-limit 구분이 필요하면 error code 추가 검토 |
| `tests/test_input_node.py` | Gmail source payload 기대값 갱신 |
| `tests/test_output_node.py` | Gmail send/draft result 기대값 갱신 |
| `tests/test_preview_executor.py` | Gmail source preview schema 테스트 추가 또는 갱신 |

### 6.7 Spring Boot 팀과 계속 맞춰야 하는 항목

FastAPI 수정만으로 FE 노출 정책을 확정할 수는 없다. Spring Boot 팀에서는 아래 항목을 함께 확인해야 한다.

| 항목 | Spring 확인 필요 이유 |
| --- | --- |
| Gmail OAuth connector 등록 | FE에서 Gmail 연결 가능 여부 결정 |
| Gmail token scope | source/sink/label picker 노출 범위 결정 |
| Gmail source catalog | FastAPI runtime mode와 노출 mode 일치 필요 |
| Gmail target-options | `label_emails` label picker 사용 가능 여부 결정 |
| Gmail sink schema | `to`, `subject`, `action`, `body` field 저장 계약 확정 |
| node lifecycle/status | `oauth_token`, `oauth_scope_insufficient`, `config.to`, `config.subject` 표시 필요 |
| template instantiate 방어 | unsupported Gmail workflow 생성 방지 |

FastAPI는 runtime capability와 payload schema를 위 설계대로 정렬한다. 선택지 C 전환 이후 FE는 Gmail source/sink/OAuth를 유지하는 방향으로 진행하므로, Spring Boot는 OAuth, catalog, schema, target-options, lifecycle/status를 “노출 차단 여부 판단”이 아니라 “사용자가 실패 원인을 이해할 수 있는 preflight/status 계약”으로 정렬해야 한다.

---

## 7. Spring Boot 현재 코드 재분석 및 수정 설계

> 작성일: 2026-05-08
> 분석 대상: 현재 Spring Boot repo 코드
> 목적: `GMAIL_NODE_ERROR_*` 문서의 요구사항을 현재 서버 구현과 대조하고, Gmail 노드 오류가 Spring 요청 처리 흐름의 어느 지점에서 발생하는지 정리한다.

### 7.1 결론 요약

현재 Spring Boot 코드 기준으로 Gmail은 완전 미구현 상태가 아니다. `GmailConnector`, `GmailOAuthTokenRefresher`, source catalog, sink catalog, lifecycle 검증, FastAPI token 전달 경로가 이미 존재한다.

다만 Gmail을 source/sink/OAuth 전체 기능으로 여는 선택지 C 기준에서는 Spring Boot 계약 보강이 필요하다. 특히 Gmail source의 remote picker provider가 없고, Gmail scope를 기능별로 검증하지 않으며, sink schema와 FastAPI 1차 권장 범위가 일부 어긋난다. FE가 Gmail source를 열면 `label_emails` target-options 조회에서 바로 실패할 가능성이 있고, Gmail sink는 token만 있으면 실행 요청까지 갈 수 있지만 실제 권한/런타임 실패를 Spring이 사전에 충분히 구분하지 못한다.

최신 제품 판단은 **선택지 C: Gmail source/sink/OAuth 모두 유지**다. 따라서 Spring Boot 쪽 권장 정책은 source를 닫는 것이 아니라, `GmailTargetOptionProvider`, 기능별 scope 검증, FastAPI error mapping, lifecycle/preflight를 구현해 Gmail 진입 후 실패 원인을 명확히 표시하는 것이다.

### 7.2 현재 요청 처리 흐름

#### Gmail OAuth connect

요청:

```http
POST /api/oauth-tokens/gmail/connect
```

처리 흐름:

1. `OAuthTokenController.connectService()`가 로그인 사용자를 꺼낸다.
2. 생성자에서 주입된 `ExternalServiceConnector` 목록을 `getServiceName()` 기준 map으로 만들고, `gmail` key로 connector를 찾는다.
3. 현재 코드에는 `GmailConnector#getServiceName()`이 `gmail`을 반환하므로 connector map 등록 자체는 가능하다.
4. `GmailConnector.connect()`는 Google OAuth URL을 반환한다.
5. callback 성공 시 `OAuthTokenService.saveToken(userId, "gmail", ...)`로 token을 저장한다.

현재 판단:

- 과거 문서의 `지원하지 않는 서비스: gmail`은 현재 코드만 보면 더 이상 핵심 원인이 아니다.
- 다만 `OAuthTokenController#getConnector()`는 미지원 서비스를 `IllegalArgumentException`으로 던진다. Gmail이 환경 문제로 bean 생성 실패하거나 설정 누락으로 connector가 빠지면 표준 `UNSUPPORTED_SERVICE`가 아니라 `INTERNAL_SERVER_ERROR`로 정리될 수 있다.
- `app.oauth.gmail.scopes`는 `gmail.readonly`와 `gmail.send`를 요청한다.

#### Gmail source catalog

요청:

```http
GET /api/editor-catalog/sources
```

현재 catalog에는 `gmail` source가 있고 다음 mode를 노출한다.

| mode | output type | target schema |
| --- | --- | --- |
| `single_email` | `SINGLE_EMAIL` | `email_picker`, `picker_supported=false` |
| `new_email` | `SINGLE_EMAIL` | 없음 |
| `sender_email` | `SINGLE_EMAIL` | `text_input` |
| `starred_email` | `SINGLE_EMAIL` | 없음 |
| `label_emails` | `EMAIL_LIST` | `label_picker`, `picker_supported=false` |
| `attachment_email` | `FILE_LIST` | 없음 |

현재 판단:

- source catalog는 Gmail source를 실제 지원 대상으로 노출한다.
- 하지만 remote picker가 필요한 `label_emails`는 `label_picker`임에도 `picker_supported=false`다.
- FE 문서는 `label_picker`를 remote picker로 다루려는 방향인데, Spring catalog는 아직 remote 지원 불가로 표시한다.

#### Gmail source target-options

요청:

```http
GET /api/editor-catalog/sources/gmail/target-options?mode=label_emails
```

처리 흐름:

1. `CatalogController.getTargetOptions()`가 `TargetOptionService.getOptions()`를 호출한다.
2. `TargetOptionService`는 catalog에서 `gmail` source와 `label_emails` mode 존재 여부를 확인한다.
3. `auth_required=true`이므로 `OAuthTokenService.getDecryptedToken(userId, "gmail")`로 token을 조회한다.
4. 이후 `TargetOptionProvider` 목록에서 `getServiceKey().equals("gmail")`인 provider를 찾는다.

현재 오류 원인:

- 현재 provider 구현은 `GoogleDriveTargetOptionProvider`, `CanvasLmsTargetOptionProvider`뿐이다.
- `GmailTargetOptionProvider`가 없으므로 token 조회 후 `target option provider를 찾을 수 없습니다: gmail` 오류가 발생한다.
- token이 없으면 그보다 먼저 `OAUTH_NOT_CONNECTED`가 발생한다.

즉 Gmail label picker 오류의 Spring Boot 직접 원인은 `source_catalog.json`이 Gmail source와 `label_picker`를 노출하지만, 이를 처리할 `TargetOptionProvider`가 없다는 점이다.

#### Gmail sink schema

요청:

```http
GET /api/editor-catalog/sinks/gmail/schema?inputType=TEXT
```

현재 sink catalog:

| 항목 | 값 |
| --- | --- |
| service key | `gmail` |
| auth required | `true` |
| accepted input types | `TEXT`, `SINGLE_FILE`, `FILE_LIST` |
| required fields | `to`, `subject`, `action` |
| optional fields | `body_format` |
| action options | `send`, `draft` |

현재 판단:

- Spring schema key는 FastAPI 요청 문서의 권장값인 `to`, `subject`, `action`과 맞다.
- 다만 FastAPI 문서는 1차 노출을 `send` 중심으로 권장하는데 Spring catalog는 `draft`까지 노출한다.
- Gmail source의 `SINGLE_EMAIL`, `EMAIL_LIST` output을 Gmail sink가 직접 받지 않는다. 메일을 다시 발송/전달하는 UX가 필요하면 accepted input type을 재검토해야 한다.

#### node lifecycle/status

처리 흐름:

1. start node는 `type`, `config.source_mode`, `outputDataType`, target 필요 여부를 검사한다.
2. end node는 sink catalog의 required field를 읽어 `config.to`, `config.subject`, `config.action` 등을 검사한다.
3. auth required service는 `OAuthTokenService.getDecryptedToken(userId, serviceKey)`로 token을 확인한다.
4. `OAUTH_SCOPE_INSUFFICIENT`이면 `missingFields=["oauth_scope_insufficient"]`, 그 외 OAuth 실패는 `["oauth_token"]`을 추가한다.

현재 판단:

- 설정 누락과 OAuth 누락은 FE가 표시할 수 있는 raw key로 내려간다.
- `configured=true`, `executable=false` 분리도 현재 구조상 가능하다.
- 그러나 Gmail 자체에는 required scope 검증 테이블이 없다. `getDecryptedToken(userId, "gmail")`은 token 존재/만료만 확인하고, `gmail.send`, `gmail.readonly`를 기능별로 검증하지 않는다.
- Google Sheets만 alias scope 검증이 있고, Gmail source/sink mode별 scope 검증은 없다.

#### FastAPI 실행/preview 요청

실행 흐름:

1. `WorkflowValidator.validateForExecution()`이 lifecycle과 catalog 존재 여부를 검증한다.
2. `ExecutionService.collectServiceTokens()`가 workflow node type 중 auth required service의 token을 수집한다.
3. `WorkflowTranslator`는 start node를 `runtime_type=input`, `runtime_source={service, mode, target, canonical_input_type}`로 변환한다.
4. end node는 `runtime_type=output`, `runtime_sink={service, config}`로 변환한다.
5. `FastApiClient.execute()`가 `workflow`와 `service_tokens`를 FastAPI로 보낸다.

preview 흐름:

1. `WorkflowPreviewService`는 현재 모든 start node preview를 지원 대상으로 본다.
2. target node의 service token만 수집해 FastAPI preview endpoint로 보낸다.
3. sink node preview는 `PREVIEW_NOT_IMPLEMENTED`로 막힌다.

현재 판단:

- Gmail source preview도 start node라는 이유만으로 FastAPI까지 갈 수 있다.
- Spring은 FastAPI가 Gmail source mode를 실제 지원하는지 사전에 모른다.
- FastAPI 에러는 현재 `FASTAPI_UNAVAILABLE` 중심으로 뭉개질 수 있어 Gmail API 401/403/rate limit/runtime unsupported를 FE가 구분하기 어렵다.

### 7.3 요구사항 재정리

#### 필수 요구사항

1. Spring catalog는 실제 Spring provider와 FastAPI runtime이 처리 가능한 Gmail 기능만 노출해야 한다.
2. Gmail source target-options를 열려면 `GmailTargetOptionProvider`가 있어야 한다.
3. `label_emails`를 remote picker로 지원한다면 `target_schema.picker_supported=true`로 바꾸고 option shape를 `{id,label,description,type,metadata}`로 고정해야 한다.
4. Gmail OAuth token은 기능별 required scope를 검증해야 한다.
5. Gmail sink schema의 `action`은 실제 FastAPI/제품 1차 범위와 맞춰야 한다.
6. FastAPI 오류를 Spring이 가능한 한 표준 error code로 변환해야 한다. 이번 PR은 선택지 C 서버 계약 완성 범위로 보고 해당 변환을 포함한다.
7. 실행 전 검증에서 unsupported Gmail source/sink가 포함된 workflow를 통과시키지 않아야 한다.

#### 선택지 C 전환 요구사항

1. Gmail source catalog는 Spring catalog 기준 6개 mode를 유지한다.
2. `label_emails` target-options를 지원할 `GmailTargetOptionProvider`를 구현한다.
3. `label_emails.target_schema.picker_supported`는 remote picker 사용 가능 상태와 일치해야 한다.
4. `single_email`의 `email_picker`는 1차에서 provider를 구현하거나, 지원하지 않는다면 picker 미지원/수동 message id 정책을 명확히 문서화한다.
5. Gmail sink schema는 FastAPI runtime과 맞춰 `to`, `subject`, `action`을 authoritative key로 유지한다.
6. `draft` 노출 여부는 FastAPI helper 존재 여부가 아니라 제품 노출 정책과 테스트 완료 여부를 기준으로 결정한다.

### 7.4 Spring Boot 수정 설계

#### 7.4.1 Capability 정책 추가

Spring 내부 기준 capability를 먼저 정한다.

| capability | 의미 | 선택지 C 상태 |
| --- | --- | --- |
| `gmail.oauth` | Gmail OAuth 연결 | enabled |
| `gmail.send` | Gmail sink send | enabled after scope validation |
| `gmail.draft` | Gmail draft 생성 | product decision. 기본은 send 우선, 노출 시 scope/runtime 테스트 필요 |
| `gmail.read` | Gmail source read | enabled after scope validation |
| `gmail.labels` | Gmail label target-options | enabled after `GmailTargetOptionProvider` implementation |
| `gmail.attachments` | Gmail attachment metadata/content | metadata only 후속 |

1차 구현에서 별도 DB 기반 capability registry까지 만들 필요는 없다. 대신 catalog와 service code를 위 표와 일치시키는 것을 목표로 한다.

#### 7.4.2 Gmail source 정책

선택지 C 기준으로 Gmail source는 정식 지원 대상으로 둔다.

- `GmailTargetOptionProvider`를 추가한다.
- `label_emails.target_schema.picker_supported=true`로 변경한다.
- `single_email`도 email picker를 지원하려면 provider에서 mode별로 message list/search option을 제공한다. 지원하지 않으면 `single_email`은 catalog에서 제외하거나 text/manual id 입력 정책으로 문서화한다.
- Gmail source mode별 target 필요 여부를 현재 catalog와 유지한다.
  - `new_email`, `starred_email`, `attachment_email`: target 불필요
  - `sender_email`: sender email text 필수
  - `label_emails`: label id 필수
  - `single_email`: message id 또는 picker 선택 필수

#### 7.4.3 GmailTargetOptionProvider 설계

정식 source 지원 시 신규 클래스:

```java
@Component
@RequiredArgsConstructor
public class GmailTargetOptionProvider implements TargetOptionProvider {
    private final WebClient gmailWebClient;

    @Override
    public String getServiceKey() {
        return "gmail";
    }

    @Override
    public TargetOptionResponse getOptions(String sourceMode, String token,
                                           String parentId, String query, String cursor) {
        return switch (sourceMode) {
            case "label_emails" -> listLabels(token, query, cursor);
            case "single_email" -> listMessages(token, query, cursor);
            default -> throw new BusinessException(ErrorCode.INVALID_REQUEST,
                    "Gmail target-options를 지원하지 않는 source mode입니다: " + sourceMode);
        };
    }
}
```

label option 계약:

```json
{
  "id": "Label_123",
  "label": "뉴스레터",
  "description": null,
  "type": "label",
  "metadata": {
    "messageCount": 42,
    "unreadCount": 3
  }
}
```

오류 변환:

| Gmail API 상황 | Spring error code |
| --- | --- |
| token 없음 | `OAUTH_NOT_CONNECTED` |
| access token 만료/401 | refresh 시도 후 실패하면 `OAUTH_TOKEN_EXPIRED` |
| 403 scope 부족 | `OAUTH_SCOPE_INSUFFICIENT` |
| rate limit | `EXTERNAL_RATE_LIMITED` |
| 기타 Google API 오류 | `EXTERNAL_API_ERROR` |

#### 7.4.4 Gmail scope 검증 설계

현재 `OAuthTokenService`의 scope 검증은 Google Sheets alias에만 있다. Gmail은 service 하나 안에서 source와 sink가 서로 다른 scope를 요구하므로 기능별 검증이 필요하다.

권장 helper:

```java
public String getDecryptedToken(String userId, String service, Collection<String> requiredScopes)
```

또는:

```java
public void assertRequiredScopes(String userId, String service, List<String> requiredScopes)
```

정책:

| 기능 | required scopes |
| --- | --- |
| Gmail sink send | `https://www.googleapis.com/auth/gmail.send` |
| Gmail source read | `https://www.googleapis.com/auth/gmail.readonly` |
| Gmail label picker | `https://www.googleapis.com/auth/gmail.readonly` |

적용 지점:

- `NodeLifecycleService`에서 role/mode/action을 보고 scope 부족을 `oauth_scope_insufficient`로 표시한다.
- `ExecutionService.collectServiceTokens()`에서도 같은 scope 검증을 수행해 lifecycle과 실행 결과가 어긋나지 않게 한다.
- `TargetOptionService` 또는 `GmailTargetOptionProvider`에서 label 조회 전 read scope를 검증한다.

주의:

- 현재 OAuth 설정은 `gmail.readonly gmail.send`를 모두 요청하므로 신규 연결 사용자는 두 scope가 들어올 가능성이 높다.
- 기존 저장 token에는 scope가 없거나 부족할 수 있으므로 `GET /api/oauth-tokens` 응답에 `connected=false`, `reason=OAUTH_SCOPE_INSUFFICIENT`를 표현하는 방식을 검토한다.

#### 7.4.5 Gmail sink schema 정렬

선택지 C 1차 범위에서 Gmail sink는 유지한다. FastAPI runtime과 맞춰 다음을 authoritative contract로 둔다.

- `to`: authoritative recipient key
- `subject`: required
- `body_format`: optional, `plain`/`html`
- `action`: 1차 기본은 `send`; `draft`는 제품 노출을 결정하고 테스트가 완료된 경우에만 options에 포함
- accepted input type은 현재 `TEXT`, `SINGLE_FILE`, `FILE_LIST`지만 실제 body/attachment 처리 범위에 맞춰 조정한다.

권장 1차 schema:

```json
{
  "fields": [
    { "key": "to", "label": "수신자", "type": "email_input", "required": true },
    { "key": "subject", "label": "제목", "type": "text", "required": true },
    { "key": "body_format", "label": "본문 포맷", "type": "select", "options": ["plain", "html"], "required": false },
    { "key": "action", "label": "동작", "type": "select", "options": ["send"], "required": true }
  ]
}
```

FastAPI에는 draft helper가 있으나, 선택지 C의 필수 요구는 Gmail source/sink 유지와 send 가능성이다. `draft`는 Gmail source 전환과 별개로 후속 제품 노출 여부를 결정한다.

#### 7.4.6 FastAPI error 변환 설계

현재 `FastApiClient`는 `WebClientResponseException`을 대부분 `FASTAPI_UNAVAILABLE`로 변환한다. Gmail 노드 오류를 FE가 정확히 표시하려면 FastAPI error body의 `error_code`를 읽어 Spring `ErrorCode`로 매핑해야 한다.

선택지 C 기준 중요도:

- Gmail source/sink/OAuth를 숨기지 않기 때문에 runtime/source preview 실패는 사용자에게 더 자주 노출될 수 있다.
- 이 변환이 없으면 Gmail read scope 부족, Gmail API 403, runtime unsupported가 모두 포괄적인 FastAPI 실패처럼 보일 수 있다.
- 따라서 이번 PR에는 `FastApiClient` error body parsing과 Spring `ErrorCode` mapping을 포함한다.

권장 매핑:

| FastAPI error_code | Spring ErrorCode |
| --- | --- |
| `OAUTH_TOKEN_MISSING`, `OAUTH_TOKEN_INVALID` | `OAUTH_NOT_CONNECTED` 또는 `OAUTH_TOKEN_EXPIRED` |
| `OAUTH_SCOPE_INSUFFICIENT` | `OAUTH_SCOPE_INSUFFICIENT` |
| `EXTERNAL_RATE_LIMITED` | `EXTERNAL_RATE_LIMITED` |
| `EXTERNAL_API_ERROR` | `EXTERNAL_API_ERROR` |
| `UNSUPPORTED_RUNTIME_SOURCE`, `UNSUPPORTED_RUNTIME_SINK` | `PREFLIGHT_VALIDATION_FAILED` 또는 신규 `RUNTIME_UNSUPPORTED` |
| 내부 인증 실패 `UNAUTHORIZED` | `FASTAPI_UNAVAILABLE` |

이 변경은 Gmail뿐 아니라 다른 외부 서비스에도 영향을 주므로 `FastApiClient` 공통 error parser로 구현한다.

#### 7.4.7 실행 전 preflight 검증

선택지 C에서는 Gmail source/sink를 숨기지 않는다. 대신 token 없음, scope 부족, target 누락, target-options 실패, FastAPI runtime 오류를 실행 전 또는 preview 시점에 구분해서 알려야 한다.

권장 위치:

- `WorkflowValidator.validateForExecution()`
- 또는 별도 `RuntimeCapabilityService`

검증 예:

| 노드 | 조건 | 실패 메시지 |
| --- | --- | --- |
| Gmail source | read scope 부족 | Gmail 메일 조회 권한이 부족합니다 |
| Gmail `label_emails` | label target 누락 | Gmail 라벨을 선택해야 합니다 |
| Gmail `label_emails` | label option provider/API 실패 | Gmail 라벨 목록을 불러오지 못했습니다 |
| Gmail sink `send` | send scope 부족 | Gmail 발송 권한이 부족합니다 |
| Gmail sink `action=draft` | draft 미노출 정책 | Gmail draft action은 아직 지원되지 않습니다 |

이렇게 해야 FE가 선택지 C 기준으로 Gmail 진입을 열더라도 사용자가 raw server exception 대신 필요한 조치(연결, 권한 재승인, target 선택, 잠시 후 재시도)를 이해할 수 있다.

### 7.5 원인별 사용자 오류 매핑

| 사용자 행동 | 현재 발생 가능 오류 | Spring 원인 | 권장 처리 |
| --- | --- | --- | --- |
| Gmail OAuth 연결 | 환경/bean 문제 시 내부 오류 | `IllegalArgumentException` 또는 설정 누락 | `UNSUPPORTED_SERVICE`/설정 오류를 표준화 |
| Gmail label picker 열기 | `target option provider를 찾을 수 없습니다: gmail` | `GmailTargetOptionProvider` 없음 | provider 구현 및 표준 API error shape |
| Gmail source preview | FastAPI 실패가 `FASTAPI_UNAVAILABLE`로 표시 | runtime 지원/권한/API 오류 미분리 | FastAPI error code 매핑 |
| Gmail sink 실행 | scope 부족이 실행 후 외부 API 실패로 표시 가능 | `gmail.send` 사전 검증 없음 | role/action별 scope 검증 |
| Gmail draft 선택 | runtime 미확인 상태에서 노출 | sink schema가 `draft`까지 노출 | action options를 runtime과 정렬 |
| Gmail 포함 template 실행 | OAuth/scope/target 누락 가능 | template이 Gmail workflow를 생성 | template은 허용하고 node lifecycle/preflight에서 안내 |

### 7.6 권장 작업 순서

1. 선택지 C를 기준으로 Gmail OAuth/source/sink catalog를 유지한다.
2. `GmailTargetOptionProvider`를 구현하고 `label_emails.picker_supported=true`로 바꾼다.
3. `OAuthTokenService`에 기능별 scope 검증 API를 추가한다.
4. `NodeLifecycleService`, `ExecutionService`, `TargetOptionService`에서 Gmail role/mode/action별 required scope를 적용한다.
5. Gmail sink `action` options를 FastAPI 실제 지원 범위와 제품 노출 정책에 맞춘다.
6. `FastApiClient`가 FastAPI error body를 파싱해 OAuth/scope/external/runtime 오류를 구분하도록 개선한다.
7. `WorkflowValidator` 또는 lifecycle/preflight 흐름에서 Gmail token/scope/target/runtime readiness를 구분한다.
8. FastAPI error mapping을 이번 PR 범위에 포함한다.
   - `FastApiClient` error body parser와 mapping 테스트를 추가한다.
9. 테스트를 추가한다.
   - Gmail label target-options provider 없음 또는 있음 케이스
   - Gmail sink send scope 부족 시 `oauth_scope_insufficient`
   - Gmail source read scope 부족 시 `oauth_scope_insufficient`
   - Gmail draft disabled 시 preflight 실패
   - FastAPI `OAUTH_SCOPE_INSUFFICIENT` error mapping

### 7.7 최종 설계 판단

현재 Spring Boot 서버에서 Gmail 오류가 나는 가장 직접적인 지점은 Gmail source target-options다. catalog는 Gmail source와 `label_picker`를 노출하지만 Spring에는 Gmail target option provider가 없다.

OAuth connector는 현재 존재하므로 Gmail을 전부 미지원으로 보는 것은 최신 코드와 맞지 않는다. 선택지 C가 최종 판단이므로 source/sink/OAuth를 열어두되, Gmail OAuth token을 기능별 scope로 검증하고, FastAPI runtime error를 Spring preflight/status에서 구분할 수 있어야 한다.

따라서 이번 Spring Boot 기준 설계는 다음으로 확정한다.

- Gmail OAuth connector는 유지한다.
- Gmail source catalog는 Spring catalog 기준 6개 mode를 유지한다.
- Gmail sink는 `send` 중심으로 지원하되 `gmail.send` scope 검증을 추가한다.
- `GmailTargetOptionProvider`를 구현해 `label_emails` remote picker를 실제 동작하게 한다.
- Gmail source read/label picker에는 `gmail.readonly` scope 검증을 적용한다.
- FastAPI canonical payload 계약은 반영되었으므로 Spring은 FastAPI error body를 파싱해 OAuth/scope/external/runtime 오류를 FE가 표시 가능한 형태로 변환한다.
- Gmail required template은 차단하지 않고 OAuth/scope/status/preflight 흐름으로 진입하게 둔다.
