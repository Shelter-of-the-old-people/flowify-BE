# Gmail Sender Display Name Design

> 작성일: 2026-05-15
> 대상 레포: `flowify-BE`
> 범위: Gmail 발신자 표시명 보장 기능을 위한 FastAPI 설계
> 관련 레포: `flowify-BE-spring`, `flowify-FE`

---

## 1. 목적

이 문서는 Gmail sink 발송 시 `From` 헤더의 발신자 표시명을
깨짐 없이, 그리고 가능한 한 안정적으로 `이름 + 이메일` 형식으로 보장하기 위한 FastAPI 설계를 정의한다.

이번 이슈의 목표는 아래와 같다.

- Gmail 메일 발송 시 표시명이 bare email fallback에만 머물지 않도록 한다.
- Spring이 제공하는 사용자 표시명을 Gmail `From` 헤더 구성의 우선 소스로 사용한다.
- 기존 Gmail `sendAs.displayName` 및 bare email fallback 경로를 유지한다.
- 기존 source/sink 및 다른 서비스 실행 경로를 깨뜨리지 않는다.

---

## 2. 배경

이전 이슈에서 Gmail 헤더 인코딩 깨짐 문제는 아래 방식으로 1차 수정되었다.

- Gmail 수신 시 `Subject`, `From`, `To` MIME decode
- Gmail 발송 시 `sendAs.displayName` 우선 사용
- 표시명이 없거나 조회 실패 시 bare email fallback

이 수정으로 아래 문제는 해결되었다.

- `ê¹€ë¯¼í˜¸`
- `ÃªÂ¹â¬Ã«Â¯Â¼Ã­ËÂ¸`

같은 깨진 문자열이 더 이상 사용자에게 노출되지 않는다.

하지만 실환경에서는 여전히 아래가 관찰되었다.

- 기대: `김민호 <mhtiger362@gmail.com>`
- 실제: `mhtiger362@gmail.com`

즉 버그는 닫혔지만,
표시명 보장이라는 제품 요구는 아직 충족되지 않았다.

---

## 3. 현재 구조 분석

### 3.1 FastAPI가 현재 가진 정보

FastAPI는 Spring으로부터 아래만 직접 받는다.

- `workflow`
- `service_tokens`
- `X-User-ID`

즉 Gmail `From` 헤더에 쓸 사용자 표시명 후보는 받지 않는다.

### 3.2 현재 GmailService 동작

현재 `app/services/integrations/gmail.py`는 아래 우선순위를 사용한다.

1. Gmail `settings/sendAs` 조회
2. primary/default sendAs 선택
3. `displayName`이 있으면 `이름 + 이메일`
4. 없으면 bare email

이 구조는 Gmail 계정 설정에 의존한다.

### 3.3 한계

- Gmail `sendAs.displayName`이 비어 있으면 표시명 보장 불가
- 로그인 사용자 이름과 Gmail 발송 표시명이 분리됨
- 애플리케이션 사용자 기준 일관된 발신자 표시를 만들 수 없음

---

## 4. 설계 목표

이번 이슈에서 FastAPI가 달성해야 하는 목표는 아래와 같다.

1. Spring이 전달한 사용자 표시명을 Gmail `From` 헤더 구성의 1순위로 사용한다.
2. 그 값이 없으면 기존 `sendAs.displayName`을 사용한다.
3. 그것도 없으면 bare email로 fallback 한다.
4. Gmail 이외의 서비스는 영향 없이 그대로 동작한다.

---

## 5. 입력 계약 변경

### 5.1 새 runtime context 수용

FastAPI는 execute/preview request body에 아래 구조가 추가되는 것을 허용해야 한다.

```json
{
  "workflow": { "...": "..." },
  "service_tokens": {
    "gmail": "ya29..."
  },
  "runtime_context": {
    "user_profile": {
      "user_id": "665f...",
      "email": "mhtiger362@gmail.com",
      "display_name": "김민호"
    }
  }
}
```

핵심 필드:

- `runtime_context.user_profile.display_name`
- `runtime_context.user_profile.email`

### 5.2 backward compatibility

이 필드는 optional이다.

즉 아래 모두 허용해야 한다.

- 새 Spring이 보낸 request
- 구버전 Spring 또는 테스트 코드가 보낸 기존 request

request body에 `runtime_context`가 없어도 예외를 내면 안 된다.

---

## 6. Gmail 표시명 결정 규칙

FastAPI는 Gmail 발송 시 아래 우선순위를 사용한다.

### 6.1 우선순위

1. `runtime_context.user_profile.display_name`
2. Gmail `sendAs.displayName`
3. bare email

### 6.2 이메일 주소 우선순위

보내는 주소의 authoritative source는 기존과 동일하게 Gmail 계정 정보다.

1. `sendAs.sendAsEmail`
2. Gmail profile `emailAddress`

즉 표시명만 Spring에서 보강하고,
보내는 실제 이메일 주소는 Gmail 계정 기준을 유지한다.

### 6.3 기대 결과

Spring이 `display_name = "김민호"`를 보냈고 Gmail 계정 이메일이 `mhtiger362@gmail.com`이면,
최종 `From` 헤더는 아래를 목표로 한다.

- `김민호 <mhtiger362@gmail.com>`

---

## 7. FastAPI 구현 책임

### 7.1 요청 모델 확장

FastAPI request model 또는 실행 컨텍스트에서 `runtime_context.user_profile.display_name`을 읽을 수 있어야 한다.

이 값은 Gmail sink 실행 시점에 접근 가능해야 한다.

### 7.2 GmailService 호출 규칙

`output_node.py`의 Gmail send/draft 경로는
사용자 표시명 후보를 `GmailService`에 전달해야 한다.

즉 현재의

- token
- to
- subject
- body
- attachments

외에

- `preferred_display_name`

같은 개념이 추가되어야 한다.

### 7.3 GmailService 내부 책임

`GmailService`는 아래를 책임진다.

- preferred display name이 있으면 그것을 사용
- 없으면 기존 `sendAs.displayName` 사용
- 최종적으로 MIME-safe `From` 헤더 생성

---

## 8. 상세 설계

### 8.1 실행 컨텍스트에서 표시명 읽기

권장 방향:

- request-level `runtime_context`를 executor가 각 node 실행에 함께 전달
- Gmail sink에서만 이 값을 꺼내 사용

중요한 점:

- source node, middle node, 다른 sink는 이 필드를 무시해도 된다
- Gmail sink만 선택적으로 사용한다

### 8.2 GmailService API 확장

현재:

- `send_message(token, to, subject, body, attachments=None)`
- `create_draft(token, to, subject, body, attachments=None)`

제안:

- `send_message(..., preferred_display_name="")`
- `create_draft(..., preferred_display_name="")`

### 8.3 `_get_sender_identity()` 규칙 변경

현재는 `sendAs.displayName` 중심이다.

변경 후는 아래처럼 동작해야 한다.

1. sender email 조회
2. preferred display name 있으면 우선 사용
3. 없으면 `sendAs.displayName`
4. 그것도 없으면 empty string

즉 함수는 아래 의미를 가져야 한다.

- `email_address`
- `resolved_display_name`

---

## 9. 예외 및 fallback 정책

### 9.1 표시명 없음

아래 경우는 정상으로 처리한다.

- `runtime_context` 없음
- `user_profile` 없음
- `display_name` 없음
- `display_name`이 공백

이 경우 기존 `sendAs.displayName -> bare email` fallback을 사용한다.

### 9.2 Gmail sendAs 조회 실패

이전 이슈와 동일하게,
`sendAs` 조회 실패는 bare email fallback으로 처리한다.

Spring 표시명이 있더라도,
이메일 주소 확보를 위해 profile 조회는 계속 필요하다.

### 9.3 MIME 안전성

표시명은 기존과 동일하게 RFC 2047/UTF-8 안전한 방식으로 `From` 헤더에 들어가야 한다.

---

## 10. 영향 범위

### 10.1 직접 영향

- `app/models/requests.py` 또는 실행 request parsing 계층
- executor 실행 컨텍스트
- `app/core/nodes/output_node.py`
- `app/services/integrations/gmail.py`

### 10.2 간접 영향

- Gmail integration unit test
- output node test
- 실환경 Gmail relay E2E

### 10.3 영향 없음

- Google Sheets
- Slack
- Notion
- Drive
- Gmail source read path 자체

---

## 11. 테스트 계획

### 11.1 단위 테스트

- `preferred_display_name`이 있으면 `From`에 그 값이 우선 적용되는지
- `preferred_display_name`이 없으면 `sendAs.displayName`을 쓰는지
- 둘 다 없으면 bare email로 가는지

### 11.2 회귀 테스트

- 기존 Gmail source decode 테스트 유지
- 기존 Gmail send/draft 성공 테스트 유지
- 다른 sink 관련 테스트 영향 없음 확인

### 11.3 실환경 테스트

- Gmail -> LLM -> Gmail relay 발송
- 자기 자신이 받은 메일을 Gmail source로 재감지
- Gmail UI와 Flowify payload 양쪽에서 `From`이 `김민호 <...>` 또는 최소한 정상 UTF-8 이름으로 보이는지 확인

---

## 12. 범위 제외

이번 설계 범위에서 제외한다.

- FE에서 발신자명 입력 UI 제공
- 사용자별 custom `from_name` 설정 저장
- alias 선택 UI
- Gmail source payload에 sender name 별도 정규화 필드 추가

이번 이슈는 Spring이 전달한 사용자 이름을 Gmail `From` 표시명에 활용하는 범위까지만 본다.

---

## 13. 결론

이번 기능의 핵심은 FastAPI가 Gmail 계정 설정에만 의존하지 않고,
Spring이 알고 있는 사용자 이름을 Gmail 발송 헤더 구성에 활용하는 것이다.

FastAPI는 아래 규칙만 지키면 된다.

- Spring `display_name` 우선
- 없으면 `sendAs.displayName`
- 그것도 없으면 bare email

이 설계를 기준으로 구현하면,
이전 이슈에서 해결한 “깨진 문자열 제거”를 넘어
“표시명 보장”까지 같은 Gmail 발송 경로 안에서 자연스럽게 확장할 수 있다.
