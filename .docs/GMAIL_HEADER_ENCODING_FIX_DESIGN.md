# Gmail Header Encoding Fix Design

> 작성일: 2026-05-15
> 대상 레포: `flowify-BE`
> 범위: Gmail 발송/수신 헤더 인코딩 깨짐 수정
> 관련 레포: `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 Gmail sink로 보낸 메일을 다시 Gmail source가 읽을 때,
발신자 표시명과 제목 같은 헤더가 깨져 보이는 문제의 원인과 수정 방향을 정리한다.

이번 이슈의 목표는 다음 네 가지다.

- Gmail 발송 메일의 `From` 헤더가 깨진 문자열로 전달되지 않게 한다.
- 가능한 경우 `이름 + 이메일` 형식의 정상적인 발신자 표시를 유지한다.
- Gmail 수신 경로에서 `Subject`, `From`, `To` 헤더를 MIME 규격에 맞게 decode 한다.
- 위 목표를 `flowify-BE` 단독 수정으로 어디까지 닫을 수 있는지 명확히 한다.

---

## 2. 문제 요약

실환경 테스트에서 아래 시나리오를 반복 실행했을 때 문제가 재현되었다.

- 워크플로우 A: `Gmail(new_email) -> LLM -> Gmail(send)`
- 워크플로우 B: `Gmail(new_email) -> LLM -> Google Sheets`

워크플로우 A가 자기 자신에게 보낸 메일을 워크플로우 B가 다시 읽었을 때,
발신자 표시명이 `김민호` 대신 다음과 같은 깨진 문자열로 관찰되었다.

- `ê¹€ë¯¼í˜¸`
- `ÃªÂ¹â¬Ã«Â¯Â¼Ã­ËÂ¸`

중요한 관찰 포인트는 다음과 같다.

- 메일 본문과 제목 전달 자체는 정상이다.
- 깨짐은 발신자 표시명과 같은 헤더 계층에서 발생한다.
- Gmail UI와 Flowify source payload에서 모두 같은 현상이 재현된다.
- 따라서 FE 렌더링 문제가 아니라, 발송 헤더 생성 또는 수신 헤더 decode 문제로 보는 것이 맞다.

---

## 3. 재현 결과

### 3.1 발송과 수신 자체는 성공

- Gmail sink의 send action은 정상적으로 메일을 보낸다.
- Gmail source `new_email`도 방금 보낸 메일을 다시 감지한다.

### 3.2 깨짐 위치는 `From` 표시명

- 이전 구현 기준 감지 payload:
  - `from = "\"ê¹€ë¯¼í˜¸\" <mhtiger362@gmail.com>"`
- 같은 메일을 Gmail 웹 UI에서 봐도 발신자 이름이 깨져 표시되었다.

즉, 발송 단계에서 만들어진 `From` 헤더가 이미 잘못되었거나,
수신 단계에서 MIME decode를 하지 않아 raw 값이 그대로 노출된 것이다.

---

## 4. 원인 분석

핵심 원인은 `app/services/integrations/gmail.py` 두 지점에 있다.

### 4.1 발송 경로가 `From` 헤더를 안정적으로 만들지 못함

기존 `_build_raw_message()`는 다음 요소만 명시적으로 작성했다.

- `To`
- `Subject`
- 본문

즉 `From` 헤더를 직접 제어하지 않았고,
Gmail 계정의 기본 발신자 설정과 인코딩 처리에 전적으로 의존했다.

이 경로에서는 계정 기본 표시명이 깨져 있거나,
Gmail이 전달한 헤더를 다시 읽는 과정에서 인코딩이 꼬이면
깨진 문자열이 그대로 노출될 수 있다.

### 4.2 수신 경로가 MIME 헤더 decode를 하지 않음

기존 `get_message()`는 Gmail payload의 `Subject`, `From`, `To`를
거의 raw 문자열 그대로 반환했다.

이 때문에 다음 경우를 흡수하지 못한다.

- RFC 2047 encoded-word 헤더
- bytes 조각 + declared encoding 조합
- UTF-8 fallback이 필요한 헤더

결과적으로 Gmail이 정상적인 MIME 헤더를 반환하더라도
Flowify runtime payload에서 깨진 값처럼 보일 수 있다.

### 4.3 BE 단독 수정 가능 여부

초기 가설은 “BE만으로는 display name을 복원하기 어렵다”는 쪽이었다.
하지만 공식 Gmail API 문서를 다시 확인한 결과,
현재 토큰 스코프(`gmail.readonly`, `gmail.send`)만으로도
`users.settings.sendAs.list/get` 호출이 가능하다.

공식 문서 기준:

- `users.getProfile`은 `emailAddress`만 반환한다.
- `users.settings.sendAs` 리소스는 `displayName`을 제공한다.
- `users.settings.sendAs.list/get`은 `gmail.readonly` 스코프로도 호출 가능하다.

현재 Spring 설정도 다음 스코프를 사용한다.

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`

그리고 FastAPI 런타임에는 `X-User-ID`만 전달되지만,
이번 수정에는 사용자 이름을 Spring에서 별도로 내려줄 필요가 없다.
BE가 Gmail API에서 `sendAs.displayName`을 직접 읽을 수 있기 때문이다.

따라서 이번 이슈는 `flowify-BE` 단독 수정으로
`display name 우선, 없으면 bare email fallback`까지 처리할 수 있다.

---

## 5. 수정 방향

### 5.1 발송 시 `sendAs.displayName`을 우선 사용

Gmail의 `users.settings.sendAs.list`를 호출해
현재 계정의 primary/default send-as 엔트리를 찾는다.

우선순위:

1. `isPrimary == true`
2. `isDefault == true`
3. 첫 번째 send-as 항목

이 엔트리에서 다음을 얻는다.

- `sendAsEmail`
- `displayName`

이후 `From` 헤더는 아래 규칙으로 생성한다.

- `displayName`이 있으면: `김민호 <mhtiger362@gmail.com>`
- `displayName`이 없으면: `mhtiger362@gmail.com`

### 5.2 `From` 헤더는 UTF-8 MIME-safe 방식으로 작성

한글 표시명은 직접 문자열을 이어붙이지 않고,
Python email 라이브러리의 헤더 인코딩을 거쳐 MIME-safe 하게 만든다.

예상 결과:

- raw 헤더는 RFC 2047 encoded-word 형식이 될 수 있음
- 수신 Gmail UI와 재감지 payload에서는 사람이 읽는 `김민호 <...>`로 보임

### 5.3 수신 시 `Subject`, `From`, `To` decode 보강

`decode_header()` 기반 helper를 유지하되,
실제 입력에서 자주 만나는 경우를 안전하게 처리한다.

decode 정책:

- declared encoding 우선
- `utf-8` fallback
- 제한적 `cp949`, `latin-1` fallback
- 최종 실패 시 `errors="replace"`

목표는 “최대한 정상적으로 읽고, 최악의 경우에도 깨진 bytes를 그대로 노출하지 않기”다.

### 5.4 fallback 전략

다음 경우는 fallback 한다.

- `sendAs` 조회가 실패함
- `sendAsEmail`이 비어 있음
- `displayName`이 비어 있음

fallback 결과:

- 최소한 bare email로 `From`을 명시
- 깨진 한글 표시명보다 안정적인 결과를 우선 보장

---

## 6. 구현 포인트

수정 대상 파일:

- `app/services/integrations/gmail.py`

구현 포인트:

1. Gmail profile 조회 helper 유지
   - bare email fallback 용도

2. `sendAs` 조회 helper 추가
   - `GET /gmail/v1/users/me/settings/sendAs`
   - primary/default alias의 `displayName`, `sendAsEmail` 추출

3. sender identity helper 추가
   - 반환값 예시:
     - `("mhtiger362@gmail.com", "김민호")`
     - `("mhtiger362@gmail.com", "")`

4. `_build_raw_message()` 개선
   - `from_address`
   - `from_display_name`
   - 둘 다 받아서 `From` 헤더 생성

5. `get_message()` 개선
   - `Subject`, `From`, `To`를 decode helper 거쳐 반환

6. 진단 로그 추가
   - `sendAs` 조회 실패 시 warning
   - `displayName`이 비어 bare email fallback 될 때 info 로그

---

## 7. 테스트 계획

### 7.1 단위 테스트

테스트 파일:

- `tests/test_integrations/test_gmail.py`

필수 케이스:

1. `sendAs.displayName`이 있을 때 `From` 헤더에 이름+이메일이 들어가는지
2. `displayName`이 없을 때 bare email로 fallback 하는지
3. `send_message()`가 `sendAs -> profile fallback` 순서를 따르는지
4. `create_draft()`도 동일하게 동작하는지
5. `get_message()`가 MIME encoded `Subject`, `From`, `To`를 정상 decode 하는지

### 7.2 회귀 테스트

영향 범위:

- `tests/test_input_node.py`
- `tests/test_output_node.py`

Gmail source/sink의 canonical payload 계약이 유지되는지 다시 본다.

### 7.3 실환경 테스트

필수 시나리오:

1. `Gmail(new_email) -> LLM -> Gmail(send)`
2. `Gmail(new_email) -> LLM -> Google Sheets`

검증 포인트:

- Gmail 웹 UI에서 발신자 표시명이 더 이상 깨지지 않는지
- 재감지 payload의 `from`, `sender`가 정상 문자열인지
- 제목/본문/감지 흐름 자체에는 회귀가 없는지

### 7.4 현재 실환경 검증 메모

현재 테스트 계정 기준 실환경 재검증 결과는 다음과 같았다.

- 기존 깨진 값
  - `"ê¹€ë¯¼í˜¸" <mhtiger362@gmail.com>`
- 보강 후 재감지 값
  - `mhtiger362@gmail.com`

즉 이번 보강으로 **깨진 표시명은 제거되었고**, 실환경에서는 **bare email fallback**이 실제로 관찰되었다.

이 결과가 의미하는 바는 다음 둘 중 하나다.

1. 현재 계정의 primary `sendAs.displayName`이 비어 있다.
2. 현재 토큰/계정 상태에서 `sendAs` 조회가 실패해 fallback이 발동한다.

코드상으로는 두 경우 모두 안전하게 bare email로 내려오므로,
이번 이슈 기준의 1차 버그 수정 목표인 “깨진 문자열 제거”는 달성한다.

반면 **항상 `김민호 <mhtiger362@gmail.com>`처럼 이름까지 보장하는 것**은
실환경 계정 데이터와 토큰 상태에 따라 달라질 수 있다.

이 보장을 제품 요구사항으로 올리려면, 후속으로 아래 중 하나를 검토해야 한다.

- Spring이 인증 사용자 display name을 FastAPI 실행 계약에 포함
- Gmail connector가 OAuth 저장 시 alias/displayName 메타데이터를 별도 보관
- FE/BE-spring에 `from_name` 같은 명시적 설정 필드 추가

---

## 8. Out of Scope

이번 이슈에서 제외하는 항목:

- FE에서 발신자 표시명 직접 입력 UI 추가
- Spring catalog/schema에 `from_name` 필드 추가
- 사용자가 여러 send-as alias 중 하나를 선택하는 기능
- 임의 mojibake 패턴을 역추적 복구하는 공격적 heuristic

이번 범위는 “현재 Gmail 계정에 이미 설정된 기본 발신자 이름을 안전하게 보존한다”는 버그 수정에 집중한다.

---

## 9. 결정 요약

이번 이슈는 `flowify-BE` 단독 수정으로 진행한다.

최종 방향은 다음과 같다.

- 발송 시 `sendAs.displayName`을 우선 사용해 `이름 + 이메일` 형식의 `From`을 생성한다.
- `displayName`이 없거나 조회에 실패하면 bare email로 fallback 한다.
- 수신 시 `Subject`, `From`, `To`를 MIME 규격에 맞게 decode 한다.
- 1차 목표인 “깨진 문자열 제거”는 BE 단독으로 해결한다.
- 다만 “항상 사용자 이름까지 보장”은 실환경 계정/토큰 상태에 따라 추가 계약 확장이 필요할 수 있다.
