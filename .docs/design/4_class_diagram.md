# 3.2 Class Diagram (클래스 다이어그램)

---

## PK-C01: 회원 및 인증 관리

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C01 |
| **클래스 다이어그램 명** | 회원 및 인증 관리 |

```
┌─────────────────────────────┐
│     <<@RestController>>     │
│       AuthController        │
├─────────────────────────────┤
│ - authService: AuthService  │
├─────────────────────────────┤
│ + googleLogin()             │
│ + googleCallback()          │
│ + refreshToken()            │
│ + logout()                  │
└──────────┬──────────────────┘
           │ uses
           ▼
┌─────────────────────────────┐       ┌──────────────────────────────┐
│       <<@Service>>          │       │       <<@Component>>         │
│        AuthService          │──────▶│        JwtProvider           │
├─────────────────────────────┤       ├──────────────────────────────┤
│ - userRepository            │       │ - secretKey: String          │
│ - jwtProvider               │       │ - accessExpirationMs: long   │
├─────────────────────────────┤       │ - refreshExpirationMs: long  │
│ + processGoogleLogin()      │       ├──────────────────────────────┤
│ + refreshAccessToken()      │       │ + generateAccessToken()      │
│ + logout()                  │       │ + generateRefreshToken()     │
└──────────┬──────────────────┘       │ + validateToken()            │
           │ uses                     │ + getUserIdFromToken()       │
           ▼                          │ + getEmailFromToken()        │
┌─────────────────────────────┐       └──────────────────────────────┘
│    <<MongoRepository>>      │                    │
│      UserRepository         │                    │ used by
├─────────────────────────────┤                    ▼
│ + findByEmail()             │       ┌──────────────────────────────┐
│ + findByGoogleId()          │       │  <<OncePerRequestFilter>>    │
└──────────┬──────────────────┘       │       JwtAuthFilter          │
           │ manages                  ├──────────────────────────────┤
           ▼                          │ - jwtProvider: JwtProvider   │
┌─────────────────────────────┐       │ - userRepository             │
│       <<@Document>>         │       ├──────────────────────────────┤
│          User               │       │ # doFilterInternal()         │
├─────────────────────────────┤       └──────────────────────────────┘
│ - id: String                │
│ - email: String             │       ┌──────────────────────────────┐
│ - name: String              │       │     <<@Configuration>>       │
│ - picture: String           │       │      SecurityConfig          │
│ - googleId: String          │       ├──────────────────────────────┤
│ - refreshToken: String      │       │ - jwtAuthFilter              │
│ - createdAt: Instant        │       ├──────────────────────────────┤
│ - updatedAt: Instant        │       │ + securityFilterChain()      │
│ - lastLoginAt: Instant      │       └──────────────────────────────┘
└─────────────────────────────┘

DTO:
┌──────────────────────┐  ┌─────────────────────────┐
│    LoginResponse     │  │  TokenRefreshRequest    │
├──────────────────────┤  ├─────────────────────────┤
│ - accessToken        │  │ - refreshToken: String  │
│ - refreshToken       │  └─────────────────────────┘
│ - user: UserResponse │
└──────────────────────┘
```

---

## PK-C02: 사용자 관리

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C02 |
| **클래스 다이어그램 명** | 사용자 관리 |

```
┌─────────────────────────────┐
│     <<@RestController>>     │
│       UserController        │
├─────────────────────────────┤
│ - userService: UserService  │
├─────────────────────────────┤
│ + getMe()                   │
│ + updateMe()                │
│ + deleteMe()                │
└──────────┬──────────────────┘
           │ uses
           ▼
┌─────────────────────────────┐
│       <<@Service>>          │
│        UserService          │
├─────────────────────────────┤
│ - userRepository            │
│ - workflowRepository        │
│ - oauthTokenRepository      │
│ - executionRepository       │
├─────────────────────────────┤
│ + getUserById()             │
│ + updateUser()              │
│ + deleteUser()              │
└──────────┬──────────────────┘
           │ uses
           ▼
┌─────────────────────────────┐
│    <<MongoRepository>>      │       ┌──────────────────────┐
│      UserRepository         │       │     UserResponse     │
├─────────────────────────────┤       ├──────────────────────┤
│ + findByEmail()             │       │ - id: String         │
│ + findByGoogleId()          │       │ - email: String      │
└─────────────────────────────┘       │ - name: String       │
                                      │ - picture: String    │
                                      │ - createdAt: Instant │
                                      └──────────────────────┘
```

---

## PK-C03: 워크플로우 관리

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C03 |
| **클래스 다이어그램 명** | 워크플로우 관리 |

```
┌────────────────────────────────────┐
│        <<@RestController>>         │
│        WorkflowController          │
├────────────────────────────────────┤
│ - workflowService: WorkflowService │
├────────────────────────────────────┤
│ + createWorkflow()                 │
│ + getWorkflows()                   │
│ + getWorkflow()                    │
│ + updateWorkflow()                 │
│ + deleteWorkflow()                 │
│ + shareWorkflow()                  │
│ + generateWorkflow()               │
│ + getNodeChoices()                 │  ← 이전 노드 기반 선택지 조회
│ + selectNodeChoice()               │  ← 사용자 선택 전송
│ + addMiddleNode()                  │  ← 확정된 중간 노드 추가
│ + updateNode()                     │  ← 노드 설정 수정
│ + deleteNode()                     │  ← 노드 삭제 + 캐스케이드
└──────────┬─────────────────────────┘
           │ uses
           ▼
┌────────────────────────────────────┐       ┌───────────────────────────┐
│        <<@Service>>                │──────▶│   WorkflowValidator       │
│        WorkflowService             │       ├───────────────────────────┤
├────────────────────────────────────┤       │ + validate()              │
│ - workflowRepository               │       │ - checkCyclicReference()  │
│ - workflowValidator                │       │ - checkIsolatedNodes()    │
│ - fastApiClient                    │       │ - checkRequiredConfig()   │
│ - choiceMappingService             │       │ - checkDataTypeCompat()   │
├────────────────────────────────────┤       └───────────────────────────┘
│ + createWorkflow()                 │
│ + getWorkflowsByUserId()           │
│ + getWorkflowById()                │
│ + updateWorkflow()                 │
│ + deleteWorkflow()                 │
│ + shareWorkflow()                  │
│ + generateWorkflowFromPrompt()     │
│ + setupStartNode()                 │  ← 시작 노드 설정 (UC-W01-A)
│ + setupEndNode()                   │  ← 도착 노드 설정 (UC-W01-B)
│ + getNodeChoices()                 │  ← NEW: 이전 노드 기반 선택지 조회
│ + selectNodeChoice()               │  ← NEW: 사용자 선택 처리
│ + addMiddleNode()                  │  ← 중간 노드 추가 (UC-W01-D)
│ + updateNode()                     │  ← NEW: 노드 설정 수정
│ + deleteNodeCascade()              │  ← 노드 삭제 + 후속 노드 캐스케이드 삭제
│ + chatGenerateWorkflow()           │  ← 채팅형 AI 생성 (UC-W02)
│ - verifyOwnership()                │
│ - verifyAccess()                   │
│ - determineNodeType()              │  ← 사용자 선택 → 내부 노드 타입 결정
└──────────┬─────────────────────────┘
           │ uses
           ▼
┌────────────────────────────────────┐
│       <<MongoRepository>>          │
│       WorkflowRepository           │
├────────────────────────────────────┤
│ + findByUserId()                   │
│ + findByUserIdOrSharedWithContaining() │
└──────────┬─────────────────────────┘
           │ manages
           ▼
┌────────────────────────────┐  ┌─────────────────────────┐  ┌───────────────────┐
│     <<@Document>>          │  │    NodeDefinition       │  │  EdgeDefinition   │
│       Workflow             │  ├─────────────────────────┤  ├───────────────────┤
├────────────────────────────┤  │ - id: String            │  │ - source: String  │
│ - id: String               │  │ - category: String      │  │ - target: String  │
│ - name: String             │  │ - type: String          │  └───────────────────┘
│ - description: String      │  │ - config: Map           │
│ - userId: String           │  │ - position: Position    │
│ - sharedWith: List<String> │  │ - dataType: String      │  ← 입력 데이터 타입
│ - isTemplate: boolean      │  │ - outputDataType: String│  ← 출력 데이터 타입
│ - templateId: String       │  │ - role: String          │  ← start|end|middle
│ - nodes: List<NodeDef.>    │  │ - authWarning: boolean  │  ← 미인증 경고
│ - edges: List<EdgeDef.>    │  └─────────────────────────┘
│ - trigger: TriggerConfig   │
│ - isActive: boolean        │
│ - createdAt: Instant       │
│ - updatedAt: Instant       │
└────────────────────────────┘

임베디드 값 객체:
┌───────────────────┐  ┌───────────────────────┐
│    Position       │  │    TriggerConfig      │
├───────────────────┤  ├───────────────────────┤
│ - x: double       │  │ - type: String        │
│ - y: double       │  │ - config: Map         │
└───────────────────┘  └───────────────────────┘

DTO:
┌───────────────────────────┐  ┌───────────────────────────┐  ┌───────────────────────┐
│  WorkflowCreateRequest    │  │  WorkflowUpdateRequest    │  │   WorkflowResponse    │
├───────────────────────────┤  ├───────────────────────────┤  ├───────────────────────┤
│ - name: String            │  │ - name: String            │  │ - id: String          │
│ - description: String     │  │ - description: String     │  │ - name: String        │
│ - nodes: List<NodeDef.>   │  │ - nodes: List<NodeDef.>   │  │ - description: String │
│ - edges: List<EdgeDef.>   │  │ - edges: List<EdgeDef.>   │  │ - nodes, edges        │
│ - trigger: TriggerConfig  │  │ - trigger: TriggerConfig  │  │ - createdAt, updatedAt│
└───────────────────────────┘  └───────────────────────────┘  └───────────────────────┘
```

---

## PK-C04: 워크플로우 실행

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C04 |
| **클래스 다이어그램 명** | 워크플로우 실행 |

```
┌────────────────────────────────────────┐
│          <<@RestController>>           │
│          ExecutionController           │
├────────────────────────────────────────┤
│ - executionService: ExecutionService   │
├────────────────────────────────────────┤
│ + executeWorkflow()                    │
│ + getExecutions()                      │
│ + getExecutionDetail()                 │
│ + rollbackExecution()                  │
└──────────┬─────────────────────────────┘
           │ uses
           ▼
┌────────────────────────────────────────┐
│          <<@Service>>                  │
│          ExecutionService              │
├────────────────────────────────────────┤
│ - executionRepository                  │
│ - workflowService                      │
│ - fastApiClient                        │
│ - oauthTokenService                    │
│ - snapshotService                      │
├────────────────────────────────────────┤
│ + executeWorkflow()                    │
│ + getExecutionsByWorkflowId()          │
│ + getExecutionDetail()                 │
│ + rollbackExecution()                  │
└──────┬────────────┬────────────────────┘
       │            │
       ▼            ▼
┌──────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│  FastApiClient   │  │   SnapshotService       │  │  ExecutionRepository    │
├──────────────────┤  ├─────────────────────────┤  ├─────────────────────────┤
│ - webClient      │  │ - executionRepository   │  │ + findByWorkflowId()    │
├──────────────────┤  │ - fastApiClient         │  │ + findByUserId()        │
│ + execute()      │  ├─────────────────────────┤  └──────────┬──────────────┘
│ + getStatus()    │  │ + getSnapshot()         │             │ manages
│ + requestRollback│  │ + requestRollback()     │             ▼
│ + generateWF()   │  └─────────────────────────┘  ┌─────────────────────────┐
└──────────────────┘                               │     <<@Document>>       │
                                                   │   WorkflowExecution     │
                                                   ├─────────────────────────┤
                                                   │ - id: String            │
                                                   │ - workflowId: String    │
                                                   │ - userId: String        │
                                                   │ - state: String         │
                                                   │ - nodeLogs: List<NodeLog>│
                                                   │ - startedAt: Instant    │
                                                   │ - finishedAt: Instant   │
                                                   └─────────────────────────┘

임베디드 문서:
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│      NodeLog          │  │    NodeSnapshot        │  │     ErrorDetail       │
├───────────────────────┤  ├───────────────────────┤  ├───────────────────────┤
│ - nodeId: String      │  │ - capturedAt: Instant  │  │ - code: String        │
│ - status: String      │  │ - stateData: Map       │  │ - message: String     │
│ - inputData: Map      │  └───────────────────────┘  │ - stackTrace: String  │
│ - outputData: Map     │                              └───────────────────────┘
│ - snapshot: NodeSnap. │
│ - error: ErrorDetail  │
│ - startedAt: Instant  │
│ - finishedAt: Instant │
└───────────────────────┘
```

---

## PK-C05: 템플릿 관리

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C05 |
| **클래스 다이어그램 명** | 템플릿 관리 |

```
┌──────────────────────────────────────────┐
│          <<@RestController>>             │
│          TemplateController              │
├──────────────────────────────────────────┤
│ - templateService: TemplateService       │
├──────────────────────────────────────────┤
│ + getTemplates()                         │
│ + getTemplateById()                      │
│ + instantiateTemplate()                  │
│ + createTemplate()                       │
└──────────┬───────────────────────────────┘
           │ uses
           ▼
┌──────────────────────────────────────────┐
│          <<@Service>>                    │
│          TemplateService                 │
├──────────────────────────────────────────┤
│ - templateRepository                     │
│ - workflowService                        │
├──────────────────────────────────────────┤
│ + getTemplates()                         │
│ + getTemplateById()                      │
│ + instantiateTemplate()                  │
│ + createUserTemplate()                   │
└──────────┬───────────────────────────────┘
           │ uses
           ▼
┌──────────────────────────────────────────┐
│       <<MongoRepository>>                │
│       TemplateRepository                 │
├──────────────────────────────────────────┤
│ + findByCategory()                       │
│ + findByIsSystem()                       │
└──────────┬───────────────────────────────┘
           │ manages
           ▼
┌──────────────────────────────────────────┐
│          <<@Document>>                   │
│           Template                       │
├──────────────────────────────────────────┤
│ - id: String                             │
│ - name: String                           │
│ - description: String                    │
│ - category: String                       │
│ - icon: String                           │
│ - nodes: List<NodeDefinition>            │
│ - edges: List<EdgeDefinition>            │
│ - requiredServices: List<String>         │
│ - isSystem: boolean                      │
│ - authorId: String                       │
│ - useCount: int                          │
│ - createdAt: Instant                     │
└──────────────────────────────────────────┘
```

---

## PK-C06: OAuth 토큰 관리

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C06 |
| **클래스 다이어그램 명** | OAuth 토큰 관리 |

```
┌────────────────────────────────────────────────┐
│            <<@RestController>>                 │
│           OAuthTokenController                 │
├────────────────────────────────────────────────┤
│ - oauthTokenService: OAuthTokenService         │
├────────────────────────────────────────────────┤
│ + getConnectedServices()                       │
│ + connectService()                             │
│ + oauthCallback()                              │
│ + disconnectService()                          │
└──────────┬─────────────────────────────────────┘
           │ uses
           ▼
┌────────────────────────────────────────────────┐
│            <<@Service>>                        │
│           OAuthTokenService                    │
├────────────────────────────────────────────────┤
│ - oauthTokenRepository                         │
│ - tokenEncryptionService                       │
├────────────────────────────────────────────────┤
│ + getConnectedServices()                       │
│ + saveToken()                                  │
│ + getDecryptedToken()                          │
│ + refreshTokenIfNeeded()                       │
│ + deleteToken()                                │
└──────────┬─────────────────────────────────────┘
           │ uses
           ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│    <<@Service>>              │  │       <<MongoRepository>>        │
│  TokenEncryptionService      │  │     OAuthTokenRepository         │
├──────────────────────────────┤  ├──────────────────────────────────┤
│ - secretKey: String          │  │ + findByUserIdAndService()       │
├──────────────────────────────┤  │ + findByUserId()                 │
│ + encrypt()                  │  │ + deleteByUserIdAndService()     │
│ + decrypt()                  │  └──────────┬───────────────────────┘
└──────────────────────────────┘             │ manages
                                             ▼
                                  ┌──────────────────────────────────┐
                                  │       <<@Document>>              │
                                  │         OAuthToken               │
                                  ├──────────────────────────────────┤
                                  │ - id: String                     │
                                  │ - userId: String                 │
                                  │ - service: String                │
                                  │ - accessToken: String (encrypted)│
                                  │ - refreshToken: String(encrypted)│
                                  │ - tokenType: String              │
                                  │ - expiresAt: Instant             │
                                  │ - scopes: List<String>           │
                                  │ - createdAt: Instant             │
                                  │ - updatedAt: Instant             │
                                  └──────────────────────────────────┘
```

---

## PK-C07: 공통 모듈

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C07 |
| **클래스 다이어그램 명** | 공통 모듈 |

```
┌─────────────────────────────────────┐
│    <<@RestControllerAdvice>>        │
│     GlobalExceptionHandler          │
├─────────────────────────────────────┤
│ + handleBusinessException()         │
│ + handleValidationException()       │
│ + handleException()                 │
└─────────────────────────────────────┘
           │ catches
           ▼
┌──────────────────────────┐       ┌──────────────────────────┐
│    BusinessException     │──────▶│      <<enum>>            │
├──────────────────────────┤       │      ErrorCode           │
│ - errorCode: ErrorCode   │       ├──────────────────────────┤
│ - message: String        │       │ AUTH_INVALID_TOKEN (401)  │
├──────────────────────────┤       │ AUTH_EXPIRED_TOKEN (401)  │
│ + getErrorCode()         │       │ AUTH_FORBIDDEN (403)      │
│ + getMessage()           │       │ WORKFLOW_NOT_FOUND (404)  │
└──────────────────────────┘       │ WORKFLOW_ACCESS_DENIED    │
                                   │ WORKFLOW_VALIDATION_FAILED│
┌──────────────────────────┐       │ OAUTH_NOT_CONNECTED (400)│
│    <<generic>>           │       │ OAUTH_TOKEN_EXPIRED (400)│
│    ApiResponse<T>        │       │ EXTERNAL_API_ERROR (502) │
├──────────────────────────┤       │ LLM_API_ERROR (502)      │
│ - success: boolean       │       │ LLM_GENERATION_FAILED    │
│ - data: T                │       │ EXECUTION_FAILED (500)   │
│ - message: String        │       │ CRAWL_FAILED (502)       │
│ - errorCode: String      │       │ DATA_CONVERSION_FAILED   │
├──────────────────────────┤       │ FASTAPI_UNAVAILABLE (503)│
│ + success(data)          │       │ USER_NOT_FOUND (404)     │
│ + error(errorCode, msg)  │       │ TEMPLATE_NOT_FOUND (404) │
└──────────────────────────┘       │ INVALID_REQUEST (400)    │
                                   └──────────────────────────┘
┌──────────────────────────┐
│    PageResponse<T>       │       ┌──────────────────────────┐
├──────────────────────────┤       │      RetryPolicy         │
│ - content: List<T>       │       ├──────────────────────────┤
│ - page: int              │       │ - maxRetries: int        │
│ - size: int              │       │ - initialDelay: long     │
│ - totalElements: long    │       ├──────────────────────────┤
│ - totalPages: int        │       │ + executeWithRetry()     │
└──────────────────────────┘       └──────────────────────────┘

┌──────────────────────────┐  ┌──────────────────────────────┐
│ <<@RestController>>      │  │      <<@Service>>             │
│   HealthController       │  │   DataConversionService       │
├──────────────────────────┤  ├──────────────────────────────┤
│ + health()               │  │ + convert()                   │
└──────────────────────────┘  │ + getFieldMapping()           │
                              └──────────────────────────────┘

Configuration:
┌──────────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  <<@Configuration>>      │  │  <<@Configuration>>  │  │  <<@Configuration>>  │
│    CorsConfig            │  │  WebClientConfig     │  │    MongoConfig       │
├──────────────────────────┤  ├──────────────────────┤  ├──────────────────────┤
│ + corsFilter()           │  │ + webClient()        │  │ @EnableMongoAuditing │
└──────────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

---

## PK-C08: 선택지 매핑 시스템

> **NEW**: update.md의 선택지 매핑 시스템 요구사항에 따라 추가.

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-C08 |
| **클래스 다이어그램 명** | 선택지 매핑 시스템 |

```
┌──────────────────────────────────────────────────────┐
│            <<@Service>>                              │
│         ChoiceMappingService                         │
├──────────────────────────────────────────────────────┤
│ - objectMapper: ObjectMapper                         │
│ - mappingRules: MappingRules                         │  ← mapping_rules.json 파싱 결과
│ - mappingRulesPath: String                           │  ← classpath:docs/mapping_rules.json
├──────────────────────────────────────────────────────┤
│ - loadMappingRules()                                 │  ← @PostConstruct: JSON 파일 로드
│ + getCategories()                                    │  ← 카테고리 목록
│ + getServicesByCategory(category: String)            │  ← 카테고리별 서비스 목록
│ + getStartChoices(service: String)                   │  ← 시작 노드 실행 조건 선택지
│ + getEndChoices(service: String)                     │  ← 도착 노드 동작 유형 선택지
│ + getOptionsForNode(prevOutputType, context: Map)    │  ← 핵심: 데이터 타입별 선택지 조회
│ + onUserSelect(optionId, dataType: String)           │  ← 선택 처리 → 노드 타입 + 후속 설정
│ + getProcessingMethodChoices(dataType: String)       │  ← 1차: 처리 방식 ("한 건씩"/"전체")
│ - filterByApplicableWhen(actions, context: Map)      │  ← applicable_when 조건 필터링
│ - resolveOptionsSource(action, context: Map)         │  ← 동적 선택지 생성 (fields_from_data 등)
└──────────────────────────────────────────────────────┘

내부 DTO:
┌───────────────────────────┐  ┌───────────────────────────┐  ┌───────────────────────────┐
│    MappingRules           │  │    DataTypeConfig         │  │    Action                 │
├───────────────────────────┤  ├───────────────────────────┤  ├───────────────────────────┤
│ - meta: Meta              │  │ - label: String           │  │ - id: String              │
│ - dataTypes: Map<>        │  │ - requiresProcessing:bool │  │ - label: String           │
│ - nodeTypes: Map<>        │  │ - processingMethod: PM    │  │ - nodeType: String        │
│ - serviceFields: Map<>    │  │ - actions: List<Action>   │  │ - outputDataType: String  │
└───────────────────────────┘  └───────────────────────────┘  │ - priority: int           │
                                                              │ - applicableWhen: Map     │
┌───────────────────────────┐  ┌───────────────────────────┐  │ - followUp: FollowUp      │
│    FollowUp               │  │    NodeSelectionResult    │  │ - branchConfig: BranchCfg │
├───────────────────────────┤  ├───────────────────────────┤  └───────────────────────────┘
│ - question: String        │  │ - nodeType: String        │
│ - options: List<Option>   │  │ - outputDataType: String  │
└───────────────────────────┘  │ - followUp: FollowUp      │
                               │ - branchConfig: BranchCfg │
                               └───────────────────────────┘

노드 타입 (6가지): LOOP | CONDITION_BRANCH | AI | DATA_FILTER | AI_FILTER | PASSTHROUGH
```
