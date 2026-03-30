# 4. 요구분석 참조표

---

## 4.1 기능 요구사항 추적표 (Spring Boot 담당)

아래 표는 Spring Boot 메인 백엔드가 담당하는 유스케이스에 대한 요구분석 참조표이다.

| 항번 | 요구사항 식별자 | 요구사항명 | 서브시스템 식별자 | UCD 식별자 | UC 식별자 | 유스케이스명 | 인터페이스 식별자 | 인터페이스명 | 시퀀스 다이어그램 식별자 | 클래스 다이어그램 식별자 | 클래스 식별자 |
|------|--------------|----------|---------------|----------|---------|-----------|---------------|------------|-------------------|-------------------|-----------|
| 1 | SFR-01 | 회원 및 인증 관리 | PK-SS01 | UCD-01 | UC-U01 | Google SSO 로그인 | I-U01 | 공통 메인/로그인 화면 | SD-U01 | PK-C01 | DC-C0101, DC-C0102, DC-C0103, DC-C0104, DC-C0105, DC-C0106 |
| 2 | SFR-01 | 회원 및 인증 관리 | PK-SS01 | UCD-01 | UC-U02 | 서비스별 OAuth 인증 | I-U02 | 외부 서비스 연동 설정창 | SD-U02 | PK-C06 | DC-C0601, DC-C0602, DC-C0603, DC-C0604, DC-C0605 |
| 3 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W01-A | 시작 노드 설정 | I-W01 | 가이드형 노드 설정 화면 | SD-W04 | PK-C03, PK-C08 | DC-C0301, DC-C0302, DC-C0305, DC-C0801 |
| 3-1 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W01-B | 도착 노드 설정 | I-W01 | 가이드형 노드 설정 화면 | SD-W05 | PK-C03, PK-C08 | DC-C0301, DC-C0302, DC-C0305, DC-C0801 |
| 3-2 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W01-C | 중간 과정 결정 | I-W01 | 생성 방식 선택 화면 | - | PK-C03 | DC-C0301, DC-C0302 |
| 3-3 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W01-D | 직접 설정 상세 | I-W01 | 양측 패널 편집 화면 | SD-W06 | PK-C03, PK-C08 | DC-C0301, DC-C0302, DC-C0305, DC-C0801 |
| 4 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W02 | LLM 기반 플로우 자동 생성 (채팅형) | I-W02 | 채팅형 대화 인터페이스 | SD-W03 | PK-C03, PK-C04 | DC-C0301, DC-C0302, DC-C0403 |
| 5 | SFR-02 | 워크플로우 설계 | PK-SS02 | UCD-02 | UC-W03 | 템플릿 기반 플로우 생성 | I-W03 | 자동화 템플릿 마켓 | SD-W02 | PK-C05, PK-C06 | DC-C0501, DC-C0502, DC-C0503, DC-C0504, DC-C0602 |
| 6 | SFR-06 | 실행 및 모니터링 | PK-SS06 | UCD-06 | UC-E01 | 워크플로우 테스트 및 실행 | I-E01 | 에디터 상단 실행 도구 | SD-E01 | PK-C04 | DC-C0401, DC-C0402, DC-C0403, DC-C0404, DC-C0405, DC-C0406 |
| 7 | SFR-06 | 실행 및 모니터링 | PK-SS06 | UCD-06 | UC-E02 | 노드별 데이터 흐름 미리보기 | I-E02 | 실시간 데이터 디버그 뷰 | SD-E02 | PK-C04 | DC-C0401, DC-C0402, DC-C0405, DC-C0406 |

---

## 4.2 Spring Boot 관여 범위 상세

### UC별 Spring Boot 역할

| UC 식별자 | 유스케이스명 | Spring Boot 역할 | 비고 |
|----------|-----------|-----------------|------|
| UC-U01 | Google SSO 로그인 | **전담** — Google OAuth 콜백 처리, JWT 발급, 사용자 자동 등록 | |
| UC-U02 | 서비스별 OAuth 인증 | **전담** — OAuth 콜백 처리, 토큰 암호화 저장/갱신/삭제 | |
| UC-W01-A | 시작 노드 설정 | **전담** — 카테고리/서비스 선택, 실행 조건 결정, 선택지 매핑 제공 | ChoiceMappingService 활용 |
| UC-W01-B | 도착 노드 설정 | **전담** — 카테고리/서비스/동작 유형 선택, 세부 설정 지연 | ChoiceMappingService 활용 |
| UC-W01-C | 중간 과정 결정 | **전담** — AI 생성/직접 설정 방식 선택 | |
| UC-W01-D | 직접 설정 상세 | **전담** — 3단계 설정 흐름, 노드 타입 결정, 캐스케이드 삭제 | ChoiceMappingService 활용 |
| UC-W02 | LLM 기반 플로우 자동 생성 (채팅형) | **중계** — 채팅형 대화를 FastAPI로 위임, 결과를 워크플로우로 저장 | FastAPI가 LLM 처리 |
| UC-W03 | 템플릿 기반 플로우 생성 | **전담** — 템플릿 조회, 노드/엣지 복사, 미인증 노드 경고 설정 | authWarning 플래그 설정 |
| UC-S01~S05 | 서비스 연동 노드 설정 | **토큰 제공** — 실행 시 해당 서비스의 복호화된 토큰을 FastAPI에 전달 | 노드 설정은 프론트+Spring CRUD |
| UC-P01~P09 | 프로세싱/로직 노드 | **저장** — 노드 config를 워크플로우 문서에 저장 | 실행은 FastAPI |
| UC-A01 | AI 처리 설정 | **저장** — AI 노드 프롬프트를 워크플로우 문서에 저장 | LLM 호출은 FastAPI |
| UC-E01 | 워크플로우 테스트 및 실행 | **위임+모니터링** — 유효성 검증 → 토큰 복호화 → FastAPI 위임 → 실행 이력 제공 | |
| UC-E02 | 노드별 데이터 흐름 미리보기 | **조회 전담** — MongoDB에서 실행 이력(nodeLogs) 조회 후 프론트에 반환 | FastAPI가 기록한 데이터 |

---

## 4.3 비기능 요구사항 추적표 (Spring Boot 관련)

### 예외 요구사항 매핑

| 요구사항 식별자 | 요구사항명 | 대응 에러코드 | 대응 클래스 | 처리 방식 |
|--------------|----------|------------|-----------|----------|
| EXR-01 | 외부 서비스 API 연결 오류 | EXTERNAL_API_ERROR | RetryPolicy, FastApiClient | 최대 3회 Exponential Backoff 재시도 |
| EXR-02 | OAuth 인증 오류 | OAUTH_TOKEN_EXPIRED | OAuthTokenService | Refresh Token 자동 갱신 (Lazy Refresh) |
| EXR-03 | LLM API 오류 | LLM_API_ERROR | RetryPolicy | Rate Limit 대기 후 재시도, 서버 오류 최대 2회 |
| EXR-04 | LLM 기반 워크플로우 자동 생성 실패 | LLM_GENERATION_FAILED | - | FastAPI에서 처리, Spring Boot는 에러 중계 |
| EXR-05 | 워크플로우 설계 유효성 오류 | WORKFLOW_VALIDATION_FAILED | WorkflowValidator | 순환참조, 고립노드, 필수설정 누락 검증 |
| EXR-06 | 워크플로우 실행 오류 | EXECUTION_FAILED | SnapshotService, ExecutionService | 스냅샷 기반 롤백 지원 (FastAPI가 스냅샷 캡처, Spring Boot는 롤백 요청 중계) |
| EXR-07 | 웹 수집 오류 | CRAWL_FAILED | - | FastAPI에서 처리, Spring Boot는 에러 중계 |
| EXR-08 | 이기종 데이터 규격 변환 오류 | DATA_CONVERSION_FAILED | DataConversionService | 자동 변환 시도, 실패 시 수동 매핑 안내 |

### 성능 요구사항 매핑

| 요구사항 식별자 | 요구사항명 | Spring Boot 대응 |
|--------------|----------|-----------------|
| SPR-01 | 성능 일반 | API 응답 500ms 이내, MongoDB 인덱스 최적화 |
| SPR-02 | 동시 처리 성능 | Spring Boot 내장 톰캣 스레드풀, WebClient 비동기 호출 |
| SPR-03 | 시스템 자원 사용률 | Docker 컨테이너 리소스 제한 |

---

## 4.4 클래스 다이어그램 ↔ 클래스 식별자 전체 매핑

| 클래스 다이어그램 식별자 | 서브시스템명 | 클래스 식별자 | 클래스 명 |
|----------------------|-----------|------------|---------|
| PK-C01 | 회원 및 인증 관리 | DC-C0101 | AuthController |
| PK-C01 | 회원 및 인증 관리 | DC-C0102 | AuthService |
| PK-C01 | 회원 및 인증 관리 | DC-C0103 | JwtProvider |
| PK-C01 | 회원 및 인증 관리 | DC-C0104 | JwtAuthFilter |
| PK-C01 | 회원 및 인증 관리 | DC-C0105 | LoginResponse |
| PK-C01 | 회원 및 인증 관리 | DC-C0106 | TokenRefreshRequest |
| PK-C02 | 사용자 관리 | DC-C0201 | UserController |
| PK-C02 | 사용자 관리 | DC-C0202 | UserService |
| PK-C02 | 사용자 관리 | DC-C0203 | UserRepository |
| PK-C02 | 사용자 관리 | DC-C0204 | User |
| PK-C02 | 사용자 관리 | DC-C0205 | UserResponse |
| PK-C03 | 워크플로우 관리 | DC-C0301 | WorkflowController |
| PK-C03 | 워크플로우 관리 | DC-C0302 | WorkflowService |
| PK-C03 | 워크플로우 관리 | DC-C0303 | WorkflowValidator |
| PK-C03 | 워크플로우 관리 | DC-C0304 | Workflow |
| PK-C03 | 워크플로우 관리 | DC-C0305 | NodeDefinition |
| PK-C03 | 워크플로우 관리 | DC-C0306 | EdgeDefinition |
| PK-C03 | 워크플로우 관리 | DC-C0307 | WorkflowCreateRequest |
| PK-C03 | 워크플로우 관리 | DC-C0308 | WorkflowUpdateRequest |
| PK-C03 | 워크플로우 관리 | DC-C0309 | WorkflowResponse |
| PK-C03 | 워크플로우 관리 | DC-C0310 | Position |
| PK-C03 | 워크플로우 관리 | DC-C0311 | TriggerConfig |
| PK-C04 | 워크플로우 실행 | DC-C0401 | ExecutionController |
| PK-C04 | 워크플로우 실행 | DC-C0402 | ExecutionService |
| PK-C04 | 워크플로우 실행 | DC-C0403 | FastApiClient |
| PK-C04 | 워크플로우 실행 | DC-C0404 | SnapshotService |
| PK-C04 | 워크플로우 실행 | DC-C0405 | WorkflowExecution |
| PK-C04 | 워크플로우 실행 | DC-C0406 | ExecutionRepository |
| PK-C04 | 워크플로우 실행 | DC-C0407 | NodeLog |
| PK-C04 | 워크플로우 실행 | DC-C0408 | NodeSnapshot |
| PK-C04 | 워크플로우 실행 | DC-C0409 | ErrorDetail |
| PK-C05 | 템플릿 관리 | DC-C0501 | TemplateController |
| PK-C05 | 템플릿 관리 | DC-C0502 | TemplateService |
| PK-C05 | 템플릿 관리 | DC-C0503 | TemplateRepository |
| PK-C05 | 템플릿 관리 | DC-C0504 | Template |
| PK-C06 | OAuth 토큰 관리 | DC-C0601 | OAuthTokenController |
| PK-C06 | OAuth 토큰 관리 | DC-C0602 | OAuthTokenService |
| PK-C06 | OAuth 토큰 관리 | DC-C0603 | TokenEncryptionService |
| PK-C06 | OAuth 토큰 관리 | DC-C0604 | OAuthTokenRepository |
| PK-C06 | OAuth 토큰 관리 | DC-C0605 | OAuthToken |
| PK-C07 | 공통 모듈 | DC-C0701 | SecurityConfig |
| PK-C07 | 공통 모듈 | DC-C0702 | WebClientConfig |
| PK-C07 | 공통 모듈 | DC-C0703 | CorsConfig |
| PK-C07 | 공통 모듈 | DC-C0704 | MongoConfig |
| PK-C07 | 공통 모듈 | DC-C0705 | GlobalExceptionHandler |
| PK-C07 | 공통 모듈 | DC-C0706 | BusinessException |
| PK-C07 | 공통 모듈 | DC-C0707 | ErrorCode |
| PK-C07 | 공통 모듈 | DC-C0708 | ApiResponse |
| PK-C07 | 공통 모듈 | DC-C0709 | PageResponse |
| PK-C07 | 공통 모듈 | DC-C0710 | RetryPolicy |
| PK-C07 | 공통 모듈 | DC-C0711 | HealthController |
| PK-C07 | 공통 모듈 | DC-C0712 | DataConversionService |
