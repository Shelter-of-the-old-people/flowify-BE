# 3. 객체지향설계

## 3.1 Deployment Diagram (시스템 운용도)

---

### 전체 시스템 배포 구성도

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                   │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     React Frontend (SPA)                              │  │
│  │                     http://localhost:3000                              │  │
│  │                                                                       │  │
│  │  - 캔버스 시각적 에디터 (React Flow)                                     │  │
│  │  - 노드 설정 패널                                                       │  │
│  │  - 실행 상태 모니터링                                                    │  │
│  │  - 템플릿 마켓                                                          │  │
│  └────────────────────────────┬──────────────────────────────────────────┘  │
│                               │                                             │
│                               │ HTTPS (공개 API)                            │
│                               │ Authorization: Bearer <JWT>                 │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Docker Compose Network (flowify-net)              │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                   Spring Boot 메인 백엔드                              │  │
│  │                   http://spring-boot:8080                             │  │
│  │                                                                       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │  │
│  │  │   Auth   │ │   User   │ │ Workflow │ │ Template │ │   OAuth   │  │  │
│  │  │  Module  │ │  Module  │ │  Module  │ │  Module  │ │   Token   │  │  │
│  │  │          │ │          │ │          │ │          │ │   Module  │  │  │
│  │  └──────────┘ └──────────┘ └────┬─────┘ └──────────┘ └───────────┘  │  │
│  │                                  │                                    │  │
│  │  ┌──────────┐ ┌─────────────────┴───────────────────────┐            │  │
│  │  │  Common  │ │           Execution Module               │            │  │
│  │  │  Module  │ │  (FastApiClient, SnapshotService)        │            │  │
│  │  └──────────┘ └─────────────────┬───────────────────────┘            │  │
│  └─────────────────┬───────────────┼────────────────────────────────────┘  │
│                    │               │                                        │
│                    │               │ HTTP (내부 전용)                        │
│                    │               │ X-Internal-Token: <shared-secret>      │
│                    │               │ X-User-ID: <user_id>                   │
│                    │               │                                        │
│                    │               ▼                                        │
│  ┌─────────────────┼───────────────────────────────────────────────────┐   │
│  │                 │         FastAPI AI 서비스                          │   │
│  │                 │         http://fastapi:8000                        │   │
│  │                 │                                                    │   │
│  │                 │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │   │
│  │                 │  │ Workflow │ │   LLM    │ │ External │          │   │
│  │                 │  │ Executor │ │ Service  │ │ Service  │          │   │
│  │                 │  │ (Engine) │ │(LangChain│ │Connector │          │   │
│  │                 │  └──────────┘ └────┬─────┘ └──────────┘          │   │
│  └─────────────────┼────────────────────┼─────────────────────────────┘   │
│                    │                    │                                   │
│                    ▼                    ▼                                   │
│  ┌──────────────────────┐  ┌──────────────────────┐                       │
│  │      MongoDB 7       │  │    Vector Store       │                       │
│  │  mongodb:27017       │  │    Chroma              │                       │
│  │                      │  │                       │                       │
│  │  Collections:        │  │  - 문서 임베딩 저장    │                       │
│  │  - users             │  │  - 유사도 검색         │                       │
│  │  - workflows         │  │  - RAG 파이프라인      │                       │
│  │  - oauth_tokens      │  │                       │                       │
│  │  - templates         │  └──────────────────────┘                       │
│  │  - workflow_executions│                                                 │
│  │  - chat_history      │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS (외부 API)
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          External Services                                  │
│                                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │  Google  │ │  Slack   │ │  Notion  │ │   LLM    │ │   Web    │        │
│  │  APIs    │ │   API    │ │   API    │ │ (GPT-4o) │ │ Crawling │        │
│  │          │ │          │ │          │ │          │ │  Targets │        │
│  │ - Drive  │ │ OAuth2.0 │ │ OAuth2.0 │ │ API Key  │ │  (HTTP)  │        │
│  │ - Sheets │ │          │ │          │ │          │ │          │        │
│  │ - Gmail  │ │          │ │          │ │          │ │ - 쿠팡    │        │
│  │ - Cal.   │ │          │ │          │ │          │ │ - 원티드   │        │
│  │ OAuth2.0 │ │          │ │          │ │          │ │ - 네이버   │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 서버 구성 상세

| 서버 | 포트 | 프로토콜 | 역할 |
|------|------|---------|------|
| React Frontend | 3000 | HTTP/HTTPS | 사용자 인터페이스, SPA |
| Spring Boot | 8080 | HTTP (내부), HTTPS (공개) | 메인 백엔드, 인증/인가, CRUD, 실행 위임 |
| FastAPI | 8000 | HTTP (내부 전용) | AI 서비스, 워크플로우 실행 엔진, LLM 연동 |
| MongoDB | 27017 | MongoDB Protocol | 데이터 저장 |

---

### 통신 규격

| 구간 | 방향 | 프로토콜 | 인증 방식 |
|------|------|---------|----------|
| Frontend → Spring Boot | 단방향 요청/응답 | HTTPS | JWT (Authorization: Bearer) |
| Spring Boot → FastAPI | 단방향 요청/응답 | HTTP (내부) | X-Internal-Token + X-User-ID |
| Spring Boot → MongoDB | 양방향 | MongoDB Protocol | 연결 URI |
| FastAPI → MongoDB | 양방향 | MongoDB Protocol (Motor) | 연결 URI |
| FastAPI → External APIs | 단방향 요청/응답 | HTTPS | OAuth 2.0 / API Key |
| FastAPI → LLM | 단방향 요청/응답 | HTTPS | API Key |
| FastAPI → Vector Store | 양방향 | 내부 라이브러리 | - |

---

### Docker Compose 배포 구성

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

  fastapi:
    build: ../flowify-BE    # FastAPI 별도 레포
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
