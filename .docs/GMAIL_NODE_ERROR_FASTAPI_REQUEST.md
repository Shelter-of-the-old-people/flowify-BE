# Gmail 노드 오류 관련 FastAPI 확인 및 수정 요청

> 작성일: 2026-05-08
> 브랜치: `9-gmail-node-error-fix`
> 관련 FE 문서: `docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`, `docs/GMAIL_NODE_ERROR_FIX_DESIGN.md`
> 대상: FastAPI 개발 팀
> 목적: Gmail source/sink runtime 지원 여부와 payload 계약을 확인하고, 향후 Gmail 발송 및 필터링 기능을 온전하게 구현하기 위한 요청 사항을 정리한다.

---

## 1. 배경

FE에서는 Gmail 노드를 source/sink/OAuth 대상으로 노출하고 있었지만, Spring 백엔드 점검 문서 기준으로 Gmail connector는 미구현 상태로 기록되어 있다.

FastAPI runtime 관점에서는 아래 기능이 Gmail 노드와 연결된다.

- Gmail source 실행
  - 특정 메일 조회
  - 새 메일 조회
  - 특정 발송인 메일 조회
  - 별표/중요 메일 조회
  - 라벨 메일 목록 조회
  - 첨부파일 있는 메일 조회
- Gmail sink 실행
  - 다른 사용자에게 메일 발송
  - 향후 초안 저장
- Gmail payload normalized schema 생성
  - `SINGLE_EMAIL`
  - `EMAIL_LIST`
  - `FILE_LIST`
- 향후 Gmail preview
  - source metadata preview
  - sink no-write preview

FE의 최신 판단은 선택지 C, 즉 Gmail source/sink/OAuth 진입을 유지하는 것이다. FastAPI 팀은 Gmail runtime 지원 범위와 canonical payload를 명확히 제공해 FE data preview, Spring catalog, node lifecycle/status가 같은 계약을 바라보게 해야 한다.

---

## 2. 로컬 서버 확인 결과

현재 FE 작업 환경에서 `8000` 포트에 Python 계열 서버가 LISTEN 중이다.

비인증 직접 호출:

```http
GET http://127.0.0.1:8000/editor-catalog/sources
```

응답:

```json
{
  "success": false,
  "error_code": "UNAUTHORIZED",
  "message": "유효하지 않은 내부 인증 토큰입니다.",
  "detail": null
}
```

따라서 FastAPI는 내부 인증 토큰을 요구하는 것으로 보이며, FE 터미널에서 직접 Gmail runtime 지원 여부를 확인할 수는 없었다.

요청:

- Spring -> FastAPI 호출 시 필요한 내부 인증 헤더/토큰 계약을 문서화해 달라.
- Gmail runtime endpoint를 Spring에서 호출할 때 인증 실패와 Gmail 권한 실패가 구분되도록 error code를 내려달라.

---

## 3. FastAPI에서 확인이 필요한 Gmail runtime 범위

### 3.1 Gmail source mode 지원 여부

Spring source catalog 기준 mode 후보:

| mode key | 의미 | 기대 output type | FastAPI 지원 필요 |
| --- | --- | --- | --- |
| `single_email` | 특정 메일 사용 | `SINGLE_EMAIL` | 특정 message id 또는 picker target 기반 조회 |
| `new_email` | 새 메일 도착/최신 메일 | `SINGLE_EMAIL` | 최신/신규 메일 조회 정책 필요 |
| `sender_email` | 특정 발송인 메일 | `SINGLE_EMAIL` 또는 정책상 `EMAIL_LIST` | 발송인 filter query |
| `starred_email` | 별표/중요 메일 | `SINGLE_EMAIL` 또는 `EMAIL_LIST` | Gmail label/query 기반 조회 |
| `label_emails` | 라벨 메일 목록 | `EMAIL_LIST` | label id 기반 목록 조회 |
| `attachment_email` | 첨부파일 있는 메일 | `FILE_LIST` | 첨부파일 추출/파일 payload 변환 |

요청:

- 실제 FastAPI runtime이 지원하는 mode를 알려달라.
- 지원하지 않는 mode는 Spring catalog에서 제외하거나 Spring/FE가 unsupported status로 표현할 수 있게 명확한 error code를 내려달라.
- 각 mode가 반환하는 canonical output type을 확정해 달라.
- `sender_email`, `starred_email`이 단일 메일을 반환하는지 목록을 반환하는지 명확히 정해 달라.

---

### 3.2 Gmail sink 지원 여부

미래 핵심 기능:

- Gmail 노드에서 다른 사용자에게 메일을 발송하는 기능

FastAPI에서 필요한 동작:

- 이전 노드 output을 받아 이메일 payload를 만든다.
- Spring이 전달한 Gmail OAuth access token으로 Gmail API send를 호출한다.
- 실제 발송 성공/실패 결과를 normalized execution output으로 반환한다.

확인 요청:

- Gmail send runtime이 구현되어 있는가
- draft 저장도 지원하는가, 아니면 send만 지원하는가
- 수신자 field key는 `to`인가 `recipient`인가
- 복수 수신자를 지원하는가
- cc/bcc를 지원하는가
- subject/body를 config에서 소비하는가, input data에서 소비하는가
- attachment 전달을 지원하는가

권장 1차 범위:

- 1차는 `send`만 지원
- 수신자는 단일 email string
- subject는 config field
- body는 config template 또는 이전 TEXT output
- attachment는 후속 범위
- draft 저장은 후속 범위

---

## 4. Canonical payload 계약 요청

FE data panel과 downstream node가 안정적으로 동작하려면 FastAPI output payload가 canonical schema를 따라야 한다.

### 4.1 `SINGLE_EMAIL`

권장 payload:

```json
{
  "type": "SINGLE_EMAIL",
  "email": {
    "id": "msg-123",
    "threadId": "thread-123",
    "subject": "메일 제목",
    "from": "sender@example.com",
    "to": ["user@example.com"],
    "date": "2026-05-08T10:00:00Z",
    "body": "본문 전체 또는 정제된 본문",
    "bodyPreview": "본문 일부",
    "labels": ["INBOX", "STARRED"],
    "attachments": [
      {
        "id": "att-1",
        "filename": "report.pdf",
        "mimeType": "application/pdf",
        "size": 1024
      }
    ]
  }
}
```

FE 현재 preview UI는 `subject`, `from`, `sender`, `date`, `body`, `bodyPreview`, `attachments`류 필드를 사용할 수 있어야 한다.

요청:

- `from`과 `sender` 중 authoritative field를 정해 달라.
- 가능하면 Gmail 원본 header를 그대로 노출하기보다 normalized `from`, `to`, `subject`, `date`를 제공해 달라.

### 4.2 `EMAIL_LIST`

권장 payload:

```json
{
  "type": "EMAIL_LIST",
  "emails": [
    {
      "id": "msg-1",
      "threadId": "thread-1",
      "subject": "메일 제목",
      "from": "sender@example.com",
      "date": "2026-05-08T10:00:00Z",
      "bodyPreview": "본문 일부",
      "labels": ["INBOX"]
    }
  ],
  "metadata": {
    "count": 1,
    "truncated": false,
    "sourceMode": "label_emails"
  }
}
```

요청:

- list payload에서는 전체 body를 항상 포함할지, preview만 포함할지 정책을 정해 달라.
- 대량 메일 조회 시 limit/truncated metadata를 제공해 달라.
- FE/LLM downstream이 메일별 정보를 잃지 않도록 각 email item은 독립 객체로 유지해 달라.

### 4.3 `FILE_LIST` for Gmail attachments

`attachment_email` mode가 `FILE_LIST`를 반환한다면 권장 payload:

```json
{
  "type": "FILE_LIST",
  "files": [
    {
      "id": "gmail-msg-123:att-1",
      "name": "invoice.pdf",
      "mimeType": "application/pdf",
      "size": 2048,
      "source": "gmail",
      "messageId": "msg-123",
      "attachmentId": "att-1",
      "content": null,
      "downloadUrl": null
    }
  ],
  "metadata": {
    "count": 1,
    "truncated": false
  }
}
```

요청:

- attachment content를 runtime에서 바로 포함할지, metadata only로 둘지 정해 달라.
- Google Drive sink 등 downstream에서 사용할 수 있는 file abstraction으로 맞춰 달라.

### 4.4 Gmail send result

Gmail sink 실행 결과 권장 payload:

```json
{
  "type": "SEND_RESULT",
  "service": "gmail",
  "status": "sent",
  "messageId": "gmail-sent-message-id",
  "threadId": "thread-id",
  "to": ["recipient@example.com"],
  "subject": "발송 제목"
}
```

요청:

- 현재 output node가 별도 outputDataType을 갖지 않는다면 execution log/result에 위 정보를 담는 방식을 알려달라.
- 실패 시 Gmail API error를 사용자에게 보여줄 수 있게 sanitized message를 내려달라.

---

## 5. Gmail 필터링 기능 설계 요청

미래 기능:

- 특정 키워드 또는 발송인을 기준으로 메일을 필터링하는 기능

현재 FE/문서 기준 판단:

- 발송인 기준은 Spring catalog에 `sender_email` mode가 있으므로 source-level 조회와 잘 맞는다.
- 키워드 기준은 현재 Spring catalog에 `search_email` mode가 없으므로 FE가 임의로 만들면 안 된다.
- 키워드 필터링은 1차로 Gmail source 이후 중간 `filter`, `condition`, `data-process`, `AI` 노드에서 처리할 수 있다.

FastAPI 팀에 요청:

### 5.1 발송인 기준 필터링

`sender_email` mode를 지원한다면:

- config target이 발송인 email string인지 확인
- Gmail API query 예: `from:sender@example.com`
- 반환 타입을 `SINGLE_EMAIL`로 할지 `EMAIL_LIST`로 할지 확정
- 여러 메일이 매칭될 때 최신 1건만 반환할지 목록을 반환할지 확정

권장:

- 발송인 기준은 본질적으로 여러 메일이 매칭될 수 있으므로 장기적으로 `EMAIL_LIST`가 더 자연스럽다.
- 다만 현재 Spring catalog가 `SINGLE_EMAIL`로 정의되어 있다면 우선 catalog를 따른다.

### 5.2 키워드 기준 필터링

두 가지 구현 선택지가 있다.

#### 선택지 1: source-level Gmail search

FastAPI가 Gmail API query를 직접 수행한다.

예:

```text
subject:(keyword)
keyword
from:sender@example.com keyword
```

필요한 Spring/FE 변경:

- Spring source catalog에 실제 mode key 추가
  - 예: `keyword_emails` 또는 `search_emails`
- FE source rollout에 해당 key 추가
- target schema를 `text_input` 또는 복합 schema로 정의

주의:

- 과거 문서의 `search_email`은 현재 Spring catalog key가 아니므로 그대로 사용하지 않는다.
- 새 mode key는 Spring/FastAPI/FE가 함께 확정해야 한다.

#### 선택지 2: source 이후 중간 filter

Gmail source는 `label_emails`, `new_email`, `sender_email` 등으로 메일을 가져오고, 이후 FE workflow의 filter/condition/AI 노드가 키워드를 처리한다.

장점:

- Gmail source catalog 변경 없이 가능하다.
- FE의 기존 mapping rules에 이메일 subject/sender/body preview 추출/분류 흐름이 이미 있다.
- source query와 처리 filter 책임이 분리된다.

권장:

- 1차 구현은 선택지 2를 우선한다.
- source-level search는 Gmail API query semantics가 제품 요구로 확정된 뒤 별도 mode로 추가한다.

---

## 6. OAuth token 전달 계약

FastAPI는 Spring에서 전달하는 service token을 사용해 Gmail API를 호출할 것으로 예상한다.

확인 요청:

- service token map에서 Gmail key가 `gmail`인지 확인
- token이 FastAPI에서 바로 사용할 수 있는 decrypted access token인지 확인
- refresh token이 필요한 경우 Spring이 refresh 후 access token을 넘기는지 확인
- scope 부족을 FastAPI가 감지하면 Spring/FE에 어떤 error로 전달하는지 확인

권장 error code:

| 상황 | 권장 error code |
| --- | --- |
| Gmail token 없음 | `OAUTH_TOKEN_MISSING` |
| Gmail scope 부족 | `OAUTH_SCOPE_INSUFFICIENT` |
| Gmail API 401/403 | `EXTERNAL_AUTH_ERROR` 또는 scope-specific error |
| Gmail API rate limit | `EXTERNAL_RATE_LIMITED` |
| Gmail API 일반 실패 | `EXTERNAL_API_ERROR` |
| Gmail runtime mode 미구현 | `RUNTIME_MODE_UNSUPPORTED` |

---

## 7. Preview 관련 요청

이번 FE 이슈의 핵심 범위는 preview 구현이 아니다.

다만 향후 Gmail preview를 위해 아래 방향을 요청한다.

### 7.1 Gmail source metadata preview

목표:

- 실제 workflow 실행 없이 Gmail source가 가져올 예상 메일 목록 일부를 보여준다.

요청:

- write side effect 없어야 함
- metadata 중심 응답
- `limit`, `truncated` 제공
- body 전체 포함 여부는 옵션화
- source node token만 필요해야 함

### 7.2 Gmail sink no-write preview

목표:

- 실제 메일 발송 없이 수신자, 제목, 본문, 첨부 예정 데이터를 보여준다.

요청:

- Gmail API send/create draft 호출 금지
- payload builder와 실제 sender 분리
- preview 결과에 `to`, `subject`, `bodyPreview`, `attachments` 포함

---

## 8. Spring 팀과 맞춰야 하는 계약

FastAPI 단독으로 결정하면 안 되는 항목:

| 항목 | Spring과 맞출 내용 |
| --- | --- |
| Gmail source mode key | Spring source catalog key와 일치 |
| Gmail source target schema | FE picker/input 렌더링 기준 |
| Gmail sink schema field key | FE 설정 저장 key와 일치 |
| OAuth service token key | `gmail` 사용 |
| scope 부족 표현 | node status `oauth_scope_insufficient`로 연결 |
| runtime error code | Spring API error shape로 변환 |
| template instantiate 가능 여부 | unsupported Gmail workflow 생성 방어 |

---

## 9. FastAPI 팀에 필요한 답변

FE/Spring 노출 정책 확정을 위해 아래 질문에 답을 부탁드린다.

| 질문 | 필요 이유 |
| --- | --- |
| Gmail source runtime이 현재 구현되어 있는가? | FE source rollout 유지 여부 |
| 어떤 Gmail source mode가 실제 동작하는가? | mode 단위 노출 제어 |
| 각 mode의 output type은 무엇인가? | FE data type/payload 표시 |
| Gmail sink send가 구현되어 있는가? | Gmail 발송 기능 활성화 여부 |
| Gmail draft 저장이 구현되어 있는가? | sink action options |
| Gmail attachment 처리가 구현되어 있는가? | `FILE_LIST` 계약 |
| 발송인 기준 필터는 source-level로 가능한가? | `sender_email` mode 계약 |
| 키워드 기준 필터는 source-level로 구현할 계획인가? | 신규 mode 필요 여부 |
| Gmail API error를 어떤 code로 반환하는가? | FE 사용자 메시지 |
| service token의 scope 부족을 감지할 수 있는가? | node status/실행 조건 표시 |

---

## 10. FE 선택지 C 전환 판단

FE 요구사항은 Gmail source/sink를 모두 유지하는 선택지 C로 전환되었다.

FE는 다음처럼 동작하는 것을 목표로 한다.

1. Gmail source 신규 추가 허용
2. Gmail sink 신규 추가 허용
3. Gmail OAuth 신규 연결 허용
4. Gmail required template 인스턴스화 허용
5. Gmail source/sink 결과를 canonical data preview UI로 표시

따라서 FastAPI는 Gmail source runtime, source preview, sink send result, error code를 Spring/FE가 처리 가능한 계약으로 맞춰야 한다.

키워드 필터링은 현재 FE가 임의 source mode를 만들지 않고, 우선 중간 filter/condition/AI 노드 조합으로 처리하는 방향을 권장한다. Source-level Gmail search가 제품 요구로 확정되면 Spring catalog와 FastAPI runtime mode를 함께 추가해야 한다.

---

## 11. FastAPI 측 재검토 결과 및 수정 설계

> 재검토일: 2026-05-08
> 기준 문서: `.docs/GMAIL_NODE_ERROR_SPRING_BOOT_REQUEST.md`와 본 문서의 요청 사항
> 범위: FastAPI runtime/source/sink/payload 계약 정렬. Spring OAuth, catalog, schema, target-options 구현은 Spring Boot 담당 범위로 분리한다.

Spring Boot 요청 문서와 대조한 결과, FastAPI에는 Gmail runtime 코드가 일부 존재하지만 FE/Spring이 기대하는 canonical payload 계약과 일부 차이가 있다.

FastAPI는 아래 방향으로 수정한다.

1. Spring catalog에 없는 Gmail mode key를 FastAPI에서 임의로 추가하지 않는다.
2. 현재 Spring source catalog 후보인 6개 mode만 runtime 지원 범위로 유지한다.
3. Gmail source output을 FE data panel/downstream node가 안정적으로 처리할 수 있는 canonical schema로 정렬한다.
4. 기존 runtime/downstream 호환을 위해 `items` alias는 일정 기간 유지한다.
5. Gmail sink는 FastAPI 코드상 `send`와 `draft`가 가능하지만, 제품 1차 노출은 Spring/FE 협의 전까지 `send` 중심으로 판단한다.
6. 키워드 검색용 `search_email` 또는 유사 mode는 추가하지 않고, 1차는 filter/condition/AI 등 중간 노드 조합으로 처리한다.

### 11.1 Gmail source mode별 FastAPI 지원 정책

| mode key | FastAPI runtime 동작 | canonical output type | 1차 정책 |
| --- | --- | --- | --- |
| `single_email` | `target`을 Gmail message id로 보고 단일 메시지 조회 | `SINGLE_EMAIL` | 지원 |
| `new_email` | Gmail message list 최신 1건 조회 | `SINGLE_EMAIL` | 지원 |
| `sender_email` | `from:{target}` query 최신 1건 조회 | `SINGLE_EMAIL` | 지원 |
| `starred_email` | `is:starred` query 최신 1건 조회 | `SINGLE_EMAIL` | 지원 |
| `label_emails` | `label:{target}` query 목록 조회 | `EMAIL_LIST` | 지원 |
| `attachment_email` | `has:attachment` query 최신 1건의 첨부 metadata 조회 | `FILE_LIST` | metadata only 지원 |

`sender_email`, `starred_email`은 여러 메일이 매칭될 수 있지만, 현재 Spring catalog의 기대 타입과 기존 runtime 흐름을 고려해 1차에서는 최신 1건 `SINGLE_EMAIL`로 고정한다. 장기적으로 목록형이 필요하면 Spring catalog의 canonical type 변경 또는 별도 mode 추가를 협의해야 한다.

### 11.2 `SINGLE_EMAIL` payload 수정 설계

FastAPI source/preview는 `SINGLE_EMAIL`을 아래 구조로 반환하도록 정렬한다.

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
    "body": "본문 전체 또는 정제된 본문",
    "bodyPreview": "본문 일부",
    "labels": ["INBOX", "STARRED"],
    "attachments": [
      {
        "id": "gmail-msg-123:att-1",
        "filename": "report.pdf",
        "mimeType": "application/pdf",
        "size": 1024,
        "source": "gmail",
        "messageId": "msg-123",
        "attachmentId": "att-1",
        "content": null,
        "downloadUrl": null
      }
    ]
  }
}
```

필드 정책:

- authoritative sender field는 `from`으로 둔다.
- `sender`는 FE 호환을 위한 alias로만 제공한다.
- `to`는 가능한 경우 list로 정규화한다.
- `bodyPreview`는 Gmail `snippet` 또는 body 앞부분으로 생성한다.
- `date`는 ISO 변환을 시도하되, 변환 실패 시 Gmail 원본 header 문자열을 유지한다.
- 빈 결과는 같은 type을 유지하되 `email`에 빈 객체 또는 `null`을 둘 수 있다. 구현 시 기존 FE 호환을 우선해 빈 email 객체를 반환하는 방식을 우선 검토한다.

### 11.3 `EMAIL_LIST` payload 수정 설계

`label_emails`는 아래 구조로 반환한다.

```json
{
  "type": "EMAIL_LIST",
  "emails": [
    {
      "id": "msg-1",
      "threadId": "thread-1",
      "subject": "메일 제목",
      "from": "sender@example.com",
      "sender": "sender@example.com",
      "date": "2026-05-08T10:00:00Z",
      "bodyPreview": "본문 일부",
      "labels": ["INBOX"]
    }
  ],
  "items": [
    {
      "id": "msg-1",
      "threadId": "thread-1",
      "subject": "메일 제목",
      "from": "sender@example.com",
      "sender": "sender@example.com",
      "date": "2026-05-08T10:00:00Z",
      "bodyPreview": "본문 일부",
      "labels": ["INBOX"]
    }
  ],
  "metadata": {
    "count": 1,
    "truncated": false,
    "sourceMode": "label_emails"
  }
}
```

정책:

- canonical list field는 `emails`로 둔다.
- 기존 executor/downstream 호환을 위해 `items` alias를 당분간 함께 제공한다.
- list item에는 기본적으로 전체 `body`를 포함하지 않고 `bodyPreview` 중심으로 제공한다.
- preview에서 `include_content=true`인 경우에만 list item에 `body` 포함을 검토한다.
- `maxResults` 또는 preview `limit` 기준으로 `metadata.count`, `metadata.truncated`를 제공한다.

### 11.4 `FILE_LIST` payload 수정 설계

`attachment_email`은 아래 구조로 반환한다.

```json
{
  "type": "FILE_LIST",
  "files": [
    {
      "id": "gmail-msg-123:att-1",
      "name": "invoice.pdf",
      "filename": "invoice.pdf",
      "mimeType": "application/pdf",
      "mime_type": "application/pdf",
      "size": 2048,
      "source": "gmail",
      "messageId": "msg-123",
      "attachmentId": "att-1",
      "content": null,
      "downloadUrl": null,
      "url": ""
    }
  ],
  "items": [
    {
      "id": "gmail-msg-123:att-1",
      "name": "invoice.pdf",
      "filename": "invoice.pdf",
      "mimeType": "application/pdf",
      "mime_type": "application/pdf",
      "size": 2048,
      "source": "gmail",
      "messageId": "msg-123",
      "attachmentId": "att-1",
      "content": null,
      "downloadUrl": null,
      "url": ""
    }
  ],
  "metadata": {
    "count": 1,
    "truncated": false
  }
}
```

정책:

- canonical list field는 `files`로 둔다.
- 기존 Google Drive sink 등 downstream 호환을 위해 `items`, `filename`, `mime_type`, `url` alias를 당분간 함께 제공한다.
- 1차 구현은 attachment content를 포함하지 않는 metadata only 방식이다.
- Gmail attachment를 바로 Google Drive sink에 업로드하려면 attachment download/content fetch 기능이 추가로 필요하므로 후속 범위로 둔다.

### 11.5 Gmail sink 수정 설계

현재 FastAPI output node는 Gmail `send`와 `draft`를 호출할 수 있다. 다만 Spring/FE 1차 rollout 판단과 맞추기 위해 아래 계약으로 정리한다.

| 항목 | 1차 FastAPI 정책 |
| --- | --- |
| service key | `gmail` |
| 수신자 field | `to` |
| 수신자 형태 | 단일 email string |
| 제목 field | `subject` |
| 본문 field | `config.body` 우선, 없으면 이전 `TEXT.content` |
| action | FastAPI는 `send`, `draft` 처리 가능. Spring/FE 노출은 `send` 우선 권장 |
| cc/bcc | 후속 범위 |
| 복수 수신자 | 후속 범위 |
| attachment send | FastAPI helper는 존재하지만 제품 1차 범위에서는 후속으로 판단 |

Gmail send 결과는 기존 output node wrapper를 유지하면서 `detail` 안을 canonical `SEND_RESULT`로 정렬한다.

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

draft 결과는 Spring/FE가 action을 노출하기로 협의한 경우 아래 형태를 사용한다.

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

### 11.6 Preview 수정 설계

Gmail source preview는 runtime source와 같은 canonical schema를 사용한다.

- source preview는 write side effect가 없어야 한다.
- `limit`, `include_content`를 반영한다.
- `include_content=false`면 `body`는 비우거나 생략하고 `bodyPreview`는 유지한다.
- `label_emails` preview는 `emails`, `items`, `metadata.truncated`를 반환한다.
- sink no-write preview는 이번 1차 수정 범위에는 포함하지 않고, payload builder와 sender 분리 작업이 필요할 때 별도 진행한다.

### 11.7 Error code 및 인증 계약

현재 FastAPI 내부 인증과 OAuth 실패는 구분되어 있다.

| 상황 | 현재/수정 정책 |
| --- | --- |
| Spring -> FastAPI 내부 인증 실패 | `UNAUTHORIZED` |
| Gmail token 없음 | `OAUTH_TOKEN_INVALID` 또는 향후 `OAUTH_TOKEN_MISSING` |
| Gmail API 401 | `OAUTH_TOKEN_INVALID` |
| Gmail API 403 scope 부족 | 가능하면 `OAUTH_SCOPE_INSUFFICIENT` 추가 |
| Gmail API rate limit | 가능하면 `EXTERNAL_RATE_LIMITED` 추가 |
| 기타 Gmail API 실패 | `EXTERNAL_API_ERROR` |
| FastAPI runtime mode 미지원 | 현재 `UNSUPPORTED_RUNTIME_SOURCE` / `UNSUPPORTED_RUNTIME_SINK` 유지 |

Spring API error shape로의 최종 변환은 Spring Boot 담당 범위이므로, FastAPI는 가능한 한 구분 가능한 error code와 sanitized detail을 제공한다.

### 11.8 코드 수정 대상

예상 수정 파일:

- `app/services/integrations/gmail.py`
  - Gmail message/header/attachment normalization 보강
  - `threadId`, `labelIds`, `bodyPreview`, attachment id metadata 제공
- `app/core/nodes/input_node.py`
  - Gmail source payload를 `email`/`emails`/`files` canonical schema로 변경
  - 기존 `items` alias 유지
- `app/core/engine/preview_executor.py`
  - Gmail source preview schema를 runtime source와 동일하게 정렬
- `app/core/nodes/output_node.py`
  - Gmail send/draft 결과를 `SEND_RESULT` detail로 정규화
- `app/common/errors.py`
  - scope/rate-limit 구분이 필요하면 error code 추가 검토
- `tests/test_input_node.py`
  - Gmail source payload 기대값 갱신
- `tests/test_output_node.py`
  - Gmail send/draft result 기대값 갱신
- `tests/test_preview_executor.py`
  - Gmail source preview schema 테스트 추가 또는 갱신

### 11.9 Spring/FE 노출 정책에 대한 FastAPI 답변 초안

FastAPI 측 답변은 아래와 같이 정리한다.

1. Gmail source runtime은 현재 6개 mode 기준으로 지원 가능하도록 정렬한다.
2. `sender_email`, `starred_email`은 1차에서 최신 1건 `SINGLE_EMAIL`을 반환한다.
3. `label_emails`는 `EMAIL_LIST`, `attachment_email`은 `FILE_LIST`를 반환한다.
4. Gmail attachment는 1차 metadata only로 반환하며 content download/전달은 후속 범위다.
5. Gmail sink send는 구현되어 있으며, 1차 계약은 단일 `to`, `subject`, TEXT body 기반으로 둔다.
6. draft는 FastAPI helper가 있으나 Spring/FE action 노출 여부는 별도 협의가 필요하다.
7. keyword Gmail search mode는 이번 범위에서 추가하지 않는다.
8. FE는 선택지 C 기준으로 Gmail source/sink/OAuth 진입을 연다. 따라서 Spring OAuth connector, scope, source catalog, target-options, sink schema는 FE 노출을 막는 근거가 아니라 status/preflight/error mapping으로 사용자에게 명확히 보여야 하는 서버 계약이다.

### 11.10 FE 선택지 C 전환에 따른 FastAPI 완료 기준

FE 요구사항은 Gmail source/sink를 모두 유지하는 선택지 C로 전환되었다.

따라서 FastAPI는 Gmail runtime과 preview 계약을 아래 기준으로 완료해야 하며, 현재 FastAPI 서버 코드에는 이 기준을 반영했다.

1. Spring source catalog에 있는 Gmail 6개 mode만 처리한다.
2. mode별 output은 `SINGLE_EMAIL`, `EMAIL_LIST`, `FILE_LIST` canonical schema를 따른다.
3. Gmail sink `send` 결과는 `SEND_RESULT` 또는 동등한 canonical result schema로 반환한다.
4. Gmail source preview는 runtime source와 같은 payload schema를 사용한다.
5. OAuth/scope/external API/runtime unsupported 오류는 Spring이 변환할 수 있도록 구분 가능한 error code로 내려준다. 이 항목은 payload/schema 정렬과 별개인 error mapping 완료 기준이다.
6. keyword search source mode는 이번 범위에서 추가하지 않는다.

FE 선택지 C 구현에서 Spring 변환 완료 전까지 남는 위험:

- FastAPI payload/schema와 error code 세분화는 정렬되었지만, Spring이 FastAPI error body를 파싱하지 않으면 runtime/source preview 실패가 `FASTAPI_UNAVAILABLE`로 뭉개질 수 있다.
- FastAPI는 scope 부족을 `OAUTH_SCOPE_INSUFFICIENT`로 내려주므로, Spring 변환이 빠지면 FE가 `권한 부족` 상태를 정확히 표시하기 어렵다.
- 외부 API 실패와 runtime unsupported가 구분되지 않으면 사용자는 재연결, 권한 재승인, target 재선택, 잠시 후 재시도 중 어떤 조치를 해야 하는지 알기 어렵다.

FastAPI 쪽 반영 상태:

| 항목 | 상태 |
| --- | --- |
| Gmail source 6개 mode canonical payload 정렬 | 반영 |
| Gmail sink send result schema 정렬 | 반영 |
| Gmail source preview schema 정렬 | 반영 |
| tests 갱신 | 반영 |
| FastAPI error code 추가 세분화 | 반영. `OAUTH_TOKEN_INVALID`, `OAUTH_SCOPE_INSUFFICIENT`, `EXTERNAL_API_ERROR`, `EXTERNAL_RATE_LIMITED`, `UNSUPPORTED_RUNTIME_SOURCE/SINK` 구분 |
| Spring `FastApiClient` error body parsing | Spring Boot PR에 반영. FastAPI `error_code`를 Spring `ErrorCode`로 변환 |

### 11.11 선택지 C 기준 남은 서버 의존성

FastAPI 계약 정렬 이후에도 선택지 C의 사용자 경험이 완성되려면 Spring Boot와 FE에서 아래 항목이 함께 맞아야 한다.

| 영역 | 남은 작업 |
| --- | --- |
| Spring OAuth/scope | Gmail source read, label picker, sink send scope를 기능별로 검증하고 `oauth_scope_insufficient`로 표현 |
| Spring target-options | `label_emails`용 Gmail label option provider 구현 및 `label_picker` 응답 shape 고정 |
| Spring preflight/status | token 없음, scope 부족, target 누락, FastAPI runtime 오류를 FE가 표시 가능한 missing field/error code로 변환 |
| FE add-node | Gmail source/sink/OAuth allowlist 복구와 최초 생성 위자드 `label_picker` remote 처리 |
| FE preview/data panel | `SINGLE_EMAIL.email`, `EMAIL_LIST.emails/items`, `FILE_LIST.files/items`, `SEND_RESULT` 표시 호환성 확인 |

선택지 C에서는 위 항목이 미완료라는 이유로 Gmail 진입을 숨기지 않는다. 대신 각 실패 지점을 인증 필요, 권한 부족, target 선택 필요, 외부 API 실패, runtime 실패로 나누어 사용자에게 설명 가능한 상태로 표시한다.

### 11.12 FastAPI Error Mapping 처리 방침

현재 FastAPI runtime payload/schema 정렬은 반영되었지만, Spring Boot `FastApiClient`가 FastAPI error body의 `error_code`를 세분화해 Spring error shape로 변환하는 작업은 별도다.

PR 범위 판단:

| PR 범위 | FastAPI error mapping 처리 |
| --- | --- |
| Gmail label picker + scope 검증 + sink send 정렬 | Spring Boot PR에 포함 |
| 선택지 C 서버 계약 완성 | FastAPI error mapping까지 포함해 진행 |

선택지 C 서버 계약 완성을 위해 아래 mapping과 테스트를 포함한다.

| FastAPI `error_code` | Spring/FE 기대 표현 |
| --- | --- |
| `OAUTH_SCOPE_INSUFFICIENT` | `oauth_scope_insufficient`, 사용자 문구 `권한 부족` |
| `OAUTH_TOKEN_INVALID` 또는 token missing 계열 | `oauth_token`, 재연결 안내 |
| `EXTERNAL_API_ERROR` | 외부 서비스 오류 |
| `EXTERNAL_RATE_LIMITED` | 요청 제한 또는 잠시 후 재시도 안내 |
| `UNSUPPORTED_RUNTIME_SOURCE`, `UNSUPPORTED_RUNTIME_SINK` | runtime/preflight unsupported |

권장 테스트:

- FastAPI `OAUTH_SCOPE_INSUFFICIENT` 응답이 Spring `OAUTH_SCOPE_INSUFFICIENT`로 변환된다.
- FastAPI token invalid/missing 응답이 OAuth 재연결 상태로 변환된다.
- FastAPI external API 실패가 일반 `FASTAPI_UNAVAILABLE`이 아니라 외부 서비스 오류로 보인다.
- Gmail source preview 실패가 raw FastAPI error body를 노출하지 않는다.
