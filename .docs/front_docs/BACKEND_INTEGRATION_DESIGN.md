# 백엔드 연동 기반 설계

> 작성일: 2026-04-10
> 마지막 수정: 2026-04-10 (리뷰 피드백 2차 반영)
> 대상 백엔드: [flowify-BE-spring](https://github.com/Shelter-of-the-old-people/flowify-BE-spring)
> 대상 프론트: flowify-fe (React + TypeScript + React Flow)

---

## 1. 현재 상태 요약

### 1-1. 프론트엔드 API 연결 현황

API 모듈 5개, 함수 25개가 **정의만** 돼 있고, 실제로 호출되는 건 **2개**뿐이다.

| API 모듈 | 정의된 함수 | 실제 호출 | 호출 위치 |
|---|---|---|---|
| `authApi` | 4개 | `logout()` 1개 | `useLogout.ts` |
| `workflowApi` | 13개 | `create()` 1개 | `useCreateWorkflowShortcut.ts` |
| `templateApi` | 4개 | 0개 | - |
| `executionApi` | 4개 | 0개 | - |
| `oauthApi` | 3개 | 0개 | - |

- React Query(useQuery/useMutation)는 설정만 돼 있고 **어디에서도 사용되지 않는다.**
- `workflow-adapter.ts`에 양방향 변환 함수가 존재하지만, 실제 API 호출과 연결되지 않았다.

### 1-2. 페이지별 구현 상태

에디터와 나머지 페이지의 상태가 다르다.

| 페이지 | 상태 | 설명 |
|---|---|---|
| **WorkflowEditorPage** | **기능 구현됨** | store, canvas, node 추가, panel 위저드, dual-panel 레이아웃까지 동작. API 연결만 안 됨 (`isLoading = false` 하드코딩) |
| LoginPage | placeholder | 빈 페이지 |
| WorkflowsPage | placeholder | 하드코딩된 카드 |
| TemplatesPage | placeholder | 하드코딩된 카테고리 |
| TemplateDetailPage | placeholder | 정적 UI |

### 1-3. 백엔드 API 구조

- Spring Boot + MongoDB, 패키지 6개 (`auth`, `user`, `workflow`, `execution`, `template`, `oauth`)
- API 약 32개, 모든 응답은 `ApiResponse<T>` 래핑
- 실행은 FastAPI에 위임하는 오케스트레이터 구조
- 인증은 Google OAuth → 자체 JWT (access 30분 / refresh 7일)

---

## 2. 타입 불일치 분석

### 2-1. 인증 (auth)

#### `GET /api/auth/google` - 로그인 시작

| 구분 | 내용 |
|---|---|
| 프론트 현재 | `apiClient.get<ApiResponse<string>>("/auth/google")` — JSON 응답 기대 |
| 백엔드 실제 | `ResponseEntity.status(302).header(LOCATION, googleUrl)` — **302 리다이렉트** |
| 불일치 | **구조적 불일치.** axios는 302를 JSON으로 파싱할 수 없다 |

#### `POST /api/auth/refresh` - 토큰 갱신

| 구분 | 내용 |
|---|---|
| 프론트 현재 | 응답 타입 `RefreshTokenResponse { accessToken, refreshToken }` |
| 백엔드 실제 | 응답 타입 `LoginResponse { accessToken, refreshToken, user: UserResponse }` |
| 불일치 | 백엔드는 user를 포함한 `LoginResponse`를 반환한다 |

#### `GET /api/auth/google/callback` - OAuth 콜백

| 구분 | 내용 |
|---|---|
| 프론트 현재 | `AuthUser { id, email, name, picture }` |
| 백엔드 실제 | `UserResponse { id, email, name, picture, createdAt }` |
| 불일치 | `createdAt` 필드 누락 (minor) |

### 2-2. 노드 정의 (가장 큰 불일치)

#### `NodeDefinition` 구조

| 필드 | 프론트 `NodeDefinitionResponse` | 백엔드 `NodeDefinition` | 상태 |
|---|---|---|---|
| 타입 식별 | `type: string` (단일 필드) | `category: string` + `type: string` | **구조적 불일치** |
| 라벨 | `label: string` | 없음 | **프론트 전용 필드** — 백엔드에 추가 요청 필요 |
| id | `string` | `String` | 일치 |
| position | `{ x, y }` | `Position { x, y }` | 일치 |
| config | `Record<string, unknown>` | `Map<String, Object>` | 일치 |
| dataType | `string \| null` | `String` (nullable) | 일치 |
| outputDataType | `string \| null` | `String` (nullable) | 일치 |
| role | `"start" \| "end" \| "middle"` | `String` | 일치 |
| authWarning | `boolean?` | `boolean` | 일치 |

**핵심 문제:**
백엔드는 노드를 `category: "service"` + `type: "communication"`으로 2단계로 식별한다.
프론트는 `type: "communication"` 하나로 식별한다.

### 2-3. 엣지 정의

| 필드 | 프론트 `EdgeDefinitionResponse` | 백엔드 `EdgeDefinition` | 상태 |
|---|---|---|---|
| id | 있음 | **없음** | 백엔드에 추가 요청 필요 |
| source | 있음 | 있음 | 일치 |
| target | 있음 | 있음 | 일치 |
| sourceHandle | 있음 | **없음** | 프론트 전용 (React Flow) |
| targetHandle | 있음 | **없음** | 프론트 전용 (React Flow) |

**Edge 보존 정책:**

현재 프론트엔드는 edge에 대해 다음 계약을 갖고 있다:
- `FlowEdgeData` (`src/entities/connection/model/types.ts`): `label`, `variant` 필드
- `FlowArrowEdge` (`src/entities/connection/ui/FlowArrowEdge.tsx`): 커스텀 렌더러
- `workflow-adapter.ts`: `id`, `sourceHandle`, `targetHandle`을 round-trip

같은 source/target 사이의 복수 edge(조건 분기)를 지원하려면 edge id가 필수다.
따라서 **edge 필드를 제거하는 것이 아니라 명시적으로 보존**해야 한다:

1. **백엔드에 `id` 필드 추가 요청** (우선)
2. 합의 전까지는 어댑터에서 프론트 전용 필드(`id`, `sourceHandle`, `targetHandle`)를 보존하되, 백엔드로 보낼 때는 `source`/`target`만 전송
3. 백엔드에서 받을 때는 `id`가 없으면 `crypto.randomUUID()`로 생성 (중복 edge 구분을 위해 단순 패턴 불가)

### 2-4. 워크플로우 응답

| 필드 | 프론트 `WorkflowResponse` | 백엔드 `WorkflowResponse` | 상태 |
|---|---|---|---|
| id, name, description, userId | 있음 | 있음 | 일치 |
| nodes, edges | 있음 | 있음 | 내부 구조 불일치 (2-2, 2-3 참고) |
| trigger | 있음 | 있음 | 일치 |
| isActive | 있음 | 있음 | 일치 |
| createdAt, updatedAt | 있음 | 있음 | 일치 |
| **status** | `"active" \| "inactive"` | 없음 | 프론트 전용 — `isActive`에서 파생 |
| **sharedWith** | `string[]` | 없음 (Response DTO 미포함) | 엔티티에는 존재하나 응답에 빠져있음 |
| **isTemplate** | `boolean` | 없음 (Response DTO 미포함) | 동일 |
| **templateId** | `string \| null` | 없음 (Response DTO 미포함) | 동일 |
| **warnings** | 없음 | `List<ValidationWarning>` | 프론트 타입 누락 |

**영향 범위:**

이 불일치는 API 타입(`src/shared/api/workflow.api.ts`)뿐 아니라 **도메인 엔티티 타입에도 영향**을 준다:

- `src/entities/workflow/model/types.ts`의 `Workflow` 인터페이스가 `status`, `sharedWith`, `isTemplate`, `templateId`를 **필수 필드**로 갖고 있다
- `WorkflowSummary`가 `Pick<Workflow, ... | "status">`로 `status`에 의존한다

따라서 API 응답 타입 수정 시 도메인 타입도 함께 수정해야 한다:
- `status` → optional로 변경하고 `isActive`에서 파생하는 getter/유틸 추가
- `sharedWith`, `isTemplate`, `templateId` → 백엔드 Response DTO 추가 요청. 합의 전까지 optional 처리

### 2-5. 워크플로우 목록 조회

| 구분 | 내용 |
|---|---|
| 프론트 현재 | `ApiResponse<WorkflowSummary[]>` — 배열 |
| 백엔드 실제 | `ApiResponse<PageResponse<WorkflowResponse>>` — 페이징 래핑 |
| 불일치 | 응답 구조 + 파라미터(`page`, `size`) 누락 |

### 2-6. 노드 추가 요청

| 필드 | 프론트 `NodeAddRequest` | 백엔드 `NodeAddRequest` | 상태 |
|---|---|---|---|
| 타입 식별 | `type` | `category` + `type` | 불일치 |
| label | 있음 | 없음 | 백엔드에 추가 요청 필요 |
| position | 있음 | 있음 | 일치 |
| config | 있음 | 있음 | 일치 |
| prevNodeId | 있음 | 있음 | 일치 |
| dataType | 없음 | 있음 | 프론트 누락 |
| outputDataType | 없음 | 있음 | 프론트 누락 |
| role | 없음 | 있음 | 프론트 누락 |
| authWarning | 없음 | 있음 | 프론트 누락 |

### 2-7. 선택지 확정 요청

| 필드 | 프론트 `NodeChoiceSelectRequest` | 백엔드 `NodeChoiceSelectRequest` | 상태 |
|---|---|---|---|
| 선택 ID | `actionId` | `selectedOptionId` | **필드명 불일치** |
| 데이터 타입 | 없음 | `dataType` (필수, `@NotBlank`) | 프론트 누락 |
| 추가 정보 | `processingMethod?`, `options?` | `context: Map<String, Object>` | **구조 불일치** |

---

## 3. NodeType 매핑 테이블

프론트엔드의 15개 `NodeType`이 백엔드의 `category` + `type` 조합과 대응하는 매핑이다.

> 백엔드 코드에서 category를 enum으로 명시하지 않았으므로, 이 매핑은 프론트에서 정의하고 백엔드와 합의해야 한다.

| 프론트 `NodeType` | 백엔드 `category` | 백엔드 `type` | 분류 |
|---|---|---|---|
| `communication` | `service` | `communication` | 도메인 서비스 |
| `storage` | `service` | `storage` | 도메인 서비스 |
| `spreadsheet` | `service` | `spreadsheet` | 도메인 서비스 |
| `web-scraping` | `service` | `web-scraping` | 도메인 서비스 |
| `calendar` | `service` | `calendar` | 도메인 서비스 |
| `notification` | `service` | `notification` | 알림 서비스 |
| `trigger` | `control` | `trigger` | 제어 흐름 |
| `filter` | `control` | `filter` | 제어 흐름 |
| `loop` | `control` | `loop` | 제어 흐름 |
| `condition` | `control` | `condition` | 제어 흐름 |
| `multi-output` | `control` | `multi-output` | 제어 흐름 |
| `early-exit` | `control` | `early-exit` | 제어 흐름 |
| `data-process` | `processing` | `data-process` | 데이터 처리 |
| `output-format` | `processing` | `output-format` | 데이터 처리 |
| `llm` | `ai` | `llm` | AI 처리 |

---

## 4. 인증 흐름 설계

### 4-1. 현재 백엔드 동작

```
GET /api/auth/google
  → 302 redirect to Google OAuth URL
  → Google 인증 완료
  → GET /api/auth/google/callback?code=xxx
  → JSON 응답: ApiResponse<LoginResponse>
```

`AuthService.getGoogleLoginUrl(baseUrl)`에서 redirect_uri를 **백엔드 URL** 기준으로 설정한다.
즉 Google이 code를 백엔드로 돌려보내고, 백엔드가 JSON으로 응답하는 구조이다.

### 4-2. 프론트 대응 설계

#### 시나리오 A: 프론트 콜백 (권장)

Google redirect_uri를 프론트 URL로 설정하고, 프론트가 code를 받아 백엔드에 전달하는 방식이다.
토큰이 URL에 노출되지 않으므로 보안상 가장 안전하다.

```
1. 프론트가 Google OAuth URL을 구성:
   - client_id: 환경변수 VITE_GOOGLE_CLIENT_ID
   - redirect_uri: 프론트 /login/callback
   - response_type: code
   - state: crypto.randomUUID()로 생성, sessionStorage에 저장
   - scope: openid email profile
2. window.location.href = googleOAuthUrl
3. Google 인증 → 프론트 /login/callback?code=xxx&state=yyy
4. 프론트 콜백 페이지:
   a. URL의 state와 sessionStorage의 state를 비교 (CSRF 방어)
   b. 검증이 끝나면 sessionStorage의 state를 삭제 (재사용 방지)
   c. 불일치 시 에러 표시, /login으로 리다이렉트
   d. 일치 시 authApi.googleCallback(code) 호출
      - 현재 코드: GET /auth/google/callback?code= (query param)
      - code는 일회용이고 수초 내 만료되므로 GET query로도 보안 위험은 낮음
5. 백엔드가 code로 Google token exchange → JWT 발급 → JSON 응답
6. 프론트가 토큰을 localStorage에 저장 → /workflows 이동
```

**CSRF 방어 — `state` 파라미터:**
- 프론트가 OAuth URL 구성 시 `state`를 생성하여 `sessionStorage`에 저장한다
- Google이 콜백 시 `state`를 그대로 돌려보내므로, 콜백 페이지에서 저장값과 비교한다
- 불일치하면 인증 처리를 중단한다 (CSRF 공격 방지)
- 검증이 끝나면 성공/실패 여부와 무관하게 `state`를 삭제한다

**전제 조건:** 백엔드의 redirect_uri 구성이 프론트 URL을 가리키도록 수정 필요. 또는 프론트가 직접 Google OAuth URL을 구성하되, 백엔드 콜백 API가 프론트 origin에서 오는 code도 처리할 수 있어야 한다.

**콜백 API 계약 현재 상태:**
현재 `src/shared/api/auth.api.ts`에서 `googleCallback(code)`는 `GET /auth/google/callback?code=${code}`로 정의돼 있다. 이 계약은 백엔드의 현재 구현(`@GetMapping("/google/callback") @RequestParam String code`)과 일치하므로 **변경하지 않는다.** code는 일회용이고 수초 내 만료되므로 query param 노출의 보안 위험은 낮다. 향후 POST body 전달로 변경하려면 프론트 API와 백엔드 컨트롤러를 동시에 수정해야 한다.

**보안 포인트:**
- authorization code는 일회용이고 수초 내 만료되므로 URL에 노출돼도 위험이 낮다
- 토큰은 JSON 응답 body로만 전달되므로 URL/Referer/브라우저 히스토리에 남지 않는다
- `state` 파라미터로 CSRF 공격을 방어한다

#### 시나리오 B: 백엔드 콜백 + 일회용 코드 교환 (대안)

백엔드가 콜백 처리 후 프론트로 리다이렉트하되, **토큰 대신 일회용 교환 코드**를 전달한다.

```
1. window.location.href = `${API_BASE_URL}/auth/google`
2. 백엔드 302 → Google
3. Google 인증 → 백엔드 /api/auth/google/callback?code=xxx
4. 백엔드가 JWT 발급, 일회용 교환 코드(exchange_code) 생성하여 서버에 임시 저장
5. 백엔드가 프론트로 redirect: ${FRONTEND_URL}/login/callback?exchange_code=...
6. 프론트가 exchange_code로 POST /api/auth/exchange 호출 → 토큰 수령
```

**장점:** access/refresh 토큰이 URL에 절대 노출되지 않는다.
**단점:** 백엔드에 exchange 엔드포인트와 임시 저장소 추가 필요.

#### ~~시나리오 C: 백엔드 콜백 + URL에 토큰 전달 (지양)~~

~~백엔드가 콜백 후 `?accessToken=...&refreshToken=...`을 query string으로 전달하는 방식.~~

**이 방식은 사용하지 않는다.** 토큰이 브라우저 히스토리, 서버 로그, Referer 헤더에 남아 보안 위험이 크다. 현재 프론트가 localStorage에 토큰을 저장하는 구조(`client.ts:33`)와 결합하면 리스크가 더 커진다.

### 4-3. 프론트 기반 구현 (시나리오 공통)

어떤 시나리오든 프론트에서 필요한 기반은 동일하다:

1. **콜백 라우트** (`/login/callback`) — URL에서 code/state 추출 + state 검증 + 검증 후 state 정리
2. **세션 관리** — 아래 4-4에서 상세 설명
3. **인증 가드** — 토큰 없는 사용자를 `/login`으로 리다이렉트
4. **라우터 수정** — 콜백 라우트 추가, 보호 라우트 적용

### 4-4. 세션 관리 책임 통합

현재 세션 관련 코드가 두 곳에 분산돼 있다:

| 파일 | 현재 역할 |
|---|---|
| `src/shared/api/client.ts` | 토큰 읽기(`getAccessToken`), 쓰기(`storeTokens`), 삭제(`clearTokens`), 리다이렉트(`redirectToLogin`) |
| `src/shared/libs/auth-session.ts` | 토큰 삭제(`clearAuthSession`)만 — `client.ts`의 `clearTokens`와 중복 |

이대로 `auth-session.ts`에 사용자 정보 저장을 추가하면 세션 소스가 둘로 갈린다.

**통합 방침:**

`auth-session.ts`를 **세션의 단일 소스(single source of truth)**로 만들고, `client.ts`는 이를 import해서 쓴다.

```typescript
// src/shared/libs/auth-session.ts (통합 후)

const ACCESS_TOKEN_KEY = "accessToken";
const REFRESH_TOKEN_KEY = "refreshToken";
const USER_KEY = "authUser";

// ── 토큰 ──
export const getAccessToken = () => localStorage.getItem(ACCESS_TOKEN_KEY);
export const getRefreshToken = () => localStorage.getItem(REFRESH_TOKEN_KEY);

export const storeTokens = (accessToken: string, refreshToken: string) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
};

// ── 사용자 정보 ──
export const getAuthUser = (): AuthUser | null => {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
};

export const storeAuthUser = (user: AuthUser) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};

// ── 전체 세션 정리 ──
export const clearAuthSession = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

// ── 인증 여부 ──
export const isAuthenticated = () => getAccessToken() !== null;
```

```typescript
// src/shared/api/client.ts (변경)
// 토큰/사용자 관련 함수를 auth-session.ts에서 import
import {
  getAccessToken,
  getRefreshToken,
  storeTokens,
  storeAuthUser,
  clearAuthSession,
} from "../libs/auth-session";

// 기존 getAccessToken, getRefreshToken, storeTokens, clearTokens 함수 삭제
// refresh 응답(LoginResponse)에서 user도 함께 저장
// redirectToLogin은 client.ts에 유지 (API 레이어의 에러 핸들링 책임)
```

이렇게 하면:
- 토큰 저장소 키 상수가 한 곳에만 존재한다
- 사용자 정보도 같은 모듈에서 관리된다
- `client.ts`는 세션 데이터를 import만 하고, HTTP 에러 핸들링에 집중한다

### 4-5. OAuth URL 구성 책임 분리

Google OAuth URL 구성과 `state` 저장은 브라우저 환경 의존 로직이다. 따라서 **HTTP 계약만 다루는** `src/shared/api/auth.api.ts`가 아니라 `src/shared/libs/` 하위 유틸로 두는 편이 현재 프로젝트 컨벤션에 맞다.

**역할 분리 원칙:**

- `src/shared/api/auth.api.ts` — 백엔드 HTTP 계약 (`googleCallback`, `refresh`, `logout`)
- `src/shared/libs/auth-session.ts` — 토큰/사용자 세션 저장소
- `src/shared/libs/google-oauth.ts` — Google OAuth URL 구성, `state` 생성/읽기/삭제

```typescript
// src/shared/libs/google-oauth.ts

const OAUTH_STATE_KEY = "googleOAuthState";
const GOOGLE_OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

export const createGoogleOAuthUrl = () => {
  const state = crypto.randomUUID();
  sessionStorage.setItem(OAUTH_STATE_KEY, state);

  const params = new URLSearchParams({
    client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
    redirect_uri: `${window.location.origin}/login/callback`,
    response_type: "code",
    scope: "openid email profile",
    state,
  });

  return `${GOOGLE_OAUTH_URL}?${params.toString()}`;
};

export const readOAuthState = () => sessionStorage.getItem(OAUTH_STATE_KEY);

export const clearOAuthState = () => {
  sessionStorage.removeItem(OAUTH_STATE_KEY);
};
```

이렇게 두면 `LoginPage`는 `createGoogleOAuthUrl()`만 호출하면 되고, `auth.api.ts`는 axios 기반 백엔드 통신 계약만 유지한다.

---

## 5. 에디터 저장 전략

### 5-1. Phase 1: 일괄 저장 방식 (권장)

```
 ┌───────────────────────┐
 │    workflowStore       │  ← Zustand (로컬 상태)
 │    nodes[], edges[]    │
 └───────────┬───────────┘
             │
  에디터 진입: GET /api/workflows/{id}
             │
             ▼
  hydrateStore(response)  →  store에 세팅
             │
  ...사용자 편집 (로컬에서만 변경)...
             │
  "저장" 버튼: toWorkflowUpdateRequest(store)
             │
             ▼
  PUT /api/workflows/{id}
             │
             ▼
  서버 검증 + 저장, warnings 반환
             │
             ▼
  프론트에서 warnings 표시
```

- 장점: API 호출 최소화, 구현 단순, 기존 store 구조와 자연스럽게 맞음
- 단점: 저장 전 브라우저 닫으면 편집 내용 유실
- 보완: `beforeunload` 이벤트로 미저장 경고 표시

### 5-2. Phase 2: 건별 동기화 (향후)

노드 추가/수정/삭제마다 개별 API 호출. 낙관적 업데이트 + 에러 시 롤백.
공유 편집, 실시간 백업이 필요할 때 전환한다.

---

## 6. 선택 위저드 연동 전략

### 6-1. 현재 상태

프론트에 `src/features/choice-panel/model/mappingRules.ts`로 **1200개 시나리오의 규칙이 하드코딩**돼 있다.
백엔드에도 `mapping_rules.json`에 동일한 규칙이 있다.

### 6-2. 권장 방향: 서버 위임

규칙이 두 곳에 있으면 동기화 문제가 생긴다. 프론트 `MAPPING_RULES`를 제거하고 서버 API를 사용한다.

```
[위저드 흐름]

1. 사용자가 노드 클릭 → OutputPanel 위저드 모드 진입
2. GET /api/workflows/{id}/choices/{prevNodeId}
   → ChoiceResponse { dataType, requiresProcessingMethod, processingMethods?, actions }
3. 사용자가 선택
4. POST /api/workflows/{id}/choices/{prevNodeId}/select
   → NodeSelectionResult { nodeType, outputDataType, config, followUp?, branchConfig? }
5. 결과를 바탕으로 store에 노드 추가
```

### 6-3. 전환 시 변경점과 주의사항

| 파일 | 변경 | 비고 |
|---|---|---|
| `src/features/choice-panel/model/mappingRules.ts` | 삭제 또는 오프라인 fallback으로 보관 | |
| `src/features/choice-panel/model/types.ts` | **유지** — 서버 응답 타입과 통일 | |
| `src/features/choice-panel/model/dataTypeKeyMap.ts` | **유지** — 백엔드가 프론트 native `DataType`을 내려준다는 합의 전까지 변환 유틸 필요 | OutputPanel(`src/widgets/output-panel/ui/OutputPanel.tsx:198`)이 `toMappingKey()`에 직접 의존하고 있으며, 기존 설계 문서(`NODE_SETUP_WIZARD_DESIGN.md`)에서도 유지 대상으로 잡고 있다 |

**서버 위임 전환 시 `dataTypeKeyMap.ts` 처리 방침:**

백엔드 `ChoiceResponse`는 `dataType`을 `UPPER_SNAKE_CASE`(`FILE_LIST` 등)로 내려준다. 현재 OutputPanel은 프론트 `DataType`(`file-list`)을 `MappingDataTypeKey`(`FILE_LIST`)로 변환하는 `toMappingKey()`를 사용한다. 서버 위임 시:

1. 서버 응답의 `dataType`이 이미 `UPPER_SNAKE_CASE`이므로, OutputPanel이 `toMappingKey()`를 거치지 않고 서버 응답을 직접 쓸 수 있다
2. 단, 로컬 store의 노드 `outputTypes`는 프론트 `DataType` 형식이므로, 서버 API 호출 전 변환은 여전히 필요하다
3. 따라서 `dataTypeKeyMap.ts`는 **역할이 바뀌지만 삭제되지 않는다** — 로컬→서버 방향 변환용으로 유지

---

## 7. 파일 변경 범위

### 7-1. 수정 대상 파일 (14개)

| 파일 | 변경 내용 |
|---|---|
| `src/shared/types/api.type.ts` | `ValidationWarning` 타입 추가 |
| `src/shared/api/auth.api.ts` | `AuthUser`에 `createdAt` 추가, `getGoogleLoginUrl()` 삭제, `RefreshTokenResponse` → `LoginResponse` 통일. **HTTP 계약만 유지** |
| `src/shared/api/workflow.api.ts` | **가장 큰 변경.** `NodeDefinitionResponse`에 `category` 추가, `EdgeDefinitionResponse` 보존 정책 반영, `NodeAddRequest` 확장, `NodeChoiceSelectRequest` 필드명 수정, `getList()` 페이지네이션 추가, `WorkflowResponse`에 `warnings` 추가 |
| `src/shared/api/client.ts` | `refreshAccessToken` 응답 타입을 `LoginResponse`로 수정, 토큰/사용자 세션 함수를 `auth-session.ts`에서 import하도록 변경 (자체 구현 삭제), refresh 시 `user` 저장 |
| `src/shared/libs/workflow-adapter.ts` | `category`/`type` 매핑 테이블 추가, `toNodeDefinition()` / `toFlowNode()` 수정, edge 변환에 보존 정책 적용, `hydrateStore()`에서 `status` 파생 |
| `src/shared/libs/auth-session.ts` | **세션 단일 소스로 확장.** 토큰 읽기/쓰기/삭제(기존 `client.ts`에서 이동), 사용자 정보 저장/조회, `isAuthenticated()` 추가 |
| `src/shared/libs/index.ts` | `google-oauth` barrel export 추가 |
| `src/shared/constants/route-path.ts` | `LOGIN_CALLBACK` 라우트 추가 |
| `src/shared/constants/index.ts` | `query-keys` barrel export 추가 |
| `src/app/routes/Router.tsx` | `LoginCallbackPage` 콜백 라우트 추가, 인증 가드 적용 |
| `src/app/routes/components/index.ts` | `ProtectedRoute` barrel export 추가 (현재 빈 파일) |
| `src/entities/workflow/model/types.ts` | `Workflow` 인터페이스에서 `status` optional 처리 또는 제거 후 파생 유틸 추가, `sharedWith`/`isTemplate`/`templateId` optional 처리, `warnings` 필드 추가. `WorkflowSummary`의 `status` 의존성 제거 또는 `isActive` 기반으로 변경 |
| `src/pages/index.ts` | `login-callback` barrel export 추가 |
| `src/pages/login/LoginPage.tsx` | Google 로그인 버튼 연결. `createGoogleOAuthUrl()` 호출 후 브라우저 이동 |

### 7-2. 신규 파일 (5개)

| 파일 | 역할 |
|---|---|
| `src/shared/constants/query-keys.ts` | React Query 캐시 키 상수 정의 |
| `src/shared/libs/google-oauth.ts` | Google OAuth URL 구성, `state` 생성/읽기/삭제 유틸 |
| `src/app/routes/components/ProtectedRoute.tsx` | 인증 가드 컴포넌트 — `isAuthenticated()`로 토큰 체크 → 없으면 `/login` 리다이렉트 |
| `src/pages/login-callback/LoginCallbackPage.tsx` | OAuth 콜백 처리 페이지 (state 검증 + code 교환 + 세션 저장) |
| `src/pages/login-callback/index.ts` | `LoginCallbackPage` folder-level export |

> 인증 가드는 `src/app/routes/components/` 하위에 둔다. 이 디렉토리와 barrel export 파일은 이미 존재하므로 컨벤션에 맞는다.

### 7-3. 향후 필요 (기반 이후)

| 파일 | 역할 | barrel export 수정 필요 |
|---|---|---|
| React Query 훅 (`useWorkflowList`, `useWorkflow`, `useSaveWorkflow` 등) | 각 도메인별 서버 상태 관리 | 해당 feature/shared 모듈의 index.ts |

---

## 8. React Query 키 설계

```typescript
export const QUERY_KEYS = {
  // 사용자
  currentUser: ["user", "me"] as const,

  // 워크플로우
  workflows: ["workflows"] as const,
  workflow: (id: string) => ["workflows", id] as const,
  workflowChoices: (workflowId: string, prevNodeId: string) =>
    ["workflows", workflowId, "choices", prevNodeId] as const,

  // 템플릿
  templates: (category?: string) =>
    category ? ["templates", { category }] : (["templates"] as const),
  template: (id: string) => ["templates", id] as const,

  // 실행
  executions: (workflowId: string) =>
    ["workflows", workflowId, "executions"] as const,
  execution: (workflowId: string, execId: string) =>
    ["workflows", workflowId, "executions", execId] as const,

  // OAuth 토큰
  oauthTokens: ["oauth-tokens"] as const,
} as const;
```

---

## 9. 어댑터 수정 상세 설계

### 9-1. NodeType 매핑 함수

```typescript
// 프론트 NodeType → 백엔드 { category, type }
const NODE_TYPE_TO_BACKEND: Record<NodeType, { category: string; type: string }> = {
  communication: { category: "service", type: "communication" },
  storage:       { category: "service", type: "storage" },
  spreadsheet:   { category: "service", type: "spreadsheet" },
  "web-scraping": { category: "service", type: "web-scraping" },
  calendar:      { category: "service", type: "calendar" },
  notification:  { category: "service", type: "notification" },
  trigger:       { category: "control", type: "trigger" },
  filter:        { category: "control", type: "filter" },
  loop:          { category: "control", type: "loop" },
  condition:     { category: "control", type: "condition" },
  "multi-output": { category: "control", type: "multi-output" },
  "early-exit":  { category: "control", type: "early-exit" },
  "data-process": { category: "processing", type: "data-process" },
  "output-format": { category: "processing", type: "output-format" },
  llm:           { category: "ai", type: "llm" },
};

// 백엔드 type → 프론트 NodeType (category는 사용하지 않고 type만으로 역매핑)
const BACKEND_TYPE_TO_NODE_TYPE: Record<string, NodeType> = Object.fromEntries(
  Object.entries(NODE_TYPE_TO_BACKEND).map(([nodeType, { type }]) => [type, nodeType as NodeType])
);
```

### 9-2. toNodeDefinition() 변경

```typescript
// Before (현재)
{
  id, type: node.data.type, label: node.data.label,
  role, position, config, dataType, outputDataType, authWarning
}

// After (수정)
{
  id,
  category: NODE_TYPE_TO_BACKEND[node.data.type].category,
  type: NODE_TYPE_TO_BACKEND[node.data.type].type,
  label: node.data.label,  // 백엔드에 label 필드 추가 요청
  role, position, config,
  dataType, outputDataType, authWarning
}
```

> **label 처리 방침:** `label`은 presentation 필드이지 config 데이터가 아니다. 현재 config 계층은 실행/설정 데이터 중심으로 정의돼 있고(`src/entities/node/model/types.ts:30`), adapter도 label을 top-level 값으로 다루고 있다(`workflow-adapter.ts:92`). **백엔드 `NodeDefinition`에 `label: String` 필드를 추가 요청**하는 것이 유일하게 올바른 방향이다.
>
> **임시 대응은 실질적으로 불가능하다.** adapter 내부 메모리 맵으로 label을 보관하는 방식은 새로고침이나 새 세션에서 `GET /workflows/{id}`를 호출하면 복원할 데이터가 없어 label이 사라진다. 즉 persisted workflow를 다시 열 때마다 모든 노드 제목이 기본값(`NODE_REGISTRY[type].label`)으로 리셋된다. 이것은 사용자에게 보이는 데이터 손실이므로 임시 대응이 아니라 결함이다.
>
> **결론:** label 필드 추가는 백엔드 합의 전까지 **구현을 시작할 수 없는 blocking 의존성**이다. 합의가 지연되면, 최소한 `toFlowNode()`에서 `NODE_REGISTRY[type].label`을 fallback으로 쓰되 사용자가 커스텀한 label은 유실된다는 제약을 명시해야 한다.

### 9-3. toFlowNode() 변경

```typescript
// Before (현재)
const nodeType = getFallbackNodeType(node.type);

// After (수정)
const nodeType = BACKEND_TYPE_TO_NODE_TYPE[node.type] ?? "llm";
const label = node.label  // 백엔드에 label 필드가 추가된 경우
  ?? NODE_REGISTRY[nodeType].label;  // fallback
```

### 9-4. Edge 변환 — 보존 정책

edge 변환은 기존 round-trip을 유지하되, 백엔드에 없는 필드의 처리를 명확히 한다.

```typescript
// toEdgeDefinition (프론트 → 백엔드)
// 백엔드에 id 필드가 추가될 때까지는 source/target만 전송
export const toEdgeDefinition = (edge: Edge): BackendEdgeDefinition => ({
  source: edge.source,
  target: edge.target,
  // 백엔드에 id 필드가 추가되면 아래 주석 해제:
  // id: edge.id,
});

// toFlowEdge (백엔드 → 프론트)
// 백엔드에서 id가 오지 않으면 UUID로 생성
export const toFlowEdge = (edge: BackendEdgeDefinition): Edge => ({
  id: edge.id ?? crypto.randomUUID(),  // 복수 edge 구분을 위해 UUID 사용
  source: edge.source,
  target: edge.target,
  sourceHandle: null,
  targetHandle: null,
});
```

**sourceHandle/targetHandle:**
React Flow 전용 필드이므로 백엔드와 주고받지 않는다. 프론트 로컬에서만 관리하며, 저장/로드 시에는 null로 초기화한다. 향후 handle 정보까지 보존해야 하면 백엔드 EdgeDefinition 확장을 요청한다.

---

## 10. 흐름별 연동 맵

### 10-1. 인증 흐름

| 프론트 화면/기능 | 현재 상태 | 백엔드 API | 비고 |
|---|---|---|---|
| LoginPage - 로그인 버튼 | 빈 페이지 | `-` (프론트에서 Google OAuth URL 구성) | `createGoogleOAuthUrl()` 호출 + `state` 저장 후 브라우저 이동 |
| OAuth 콜백 처리 | 미구현 | `GET /api/auth/google/callback?code=` | `LoginCallbackPage` 필요, `state` 검증 후 code 교환 |
| 토큰 갱신 | interceptor 구현됨 | `POST /api/auth/refresh` | 연결 완료, 타입 수정만 |
| 로그아웃 | **연결됨** | `POST /api/auth/logout` | 완료 |
| 인증 가드 | 미구현 | 프론트 단독 | 토큰 체크 → 리다이렉트 |

### 10-2. 워크플로우

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| WorkflowsPage 목록 | placeholder | `GET /api/workflows?page=&size=` |
| 워크플로우 생성 | **연결됨** | `POST /api/workflows` |
| 에디터 진입 시 로드 | store 기반, API 미연결 | `GET /api/workflows/{id}` |
| 저장 | 미연결 | `PUT /api/workflows/{id}` |
| 삭제 | 미구현 | `DELETE /api/workflows/{id}` |
| 공유 | 미구현 | `POST /api/workflows/{id}/share` |

### 10-3. 노드 선택 위저드

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| 선택지 조회 | `MAPPING_RULES` 하드코딩 | `GET /api/workflows/{id}/choices/{prevNodeId}` |
| 선택 확정 | 로컬 계산 | `POST /api/workflows/{id}/choices/{prevNodeId}/select` |

### 10-4. 실행

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| 실행 버튼 | UI만 존재 | `POST /api/workflows/{id}/execute` |
| 실행 이력 목록 | 미구현 | `GET /api/workflows/{id}/executions` |
| 실행 상세/로그 | 미구현 | `GET /api/workflows/{id}/executions/{execId}` |
| 롤백 | 미구현 | `POST /api/workflows/{id}/executions/{execId}/rollback` |

### 10-5. 템플릿

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| 목록 조회 | placeholder | `GET /api/templates` |
| 상세 조회 | placeholder | `GET /api/templates/{id}` |
| 인스턴스화 | 미구현 | `POST /api/templates/{id}/instantiate` |
| 템플릿 저장 | 미구현 | `POST /api/templates` |

### 10-6. 외부 서비스 토큰

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| 연결 목록 | 미구현 | `GET /api/oauth-tokens` |
| 서비스 연결 | 미구현 | `POST /api/oauth-tokens/{service}/connect` |
| 연결 해제 | 미구현 | `DELETE /api/oauth-tokens/{service}` |

### 10-7. 사용자

| 프론트 화면/기능 | 현재 상태 | 백엔드 API |
|---|---|---|
| 내 정보 조회 | 미구현 | `GET /api/users/me` |
| 이름 수정 | 미구현 | `PUT /api/users/me` |
| 회원 탈퇴 | 미구현 | `DELETE /api/users/me` |

---

## 11. 연동 우선순위

| 순위 | 영역 | 이유 |
|---|---|---|
| **1** | 인증 (로그인/콜백/가드) | 인증 없이 다른 API 호출 불가 |
| **2** | 워크플로우 로드/저장 | 에디터의 핵심, 데이터 영속성 |
| **3** | 워크플로우 목록 | 대시보드 기본 기능 |
| **4** | 선택 위저드 서버 연동 | 로컬 규칙 제거, 서버 기반 전환 |
| **5** | 실행 | 실제 동작의 핵심 가치 |
| **6** | 템플릿 | 온보딩/재사용 편의 |
| **7** | 외부 서비스 토큰 | 실행 전 필수이나 UI 복잡도 높음 |
| **8** | AI 생성 | FastAPI 의존, 별도 진행 가능 |

---

## 12. 백엔드에 요청할 사항

프론트 기반 작업만으로는 해결할 수 없는, 백엔드 조정이 필요한 항목이다.

| 항목 | 현재 상태 | 요청 내용 | 우선순위 | 비고 |
|---|---|---|---|---|
| OAuth redirect_uri | 백엔드 URL 기준 | redirect_uri를 프론트 URL로 변경하거나, 프론트에서 보낸 code를 처리할 수 있도록 수정 | P0 | 인증 전체의 선행 조건 |
| `NodeDefinition`에 `label` | 없음 | `label: String` 필드 추가 | P0 | **blocking** — 이 필드 없이는 사용자가 설정한 노드 제목이 저장/로드 시 유실됨. 임시 대응 불가 |
| `WorkflowResponse`에 누락 필드 | `sharedWith`, `isTemplate`, `templateId` 미포함 | Response DTO에 해당 필드 추가 | P1 | 프론트 `Workflow` 타입과 `WorkflowSummary` 타입이 이 필드에 의존 |
| `EdgeDefinition`에 `id` | 없음 | `id: String` 필드 추가 (복수 edge 구분 필수) | P1 | 조건 분기 등 같은 source/target 간 복수 edge 지원에 필수 |
| NodeType `category` 매핑 | 암묵적 | category 값 목록을 문서화하거나 enum으로 정의 | P2 | 프론트 매핑 테이블(섹션 3) 기준으로 합의 필요 |
