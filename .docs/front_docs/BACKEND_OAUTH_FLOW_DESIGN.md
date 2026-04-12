# 백엔드 주도 OAuth 플로우 설계

> 작성일: 2026-04-11
> 대상 프로젝트: `flowify-fe`
> 관련 브랜치: `refector#70-backend-oauth-resetting`
> 관련 문서: `docs/BACKEND_INTEGRATION_DESIGN.md`

---

## 1. 목적

현재 프론트 로그인은 Google OAuth 인가를 프론트가 직접 시작하고, 프론트 callback 페이지에서 `code` 를 받아 백엔드 callback API를 XHR로 호출하는 구조다.

운영 환경에서는 아래 문제가 확인됐다.

- `redirect_uri_mismatch`
- 브라우저 → 백엔드 callback API 호출 시 CORS 차단
- 백엔드 callback 엔드포인트를 브라우저 API처럼 호출하는 구조 충돌

이 문서는 인증 흐름만 별도로 분리해 **백엔드 주도 OAuth 플로우** 로 재설계하는 내용을 정의한다.

현재 서버와 합의된 프론트 callback 경로는 아래다.

```text
https://flowify-fe.vercel.app/auth/callback
```

즉, 최종 설계는 `/login/callback` 이 아니라 **`/auth/callback` 기준**으로 정리한다.

---

## 2. 현재 구조와 문제점

### 2-1. 현재 프론트 로그인 흐름

현재 코드 기준 로그인 흐름은 아래와 같다.

1. `LoginPage` 에서 `createGoogleOAuthUrl()` 호출
2. 프론트가 Google OAuth URL 직접 생성
3. Google 인증 후 프론트 `/login/callback?code=...&state=...` 로 복귀
4. `LoginCallbackPage` 가 `code`, `state` 검증
5. 프론트가 `GET /auth/google/callback?code=...` 를 axios로 호출
6. 백엔드가 Google token exchange 수행 후 JWT 반환
7. 프론트가 `localStorage` 에 토큰 저장

### 2-2. 현재 코드 위치

| 파일 | 현재 역할 |
|---|---|
| `src/pages/login/LoginPage.tsx` | Google 로그인 버튼 클릭 시 Google URL로 직접 이동 |
| `src/shared/libs/google-oauth.ts` | Google OAuth URL 구성, `state` 저장/조회/삭제 |
| `src/pages/login-callback/LoginCallbackPage.tsx` | `code/state` 검증 후 callback API 호출 |
| `src/shared/api/auth.api.ts` | `GET /auth/google/callback?code=` 호출 |
| `src/shared/libs/auth-session.ts` | access/refresh token, user 저장 |

### 2-3. 핵심 문제

#### A. OAuth 주체 불일치

- 프론트는 프론트 callback 플로우를 사용한다.
- 백엔드는 서버 callback 플로우를 전제로 한다.

즉, 인가 시작과 callback 처리 주체가 서로 다르다.

#### B. callback API 책임 불일치

현재 프론트는 백엔드 `GET /auth/google/callback` 을 일반 API처럼 호출한다.  
하지만 백엔드가 이 엔드포인트를 Google callback 수신용으로 설계했다면, 브라우저 XHR 호출과 책임이 맞지 않는다.

#### C. CORS 문제

운영에서는 프론트 origin 에서 백엔드 callback API를 직접 호출하므로 CORS 정책 영향을 받는다.  
서버 callback 엔드포인트는 브라우저 API 호출을 전제로 만들지 않기 때문에, 현재 구조는 운영 환경에서 취약하다.

#### D. redirect_uri 관리 분산

- 프론트가 Google 인가용 `redirect_uri` 를 직접 만든다.
- 백엔드가 token exchange 단계에서 또 다른 `redirect_uri` 를 사용할 수 있다.

authorization code flow 에서는 인가 단계와 교환 단계의 `redirect_uri` 가 완전히 같아야 하므로, 이 구조는 오류 가능성이 높다.

---

## 3. 목표 구조

인증 흐름은 **백엔드 주도 OAuth + 프론트 세션 확정** 구조로 통일한다.

핵심 원칙은 아래와 같다.

- Google OAuth URL 생성 주체: 백엔드
- Google callback 수신 주체: 백엔드
- 프론트 callback 라우트 역할: 최종 세션 확정
- JWT access/refresh token 저장 주체: 프론트
- 토큰 전달 방식: URL query 금지, 일회용 `exchange_code` 사용

---

## 4. 목표 플로우

### 4-1. 최종 로그인 흐름

```text
1. 사용자가 /login 에서 로그인 버튼 클릭
2. 프론트가 브라우저를 {API_BASE_URL}/auth/google 로 이동
3. 백엔드가 Google OAuth URL로 302 redirect
4. 사용자가 Google 인증 완료
5. Google이 백엔드 /api/auth/google/callback?code=... 호출
6. 백엔드가 Google token exchange + 사용자 식별 + JWT 발급 처리
7. 백엔드가 일회용 exchange_code 생성 후 서버에 임시 저장
8. 백엔드가 프론트 /auth/callback?exchange_code=... 로 302 redirect
9. 프론트 callback 페이지가 exchange_code 확인
10. 프론트가 POST /api/auth/exchange 호출
11. 백엔드가 LoginResponse 반환
12. 프론트가 accessToken, refreshToken, user 저장 후 /workflows 이동
```

### 4-2. 실패 흐름

백엔드는 실패 시 프론트 callback 페이지로 아래 형태 중 하나로 redirect 한다.

```text
/auth/callback?error=oauth_failed
/auth/callback?error=oauth_failed&message=...
```

프론트는 아래 우선순위로 처리한다.

1. `exchange_code` 가 있으면 `POST /auth/exchange`
2. `error` 가 있으면 실패 UI 표시
3. 둘 다 없으면 일반 로그인 실패 UI 표시

> `/auth/callback` 은 API 엔드포인트가 아니라 프론트 라우트다. 서버는 이 주소로 302 redirect 하고, 프론트 SPA가 callback 페이지를 렌더링해야 한다.

---

## 5. 백엔드 선행 조건

이 설계가 성립하려면 서버에서 아래를 준비해야 한다.

### 5-1. 로그인 시작 엔드포인트

#### `GET /api/auth/google`

- Google OAuth 페이지로 `302 redirect`
- 프론트는 axios 호출이 아니라 브라우저 이동으로 사용

### 5-2. Google callback 직접 처리

#### `GET /api/auth/google/callback`

- Google authorization code 수신
- Google token exchange
- 사용자 조회 또는 생성
- 앱 JWT 발급 준비
- 일회용 `exchange_code` 생성 및 임시 저장
- 프론트 callback URL 로 `302 redirect`

성공 redirect 예시:

```text
{FRONTEND_URL}/auth/callback?exchange_code=...
```

실패 redirect 예시:

```text
{FRONTEND_URL}/auth/callback?error=oauth_failed
```

### 5-3. 세션 확정 엔드포인트

#### `POST /api/auth/exchange`

요청:

```json
{
  "exchangeCode": "..."
}
```

응답:

```json
{
  "success": true,
  "data": {
    "accessToken": "...",
    "refreshToken": "...",
    "user": {
      "id": "...",
      "email": "...",
      "name": "...",
      "picture": null,
      "createdAt": "2026-04-11T12:34:56Z"
    }
  },
  "message": null,
  "errorCode": null
}
```

### 5-4. `exchange_code` 조건

- 일회용
- 짧은 TTL, 예: 30초~1분
- 사용 후 즉시 폐기
- 만료/재사용 시 명시적 에러 반환

### 5-5. 환경값

서버는 환경별 프론트 callback URL 을 알아야 한다.

예:

- local: `http://localhost:5173/auth/callback`
- dev: 별도 dev 도메인
- prod: `https://flowify-fe.vercel.app/auth/callback`

즉, `FRONTEND_URL` 과 callback path 를 함께 관리해야 한다.

---

## 6. 프론트 책임 범위

### 6-1. `LoginPage`

현재처럼 Google URL 을 직접 만들지 않는다.

#### 변경 전

- `createGoogleOAuthUrl()` 호출
- `window.location.href = googleOAuthUrl`

#### 변경 후

- 백엔드 로그인 시작 URL 로 브라우저 이동

예:

```ts
window.location.href = buildGoogleLoginStartUrl();
```

### 6-2. callback 페이지

현재처럼 `code`, `state` 를 읽지 않는다.

#### 변경 전

- `code` 추출
- `state` 추출 및 `sessionStorage` 검증
- `GET /auth/google/callback?code=...` 호출

#### 변경 후

- `/auth/callback` 라우트 진입
- `exchange_code`, `error`, `message` 추출
- `exchange_code` 가 있으면 `POST /auth/exchange`
- 성공 시 세션 저장
- 실패 시 로그인 화면 복귀

### 6-3. 세션 저장

현재 `src/shared/libs/auth-session.ts` 구조를 유지한다.

- `accessToken`
- `refreshToken`
- `authUser`

세션 저장 책임은 계속 프론트가 가진다.

### 6-4. refresh / logout

현재 `client.ts` interceptor 구조는 유지한다.

- API 요청 시 Bearer token 부착
- 401 시 `POST /auth/refresh`
- refresh 실패 시 세션 정리 후 `/login` 이동

즉, 이번 리팩터링은 **초기 로그인 진입과 callback 처리만 변경**하고, 세션 저장 이후 흐름은 유지한다.

---

## 7. 프론트 설계 원칙

현재 프로젝트 컨벤션 기준 역할 분리는 아래가 자연스럽다.

| 계층 | 책임 |
|---|---|
| `src/shared/api/*` | 백엔드 HTTP 계약 |
| `src/shared/libs/*` | 브라우저 환경 보조 로직, 세션 저장 |
| `src/pages/*` | 화면 진입/상태 처리 |
| `src/app/routes/*` | 공개/보호 라우트 구성 |

이번 설계도 이 원칙을 유지한다.

---

## 8. 파일 설계

### 8-1. 방향

| 파일 | 방향 |
|---|---|
| `src/shared/api/auth.api.ts` | `exchange`, `refresh`, `logout` 만 보유 |
| `src/shared/libs/auth-session.ts` | 세션 저장 단일 소스 유지 |
| `src/shared/libs/google-oauth.ts` | 제거 |
| `src/shared/libs/auth-redirect.ts` | 백엔드 로그인 시작 URL 조합 유틸 추가 |
| `src/pages/login/LoginPage.tsx` | 브라우저를 백엔드 로그인 시작 URL 로 이동 |
| `src/pages/auth-callback/AuthCallbackPage.tsx` | `exchange_code` 처리 전용 페이지 |

### 8-2. 수정 대상

| 파일 | 변경 내용 |
|---|---|
| `src/pages/login/LoginPage.tsx` | Google URL 직접 생성 제거, 백엔드 로그인 시작 URL 이동 |
| `src/shared/api/auth.api.ts` | `googleCallback()` 제거, `exchange()` 추가 |
| `src/shared/libs/index.ts` | `google-oauth` export 제거, `auth-redirect` export 추가 |
| `src/shared/constants/route-path.ts` | `LOGIN_CALLBACK` 를 `AUTH_CALLBACK` 로 전환, 경로 `/auth/callback` 반영 |
| `src/app/routes/Router.tsx` | callback 라우트 경로를 `/auth/callback` 으로 변경 |
| `src/pages/index.ts` | callback 페이지 export 경로 정리 |
| `src/pages/settings/SettingsPage.tsx` | callback 경로 표시 값 갱신 |
| `.env.example` | 불필요한 Google client id 관련 프론트 env 정리 |

### 8-3. 신규 대상

| 파일 | 역할 |
|---|---|
| `src/shared/libs/auth-redirect.ts` | 백엔드 로그인 시작 URL 조합 유틸 |
| `src/pages/auth-callback/AuthCallbackPage.tsx` | 인증 완료 처리 페이지 |
| `src/pages/auth-callback/index.ts` | folder-level export |

### 8-4. 제거 대상

| 파일 | 제거 이유 |
|---|---|
| `src/shared/libs/google-oauth.ts` | 프론트가 Google OAuth URL과 `state` 를 직접 다루지 않음 |
| `src/pages/login-callback/*` | callback 의미가 로그인 전용이 아니라 인증 완료 처리로 바뀌므로 `auth-callback` 구조로 정리 |

---

## 9. 단계별 적용 순서

### Phase 1. 로그인 시작 전환

- `LoginPage` 에서 Google URL 직접 생성 제거
- 브라우저를 `/auth/google` 로 이동

### Phase 2. callback 페이지 전환

- `/auth/callback` 라우트 추가
- `AuthCallbackPage` 에서 `exchange_code` 처리

### Phase 3. 인증 API 계약 전환

- `authApi.googleCallback()` 제거
- `authApi.exchange()` 추가

### Phase 4. 불필요 로직 정리

- `google-oauth.ts` 제거
- `login-callback` 폴더 제거
- 관련 export 정리
- `.env.example` 정리

### Phase 5. 예외 처리 보완

- `exchange_code` 누락
- `exchange_code` 만료
- `exchange_code` 재사용
- backend redirect error 처리

---

## 10. 예외 처리 정책

### 10-1. 프론트 callback 페이지

`/auth/callback` 진입 시 아래 우선순위로 처리한다.

1. `exchange_code` 존재
   - `POST /auth/exchange`
2. `error` 존재
   - 에러 메시지 표시
3. 그 외
   - 일반 로그인 실패 처리

### 10-2. 사용자 메시지

프론트는 Google/백엔드 내부 오류를 그대로 노출하지 않고, 아래 수준으로 일반화한다.

- 로그인 인증에 실패했습니다.
- 로그인 정보가 만료되었습니다. 다시 시도해 주세요.
- 로그인 처리 중 오류가 발생했습니다.

### 10-3. 세션 정리

callback 처리 실패 시 아래를 수행한다.

- `clearAuthSession()`
- 로그인 화면 복귀

---

## 11. 장점과 트레이드오프

### 장점

- OAuth callback 주체가 백엔드로 단일화된다
- 브라우저가 callback API를 XHR로 호출하지 않아 CORS 문제가 줄어든다
- Google `redirect_uri` 관리가 백엔드 한 곳에 모인다
- 프론트 기존 세션 구조는 유지할 수 있다
- 토큰을 URL query string 으로 전달하지 않는다

### 트레이드오프

- 백엔드에 `exchange_code` 저장소가 추가로 필요하다
- 프론트와 백엔드가 callback 에러 파라미터 규약을 합의해야 한다
- 기존 프론트 주도 OAuth 관련 코드와 문서를 정리해야 한다

---

## 12. 백엔드 확인 필요 사항

| 항목 | 확인 내용 |
|---|---|
| `FRONTEND_URL` | 운영/개발 환경별 프론트 callback URL 설정 방식 (`/auth/callback` 포함) |
| `POST /api/auth/exchange` | 신규 엔드포인트 제공 여부 |
| callback 실패 redirect | `error`, `message` 파라미터 규약 |
| `exchange_code` TTL | 만료 시간 및 재사용 처리 방식 |
| 토큰 응답 | 현재 `LoginResponse` 와 동일 구조 유지 여부 |

---

## 13. 결론

현재 로그인 문제는 단순 CORS 설정 누락보다 **프론트 주도 OAuth와 백엔드 주도 OAuth가 혼재된 구조 문제** 에 가깝다.

따라서 인증 플로우는 아래 한 줄로 정리하는 것이 가장 안전하다.

> **백엔드가 Google OAuth 시작과 callback 을 모두 처리하고, 프론트는 `/auth/callback` 에서 `exchange_code` 로 세션만 확정한다.**

이 방향은 현재 코드 컨벤션과도 잘 맞는다.

- HTTP 계약: `src/shared/api/auth.api.ts`
- 브라우저 세션 저장: `src/shared/libs/auth-session.ts`
- 화면 진입 처리: `src/pages/login`, `src/pages/auth-callback`

