# Flowify - Spring Boot 메인 백엔드 설계 문서

> 작성일: 2026-03-10
> 기반: 주제제안서, PROJECT_ANALYSIS.md, FastAPI 프로젝트 구조

---

## 1. Spring Boot 서버 역할 정의

### 1.1 역할 분담

| 영역 | Spring Boot (메인 백엔드) | FastAPI (AI 서비스) |
|------|------------------------|-------------------|
| 인증/인가 | Google SSO, JWT 발급/검증 | 내부 토큰 검증만 |
| 사용자 관리 | User CRUD, 프로필 | - |
| 워크플로우 관리 | CRUD, 소유권 관리, 공유 | 실행 엔진만 |
| OAuth 토큰 | 암호화 저장, 갱신, 관리 | 토큰 수신 후 외부 API 호출 |
| 템플릿 | 기본 제공 + 사용자 생성 관리 | - |
| 실행 요청 | 프론트 요청 → FastAPI 위임 | 워크플로우 실행, LLM 처리 |
| 실행 로그 | 조회 API 제공 | 로그 기록 |

### 1.2 전체 통신 흐름

```
┌──────────┐      HTTPS (공개)       ┌───────────────┐     HTTP (내부)     ┌──────────┐
│  React   │ ◀──────────────────▶ │  Spring Boot  │ ◀────────────────▶ │  FastAPI  │
│ Frontend │                      │   :8080       │                    │  :8000    │
└──────────┘                      └───────┬───────┘                    └─────┬────┘
                                          │                                  │
                                          ▼                                  ▼
                                   ┌──────────────┐                   ┌──────────────┐
                                   │   MongoDB    │                   │ Vector Store │
                                   │   :27017     │                   │ FAISS/Chroma │
                                   └──────────────┘                   └──────────────┘
```

**핵심 원칙**: 프론트엔드는 Spring Boot에만 요청. FastAPI는 외부에 노출하지 않는다.

---

## 2. 인증/인가 설계

### 2.1 Google SSO 단일 로그인

제안서 기준 Google 계정 단일 로그인(SSO)만 지원한다.

#### OAuth 2.0 Authorization Code Grant 플로우

```
1. 프론트엔드: Google 로그인 버튼 클릭
   → Google OAuth 동의 화면으로 리다이렉트

2. Google: 사용자 인증 후 Authorization Code 발급
   → 콜백 URL로 리다이렉트 (Spring Boot)

3. Spring Boot: Authorization Code → Google Token Endpoint 호출
   → Access Token + Refresh Token + ID Token 수신

4. Spring Boot: ID Token에서 사용자 정보 추출 (email, name, picture)
   → DB에 사용자 존재 여부 확인
   → 없으면 자동 회원가입 (users 컬렉션에 insert)
   → 있으면 기존 사용자 로드

5. Spring Boot: 자체 JWT 발급 (Flowify 서비스용)
   → Access Token (30분) + Refresh Token (7일)
   → 프론트엔드에 반환

6. 이후 모든 요청: Authorization: Bearer <flowify-jwt>
```

### 2.2 JWT 전략

| 항목 | 값 |
|------|---|
| Access Token 유효기간 | 30분 |
| Refresh Token 유효기간 | 7일 |
| 서명 알고리즘 | HS256 (대칭키) 또는 RS256 (비대칭키) |
| Payload 필수 필드 | sub (user_id), email, name, iat, exp |

#### Access Token Payload 예시

```json
{
  "sub": "6601a2b3c4d5e6f7a8b9c0d1",
  "email": "user@gmail.com",
  "name": "홍길동",
  "iat": 1710000000,
  "exp": 1710001800
}
```

#### Refresh Token 운용

```
1. Access Token 만료 시 → 프론트엔드가 /api/auth/refresh 호출
2. Refresh Token 검증 → 새 Access Token 발급
3. Refresh Token 만료 시 → 재로그인 유도
4. Refresh Token은 DB에 저장하여 강제 로그아웃 가능
```

### 2.3 Spring Security 필터 체인

```
HTTP Request
    │
    ▼
┌─────────────────────────┐
│  CorsFilter             │  CORS 처리
├─────────────────────────┤
│  JwtAuthenticationFilter│  Authorization 헤더에서 JWT 추출/검증
│                         │  → SecurityContext에 인증 정보 설정
├─────────────────────────┤
│  ExceptionTranslation   │  인증/인가 예외 처리
├─────────────────────────┤
│  AuthorizationFilter    │  엔드포인트별 접근 권한 확인
└─────────────────────────┘
```

#### 인가 규칙

```
허용 (인증 불필요):
  - GET  /api/auth/google          (Google 로그인 시작)
  - GET  /api/auth/google/callback (Google 콜백)
  - POST /api/auth/refresh         (토큰 갱신)
  - GET  /api/health               (헬스체크)

인증 필요 (JWT 필수):
  - /api/workflows/**
  - /api/templates/**
  - /api/users/**
  - /api/oauth-tokens/**
```

---

## 3. 사용자 관리

### 3.1 User 컬렉션 스키마

```json
// Collection: users
{
  "_id": "ObjectId",
  "email": "user@gmail.com",              // unique, Google 계정 이메일
  "name": "홍길동",                         // Google 프로필 이름
  "picture": "https://lh3.google...",      // Google 프로필 사진 URL
  "google_id": "1234567890",              // Google 고유 ID (sub claim)
  "refresh_token": "encrypted_string",     // Flowify Refresh Token (로그아웃용)
  "created_at": "2026-03-10T00:00:00Z",
  "updated_at": "2026-03-10T00:00:00Z",
  "last_login_at": "2026-03-10T00:00:00Z"
}
```

**인덱스:**
- `email`: unique index
- `google_id`: unique index

### 3.2 사용자 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/users/me` | 현재 로그인 사용자 정보 조회 |
| PUT | `/api/users/me` | 사용자 정보 수정 (이름 등) |
| DELETE | `/api/users/me` | 회원 탈퇴 (관련 데이터 삭제) |

---

## 4. 워크플로우 CRUD API 설계

### 4.1 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/workflows` | 워크플로우 생성 |
| GET | `/api/workflows` | 내 워크플로우 목록 (페이지네이션) |
| GET | `/api/workflows/{id}` | 워크플로우 상세 조회 |
| PUT | `/api/workflows/{id}` | 워크플로우 수정 (노드/엣지 포함) |
| DELETE | `/api/workflows/{id}` | 워크플로우 삭제 |
| POST | `/api/workflows/{id}/execute` | 워크플로우 실행 요청 (→ FastAPI 위임) |
| GET | `/api/workflows/{id}/executions` | 실행 이력 목록 |
| GET | `/api/workflows/{id}/executions/{execId}` | 실행 상세 (로그 포함) |
| POST | `/api/workflows/{id}/share` | 워크플로우 공유 설정 |

### 4.2 워크플로우 컬렉션 스키마

```json
// Collection: workflows
{
  "_id": "ObjectId",
  "name": "학습 노트 자동 생성",
  "description": "강의 자료를 요약하여 Notion에 저장",
  "user_id": "ObjectId (ref → users)",
  "shared_with": ["ObjectId"],            // 공유된 사용자 ID 목록
  "is_template": false,                    // 템플릿 여부
  "template_id": "ObjectId | null",        // 원본 템플릿 ID (템플릿에서 생성한 경우)
  "nodes": [
    {
      "id": "node_1",
      "type": "input",                     // input | llm | if_else | loop | output
      "config": {
        "source": "google_drive",
        "folder_id": "abc123"
      },
      "position": { "x": 100, "y": 200 }
    },
    {
      "id": "node_2",
      "type": "llm",
      "config": {
        "prompt": "이 문서를 요약해주세요"
      },
      "position": { "x": 400, "y": 200 }
    }
  ],
  "edges": [
    { "source": "node_1", "target": "node_2" }
  ],
  "trigger": {                             // 트리거 설정 (null이면 수동 실행만)
    "type": "schedule",                    // schedule | event
    "config": {
      "cron": "0 21 * * *"                // 매일 21시
    }
  },
  "is_active": true,                       // 트리거 활성화 여부
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**인덱스:**
- `user_id`: 일반 index (목록 조회 성능)
- `user_id` + `is_template`: compound index
- `shared_with`: multikey index

### 4.3 소유권 및 접근 제어

```
접근 규칙:
  1. 워크플로우 생성 → user_id = 현재 로그인 사용자
  2. 조회/수정/삭제 → workflow.user_id == 현재 사용자 OR 현재 사용자 in shared_with
  3. 실행 → 조회 권한과 동일
  4. 공유 설정 변경 → workflow.user_id == 현재 사용자 (소유자만)
```

구현 방식: Spring Security의 `@PreAuthorize` 또는 서비스 레이어에서 검증

---

## 5. OAuth 토큰 관리

### 5.1 관리 대상 서비스

| 서비스 | OAuth 타입 | 스코프 (예시) |
|--------|-----------|-------------|
| Google (Drive/Sheets/Gmail) | OAuth 2.0 | drive.readonly, spreadsheets, gmail.send |
| Slack | OAuth 2.0 | chat:write, channels:read |
| Notion | Internal Integration | - (토큰 기반) |
| GitHub | OAuth 2.0 | repo, issues |

### 5.2 oauth_tokens 컬렉션 스키마

```json
// Collection: oauth_tokens
{
  "_id": "ObjectId",
  "user_id": "ObjectId (ref → users)",
  "service": "google",                     // google | slack | notion | github
  "access_token": "AES256_ENCRYPTED(...)", // 암호화된 액세스 토큰
  "refresh_token": "AES256_ENCRYPTED(...)",// 암호화된 리프레시 토큰
  "token_type": "Bearer",
  "expires_at": "ISODate",                 // 액세스 토큰 만료 시각
  "scopes": ["drive.readonly", "gmail.send"],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**인덱스:**
- `user_id` + `service`: unique compound index (사용자당 서비스별 1개)

### 5.3 암호화 전략

```
암호화 알고리즘: AES-256-GCM
키 관리:
  - 암호화 키는 환경변수(ENCRYPTION_SECRET_KEY)로 관리
  - 운영 환경에서는 Secret Manager(AWS/GCP) 사용 권장
  - 키 로테이션 고려하여 key_version 필드 추가 가능

암호화/복호화 흐름:
  저장 시: plaintext → AES-256-GCM encrypt → Base64 encode → MongoDB 저장
  조회 시: MongoDB → Base64 decode → AES-256-GCM decrypt → plaintext
```

### 5.4 토큰 자동 갱신

```
방법 1 (Lazy Refresh - 권장):
  1. FastAPI가 토큰 요청 시 Spring Boot에서 expires_at 확인
  2. 만료 5분 전이면 refresh_token으로 새 access_token 발급
  3. 갱신된 토큰을 DB에 저장 후 반환

방법 2 (Background Refresh):
  1. 스케줄러가 주기적으로 만료 임박 토큰 탐색
  2. 백그라운드에서 갱신
  → 초기에는 방법 1로 구현, 사용자 수 증가 시 방법 2 추가
```

### 5.5 토큰 관리 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/oauth-tokens` | 연결된 서비스 목록 조회 (토큰 자체는 노출 X) |
| POST | `/api/oauth-tokens/{service}/connect` | 외부 서비스 OAuth 연결 시작 |
| GET | `/api/oauth-tokens/{service}/callback` | OAuth 콜백 (토큰 저장) |
| DELETE | `/api/oauth-tokens/{service}` | 서비스 연결 해제 (토큰 삭제) |

### 5.6 FastAPI에 토큰 전달 방식

```
Spring Boot가 FastAPI에 워크플로우 실행을 요청할 때:

POST http://fastapi:8000/api/v1/workflows/{id}/execute
Headers:
  X-Internal-Token: <shared-secret>
  X-User-ID: <user_id>
Body:
{
  "workflow_definition": { ... },
  "service_tokens": {
    "google": "decrypted_access_token",
    "notion": "decrypted_integration_token"
  }
}

→ FastAPI는 service_tokens를 메모리에서만 사용, 저장하지 않음
→ 실행 완료 후 즉시 폐기
```

---

## 6. 핵심 비즈니스 로직

### 6.1 템플릿 관리

#### templates 컬렉션 스키마

```json
// Collection: templates
{
  "_id": "ObjectId",
  "name": "학습 노트 자동 생성",
  "description": "강의 자료 입력 → AI 요약 → Notion 저장",
  "category": "education",                 // education | productivity | development
  "icon": "book",
  "nodes": [ ... ],                        // 사전 정의된 노드 구성
  "edges": [ ... ],
  "required_services": ["google", "notion"],// 필요한 외부 서비스 목록
  "is_system": true,                       // true: 시스템 제공, false: 사용자 생성
  "author_id": "ObjectId | null",          // 사용자 생성 템플릿인 경우
  "use_count": 0,                          // 사용 횟수 통계
  "created_at": "ISODate"
}
```

#### 기본 제공 템플릿 (제안서 기준)

| 이름 | 구성 |
|------|------|
| 학습 노트 자동 생성 | 강의 자료 입력 → AI 요약 → Notion 저장 |
| 회의록 요약 및 공유 | 회의 녹취 → AI 정리 → Slack 전송 |
| GitHub PR 코드 리뷰 | PR 생성 시 → AI 리뷰 → GitHub 코멘트 |
| 구글 시트 → 리포트 PDF | 시트 데이터 → AI 분석 → PDF 출력 |

#### 템플릿 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/templates` | 템플릿 목록 (카테고리 필터) |
| GET | `/api/templates/{id}` | 템플릿 상세 |
| POST | `/api/templates/{id}/instantiate` | 템플릿으로 워크플로우 생성 |
| POST | `/api/templates` | 사용자 템플릿 생성 (내 워크플로우를 템플릿으로) |

### 6.2 워크플로우 실행 위임 흐름

```
1. 프론트엔드: POST /api/workflows/{id}/execute
2. Spring Boot:
   a. JWT 검증 → 사용자 확인
   b. 워크플로우 조회 → 소유권/공유 확인
   c. 필요한 서비스 토큰 복호화
   d. FastAPI에 실행 요청 전달:
      POST http://fastapi:8000/api/v1/workflows/{id}/execute
      Body: { workflow_definition, service_tokens }
   e. FastAPI 응답 (execution_id) → 프론트에 반환

3. FastAPI: 비동기 실행 시작
   a. 노드 순차 실행 (엔진)
   b. 실행 로그를 MongoDB에 직접 기록

4. 프론트엔드: 실행 상태 폴링
   GET /api/workflows/{id}/executions/{execId}
   → Spring Boot가 MongoDB에서 execution 조회 후 반환
```

### 6.3 실행 이력 조회

```json
// Collection: workflow_executions (FastAPI가 기록, Spring Boot가 조회 제공)
{
  "_id": "ObjectId",
  "workflow_id": "ObjectId",
  "user_id": "ObjectId",
  "state": "success",                      // pending | running | success | failed
  "node_logs": [
    {
      "node_id": "node_1",
      "status": "success",
      "input_data": { "source": "google_drive" },
      "output_data": { "files": ["file1.pdf", "file2.pdf"] },
      "error": null,
      "started_at": "ISODate",
      "finished_at": "ISODate"
    }
  ],
  "started_at": "ISODate",
  "finished_at": "ISODate"
}
```

---

## 7. MongoDB 컬렉션 전체 요약

| 컬렉션 | 소유 서비스 | 읽기 | 쓰기 |
|--------|-----------|------|------|
| `users` | Spring Boot | Spring Boot | Spring Boot |
| `workflows` | Spring Boot | Spring Boot + FastAPI | Spring Boot |
| `oauth_tokens` | Spring Boot | Spring Boot | Spring Boot |
| `templates` | Spring Boot | Spring Boot | Spring Boot |
| `workflow_executions` | 공유 | Spring Boot (조회) | FastAPI (기록) |
| `chat_history` | FastAPI | FastAPI | FastAPI |

---

## 8. Spring Boot ↔ FastAPI 서비스 간 통신

### 8.1 내부 API 인증

```
모든 내부 통신에 공유 시크릿 헤더 포함:

  Header: X-Internal-Token: <INTERNAL_API_SECRET>

  - 양쪽 서비스가 동일한 환경변수 공유
  - FastAPI는 이 헤더 없는 외부 요청을 거부
```

### 8.2 사용자 컨텍스트 전파

```
Spring Boot → FastAPI 요청 시:

  Header: X-User-ID: <user_id>

  - FastAPI는 이 값을 신뢰 (Spring Boot가 이미 인증 완료)
  - 실행 로그에 user_id 기록용
```

### 8.3 Docker Compose 확장안

```yaml
services:
  spring-boot:
    build: ./spring          # 또는 별도 레포 경로
    ports:
      - "8080:8080"
    env_file:
      - .env
    depends_on:
      - mongodb
      - fastapi
    networks:
      - flowify-net

  fastapi:
    build: .
    ports:
      - "8000:8000"         # 개발 시에만 노출, 운영 시 내부만
    env_file:
      - .env
    depends_on:
      - mongodb
    networks:
      - flowify-net

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    networks:
      - flowify-net

networks:
  flowify-net:
    driver: bridge

volumes:
  mongo_data:
```

---

## 9. 기술 스택 상세

| 구분 | 기술 | 용도 |
|------|------|------|
| 프레임워크 | Spring Boot 3.x | 메인 백엔드 |
| 언어 | Java 21 | - |
| 빌드 도구 | Gradle (Kotlin DSL) | 의존성 관리, 빌드 |
| 보안 | Spring Security 6.x | 인증/인가 필터 |
| OAuth | Spring Security OAuth2 Client | Google SSO |
| JWT | jjwt (io.jsonwebtoken) | JWT 생성/검증 |
| DB | Spring Data MongoDB | MongoDB 접근 |
| 암호화 | Java Crypto (javax.crypto) | AES-256-GCM 토큰 암호화 |
| HTTP Client | WebClient (Spring WebFlux) | FastAPI 내부 통신 |
| 검증 | Jakarta Validation | DTO 유효성 검사 |
| 문서화 | SpringDoc OpenAPI | Swagger UI |
| 테스트 | JUnit 5 + Mockito | 단위/통합 테스트 |
| 컨테이너 | Docker | 환경 패키징 |

### 주요 의존성 (build.gradle.kts)

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-webflux") // WebClient
    implementation("io.jsonwebtoken:jjwt-api:0.12.6")
    runtimeOnly("io.jsonwebtoken:jjwt-impl:0.12.6")
    runtimeOnly("io.jsonwebtoken:jjwt-jackson:0.12.6")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.6.0")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

---

## 10. Spring Boot 프로젝트 구조 (안)

```
spring/
├── src/main/java/com/flowify/
│   ├── FlowifyApplication.java
│   ├── config/
│   │   ├── SecurityConfig.java        # Spring Security 설정
│   │   ├── WebClientConfig.java       # FastAPI 통신용 WebClient 빈
│   │   ├── CorsConfig.java            # CORS 설정
│   │   └── MongoConfig.java           # MongoDB 설정
│   ├── auth/
│   │   ├── controller/
│   │   │   └── AuthController.java    # 로그인, 콜백, 토큰 갱신
│   │   ├── service/
│   │   │   └── AuthService.java       # Google OAuth + JWT 로직
│   │   ├── jwt/
│   │   │   ├── JwtProvider.java       # JWT 생성/검증
│   │   │   └── JwtAuthFilter.java     # Security 필터
│   │   └── dto/
│   │       ├── LoginResponse.java
│   │       └── TokenRefreshRequest.java
│   ├── user/
│   │   ├── controller/
│   │   │   └── UserController.java
│   │   ├── service/
│   │   │   └── UserService.java
│   │   ├── repository/
│   │   │   └── UserRepository.java    # Spring Data MongoDB
│   │   ├── domain/
│   │   │   └── User.java             # @Document
│   │   └── dto/
│   │       └── UserResponse.java
│   ├── workflow/
│   │   ├── controller/
│   │   │   └── WorkflowController.java
│   │   ├── service/
│   │   │   └── WorkflowService.java
│   │   ├── repository/
│   │   │   └── WorkflowRepository.java
│   │   ├── domain/
│   │   │   ├── Workflow.java          # @Document
│   │   │   ├── NodeDefinition.java
│   │   │   └── EdgeDefinition.java
│   │   └── dto/
│   │       ├── WorkflowCreateRequest.java
│   │       ├── WorkflowUpdateRequest.java
│   │       └── WorkflowResponse.java
│   ├── execution/
│   │   ├── controller/
│   │   │   └── ExecutionController.java
│   │   ├── service/
│   │   │   └── ExecutionService.java  # FastAPI 위임 + 로그 조회
│   │   ├── repository/
│   │   │   └── ExecutionRepository.java
│   │   └── domain/
│   │       └── WorkflowExecution.java
│   ├── template/
│   │   ├── controller/
│   │   │   └── TemplateController.java
│   │   ├── service/
│   │   │   └── TemplateService.java
│   │   ├── repository/
│   │   │   └── TemplateRepository.java
│   │   └── domain/
│   │       └── Template.java
│   ├── oauth/
│   │   ├── controller/
│   │   │   └── OAuthTokenController.java
│   │   ├── service/
│   │   │   ├── OAuthTokenService.java
│   │   │   └── TokenEncryptionService.java  # AES-256
│   │   ├── repository/
│   │   │   └── OAuthTokenRepository.java
│   │   └── domain/
│   │       └── OAuthToken.java
│   └── common/
│       ├── exception/
│       │   ├── GlobalExceptionHandler.java
│       │   └── BusinessException.java
│       └── dto/
│           ├── ApiResponse.java       # 통일 응답 포맷
│           └── PageResponse.java      # 페이지네이션
├── src/main/resources/
│   ├── application.yml
│   └── application-dev.yml
├── src/test/java/com/flowify/
│   └── ...
├── Dockerfile
└── build.gradle.kts
```

---

## 11. 에러 처리 통일 규격

### API 응답 포맷

```json
// 성공
{
  "success": true,
  "data": { ... },
  "message": null
}

// 실패
{
  "success": false,
  "data": null,
  "message": "워크플로우를 찾을 수 없습니다.",
  "errorCode": "WORKFLOW_NOT_FOUND"
}
```

### 에러 코드 체계

| 코드 | HTTP Status | 설명 |
|------|-------------|------|
| `AUTH_INVALID_TOKEN` | 401 | JWT 유효하지 않음 |
| `AUTH_EXPIRED_TOKEN` | 401 | JWT 만료 |
| `AUTH_FORBIDDEN` | 403 | 권한 없음 |
| `WORKFLOW_NOT_FOUND` | 404 | 워크플로우 없음 |
| `WORKFLOW_ACCESS_DENIED` | 403 | 워크플로우 접근 권한 없음 |
| `OAUTH_NOT_CONNECTED` | 400 | 필요한 서비스 미연결 |
| `OAUTH_TOKEN_EXPIRED` | 400 | 외부 토큰 갱신 실패 |
| `EXECUTION_FAILED` | 500 | 실행 실패 |
| `FASTAPI_UNAVAILABLE` | 503 | FastAPI 서비스 접근 불가 |

---

## 12. 환경변수 (application.yml 기준)

```yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URL:mongodb://localhost:27017/flowify}

  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: openid, email, profile
            redirect-uri: "{baseUrl}/api/auth/google/callback"

app:
  jwt:
    secret: ${JWT_SECRET}
    access-expiration-ms: 1800000     # 30분
    refresh-expiration-ms: 604800000  # 7일

  encryption:
    secret-key: ${ENCRYPTION_SECRET_KEY}  # AES-256 키 (Base64)

  fastapi:
    base-url: ${FASTAPI_URL:http://localhost:8000}
    internal-token: ${INTERNAL_API_SECRET}

server:
  port: 8080
```
