# Flowify Spring Boot - 개발 계획서

> 작성일: 2026-03-10
> 기반 문서: PROJECT_ANALYSIS.md, SPRING_BOOT_DESIGN.md

---

## 1. 확정된 기술 결정 사항

| 항목 | 결정 | 비고 |
|------|------|------|
| 빌드 도구 | Gradle (Groovy DSL) | 기존 `build.gradle` 유지 |
| 패키지명 | `org.github.flowify` | 기존 구조 유지 |
| Spring Boot 버전 | 3.4.3 | 4.0.3에서 다운그레이드 |
| dependency-management | 1.1.7 | 기존 유지 |
| Java 버전 | 21 | 기존 유지 |
| 설정 파일 형식 | application.yml (YAML) | properties에서 전환 |
| JWT 서명 알고리즘 | HS256 (대칭키) | 단일 서버 환경에 적합 |
| Lombok | 적극 활용 | @Getter, @Builder, @NoArgsConstructor 등 |
| MongoDB 로컬 환경 | Docker Compose | 컨테이너 기반 개발 환경 |
| 개발 범위 | Spring Boot 메인 백엔드만 | FastAPI는 별도 레포 |
| 커밋 전략 | 모듈별 세분화 커밋 | Conventional Commits 형식 |
| 테스트 전략 | 모듈 구현과 함께 작성 | 각 Phase 마지막에 테스트 커밋 |
| Docker | Phase 1에서 바로 구성 | 로컬 개발 환경 우선 |
| GitHub Remote | `https://github.com/Shelter-of-the-old-people/flowify-BE-spring` | |

---

## 2. Phase 1: 기반 구축

> 목표: 프로젝트 초기 설정, 공통 모듈, 설정 클래스, Docker 환경 구성

### Step 1-1. 프로젝트 설정 변경

**작업 내용:**
- Spring Boot 4.0.3 → 3.4.3 다운그레이드 (`build.gradle` 수정)
- 필요한 의존성 전체 추가

**추가할 의존성:**
```groovy
// Web
implementation 'org.springframework.boot:spring-boot-starter-web'

// Security
implementation 'org.springframework.boot:spring-boot-starter-security'
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

// MongoDB
implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

// Validation
implementation 'org.springframework.boot:spring-boot-starter-validation'

// WebClient (FastAPI 통신)
implementation 'org.springframework.boot:spring-boot-starter-webflux'

// JWT
implementation 'io.jsonwebtoken:jjwt-api:0.12.6'
runtimeOnly 'io.jsonwebtoken:jjwt-impl:0.12.6'
runtimeOnly 'io.jsonwebtoken:jjwt-jackson:0.12.6'

// API 문서화 (Swagger)
implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.6.0'

// 테스트
testImplementation 'org.springframework.security:spring-security-test'
```

**설정 파일 전환:**
- `application.properties` → `application.yml` 전환
- `application-dev.yml` 프로필 생성

**application.yml 구조:**
```yaml
spring:
  application:
    name: Flowify
  data:
    mongodb:
      uri: ${MONGODB_URL:mongodb://localhost:27017/flowify}  # 배포 시 실제 호스트로 변경
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
    secret-key: ${ENCRYPTION_SECRET_KEY}
  fastapi:
    base-url: ${FASTAPI_URL:http://localhost:8000}  # 배포 시 실제 호스트로 변경
    internal-token: ${INTERNAL_API_SECRET}

server:
  port: ${SERVER_PORT:8080}
```

**기타:**
- `.gitignore`에 `.env` 추가
- `.env.example` 생성 (환경변수 예시 파일)

**커밋:** `chore: configure project settings and dependencies`

---

### Step 1-2. Docker 환경 구성

**작업 내용:**

**Dockerfile (멀티스테이지 빌드):**
```dockerfile
# Build Stage
FROM gradle:8.x-jdk21 AS build
WORKDIR /app
COPY . .
RUN gradle bootJar --no-daemon

# Run Stage
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

**docker-compose.yml:**
```yaml
services:
  spring-boot:
    build: .
    ports:
      - "8080:8080"
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

**커밋:** `infra: add Dockerfile and docker-compose.yml`

---

### Step 1-3. 공통 모듈 구축

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `common/dto/ApiResponse.java` | 통일 응답 포맷 (success, data, message, errorCode) |
| `common/dto/PageResponse.java` | 페이지네이션 응답 포맷 |
| `common/exception/ErrorCode.java` | 에러 코드 enum (HTTP 상태 매핑) |
| `common/exception/BusinessException.java` | 커스텀 비즈니스 예외 |
| `common/exception/GlobalExceptionHandler.java` | `@RestControllerAdvice` 전역 예외 처리 |

**ApiResponse 형식:**
```json
// 성공
{ "success": true, "data": { ... }, "message": null }

// 실패
{ "success": false, "data": null, "message": "워크플로우를 찾을 수 없습니다.", "errorCode": "WORKFLOW_NOT_FOUND" }
```

**ErrorCode enum 항목:**
| 코드 | HTTP Status | 설명 | 관련 예외 요구사항 |
|------|-------------|------|----------------|
| `AUTH_INVALID_TOKEN` | 401 | JWT 유효하지 않음 | - |
| `AUTH_EXPIRED_TOKEN` | 401 | JWT 만료 | - |
| `AUTH_FORBIDDEN` | 403 | 권한 없음 | - |
| `WORKFLOW_NOT_FOUND` | 404 | 워크플로우 없음 | - |
| `WORKFLOW_ACCESS_DENIED` | 403 | 워크플로우 접근 권한 없음 | - |
| `WORKFLOW_VALIDATION_FAILED` | 400 | 워크플로우 구조 유효성 오류 | EXR-05 |
| `OAUTH_NOT_CONNECTED` | 400 | 필요한 서비스 미연결 | - |
| `OAUTH_TOKEN_EXPIRED` | 400 | 외부 토큰 갱신 실패 | EXR-02 |
| `EXTERNAL_API_ERROR` | 502 | 외부 서비스 API 연결 오류 | EXR-01 |
| `LLM_API_ERROR` | 502 | LLM API 호출 오류 | EXR-03 |
| `LLM_GENERATION_FAILED` | 422 | LLM 워크플로우 자동 생성 실패 | EXR-04 |
| `EXECUTION_FAILED` | 500 | 워크플로우 실행 중 노드 오류 | EXR-06 |
| `CRAWL_FAILED` | 502 | 웹 수집 오류 | EXR-07 |
| `DATA_CONVERSION_FAILED` | 422 | 이기종 데이터 규격 변환 오류 | EXR-08 |
| `FASTAPI_UNAVAILABLE` | 503 | FastAPI 서비스 접근 불가 | - |
| `USER_NOT_FOUND` | 404 | 사용자 없음 | - |
| `TEMPLATE_NOT_FOUND` | 404 | 템플릿 없음 | - |
| `INVALID_REQUEST` | 400 | 잘못된 요청 | - |

**커밋:** `feat: add common response format and exception handling`

---

### Step 1-4. 설정 클래스 구축

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `config/MongoConfig.java` | MongoDB auditing 활성화 (`@EnableMongoAuditing`) |
| `config/CorsConfig.java` | CORS 설정 (프론트엔드 도메인 허용) |
| `config/WebClientConfig.java` | FastAPI 통신용 WebClient 빈 등록 |
| `config/SecurityConfig.java` | 기본 Spring Security 설정 (임시 - Phase 2에서 완성) |

**CorsConfig 허용 규칙:**
- 개발 환경: `http://localhost:3000` (React 개발 서버)
- 운영 환경: 환경변수로 관리 (배포 시 실제 도메인으로 변경)
- **주의**: localhost는 배포 환경에 따라 변경 가능

**WebClient 설정:**
- base-url: `${FASTAPI_URL}`
- default header: `X-Internal-Token`

**커밋:** `feat: add configuration classes`

---

### Step 1-5. 헬스체크 엔드포인트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `health/controller/HealthController.java` | `GET /api/health` 엔드포인트 |

**응답 예시:**
```json
{
  "success": true,
  "data": {
    "status": "UP",
    "service": "Flowify Spring Boot",
    "timestamp": "2026-03-10T12:00:00Z"
  }
}
```

**검증:** 빌드 확인 및 서버 기동 테스트

**커밋:** `feat: add health check endpoint`

---

### Step 1-6. Git Remote 설정 및 최초 푸시

**작업 내용:**
```bash
git remote add origin https://github.com/Shelter-of-the-old-people/flowify-BE-spring
git push -u origin main
```

---

## 3. Phase 2: 인증/사용자 모듈

> 목표: Google SSO 로그인, JWT 인증, 사용자 관리 API 완성

### Step 2-1. User 도메인 및 Repository

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `user/domain/User.java` | `@Document("users")` MongoDB 도메인 |
| `user/repository/UserRepository.java` | `MongoRepository<User, String>` |
| `user/dto/UserResponse.java` | 사용자 응답 DTO |

**User 스키마:**
```java
@Document("users")
public class User {
    @Id
    private String id;

    @Indexed(unique = true)
    private String email;           // Google 계정 이메일

    private String name;            // Google 프로필 이름
    private String picture;         // Google 프로필 사진 URL

    @Indexed(unique = true)
    private String googleId;        // Google 고유 ID (sub claim)

    private String refreshToken;    // Flowify Refresh Token (로그아웃용)

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    private Instant lastLoginAt;
}
```

**Repository 메서드:**
- `Optional<User> findByEmail(String email)`
- `Optional<User> findByGoogleId(String googleId)`

**커밋:** `feat: add user domain, repository and DTO`

---

### Step 2-2. JWT 인증 모듈

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `auth/jwt/JwtProvider.java` | JWT 생성/검증 (HS256) |
| `auth/jwt/JwtAuthFilter.java` | `OncePerRequestFilter` 상속 JWT 필터 |
| `auth/dto/LoginResponse.java` | 로그인 응답 DTO |
| `auth/dto/TokenRefreshRequest.java` | 토큰 갱신 요청 DTO |

**JwtProvider 주요 기능:**
- `generateAccessToken(User user)` → Access Token 발급 (30분)
- `generateRefreshToken(User user)` → Refresh Token 발급 (7일)
- `validateToken(String token)` → 토큰 유효성 검증
- `getUserIdFromToken(String token)` → 토큰에서 userId 추출
- `getEmailFromToken(String token)` → 토큰에서 email 추출

**Access Token Payload:**
```json
{
  "sub": "<user_id>",
  "email": "user@gmail.com",
  "name": "홍길동",
  "iat": 1710000000,
  "exp": 1710001800
}
```

**JwtAuthFilter 동작 흐름:**
1. `Authorization: Bearer <token>` 헤더에서 토큰 추출
2. `JwtProvider.validateToken()` 검증
3. 유효하면 `SecurityContext`에 인증 정보 설정
4. 유효하지 않으면 다음 필터로 전달 (Spring Security가 처리)

**커밋:** `feat: add JWT provider and authentication filter`

---

### Step 2-3. Google OAuth2 SSO 로그인

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `auth/controller/AuthController.java` | 인증 관련 API 컨트롤러 |
| `auth/service/AuthService.java` | Google OAuth + JWT 비즈니스 로직 |

**AuthController 엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/auth/google` | Google 로그인 시작 (리다이렉트) |
| GET | `/api/auth/google/callback` | Google 콜백 (토큰 교환 + JWT 발급) |
| POST | `/api/auth/refresh` | Access Token 갱신 |
| POST | `/api/auth/logout` | 로그아웃 (Refresh Token 무효화) |

**AuthService 동작 흐름:**
```
1. Google Authorization Code 수신
2. Google Token Endpoint 호출 → Access Token + ID Token 수신
3. ID Token 파싱 → email, name, picture, sub(google_id) 추출
4. DB에서 google_id로 사용자 조회
   → 없으면: 자동 회원가입 (users 컬렉션에 insert)
   → 있으면: 기존 사용자 로드 + lastLoginAt 갱신
5. Flowify JWT 발급 (Access + Refresh)
6. Refresh Token을 User 문서에 저장
7. LoginResponse 반환
```

**커밋:** `feat: add Google SSO authentication`

---

### Step 2-4. Spring Security 설정 완성

**수정 파일:**
- `config/SecurityConfig.java` (Phase 1에서 생성한 임시 설정 완성)

**Security Filter Chain 구성:**
```
HTTP Request
    │
    ▼
CorsFilter              → CORS 처리
    │
    ▼
JwtAuthenticationFilter → Authorization 헤더에서 JWT 추출/검증
    │                      → SecurityContext에 인증 정보 설정
    ▼
ExceptionTranslation    → 인증/인가 예외 처리
    │
    ▼
AuthorizationFilter     → 엔드포인트별 접근 권한 확인
```

**인가 규칙:**
```
허용 (인증 불필요):
  - GET  /api/auth/google
  - GET  /api/auth/google/callback
  - POST /api/auth/refresh
  - GET  /api/health

인증 필요 (JWT 필수):
  - /api/workflows/**
  - /api/templates/**
  - /api/users/**
  - /api/oauth-tokens/**
```

**설정 항목:**
- CSRF 비활성화 (REST API - Stateless)
- Session 관리: `STATELESS`
- `JwtAuthFilter`를 `UsernamePasswordAuthenticationFilter` 앞에 등록

**커밋:** `feat: configure Spring Security filter chain`

---

### Step 2-5. 사용자 관리 API

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `user/controller/UserController.java` | 사용자 관리 API |
| `user/service/UserService.java` | 사용자 비즈니스 로직 |

**엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/users/me` | 현재 로그인 사용자 정보 조회 |
| PUT | `/api/users/me` | 사용자 정보 수정 (이름 등) |
| DELETE | `/api/users/me` | 회원 탈퇴 (관련 데이터 일괄 삭제) |

**회원 탈퇴 시 삭제 대상:**
1. `users` 컬렉션에서 사용자 문서 삭제
2. `workflows` 컬렉션에서 해당 사용자의 워크플로우 삭제
3. `oauth_tokens` 컬렉션에서 해당 사용자의 토큰 삭제
4. `workflow_executions` 컬렉션에서 해당 사용자의 실행 이력 삭제

**커밋:** `feat: add user management API`

---

### Step 2-6. 인증/사용자 모듈 테스트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `auth/AuthControllerTest.java` | 인증 API 테스트 |
| `auth/jwt/JwtProviderTest.java` | JWT 생성/검증 단위 테스트 |
| `user/UserServiceTest.java` | 사용자 서비스 단위 테스트 |

**JwtProviderTest 항목:**
- Access Token 생성 및 검증
- Refresh Token 생성 및 검증
- 만료된 토큰 검증 실패
- 잘못된 서명 검증 실패
- 토큰에서 사용자 정보 추출

**커밋:** `test: add auth and user module tests`

---

## 4. Phase 3: 워크플로우 CRUD

> 목표: 워크플로우 생성/조회/수정/삭제, 실행 위임, 실행 이력 관리

### Step 3-1. 워크플로우 도메인

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/domain/Workflow.java` | `@Document("workflows")` |
| `workflow/domain/NodeDefinition.java` | 노드 임베디드 문서 |
| `workflow/domain/EdgeDefinition.java` | 엣지 임베디드 문서 |
| `workflow/repository/WorkflowRepository.java` | `MongoRepository<Workflow, String>` |

**Workflow 스키마:**
```java
@Document("workflows")
public class Workflow {
    @Id
    private String id;
    private String name;                    // 워크플로우 이름
    private String description;             // 설명
    private String userId;                  // 소유자 (ref → users)
    private List<String> sharedWith;        // 공유된 사용자 ID 목록
    private boolean isTemplate;             // 템플릿 여부
    private String templateId;              // 원본 템플릿 ID
    private List<NodeDefinition> nodes;     // 노드 목록 (category + type 구조)
    private List<EdgeDefinition> edges;     // 엣지 목록
    private TriggerConfig trigger;          // 트리거 설정 (null이면 수동)
    private boolean isActive;               // 트리거 활성화 여부
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;
}
```

**NodeDefinition:**
```java
public class NodeDefinition {
    private String id;            // "node_1"
    private String category;      // service | processing | ai
    private String type;          // 카테고리별 하위 타입 (SPRING_BOOT_DESIGN.md 4.2 참조)
    private Map<String, Object> config;    // 노드별 설정
    private Position position;    // { x, y } 캔버스 좌표
}
```

**EdgeDefinition:**
```java
public class EdgeDefinition {
    private String source;      // 출발 노드 ID
    private String target;      // 도착 노드 ID
}
```

**인덱스:**
- `@Indexed`: `userId`
- `@CompoundIndex`: `userId` + `isTemplate`
- `sharedWith`: multikey index

**커밋:** `feat: add workflow domain and repository`

---

### Step 3-2. 워크플로우 CRUD API

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/dto/WorkflowCreateRequest.java` | 워크플로우 생성 요청 DTO |
| `workflow/dto/WorkflowUpdateRequest.java` | 워크플로우 수정 요청 DTO |
| `workflow/dto/WorkflowResponse.java` | 워크플로우 응답 DTO |
| `workflow/service/WorkflowService.java` | 워크플로우 비즈니스 로직 |
| `workflow/controller/WorkflowController.java` | 워크플로우 API 컨트롤러 |

**엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/workflows` | 워크플로우 생성 |
| GET | `/api/workflows` | 내 워크플로우 목록 (페이지네이션) |
| GET | `/api/workflows/{id}` | 워크플로우 상세 조회 |
| PUT | `/api/workflows/{id}` | 워크플로우 수정 (노드/엣지 포함) |
| DELETE | `/api/workflows/{id}` | 워크플로우 삭제 |
| POST | `/api/workflows/{id}/share` | 워크플로우 공유 설정 |

**소유권 및 접근 제어:**
```
1. 워크플로우 생성 → user_id = 현재 로그인 사용자
2. 조회/수정/삭제 → workflow.userId == 현재 사용자 OR 현재 사용자 in sharedWith
3. 실행 → 조회 권한과 동일
4. 공유 설정 변경 → workflow.userId == 현재 사용자 (소유자만)
```

**커밋:** `feat: add workflow CRUD API`

---

### Step 3-3. 워크플로우 실행 위임

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `execution/domain/WorkflowExecution.java` | `@Document("workflow_executions")` |
| `execution/repository/ExecutionRepository.java` | `MongoRepository<WorkflowExecution, String>` |
| `execution/service/ExecutionService.java` | FastAPI 위임 + 로그 조회 |
| `execution/controller/ExecutionController.java` | 실행 관련 API |

**WorkflowExecution 스키마:**
```java
@Document("workflow_executions")
public class WorkflowExecution {
    @Id
    private String id;
    private String workflowId;
    private String userId;
    private String state;           // pending | running | success | failed | rollback_available
    private List<NodeLog> nodeLogs; // 노드별 실행 로그 (스냅샷 포함, SPRING_BOOT_DESIGN.md 6.3 참조)
    private Instant startedAt;
    private Instant finishedAt;
}
```

**엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/workflows/{id}/execute` | 실행 요청 (→ FastAPI 위임) |
| GET | `/api/workflows/{id}/executions` | 실행 이력 목록 |
| GET | `/api/workflows/{id}/executions/{execId}` | 실행 상세 (로그 포함) |

**실행 위임 흐름:**
```
1. 프론트엔드: POST /api/workflows/{id}/execute
2. Spring Boot:
   a. JWT 검증 → 사용자 확인
   b. 워크플로우 조회 → 소유권/공유 확인
   c. 필요한 서비스 토큰 복호화
   d. FastAPI에 실행 요청 전달:
      POST http://fastapi:8000/api/v1/workflows/{id}/execute
      Headers: X-Internal-Token, X-User-ID
      Body: { workflow_definition, service_tokens }
   e. FastAPI 응답 (execution_id) → 프론트에 반환
3. 프론트엔드: 실행 상태 폴링
   GET /api/workflows/{id}/executions/{execId}
```

**커밋:** `feat: add workflow execution delegation`

---

### Step 3-4. 워크플로우 모듈 테스트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/WorkflowServiceTest.java` | 워크플로우 서비스 단위 테스트 |
| `workflow/WorkflowControllerTest.java` | 워크플로우 API 통합 테스트 |
| `execution/ExecutionServiceTest.java` | 실행 서비스 단위 테스트 |

**테스트 항목:**
- 워크플로우 CRUD 동작 검증
- 소유권 검증 (다른 사용자의 워크플로우 접근 차단)
- 공유된 워크플로우 접근 허용
- 페이지네이션 동작 검증
- FastAPI 위임 요청 검증 (WebClient Mock)

**커밋:** `test: add workflow module tests`

---

## 5. Phase 4: 템플릿 및 OAuth 토큰 관리

> 목표: 워크플로우 템플릿, 외부 서비스 OAuth 토큰 관리, FastAPI 통신 클라이언트

### Step 4-1. 템플릿 관리

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `template/domain/Template.java` | `@Document("templates")` |
| `template/repository/TemplateRepository.java` | `MongoRepository<Template, String>` |
| `template/service/TemplateService.java` | 템플릿 비즈니스 로직 |
| `template/controller/TemplateController.java` | 템플릿 API 컨트롤러 |

**Template 스키마:**
```java
@Document("templates")
public class Template {
    @Id
    private String id;
    private String name;                        // 템플릿 이름
    private String description;                 // 설명
    private String category;                    // communication | storage | spreadsheet | web_crawl | calendar
    private String icon;                        // 아이콘 식별자
    private List<NodeDefinition> nodes;         // 사전 정의된 노드 구성
    private List<EdgeDefinition> edges;         // 엣지 구성
    private List<String> requiredServices;      // 필요한 외부 서비스 목록
    private boolean isSystem;                   // true: 시스템 제공, false: 사용자 생성
    private String authorId;                    // 사용자 생성 템플릿인 경우
    private int useCount;                       // 사용 횟수 통계
    @CreatedDate
    private Instant createdAt;
}
```

**엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/templates` | 템플릿 목록 (카테고리 필터) |
| GET | `/api/templates/{id}` | 템플릿 상세 |
| POST | `/api/templates/{id}/instantiate` | 템플릿으로 워크플로우 생성 |
| POST | `/api/templates` | 사용자 템플릿 생성 (내 워크플로우를 템플릿으로) |

**기본 제공 템플릿 (시드 데이터, 요구사항 기준):**

| 이름 | 카테고리 | 구성 |
|------|---------|------|
| 학습 노트 자동 생성 | storage | Google Drive 입력 → AI 요약 → Notion 저장 |
| 회의록 요약 및 공유 | communication | 회의 녹취 → AI 정리 → Slack 전송 |
| 뉴스 수집 및 정리 | web_crawl | 네이버 뉴스 수집 → AI 요약 → Google Sheets 기록 |
| 구글 시트 → 리포트 PDF | spreadsheet | 시트 데이터 → AI 분석 → PDF 출력 |

**커밋:** `feat: add template management`

---

### Step 4-2. 토큰 암호화 서비스

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `oauth/service/TokenEncryptionService.java` | AES-256-GCM 암호화/복호화 |

**암호화 흐름:**
```
저장 시: plaintext → AES-256-GCM encrypt → Base64 encode → MongoDB 저장
조회 시: MongoDB → Base64 decode → AES-256-GCM decrypt → plaintext
```

**키 관리:**
- 암호화 키: 환경변수 `ENCRYPTION_SECRET_KEY` (Base64 인코딩)
- Java `javax.crypto` 패키지 사용

**커밋:** `feat: add AES-256-GCM token encryption service`

---

### Step 4-3. OAuth 토큰 관리 API

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `oauth/domain/OAuthToken.java` | `@Document("oauth_tokens")` |
| `oauth/repository/OAuthTokenRepository.java` | `MongoRepository<OAuthToken, String>` |
| `oauth/service/OAuthTokenService.java` | OAuth 토큰 비즈니스 로직 |
| `oauth/controller/OAuthTokenController.java` | OAuth 토큰 API 컨트롤러 |

**OAuthToken 스키마:**
```java
@Document("oauth_tokens")
@CompoundIndex(name = "user_service_idx", def = "{'userId': 1, 'service': 1}", unique = true)
public class OAuthToken {
    @Id
    private String id;
    private String userId;              // ref → users
    private String service;             // google | slack | notion
    private String accessToken;         // AES-256 암호화
    private String refreshToken;        // AES-256 암호화
    private String tokenType;           // Bearer
    private Instant expiresAt;          // 액세스 토큰 만료 시각
    private List<String> scopes;        // 권한 범위
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;
}
```

**엔드포인트:**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/oauth-tokens` | 연결된 서비스 목록 조회 (토큰 자체는 노출 X) |
| POST | `/api/oauth-tokens/{service}/connect` | 외부 서비스 OAuth 연결 시작 |
| GET | `/api/oauth-tokens/{service}/callback` | OAuth 콜백 (토큰 저장) |
| DELETE | `/api/oauth-tokens/{service}` | 서비스 연결 해제 (토큰 삭제) |

**관리 대상 서비스 (요구사항 SFR-03 기준):**

| 서비스 | OAuth 타입 | 스코프 (예시) |
|--------|-----------|-------------|
| Google (Drive/Sheets/Gmail/Calendar) | OAuth 2.0 | drive.readonly, spreadsheets, gmail.send, calendar.events |
| Slack | OAuth 2.0 | chat:write, channels:read |
| Notion | Internal Integration | - (토큰 기반) |

**토큰 자동 갱신 전략 (Lazy Refresh):**
```
1. FastAPI가 토큰 요청 시 Spring Boot에서 expires_at 확인
2. 만료 5분 전이면 refresh_token으로 새 access_token 발급
3. 갱신된 토큰을 DB에 저장 후 반환
```

**커밋:** `feat: add OAuth token management`

---

### Step 4-4. FastAPI 통신 클라이언트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `execution/service/FastApiClient.java` | WebClient 기반 FastAPI 내부 통신 |

**통신 규격:**
```
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
```

**주요 기능:**
- WebClient 기반 비동기 HTTP 호출
- `X-Internal-Token` 헤더 자동 포함
- `X-User-ID` 사용자 컨텍스트 전파
- 서비스 토큰 복호화 후 body에 포함
- 에러 핸들링 (FastAPI 접속 불가 시 `FASTAPI_UNAVAILABLE`)
- 타임아웃 설정

**커밋:** `feat: add FastAPI internal communication client`

---

### Step 4-5. 템플릿/OAuth 모듈 테스트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `template/TemplateServiceTest.java` | 템플릿 서비스 단위 테스트 |
| `oauth/TokenEncryptionServiceTest.java` | 암호화/복호화 단위 테스트 |
| `oauth/OAuthTokenServiceTest.java` | OAuth 토큰 서비스 단위 테스트 |

**TokenEncryptionService 테스트 항목:**
- 암호화 → 복호화 라운드트립 검증
- 다른 키로 복호화 시 실패
- null/빈 문자열 처리

**커밋:** `test: add template and OAuth module tests`

---

## 6. Phase 5: 워크플로우 검증 및 고급 기능

> 목표: 요구사항 명세서(EXR-01~08, SFR-04)에 정의된 유효성 검증, 스냅샷/롤백, 이기종 데이터 변환, 재시도 정책 구현

### Step 5-1. 워크플로우 유효성 검증 서비스

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/service/WorkflowValidator.java` | 워크플로우 구조 유효성 검증 |

**검증 항목 (EXR-05 대응):**
- 필수 노드 존재 여부 (트리거 또는 수동 실행 설정)
- 노드 간 연결 끊김 검출 (연결되지 않은 고립 노드)
- 순환 참조(Cycle) 검출 (DFS 기반)
- 필수 설정값 누락 검출 (노드별 config 필수 필드)
- 노드 타입 간 호환성 검증 (service 노드에 OAuth 연동 필요 여부)

**적용 시점:**
- `POST /api/workflows/{id}/execute` 실행 전 필수 수행
- 검증 실패 시 `WORKFLOW_VALIDATION_FAILED` 에러 반환
- 오류 노드 ID 목록을 응답에 포함

**커밋:** `feat: add workflow structure validation service`

---

### Step 5-2. 스냅샷 및 롤백 메커니즘

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `execution/domain/NodeSnapshot.java` | 노드 실행 전 상태 스냅샷 임베디드 문서 |
| `execution/service/SnapshotService.java` | 스냅샷 저장 및 롤백 로직 |

**동작 흐름 (EXR-06 대응):**
```
1. 각 노드 실행 전: 현재 상태를 NodeSnapshot으로 캡처
2. 노드 실행 성공: snapshot 유지 (디버깅용)
3. 노드 실행 실패:
   a. 해당 노드를 FAILED 상태로 전환
   b. 이후 노드 실행 중단
   c. 전체 워크플로우 상태를 ROLLBACK_AVAILABLE로 전환
4. 롤백 요청 시: 마지막 성공 스냅샷으로 복원 후 재실행 가능
```

**엔드포인트 추가:**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/workflows/{id}/executions/{execId}/rollback` | 특정 실행의 롤백 요청 |

**커밋:** `feat: add snapshot-based rollback mechanism`

---

### Step 5-3. 외부 API 재시도 정책

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `common/retry/RetryPolicy.java` | 재시도 정책 공통 모듈 |

**재시도 규칙 (EXR-01, EXR-03 대응):**
- 외부 서비스 API 오류 (EXR-01): 최대 3회, Exponential Backoff (1s → 2s → 4s)
- LLM API 오류 (EXR-03): Rate Limit → 대기 후 재시도, 서버 오류 → 최대 2회 재시도
- OAuth 토큰 만료 (EXR-02): Refresh Token 자동 갱신 1회 시도 → 실패 시 재인증 안내

**커밋:** `feat: add external API retry policy`

---

### Step 5-4. 이기종 데이터 변환 모듈

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/service/DataConversionService.java` | 이기종 서비스 간 데이터 규격 변환 |

**동작 (EXR-08, UC-P06 대응):**
- 서로 다른 외부 서비스(Gmail → Notion, Google Sheets → Slack 등) 간 데이터 전달 시 공통 DTO 포맷으로 자동 변환
- 변환 실패 시 `DATA_CONVERSION_FAILED` 에러 반환 및 수동 매핑 안내
- Adapter 패턴 기반 서비스별 변환기 구현

**커밋:** `feat: add cross-service data conversion module`

---

### Step 5-5. 워크플로우 고급 기능 테스트

**생성 파일:**

| 파일 | 설명 |
|------|------|
| `workflow/WorkflowValidatorTest.java` | 유효성 검증 단위 테스트 |
| `execution/SnapshotServiceTest.java` | 스냅샷/롤백 단위 테스트 |
| `common/retry/RetryPolicyTest.java` | 재시도 정책 단위 테스트 |

**테스트 항목:**
- 순환 참조 워크플로우 검증 실패
- 필수 노드 누락 검증 실패
- 정상 워크플로우 검증 통과
- 노드 실패 시 스냅샷 생성 및 롤백 동작
- 외부 API 재시도 횟수 및 Backoff 검증

**커밋:** `test: add workflow validation, snapshot and retry tests`

---

## 7. Phase 6: 안정화 및 배포 준비

> 목표: API 문서화, 시드 데이터, 통합 테스트, Docker 최적화, 보안 검수

### Step 6-1. Swagger API 문서화

**작업 내용:**
- SpringDoc 기반 Swagger UI 설정 완성
- 각 Controller에 `@Operation`, `@ApiResponse`, `@Tag` 어노테이션 추가
- DTO에 `@Schema` 어노테이션 추가
- Swagger UI 접근 경로: `/swagger-ui.html`

**커밋:** `docs: add Swagger API documentation`

---

### Step 6-2. 기본 제공 템플릿 시드 데이터

**작업 내용:**
- `CommandLineRunner` 기반 초기 데이터 로딩
- 4개 기본 제공 템플릿 시드 데이터 삽입

**시드 데이터 조건:**
- 서버 시작 시 `templates` 컬렉션이 비어있으면 삽입
- `isSystem = true`로 설정

**커밋:** `feat: add system template seed data`

---

### Step 6-3. 통합 테스트

**작업 내용:**
- Testcontainers를 이용한 MongoDB 통합 테스트 환경
- E2E 플로우 테스트:
  1. 인증 (JWT 발급)
  2. 워크플로우 생성
  3. 워크플로우 조회/수정
  4. 실행 요청
  5. 실행 이력 조회

**추가 의존성:**
```groovy
testImplementation 'org.testcontainers:mongodb:1.19.x'
testImplementation 'org.testcontainers:junit-jupiter:1.19.x'
```

**커밋:** `test: add integration tests`

---

### Step 6-4. Docker 배포 최적화

**작업 내용:**
- Dockerfile 최적화:
  - 레이어 캐싱 (의존성 먼저 다운로드)
  - 이미지 사이즈 최소화 (JRE 기반)
- docker-compose.yml:
  - 운영 프로필 분리 고려
  - 헬스체크 추가
- `.env.example` 최종 업데이트

**커밋:** `infra: optimize Docker deployment configuration`

---

### Step 6-5. 성능 및 보안 검수

**작업 내용:**
- Spring Security 설정 최종 점검:
  - CORS 허용 도메인 확인
  - 인가 규칙 누락 없는지 점검
  - JWT 시크릿 키 강도 확인
- MongoDB 인덱스 확인:
  - `@Indexed`, `@CompoundIndex` 어노테이션 점검
  - 쿼리 성능에 필요한 인덱스 누락 확인
- 에러 핸들링 전체 검수:
  - 모든 예외가 `GlobalExceptionHandler`를 통해 처리되는지 확인
  - 에러 응답 형식 일관성 확인
- 민감 정보 노출 방지:
  - OAuth 토큰이 API 응답에 노출되지 않는지 확인
  - 스택 트레이스가 클라이언트에 전달되지 않는지 확인

**커밋:** `fix: security and performance review improvements`

---

## 8. 전체 파일 생성 목록

### 소스 파일 (`src/main/java/org/github/flowify/`)

```
FlowifyApplication.java                          (기존 유지)
config/
├── SecurityConfig.java
├── WebClientConfig.java
├── CorsConfig.java
└── MongoConfig.java
auth/
├── controller/
│   └── AuthController.java
├── service/
│   └── AuthService.java
├── jwt/
│   ├── JwtProvider.java
│   └── JwtAuthFilter.java
└── dto/
    ├── LoginResponse.java
    └── TokenRefreshRequest.java
user/
├── controller/
│   └── UserController.java
├── service/
│   └── UserService.java
├── repository/
│   └── UserRepository.java
├── domain/
│   └── User.java
└── dto/
    └── UserResponse.java
workflow/
├── controller/
│   └── WorkflowController.java
├── service/
│   ├── WorkflowService.java
│   ├── WorkflowValidator.java
│   └── DataConversionService.java
├── repository/
│   └── WorkflowRepository.java
├── domain/
│   ├── Workflow.java
│   ├── NodeDefinition.java
│   └── EdgeDefinition.java
└── dto/
    ├── WorkflowCreateRequest.java
    ├── WorkflowUpdateRequest.java
    └── WorkflowResponse.java
execution/
├── controller/
│   └── ExecutionController.java
├── service/
│   ├── ExecutionService.java
│   ├── FastApiClient.java
│   └── SnapshotService.java
├── repository/
│   └── ExecutionRepository.java
└── domain/
    ├── WorkflowExecution.java
    └── NodeSnapshot.java
template/
├── controller/
│   └── TemplateController.java
├── service/
│   └── TemplateService.java
├── repository/
│   └── TemplateRepository.java
└── domain/
    └── Template.java
oauth/
├── controller/
│   └── OAuthTokenController.java
├── service/
│   ├── OAuthTokenService.java
│   └── TokenEncryptionService.java
├── repository/
│   └── OAuthTokenRepository.java
└── domain/
    └── OAuthToken.java
common/
├── exception/
│   ├── GlobalExceptionHandler.java
│   ├── BusinessException.java
│   └── ErrorCode.java
├── dto/
│   ├── ApiResponse.java
│   └── PageResponse.java
└── retry/
    └── RetryPolicy.java
health/
└── controller/
    └── HealthController.java
```

### 리소스 파일 (`src/main/resources/`)

```
application.yml                 (신규 - properties 대체)
application-dev.yml             (신규)
docs/
├── PROJECT_ANALYSIS.md         (기존 유지)
├── SPRING_BOOT_DESIGN.md       (기존 유지)
├── DEVELOPMENT_PLAN.md         (본 문서)
└── requirements/               (요구사항 명세서)
    ├── REQUIREMENTS_INDEX.md
    ├── FUNCTIONAL_REQUIREMENTS.md
    ├── NON_FUNCTIONAL_REQUIREMENTS.md
    └── ACCEPTANCE_CRITERIA.md
```

### 테스트 파일 (`src/test/java/org/github/flowify/`)

```
FlowifyApplicationTests.java               (기존 유지)
auth/
├── AuthControllerTest.java
└── jwt/
    └── JwtProviderTest.java
user/
└── UserServiceTest.java
workflow/
├── WorkflowServiceTest.java
├── WorkflowControllerTest.java
└── WorkflowValidatorTest.java
execution/
├── ExecutionServiceTest.java
└── SnapshotServiceTest.java
common/
└── retry/
    └── RetryPolicyTest.java
template/
└── TemplateServiceTest.java
oauth/
├── TokenEncryptionServiceTest.java
└── OAuthTokenServiceTest.java
```

### 루트 파일

```
build.gradle                    (기존 수정)
Dockerfile                      (신규)
docker-compose.yml              (신규)
.env.example                    (신규)
.gitignore                      (기존 수정 - .env 추가)
```

---

## 9. 커밋 히스토리 요약

| # | Phase | 커밋 메시지 |
|---|-------|-----------|
| 1 | 1 | `chore: configure project settings and dependencies` |
| 2 | 1 | `infra: add Dockerfile and docker-compose.yml` |
| 3 | 1 | `feat: add common response format and exception handling` |
| 4 | 1 | `feat: add configuration classes` |
| 5 | 1 | `feat: add health check endpoint` |
| 6 | 2 | `feat: add user domain, repository and DTO` |
| 7 | 2 | `feat: add JWT provider and authentication filter` |
| 8 | 2 | `feat: add Google SSO authentication` |
| 9 | 2 | `feat: configure Spring Security filter chain` |
| 10 | 2 | `feat: add user management API` |
| 11 | 2 | `test: add auth and user module tests` |
| 12 | 3 | `feat: add workflow domain and repository` |
| 13 | 3 | `feat: add workflow CRUD API` |
| 14 | 3 | `feat: add workflow execution delegation` |
| 15 | 3 | `test: add workflow module tests` |
| 16 | 4 | `feat: add template management` |
| 17 | 4 | `feat: add AES-256-GCM token encryption service` |
| 18 | 4 | `feat: add OAuth token management` |
| 19 | 4 | `feat: add FastAPI internal communication client` |
| 20 | 4 | `test: add template and OAuth module tests` |
| 21 | 5 | `feat: add workflow structure validation service` |
| 22 | 5 | `feat: add snapshot-based rollback mechanism` |
| 23 | 5 | `feat: add external API retry policy` |
| 24 | 5 | `feat: add cross-service data conversion module` |
| 25 | 5 | `test: add workflow validation, snapshot and retry tests` |
| 26 | 6 | `docs: add Swagger API documentation` |
| 27 | 6 | `feat: add system template seed data` |
| 28 | 6 | `test: add integration tests` |
| 29 | 6 | `infra: optimize Docker deployment configuration` |
| 30 | 6 | `fix: security and performance review improvements` |

---

## 10. MongoDB 컬렉션 전체 요약

| 컬렉션 | 소유 서비스 | 읽기 | 쓰기 |
|--------|-----------|------|------|
| `users` | Spring Boot | Spring Boot | Spring Boot |
| `workflows` | Spring Boot | Spring Boot + FastAPI | Spring Boot |
| `oauth_tokens` | Spring Boot | Spring Boot | Spring Boot |
| `templates` | Spring Boot | Spring Boot | Spring Boot |
| `workflow_executions` | 공유 | Spring Boot (조회) | FastAPI (기록) |
| `chat_history` | FastAPI | FastAPI | FastAPI |

---

## 11. 주의사항

### Git 커밋/푸시 규칙
- 공동작성자(Co-authored-by) 헤더를 포함하지 않는다
- git config의 user.name, user.email은 프로젝트 소유자 설정을 그대로 사용한다
- AI 관련 언급을 커밋 메시지에 포함하지 않는다

### 보안 필수 사항
- `.env` 파일은 절대 Git에 커밋하지 않는다 (`.gitignore`에 포함)
- OAuth 토큰은 AES-256-GCM으로 암호화하여 저장한다
- JWT 시크릿 키는 환경변수로만 관리한다
- FastAPI 내부 통신 시 `X-Internal-Token`으로 인증한다
- 외부에서 FastAPI에 직접 접근할 수 없도록 한다

### 데이터 안전
- 워크플로우 소유권 검증을 서비스 레이어에서 반드시 수행한다
- 회원 탈퇴 시 관련 데이터를 일괄 삭제한다
- OAuth 토큰은 API 응답에 절대 노출하지 않는다
