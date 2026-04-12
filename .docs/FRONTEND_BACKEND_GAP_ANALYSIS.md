# 프론트-백엔드 연동 갭 분석

> 작성일: 2026-04-13
> 분석 기준: `front_docs/` 전체 문서 + 현재 백엔드 구현 코드
> 목적: 프론트-백엔드 연결 시 실제로 동작하지 않는 부분을 식별하고 우선순위를 정리한다.

---

## 요약

| 심각도 | 항목 수 | 설명 |
|--------|---------|------|
| 🔴 P0 (로그인 불가) | 2 | 이 문제 없이는 어떤 API도 호출 불가 |
| 🟠 P1 (데이터 손실) | 3 | 저장/로드 시 데이터 유실 발생 |
| 🟡 P2 (기능 오동작) | 3 | 특정 기능이 예상과 다르게 동작 |
| 🟢 P3 (타입 누락) | 2 | 런타임에는 문제 없으나 타입 불일치 |

---

## 🔴 P0 — 로그인 자체가 불가능한 문제

### 1. OAuth 콜백 플로우 불일치 (가장 중요)

**현재 백엔드 동작:**
```
GET /api/auth/google/callback?code=...
  → AuthController.googleCallback()
  → AuthService.processGoogleLogin()
  → return ApiResponse<LoginResponse>  ← JSON 응답 반환
```

**프론트가 기대하는 동작** (`BACKEND_OAUTH_FLOW_DESIGN.md`):
```
GET /api/auth/google/callback?code=...
  → 백엔드가 Google token exchange + JWT 발급
  → exchange_code 생성 (일회용, 30초~1분 TTL)
  → 302 redirect → {FRONT_REDIRECT_URI}/auth/callback?exchange_code=...

POST /api/auth/exchange { "exchangeCode": "..." }
  → LoginResponse 반환
```

**현재 상황:**
- 프론트는 이미 `/auth/callback` 페이지를 구현하고 `exchange_code`를 처리하도록 되어 있다.
- `docker-compose.local.yml`에도 `FRONT_REDIRECT_URI: http://localhost:5173/auth/callback`이 이미 추가돼 있다.
- 백엔드는 아직 JSON을 반환하며 redirect하지 않는다.
- `POST /api/auth/exchange` 엔드포인트가 존재하지 않는다.

**백엔드에서 필요한 변경:**
1. `application.yml`에 `FRONT_REDIRECT_URI` env var 추가
2. `AuthController.googleCallback()` → JSON 반환 대신 `302 redirect to {FRONT_REDIRECT_URI}?exchange_code=...`
3. `POST /api/auth/exchange` 신규 엔드포인트 구현
4. exchange_code 임시 저장소 (MongoDB 또는 In-Memory Map + TTL)

---

### 2. `isActive` vs `active` JSON 키 불일치 + 현재 잘못된 수정

**문제 배경:**
Lombok + Jackson의 boolean 처리 방식으로 인해 JSON 키 이름이 코드와 다르게 생성된다.

| 위치 | Java 필드 | Lombok getter | Jackson JSON 키 |
|------|-----------|---------------|----------------|
| `Workflow` 엔티티 | `boolean isActive` | `isActive()` | **`"active"`** |
| `WorkflowUpdateRequest` DTO | `Boolean isActive` | `getIsActive()` | **`"isActive"`** |
| `WorkflowResponse` DTO | `boolean isActive` | `isActive()` | **`"active"`** |

**현재 상태:**
- `WORKFLOW_LIST_PAGE_DESIGN.md`(2026-04-12)에서 프론트팀은 이미 Swagger 응답 기준(`"active"`)으로 코드를 수정 완료했다.
- 프론트는 현재 응답에서 `response.active`를 읽고, PUT 요청 body에 `{ "active": false }`를 전송한다.
- **BUT** 오늘 `WorkflowResponse`에 `@JsonProperty("isActive")`를 추가한 것은 프론트 기대와 반대 방향이라 REVERT가 필요하다.
- 진짜 문제는 `WorkflowUpdateRequest`가 `"isActive"` 키를 기대하는데 프론트는 `"active"` 키를 전송한다는 점이다.

**올바른 수정 방향:**
```java
// WorkflowResponse.java — @JsonProperty("isActive") 제거 (REVERT 필요)
private final boolean isActive;  // 그대로 → Jackson이 "active"로 직렬화

// WorkflowUpdateRequest.java — @JsonProperty("active") 추가
@JsonProperty("active")
private Boolean isActive;  // Jackson이 "active" 키로 역직렬화
```

---

## 🟠 P1 — 저장/로드 시 데이터가 유실되는 문제

### 3. `NodeDefinition`에 `label` 필드 없음

**프론트 요구사항** (`BACKEND_INTEGRATION_DESIGN.md` 섹션 12):
- 사용자가 설정한 노드 제목(`label`)이 저장/로드 시 유지돼야 한다.
- `label` 없이는 저장 후 다시 열 때 모든 노드 제목이 기본값으로 리셋된다.
- 문서에서 "임시 대응 불가능, blocking 의존성"으로 분류돼 있다.

**현재 백엔드 `NodeDefinition` 엔티티:**
```java
private String id;
private String category;
private String type;
// label 없음 ← 문제
private Position position;
private Map<String, Object> config;
private String dataType;
private String outputDataType;
private String role;
private boolean authWarning;
```

**필요한 변경:** `NodeDefinition`에 `private String label;` 추가

---

### 4. `EdgeDefinition`에 `id` 필드 없음

**프론트 요구사항** (`BACKEND_INTEGRATION_DESIGN.md` 섹션 2-3):
- 같은 source/target 사이에 복수 edge(조건 분기)를 지원하려면 edge `id`가 필수다.
- 백엔드에서 `id` 없이 오면 프론트는 `crypto.randomUUID()`로 임시 생성하지만, 저장-로드 시 id가 달라진다.

**현재 백엔드 `EdgeDefinition` 엔티티:**
```java
private String source;
private String target;
// id 없음 ← 문제
```

**필요한 변경:** `EdgeDefinition`에 `private String id;` 추가

---

### 5. `WorkflowResponse` DTO에 엔티티 필드 3개 누락

**엔티티에는 있지만 Response DTO에 없는 필드:**

| 필드 | 엔티티 | Response DTO | 영향 |
|------|--------|-------------|------|
| `sharedWith` | `List<String>` | 없음 | 공유 워크플로우 여부 프론트에서 알 수 없음 |
| `isTemplate` | `boolean` | 없음 | 템플릿 여부 구분 불가 |
| `templateId` | `String` | 없음 | 어떤 템플릿 기반인지 알 수 없음 |

**프론트 영향:** `entities/workflow/model/types.ts`의 `Workflow` 인터페이스가 이 필드들에 의존한다.

---

## 🟡 P2 — 특정 기능이 오동작하는 문제

### 6. `NodeChoiceSelectRequest` 필드명 불일치

| 필드 | 프론트 전송 | 백엔드 기대 | 상태 |
|------|------------|------------|------|
| 선택 ID | `actionId` | `selectedOptionId` | **필드명 불일치 → 매핑 실패** |
| 데이터 타입 | 없음 | `dataType` (`@NotBlank`) | **필수 필드 누락 → 400 에러** |
| 추가 정보 | `processingMethod?`, `options?` | `context: Map<String, Object>` | 구조 불일치 |

---

### 7. `NodeDefinition`에 `category` 필드 있으나 어댑터 매핑 합의 필요

**현재 상태:**
- 백엔드: `category: String` + `type: String` (예: `category: "service"`, `type: "communication"`)
- 프론트: `type: NodeType` 단일 필드 (예: `type: "communication"`)

`BACKEND_INTEGRATION_DESIGN.md` 섹션 3에 매핑 테이블이 정의돼 있으나, 실제 백엔드 enum/상수로 정의되지 않아 암묵적 합의 상태다.

---

### 8. 워크플로우 목록 API 응답 구조

| 항목 | 프론트 기대 | 백엔드 실제 |
|------|-----------|-----------|
| 응답 구조 | `ApiResponse<PageResponse<WorkflowResponse>>` | 일치 ✓ |
| 요청 파라미터 | `page`, `size` | `page`, `size` | 일치 ✓ |
| `totalElements` vs `totalPages` | 프론트 `useInfiniteQuery` 기준 | 둘 다 제공 ✓ |

목록 자체 구조는 맞지만, 위 P0~P1 문제(active 키, 누락 필드)로 인해 카드 렌더링이 실패할 수 있다.

---

## 🟢 P3 — 타입 누락 (런타임 영향 낮음)

### 9. `ValidationWarning` 타입 프론트 미정의

백엔드 `WorkflowResponse`에 `warnings: List<ValidationWarning>`가 있으나, 프론트 타입에 정의되지 않았다.
`WORKFLOW_LIST_PAGE_DESIGN.md`는 `warnings`를 이미 활용하고 있어서 실제로는 동작하지만 타입 정의가 없는 상태다.

---

### 10. `POST /api/auth/refresh` 응답 타입 불일치

| 구분 | 내용 |
|------|------|
| 프론트 기대 | `{ accessToken, refreshToken }` |
| 백엔드 실제 | `LoginResponse { accessToken, refreshToken, user: UserResponse }` |

refresh interceptor가 user 정보를 저장하지 않을 뿐, 토큰 갱신 자체는 동작한다.

---

## 수정 우선순위 로드맵

### Phase 1: 로그인 가능 상태 만들기 (P0)

```
1. AuthController.googleCallback() 수정
   → exchange_code 생성 + redirect 구현

2. POST /api/auth/exchange 신규 엔드포인트 추가

3. WorkflowResponse @JsonProperty("isActive") REVERT

4. WorkflowUpdateRequest @JsonProperty("active") 추가

5. FRONT_REDIRECT_URI 환경변수 application.yml에 추가
```

### Phase 2: 데이터 영속성 확보 (P1)

```
6. NodeDefinition에 label 필드 추가

7. EdgeDefinition에 id 필드 추가

8. WorkflowResponse에 sharedWith, isTemplate, templateId 추가
```

### Phase 3: 기능 정상화 (P2)

```
9. NodeChoiceSelectRequest 필드명 정렬
   (selectedOptionId, dataType 필드 추가)

10. category/type 매핑 enum 또는 상수로 문서화
```

---

## 백엔드 미구현 API 현황

프론트 문서에 정의돼 있으나 백엔드에 아직 없는 엔드포인트:

| 엔드포인트 | 상태 | 우선순위 |
|-----------|------|---------|
| `POST /api/auth/exchange` | ❌ 미구현 | P0 |
| `PUT /api/users/me` | ❌ 미구현 | P3 |
| `DELETE /api/users/me` | ❌ 미구현 | P3 |
| `POST /api/workflows/generate` | ❌ 미구현 | P3 |
| `POST /api/templates` | ❌ 미구현 | P3 |

---

## 현재 정상 연동 가능한 항목

| API | 상태 | 비고 |
|-----|------|------|
| `POST /api/auth/refresh` | ⚠️ 동작함 | user 타입 미저장 |
| `POST /api/auth/logout` | ✅ 연결됨 | |
| `POST /api/workflows` | ✅ 연결됨 | |
| `GET /api/workflows` | ✅ 동작 (active 키 불일치 주의) | P0 수정 후 완전 동작 |
| `GET /api/workflows/:id` | ✅ 동작 (label 유실 주의) | |
| `DELETE /api/workflows/:id` | ✅ 동작 | |
| `GET /api/workflows/:id/choices/:prevNodeId` | ✅ 동작 | |
| `POST /api/workflows/:id/choices/:prevNodeId/select` | ❌ 필드명 불일치 | P2 수정 필요 |
| `GET /api/templates` | ✅ 동작 | |
| `GET /api/templates/:id` | ✅ 동작 | |
| `POST /api/templates/:id/instantiate` | ✅ 동작 | |
| `GET /api/oauth-tokens` | ✅ 동작 | |
| `DELETE /api/oauth-tokens/:service` | ✅ 동작 | |