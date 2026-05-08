# Gmail 노드 오류 관련 Spring Boot 확인 및 수정 요청

> 작성일: 2026-05-08  
> FE 브랜치: `feat#145-gmail-error-check-and-fix&update`  
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

FE 쪽 현재 임시 설계 판단은 다음과 같다.

- 실제 API 확인이 불가능하거나 Gmail connector 미지원이면 Gmail 신규 진입을 닫는다.
- Gmail 발송이 확인되면 Gmail sink만 다시 열 수 있다.
- Gmail source/read/label target-options까지 확인되어야 Gmail source를 다시 열 수 있다.

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

- 실제 지원하지 않는 Gmail source mode는 catalog에서 제외하거나 FE와 협의해 rollout에서 닫을 수 있게 알려달라.
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
- endpoint가 미구현이면 FE가 Gmail source를 닫을 수 있도록 명확히 알려달라.

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

### 3.7 Template instantiate 방어 관련 요청

FE 코드 확인 결과, 템플릿 상세 화면은 `requiredServices`를 표시하고 곧바로 아래 API를 호출한다.

```http
POST /api/templates/{id}/instantiate
```

따라서 FE에서 새 노드 추가 UI의 Gmail을 닫아도 Gmail required template 경로로 Gmail node가 생성될 수 있다.

FE 1차 설계:

- Gmail 전체 비활성화 상태에서는 Gmail required template의 “가져오기” 버튼을 비활성화한다.
- 목록에서 템플릿 자체를 숨기지는 않는다.

Spring 팀 확인 요청:

- `TemplateSummary.requiredServices`만으로는 Gmail source와 sink를 구분할 수 없다.
- 선택지 B처럼 Gmail sink만 지원하는 경우에는 template detail의 `nodes`를 보고 Gmail node role/source/sink를 판정해야 할 수 있다.
- 서버에서 template instantiate 단계에도 unsupported service 검증을 할 수 있는지 확인해 달라.
- FE 방어가 있더라도 API 차원에서 unsupported Gmail workflow 생성을 막을 수 있으면 더 안전하다.

요청 후보:

- `POST /api/templates/{id}/instantiate`에서 unsupported service가 포함되면 표준 error code를 반환
- 또는 template detail/summary에 서비스별 지원 상태나 unsupported reason 제공

---

## 4. FE 지원 범위 확정에 필요한 Spring 답변

아래 항목에 답을 주시면 FE에서 Gmail 노출 정책을 확정할 수 있다.

| 질문 | 답변에 따른 FE 선택 |
| --- | --- |
| `/oauth-tokens/gmail/connect`가 동작하는가? | 아니오면 Gmail 전체 비활성화 |
| Gmail token에 `gmail.send` scope가 있는가? | 예면 Gmail sink 후보 |
| Gmail sink schema가 안정적으로 내려오는가? | 예면 Gmail sink 유지 가능 |
| Gmail read/label/search scope가 있는가? | 예면 Gmail source 후보 |
| Gmail source catalog mode들이 실제 runtime과 일치하는가? | 예면 source rollout 유지 가능 |
| `label_emails` target-options가 동작하는가? | 예면 `label_picker` FE 보정 가능 |
| 키워드 검색 source mode가 필요한가? | 필요하면 새 catalog mode 협의 |
| template instantiate에서 unsupported Gmail을 막을 수 있는가? | 가능하면 FE와 서버 이중 방어 |

---

## 5. FE 현재 권장 판단

Spring에서 Gmail OAuth/source/sink 지원이 명확히 확인되기 전까지 FE는 아래로 진행하는 것이 안전하다.

1. Gmail source 신규 추가 차단
2. Gmail sink 신규 추가 차단
3. Gmail OAuth 신규 연결 차단
4. Gmail required template 상세에서 가져오기 버튼 비활성화
5. 기존 Gmail node와 email data type 표시 로직은 유지

Spring에서 Gmail sink만 확인되면 FE는 Gmail sink만 다시 열 수 있다.  
Spring에서 Gmail source, label target-options, read scope까지 확인되면 FE는 Gmail source와 `label_picker`를 다시 열 수 있다.

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

FastAPI는 runtime capability와 payload schema를 위 설계대로 정렬하되, FE에서 Gmail source/sink/OAuth를 실제로 다시 여는 결정은 Spring OAuth, catalog, schema, target-options 확인 이후 진행하는 것이 안전하다.
