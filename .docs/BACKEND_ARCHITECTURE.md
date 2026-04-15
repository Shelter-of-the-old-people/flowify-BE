# Flowify Spring Boot 백엔드 동작 흐름 문서

> 작성일: 2026-04-15
> 목적: Spring Boot 백엔드의 전체 동작 흐름과 FastAPI 통신 구조를 문서화한다.

---

## 1. 시스템 구성

```
[프론트엔드]  ←→  [Spring Boot]  ←→  [FastAPI (AI/실행 엔진)]
                       ↕
                  [MongoDB]
                       ↕
              [외부 OAuth (Google, Slack)]
```

- **Spring Boot**: 인증, 워크플로우 CRUD, 사용자 관리, OAuth 토큰 관리, FastAPI 호출 중계
- **FastAPI**: AI 워크플로우 생성, 워크플로우 실행, 롤백 처리 (Spring Boot가 위임)
- **MongoDB**: 사용자, 워크플로우, 실행 이력, OAuth 토큰, 템플릿, 교환 코드 저장

---

## 2. 인증 흐름

### 2-1. Google 로그인

```
[사용자]
  │
  ▼ GET /api/auth/google
[Spring Boot]
  └─ 302 → https://accounts.google.com/o/oauth2/v2/auth?...
       │
[Google]
  └─ 사용자 로그인 & 동의
       │
       ▼ GET /api/auth/google/callback?code=...
[Spring Boot]
  ├─ POST https://oauth2.googleapis.com/token (code → id_token 교환)
  ├─ GET https://oauth2.googleapis.com/tokeninfo (사용자 정보 조회)
  ├─ MongoDB에서 사용자 조회 또는 신규 생성
  ├─ JWT (accessToken + refreshToken) 생성
  ├─ 일회용 exchange_code 생성 (MongoDB, 30초 TTL)
  └─ 302 → https://프론트/auth/callback?exchange_code=...
       │
[프론트엔드]
  │
  ▼ POST /api/auth/exchange { "exchangeCode": "..." }
[Spring Boot]
  ├─ exchange_code 조회 → 즉시 삭제 (1회용)
  └─ 응답: { accessToken, refreshToken, user }
       │
[프론트엔드]
  └─ 토큰 저장 → 로그인 완료
```

### 2-2. 토큰 갱신

```
[프론트엔드]
  │
  ▼ POST /api/auth/refresh { "refreshToken": "..." }
[Spring Boot]
  ├─ refreshToken 검증 (만료 여부, DB 일치 여부)
  ├─ 새 accessToken + refreshToken 생성
  └─ 응답: { accessToken, refreshToken, user }
```

### 2-3. 로그아웃

```
[프론트엔드]
  │
  ▼ POST /api/auth/logout (JWT 필요)
[Spring Boot]
  └─ DB에서 refreshToken 삭제
```

---

## 3. 워크플로우 CRUD 흐름

이 영역의 모든 API는 JWT 인증이 필요하다. FastAPI 호출 없이 Spring Boot ↔ MongoDB로만 동작한다.

### 3-1. 워크플로우 생성

```
[프론트엔드]
  │
  ▼ POST /api/workflows { name, description, nodes, edges, trigger }
[Spring Boot]
  ├─ 유효성 검사 (순환 참조, 고립 노드, 필수 설정)
  ├─ MongoDB에 저장
  └─ 응답: WorkflowResponse (검증 경고 포함)
```

### 3-2. 워크플로우 목록 조회

```
[프론트엔드]
  │
  ▼ GET /api/workflows
[Spring Boot]
  ├─ 내 워크플로우 + 공유받은 워크플로우 전체 조회
  ├─ updatedAt 내림차순 정렬
  └─ 응답: List<WorkflowResponse>
```

> 페이지네이션 없음. 프론트엔드에서 무한 스크롤 처리.

### 3-3. 워크플로우 상세 조회 / 수정 / 삭제

```
GET    /api/workflows/{id}         → 상세 조회 (소유자 또는 공유 대상만)
PUT    /api/workflows/{id}         → 수정 (이름, 설명, 노드, 엣지, 트리거, 활성 상태)
DELETE /api/workflows/{id}         → 삭제 (소유자만)
```

### 3-4. 워크플로우 공유

```
POST /api/workflows/{id}/share { "userIds": ["userId1", "userId2"] }
→ 소유자만 공유 가능. sharedWith 목록에 사용자 추가.
```

### 3-5. 노드 관리

```
GET    /api/workflows/{id}/choices/{prevNodeId}            → 다음 노드 선택지 조회
POST   /api/workflows/{id}/choices/{prevNodeId}/select     → 노드 선택 확정
POST   /api/workflows/{id}/nodes                           → 노드 추가
PUT    /api/workflows/{id}/nodes/{nodeId}                  → 노드 수정
DELETE /api/workflows/{id}/nodes/{nodeId}                  → 노드 삭제 (후속 노드 캐스케이드)
```

---

## 4. AI 워크플로우 생성 흐름 (FastAPI 연동)

```
[프론트엔드]
  │
  ▼ POST /api/workflows/generate { "prompt": "매일 오전 9시에 Gmail 확인 후 Slack 전달" }
[Spring Boot]
  │
  ▼ POST {FASTAPI_URL}/api/v1/workflows/generate
  │   Header: X-Internal-Token, X-User-ID
  │   Body: { "prompt": "..." }
[FastAPI]
  │   ┌─────────────────────────────────────────┐
  │   │ FastAPI 내부 처리 (Spring Boot는 모름)   │
  │   │ - LLM 호출하여 워크플로우 구조 생성      │
  │   │ - 노드, 엣지, 트리거 JSON 구성          │
  │   └─────────────────────────────────────────┘
  │
  ▼ 응답: WorkflowCreateRequest 호환 JSON
[Spring Boot]
  ├─ ObjectMapper로 WorkflowCreateRequest 변환
  ├─ MongoDB에 워크플로우 저장
  └─ 응답: WorkflowResponse
```

---

## 5. 워크플로우 실행 흐름 (FastAPI 연동)

```
[프론트엔드]
  │
  ▼ POST /api/workflows/{id}/execute
[Spring Boot]
  ├─ 워크플로우 조회 (MongoDB)
  ├─ 접근 권한 검증 (소유자 또는 공유 대상)
  ├─ 유효성 검사 (WorkflowValidator)
  ├─ 서비스 토큰 수집:
  │   category == "service" 인 노드 → OAuthTokenService에서 복호화된 토큰 조회
  │   (토큰 만료 임박 시 자동 갱신 시도, 미연결 시 400 에러)
  │
  ▼ POST {FASTAPI_URL}/api/v1/workflows/{id}/execute
  │   Header: X-Internal-Token, X-User-ID
  │   Body: {
  │     "workflow": { 워크플로우 전체 정의 },
  │     "service_tokens": { "slack": "xoxb-...", "gmail": "ya29.a0..." }
  │   }
[FastAPI]
  │   ┌─────────────────────────────────────────────────┐
  │   │ FastAPI 내부 처리 (Spring Boot는 모름)           │
  │   │ - 노드 순서대로 실행                             │
  │   │ - service_tokens으로 외부 API 호출               │
  │   │ - 실행 결과를 MongoDB workflow_executions에 저장  │
  │   └─────────────────────────────────────────────────┘
  │
  ▼ 응답: { "execution_id": "exec_abc123" }
[Spring Boot]
  └─ execution_id를 프론트에 반환
       │
[프론트엔드]
  └─ execution_id로 실행 상태 폴링:
       GET /api/workflows/{id}/executions/{execId}
```

---

## 6. 실행 중지 흐름 (FastAPI 연동)

```
[프론트엔드]
  │
  ▼ POST /api/workflows/{id}/executions/{execId}/stop
[Spring Boot]
  ├─ 실행 이력 조회 (MongoDB)
  ├─ 권한 검증
  ├─ state == "running" 검증 (아니면 400 에러)
  │
  ▼ POST {FASTAPI_URL}/api/v1/executions/{execId}/stop
  │   Header: X-Internal-Token, X-User-ID
[FastAPI]
  │   ┌────────────────────────────────────────┐
  │   │ FastAPI 내부 처리 (Spring Boot는 모름)  │
  │   │ - 실행 중인 노드 처리 중단              │
  │   │ - state를 "stopped" 또는 "failed"로 변경│
  │   └────────────────────────────────────────┘
  │
  ▼ HTTP 2xx
[Spring Boot]
  └─ 성공 응답 반환
```

---

## 7. 실행 롤백 흐름 (FastAPI 연동)

```
[프론트엔드]
  │
  ▼ POST /api/workflows/{id}/executions/{execId}/rollback?nodeId=node_abc
[Spring Boot]
  ├─ 실행 이력 조회 & 권한 검증
  ├─ SnapshotService → FastApiClient.rollback() 호출
  │
  ▼ POST {FASTAPI_URL}/api/v1/executions/{execId}/rollback
  │   Header: X-Internal-Token, X-User-ID
  │   Body: { "node_id": "node_abc" | null }
[FastAPI]
  │   ┌────────────────────────────────────────┐
  │   │ FastAPI 내부 처리 (Spring Boot는 모름)  │
  │   │ - 스냅샷 기반 상태 복원                 │
  │   │ - node_id가 null이면 마지막 성공 지점   │
  │   └────────────────────────────────────────┘
  │
  ▼ HTTP 2xx
[Spring Boot]
  └─ 성공 응답 반환
```

---

## 8. 실행 이력 조회 흐름

FastAPI 호출 없이 Spring Boot가 MongoDB에서 직접 조회한다.

```
GET /api/workflows/{id}/executions            → 워크플로우의 전체 실행 이력
GET /api/workflows/{id}/executions/{execId}   → 특정 실행의 노드별 로그 포함 상세 정보
```

> FastAPI가 실행 결과를 MongoDB `workflow_executions` 컬렉션에 직접 저장해야 한다.

---

## 9. 외부 서비스 OAuth 연동 흐름 (Slack)

```
[프론트엔드] (JWT 보유)
  │
  ▼ POST /api/oauth-tokens/slack/connect
[Spring Boot]
  ├─ userId를 AES-GCM 암호화 → state 파라미터 생성
  └─ 응답: { "authUrl": "https://slack.com/oauth/v2/authorize?...&state=..." }
       │
[프론트엔드]
  └─ window.location.href = authUrl
       │
[Slack]
  └─ 사용자 로그인 & 권한 허용
       │
       ▼ GET /api/oauth-tokens/slack/callback?code=...&state=... (JWT 없음)
[Spring Boot]
  ├─ state 복호화 → userId 추출
  ├─ POST https://slack.com/api/oauth.v2.access (code → access_token 교환)
  ├─ access_token을 AES-GCM 암호화하여 MongoDB 저장
  └─ 302 리다이렉트
       │
       ▼ 성공: https://프론트/oauth/callback?service=slack&connected=true
       ▼ 실패: https://프론트/oauth/callback?service=slack&error=oauth_failed
```

### 연결 확인 / 해제

```
GET    /api/oauth-tokens              → 연결된 서비스 목록
DELETE /api/oauth-tokens/{service}    → 서비스 연결 해제 (토큰 삭제)
```

---

## 10. 템플릿 흐름

FastAPI 호출 없이 Spring Boot ↔ MongoDB로만 동작한다.

```
GET  /api/templates                  → 템플릿 목록 (카테고리 필터 가능)
GET  /api/templates/{id}             → 템플릿 상세
POST /api/templates/{id}/instantiate → 템플릿 → 새 워크플로우 생성 (JWT 필요)
POST /api/templates                  → 내 워크플로우를 템플릿으로 저장 (JWT 필요)
```

---

## 11. 사용자 관리 흐름

```
GET    /api/users/me    → 내 정보 조회
PUT    /api/users/me    → 이름 수정
DELETE /api/users/me    → 회원 탈퇴 (캐스케이드: 실행이력, OAuth토큰, 워크플로우 전부 삭제)
```

---

## 12. FastAPI 통신 요약

### Spring Boot → FastAPI 호출 목록

| Spring Boot 엔드포인트 | FastAPI 엔드포인트 | 목적 |
|---|---|---|
| `POST /api/workflows/generate` | `POST /api/v1/workflows/generate` | AI 워크플로우 생성 |
| `POST /api/workflows/{id}/execute` | `POST /api/v1/workflows/{id}/execute` | 워크플로우 실행 |
| `POST /api/workflows/{id}/executions/{execId}/stop` | `POST /api/v1/executions/{execId}/stop` | 실행 중지 |
| `POST /api/workflows/{id}/executions/{execId}/rollback` | `POST /api/v1/executions/{execId}/rollback` | 실행 롤백 |

### 공통 헤더

```
X-Internal-Token: ${INTERNAL_API_SECRET}
X-User-ID: {userId}
Content-Type: application/json
```

### FastAPI가 담당하는 영역 (Spring Boot는 모름)

| 영역 | 설명 |
|------|------|
| AI/LLM 호출 | 자연어 프롬프트를 워크플로우 JSON으로 변환 |
| 노드 실행 | 노드 순서대로 외부 서비스 API 호출 (service_tokens 사용) |
| 실행 상태 저장 | `workflow_executions` 컬렉션에 실행 결과 직접 저장 |
| 실행 중지 | 진행 중인 노드 처리 중단, state 업데이트 |
| 스냅샷 롤백 | 실행 스냅샷 기반 상태 복원 |

### FastAPI → Spring Boot 방향

현재 FastAPI가 Spring Boot에 콜백하는 엔드포인트는 **구현되어 있지 않다.** 실행 완료/실패 알림이 필요하면 웹훅 방식을 협의 후 추가해야 한다. 현재는 프론트엔드 폴링(`GET /api/workflows/{id}/executions/{execId}`)으로만 상태를 확인할 수 있다.

---

## 13. MongoDB 컬렉션

| 컬렉션 | 설명 | 주요 인덱스 |
|--------|------|------------|
| `users` | 사용자 계정 (Google SSO) | `googleId` (unique) |
| `workflows` | 워크플로우 정의 | `userId`, `sharedWith` |
| `workflow_executions` | 실행 이력 + 노드 로그 | `workflowId`, `userId` |
| `oauth_tokens` | 암호화된 서비스 토큰 | `(userId, service)` compound unique |
| `templates` | 워크플로우 템플릿 | `category` |
| `exchange_codes` | 일회용 인증 교환 코드 | `code` (unique), `createdAt` (TTL 30초) |

---

## 14. 보안 구조

| 항목 | 구현 |
|------|------|
| 인증 | JWT (accessToken 30분, refreshToken 7일) |
| OAuth 토큰 저장 | AES-256-GCM 암호화 (12바이트 IV, 128비트 태그) |
| 서버 간 통신 | X-Internal-Token 공유 비밀 검증 |
| 접근 제어 | 워크플로우/실행 소유자 또는 공유 대상만 접근 |
| CSRF | 비활성화 (Stateless REST API) |
| CORS | 환경변수로 허용 origin 관리 |
| 공개 엔드포인트 | `/api/health`, `/api/auth/**`, `/api/oauth-tokens/*/callback`, Swagger |

---

## 15. 환경 변수 목록

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `MONGODB_URL` | MongoDB 연결 URI | `mongodb://localhost:27017/flowify` |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | (필수) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | (필수) |
| `GOOGLE_REDIRECT_URI` | Google 콜백 URL | (필수) |
| `FRONT_REDIRECT_URI` | 프론트 인증 콜백 URL | (필수) |
| `SLACK_CLIENT_ID` | Slack App Client ID | (필수) |
| `SLACK_CLIENT_SECRET` | Slack App Client Secret | (필수) |
| `SLACK_REDIRECT_URI` | Slack 콜백 URL | (필수) |
| `JWT_SECRET` | JWT 서명 키 | (필수) |
| `ENCRYPTION_SECRET_KEY` | AES-256 암호화 키 (Base64) | (필수) |
| `FASTAPI_URL` | FastAPI 베이스 URL | `http://localhost:8000` |
| `INTERNAL_API_SECRET` | 서버 간 인증 토큰 | (필수) |
| `CORS_ALLOWED_ORIGINS` | CORS 허용 origin | `http://localhost:3000` |
| `SERVER_PORT` | 서버 포트 | `8080` |

---

## 16. 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-04-15 | 최초 작성. 전체 백엔드 동작 흐름 문서화. |
