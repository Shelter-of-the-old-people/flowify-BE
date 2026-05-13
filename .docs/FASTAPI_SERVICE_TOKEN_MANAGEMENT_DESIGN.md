# FastAPI Service Token Management Design

> 작성일: 2026-05-13
> 대상 저장소: `flowify-BE`
> 범위: FastAPI runtime 기준 service token 관리 기능 영향 범위 정리
> 관련 저장소: `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 사용자 직접 입력형 service token 관리 기능이 들어올 때 FastAPI가 어떤 영향을 받는지와, 어떤 책임을 계속 맡지 않는지를 정리한다.

이번 이슈의 핵심은 token을 "어디서 입력하고 어떻게 저장/검증할지"에 있다.

이 책임의 owner는 `flowify-BE-spring`과 `flowify-FE`이며, FastAPI는 기존처럼 실행 시점에 전달된 `service_tokens`를 소비하는 런타임 엔진 역할을 유지한다.

---

## 2. 결론 요약

이번 이슈의 v1 범위에서 FastAPI는 새로운 token 관리 API를 만들지 않는다.

FastAPI는 아래 원칙을 유지한다.

- Spring이 실행 요청에 포함해 준 `service_tokens`만 사용한다.
- token의 저장, 암호화, 마스킹, 재노출 정책은 담당하지 않는다.
- token 발급 방법 안내 UI와 도움말은 담당하지 않는다.
- token 누락 또는 무효 token에 대한 런타임 에러 처리는 기존 방식대로 유지한다.

즉 이번 이슈에서 FastAPI는 "변경 최소"가 기본 전략이다.

---

## 3. 현재 런타임 계약

FastAPI는 이미 workflow 실행과 preview 실행에서 아래 구조를 사용한다.

- `service_tokens[service_key] = decrypted access token`

대표 예시:

- `service_tokens["notion"]`
- `service_tokens["github"]`
- `service_tokens["canvas_lms"]`
- `service_tokens["google_drive"]`
- `service_tokens["gmail"]`

이번 이슈가 들어와도 이 계약 자체는 바뀌지 않는다.

FastAPI 입장에서는 token의 출처가 아래 둘 중 어느 쪽이든 동일하게 취급한다.

- OAuth redirect 기반 연결
- 사용자가 직접 입력해 저장한 manual token

---

## 4. FastAPI 책임 범위

### 4.1 FastAPI가 계속 담당하는 것

- 실행 시점 token 사용
- preview 시점 token 사용
- 외부 API 호출
- token 누락 시 런타임 에러 반환
- token 무효/만료 시 외부 API 에러를 Flowify 에러로 변환

### 4.2 FastAPI가 이번 이슈에서도 담당하지 않는 것

- token 입력 UI
- token 발급 방법 안내 UI
- token 저장 API
- token 암호화 저장
- token 마스킹 규칙
- token 재노출 정책
- 서비스별 사전 검증 API

위 항목은 Spring과 FE가 담당한다.

---

## 5. 서비스별 영향

이번 이슈에서 직접 입력형으로 다루는 대상은 아래 서비스다.

- `notion`
- `github`
- `canvas_lms`

FastAPI는 이 서비스들에 대해 이미 token 소비 경로를 가지고 있으므로, v1에서는 별도 런타임 확장이 필수는 아니다.

중요한 점은 Spring이 아래를 보장해야 한다는 것이다.

- 실행 전에 올바른 service key로 token을 주입한다.
- 누락 token은 실행 전에 최대한 걸러낸다.
- 서비스별 검증 실패 token은 저장 단계에서 최대한 차단한다.

---

## 6. Spring에 기대하는 보장

FastAPI가 안정적으로 그대로 재사용되려면 Spring은 아래를 보장해야 한다.

- manual token도 기존 OAuth token과 같은 방식으로 암호화 저장한다.
- 실행 시점에는 복호화된 access token만 `service_tokens`에 담아 전달한다.
- service key 이름은 기존 런타임 계약과 동일하게 유지한다.
- alias 서비스 정책은 기존 규칙을 유지한다.
  - 예: `google_sheets`는 계속 `google_drive` token alias 정책을 따른다.

이 보장이 지켜지면 FastAPI는 token 출처와 무관하게 기존 실행 코드를 그대로 사용할 수 있다.

---

## 7. Spring handoff 계약 상세

### 7.1 실행 요청 계약

Spring은 manual token이 저장된 서비스도 기존 실행 요청과 같은 구조로 FastAPI에 전달해야 한다.

예시:

```json
{
  "workflow": { "...": "..." },
  "service_tokens": {
    "github": "<decrypted token>",
    "notion": "<decrypted token>"
  }
}
```

FastAPI는 아래처럼 token 출처를 알 수 있는 부가 필드를 요구하지 않는다.

- `connectionMethod`
- `maskedHint`
- `accountLabel`
- `validationStatus`

위 정보는 FE summary용이며, runtime payload에는 포함하지 않는 편이 맞다.

### 7.2 preview 요청 계약

preview 요청도 같은 원칙을 따른다.

- manual token 서비스 preview가 필요하면 Spring이 기존 `service_tokens` 필드에 decrypted token을 넣어 전달한다.
- preview payload 구조는 token 관리 기능 때문에 별도 분기하지 않는다.

즉 실행과 preview 모두 "token 출처가 무엇이든 FastAPI는 같은 방식으로 소비한다"가 핵심 계약이다.

---

## 8. 런타임 에러 계약

manual token 기능이 들어와도 FastAPI의 런타임 에러 구조는 크게 바꾸지 않는다.

주요 기준:

- token 자체가 없으면 `OAUTH_NOT_CONNECTED`
- token이 있지만 scope가 부족하면 `OAUTH_SCOPE_INSUFFICIENT`
- token이 무효하거나 만료되면 `OAUTH_TOKEN_INVALID` 또는 `OAUTH_TOKEN_EXPIRED`
- 외부 서비스 호출 실패는 `EXTERNAL_SERVICE_ERROR` 또는 `EXTERNAL_API_ERROR`

중요한 점은 아래다.

- "manual token에서 온 에러"라는 별도 분류를 FastAPI가 만들지 않는다.
- 사용자가 token을 어디서 발급했는지, 어떤 화면에서 저장했는지는 FastAPI 관심사가 아니다.
- FE는 Spring이 넘겨준 summary와 FastAPI 에러를 조합해 사용자 메시지를 만든다.

이 원칙을 유지하면 token 입력 기능이 들어와도 기존 런타임 에러 처리 코드를 크게 흔들지 않아도 된다.

---

## 9. 도움창 범위 판단

토큰 발급 도움창은 이번 이슈에 포함하는 것이 맞다.

이유는 아래와 같다.

- manual token 입력 기능만 있으면 실제 사용자 완료율이 낮다.
- Notion, GitHub, Canvas LMS는 token 발급 위치와 권한 요구가 직관적이지 않다.
- 도움창은 FastAPI 구현 변경 없이도 사용자 성공률을 크게 올릴 수 있다.

다만 이 도움창은 FE 문서와 구현 범위다.

FastAPI가 이 도움창을 위해 추가 API를 제공할 필요는 없다.

---

## 10. Out of Scope

이번 v1에서 FastAPI의 범위 밖으로 두는 항목은 아래와 같다.

- 저장된 raw token 다시 보여주기
- 서비스별 token capability 상세 분석 결과 반환
- 사용자별 Canvas base URL 동적 처리
- manual token 발급 대행
- token rotation 정책 자동화

특히 Canvas 인스턴스 URL은 현재 서버 설정 기반이므로, 사용자별 Canvas 도메인 입력까지 요구되면 별도 후속 이슈로 분리하는 것이 안전하다.

---

## 11. 결정 요약

이번 이슈는 FastAPI에서 token 관리 기능을 새로 만드는 작업이 아니다.

FastAPI의 기준 결론은 아래와 같다.

- token 관리의 owner는 Spring과 FE다.
- FastAPI는 기존 `service_tokens` 소비 계약을 유지한다.
- manual token 입력이 들어와도 런타임 payload 구조는 가능하면 바꾸지 않는다.
- token 발급 도움창은 같은 이슈에 포함해도 되지만 FastAPI 변경 사항은 없다.
