# Flowify Spring Boot 설계 요약서

## 1. 시스템 개요

Flowify는 비전문가가 AI 자동화 파이프라인을 **코드 없이** 구축할 수 있는 노드 기반 워크플로우 플랫폼이다. **[입력 → AI 처리 → 출력]** 의 3단계 구조로 동작하며, 사용자에게 기술 용어를 노출하지 않고 일상 언어 기반의 가이드형 설정을 제공한다.

Spring Boot 백엔드는 다음을 담당한다:
- Google OAuth 2.0 SSO 인증 및 JWT 세션 관리
- 워크플로우 CRUD 및 소유권/공유 관리
- **가이드형 워크플로우 생성** (시작 노드 → 도착 노드 → 중간 과정 순서)
- **데이터 타입 기반 동적 선택지 매핑** (ChoiceMappingService → `mapping_rules.json` 설정 파일 기반)
- 워크플로우 실행을 FastAPI AI 서비스에 위임 및 실행 이력 제공
- 외부 서비스(Google, Slack, Notion) OAuth 토큰의 암호화 저장/자동 갱신
- 시스템/사용자 워크플로우 템플릿 관리 (미인증 서비스 경고 포함)

---

## 2. 기술 스택 및 제약사항

| 항목 | 내용 |
|------|------|
| 프레임워크 | Spring Boot 3.4.3 / Java 21 |
| 빌드 도구 | Gradle (Groovy DSL) |
| 패키지명 | `org.github.flowify` |
| 데이터베이스 | MongoDB 7 (Spring Data MongoDB) |
| 배포 | Docker Compose |
| 인증 | JWT HS256 (Access 30분 / Refresh 7일) |
| 토큰 암호화 | AES-256-GCM |
| Lombok | 적극 활용 |

### 핵심 설계 원칙
- **서버 분리**: Spring Boot(8080)와 FastAPI(8000)는 별도 서버로 분리
- **프론트엔드 단일 접점**: React(3000) → Spring Boot만 통신, FastAPI는 외부 미노출
- **내부 통신 인증**: `X-Internal-Token` (공유 시크릿) + `X-User-ID` 헤더
- **Stateless**: CSRF 비활성화, 세션 STATELESS
- **데이터 격리**: user_id 단위 소유권 관리, OAuth 토큰은 API 응답에 미노출
- **재시도 정책**: 외부 API 최대 3회, LLM API 최대 2회 Exponential Backoff

---

## 3. 데이터베이스 설계 요약

### 컬렉션 5개

| 컬렉션 | 역할 | 주요 인덱스 | 소유 서비스 |
|--------|------|-----------|-----------|
| `users` | 사용자 정보 | email(Unique), googleId(Unique) | Spring Boot 전담 |
| `workflows` | 워크플로우 정의 (노드/엣지 임베디드) | userId, userId+isTemplate, sharedWith | Spring Boot(쓰기), 양쪽(읽기) |
| `oauth_tokens` | 외부 서비스 OAuth 토큰 (암호화) | userId+service(Unique) | Spring Boot 전담 |
| `templates` | 워크플로우 템플릿 | category, isSystem | Spring Boot 전담 |
| `workflow_executions` | 실행 이력 및 노드별 로그 | workflowId, userId | Spring Boot(조회), FastAPI(기록) |

### 주요 임베디드 구조
- **workflows.nodes[]**: id, category(communication|storage|spreadsheet|web_crawl|calendar|ai|processing), type, config, position, dataType, outputDataType, role(start|end|middle), authWarning
- **workflows.edges[]**: source, target
- **workflow_executions.nodeLogs[]**: nodeId, status, inputData, outputData, snapshot, error, startedAt, finishedAt

---

## 4. 모듈 및 클래스 구성

### 4.1 회원 및 인증 (auth/)

| 클래스 | 역할 |
|--------|------|
| AuthController | Google SSO 로그인/콜백, 토큰 갱신, 로그아웃 API |
| AuthService | Google OAuth 처리, JWT 발급, 자동 회원가입 |
| JwtProvider | JWT 생성/검증/파싱 (HS256) |
| JwtAuthFilter | 요청마다 Bearer 토큰 검증 → SecurityContext 설정 |
| SecurityConfig | Spring Security 필터 체인 구성 |

### 4.2 사용자 관리 (user/)

| 클래스 | 역할 |
|--------|------|
| UserController | 내 정보 조회/수정/탈퇴 API (`/api/users/me`) |
| UserService | 사용자 CRUD, 탈퇴 시 관련 데이터 일괄 삭제 |
| User | MongoDB Document (id, email, name, picture, googleId, refreshToken) |

### 4.3 워크플로우 관리 (workflow/)

| 클래스 | 역할 |
|--------|------|
| WorkflowController | 워크플로우 CRUD + 공유 + LLM 기반 생성 API |
| WorkflowService | CRUD, 소유권/접근 검증, 페이지네이션, LLM 기반 워크플로우 생성 중계 |
| WorkflowValidator | 순환 참조(DFS), 고립 노드, 필수 설정 누락 검증 |
| Workflow | MongoDB Document (nodes, edges, trigger 임베디드) |

### 4.4 워크플로우 실행 (execution/)

| 클래스 | 역할 |
|--------|------|
| ExecutionController | 실행 요청, 이력 조회, 롤백 API |
| ExecutionService | 소유권 검증 → 유효성 검증 → 토큰 복호화 → FastAPI 위임 |
| FastApiClient | WebClient 기반 FastAPI 통신 (X-Internal-Token, X-User-ID 헤더) |
| SnapshotService | 스냅샷 조회 및 FastAPI에 롤백 요청 중계 (스냅샷 캡처는 FastAPI 담당) |

### 4.5 템플릿 관리 (template/)

| 클래스 | 역할 |
|--------|------|
| TemplateController | 템플릿 목록/상세, 인스턴스화, 사용자 템플릿 생성 API |
| TemplateService | 템플릿 조회, 인스턴스화(노드/엣지 복사 → 새 워크플로우 생성), useCount 관리 |
| Template | MongoDB Document (nodes, edges, requiredServices, isSystem, authorId) |

### 4.6 OAuth 토큰 관리 (oauth/)

| 클래스 | 역할 |
|--------|------|
| OAuthTokenController | 연결된 서비스 조회, 연결/해제, OAuth 콜백 API |
| OAuthTokenService | 토큰 암호화 저장, 복호화 반환, Lazy Refresh(만료 5분 전 자동 갱신) |
| TokenEncryptionService | AES-256-GCM 암호화/복호화 |

### 4.7 공통 모듈 (common/, config/)

| 클래스 | 역할 |
|--------|------|
| GlobalExceptionHandler | BusinessException/Validation/기타 예외 처리 |
| BusinessException + ErrorCode | 18종 에러코드 (401/403/404/400/500/502/503/422) |
| ApiResponse\<T\> | 통일 응답 포맷 (success, data, message, errorCode) |
| PageResponse\<T\> | 페이지네이션 응답 포맷 |
| RetryPolicy | Exponential Backoff 재시도 |
| HealthController | 서버 상태 확인 API (MongoDB, FastAPI 연결 상태) |
| DataConversionService | 이기종 데이터 규격 변환 (EXR-08) |
| CorsConfig | CORS 설정 (개발: localhost:3000) |
| WebClientConfig | FastAPI 통신용 WebClient 빈 |
| MongoConfig | @EnableMongoAuditing |

---

## 5. API 엔드포인트 요약

### 인증
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/auth/google` | Google OAuth 리다이렉트 |
| GET | `/api/auth/google/callback` | Google 콜백 → JWT 발급 |
| POST | `/api/auth/refresh` | Access Token 갱신 |
| POST | `/api/auth/logout` | 로그아웃 (Refresh Token 무효화) |

### 사용자
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/users/me` | 내 정보 조회 |
| PUT | `/api/users/me` | 내 정보 수정 |
| DELETE | `/api/users/me` | 회원 탈퇴 |

### 워크플로우
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/workflows` | 워크플로우 생성 |
| GET | `/api/workflows` | 워크플로우 목록 (페이지네이션) |
| GET | `/api/workflows/{id}` | 워크플로우 상세 |
| PUT | `/api/workflows/{id}` | 워크플로우 수정 |
| DELETE | `/api/workflows/{id}` | 워크플로우 삭제 |
| POST | `/api/workflows/{id}/share` | 공유 설정 |
| POST | `/api/workflows/generate` | LLM 기반 워크플로우 자동 생성 (UC-W02) |

### 선택지 및 노드 (UC-W01-D 직접 설정)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/workflows/{id}/choices/{prevNodeId}` | 이전 노드 outputDataType 기반 선택지 조회 |
| POST | `/api/workflows/{id}/choices/{prevNodeId}/select` | 사용자 선택 전송 → 후속 설정 또는 노드 타입 확정 |
| POST | `/api/workflows/{id}/nodes` | 확정된 노드 추가 + edge 생성 |
| PUT | `/api/workflows/{id}/nodes/{nodeId}` | 노드 설정 수정 |
| DELETE | `/api/workflows/{id}/nodes/{nodeId}` | 노드 삭제 + 캐스케이드 |

### 실행
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/workflows/{id}/execute` | 실행 요청 → FastAPI 위임 |
| GET | `/api/workflows/{id}/executions` | 실행 이력 목록 |
| GET | `/api/workflows/{id}/executions/{execId}` | 실행 상세 (노드 로그 포함) |
| POST | `/api/workflows/{id}/executions/{execId}/rollback` | 스냅샷 기반 롤백 |

### 템플릿
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/templates` | 템플릿 목록 (카테고리 필터) |
| GET | `/api/templates/{id}` | 템플릿 상세 |
| POST | `/api/templates/{id}/instantiate` | 템플릿 → 워크플로우 생성 |
| POST | `/api/templates` | 사용자 템플릿 생성 |

### OAuth 토큰
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/oauth-tokens` | 연결된 서비스 목록 |
| POST | `/api/oauth-tokens/{service}/connect` | OAuth 연결 시작 |
| GET | `/api/oauth-tokens/{service}/callback` | OAuth 콜백 → 토큰 저장 |
| DELETE | `/api/oauth-tokens/{service}` | 서비스 연결 해제 |

### 헬스체크
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 확인 (MongoDB, FastAPI 연결 상태) |

---

## 6. 예외 처리 요약

| 식별자 | 상황 | 에러코드 | 처리 방식 |
|--------|------|---------|----------|
| EXR-01 | 외부 서비스 API 오류 | EXTERNAL_API_ERROR(502) | 최대 3회 Exponential Backoff 재시도 |
| EXR-02 | OAuth 토큰 만료 | OAUTH_TOKEN_EXPIRED(400) | Refresh Token으로 Lazy Refresh |
| EXR-03 | LLM API 오류 | LLM_API_ERROR(502) | 최대 2회 재시도 |
| EXR-05 | 워크플로우 유효성 오류 | WORKFLOW_VALIDATION_FAILED(400) | 순환참조/고립노드/필수설정 검증 |
| EXR-06 | 워크플로우 실행 오류 | EXECUTION_FAILED(500) | 스냅샷 기반 롤백 지원 (FastAPI 캡처, Spring Boot 중계) |

---

## 7. 서비스 간 통신 흐름

1. **React** → `HTTPS + JWT` → **Spring Boot** (모든 클라이언트 요청의 단일 진입점)
2. **Spring Boot** → `HTTP + X-Internal-Token + X-User-ID` → **FastAPI** (실행 위임)
3. **Spring Boot** ↔ **MongoDB** (사용자, 워크플로우, 토큰, 템플릿 관리)
4. **FastAPI** → **MongoDB** (실행 이력 기록), **LLM/외부 API** (실제 실행)
5. **프론트엔드 폴링**: React는 실행 요청 후 주기적으로 실행 상태 API를 호출하여 실시간 진행 상태를 표시한다.
