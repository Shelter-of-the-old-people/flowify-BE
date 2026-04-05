# 1. FastAPI 시스템 개요 및 아키텍처

---

## 1.1 시스템의 역할과 목표

Flowify 시스템 내에서 FastAPI 서버는 **비동기 기반 워크플로우 실행 엔진**이자 **AI(LLM) 처리 전담 마이크로서비스**로 동작합니다.
Spring Boot 메인 백엔드가 회원, 권한, 워크플로우 메타데이터(CRUD)를 관리한다면, FastAPI는 실제 데이터가 흐르고 가공되는 파이프라인의 **실행(Execution)**을 담당합니다.

### 핵심 목표

- **비동기 고성능 처리**: LLM 호출 및 외부 서비스(Google Drive, Slack 등) API 통신 시 발생하는 I/O 대기 시간을 최소화하기 위해 비동기(Async/Await) 기반으로 파이프라인을 처리합니다.
- **유연한 확장성 (OCP 준수)**: Strategy와 Factory 패턴을 적용하여, 향후 새로운 도메인의 노드(예: GitHub, Jira 연동 등)가 추가되더라도 기존 실행 엔진 코드는 수정되지 않도록 설계합니다.
- **LLM 오케스트레이션**: LangChain을 활용하여 복잡한 프롬프트 체이닝, 출력 파싱, 외부 도구 연동(RAG 등)을 효과적으로 제어합니다.

---

## 1.2 시스템 아키텍처 및 데이터 흐름

### 1.2.1 전체 컨텍스트 아키텍처

프론트엔드는 FastAPI 서버와 직접 통신하지 않으며, 모든 요청은 Spring Boot를 거쳐 내부 통신으로 전달됩니다.

```text
[ Frontend (React) ]  <---(REST API)--->  [ Spring Boot (Main BE) ]
                                                  | (Internal REST API)
                                                  V
                                          [ FastAPI (AI/Engine) ] ---> [ MongoDB (Execution Logs) ]
                                                  |
                                                  +---> [ External APIs (Google, Slack) ]
                                                  +---> [ OpenAI API (LLM) ]
                                                  +---> [ ChromaDB (Vector Store) ]
```

### 1.2.2 내부 레이어드 아키텍처

FastAPI 내부는 역할에 따라 명확히 계층이 분리됩니다.

1. **API Router Layer (`app/api/`)**: Spring Boot로부터의 내부 API 요청을 수신하고 응답합니다. (`X-Internal-Token` 기반 인증)
2. **Core Engine Layer (`app/core/engine/`)**: 워크플로우 실행을 조율합니다. 상태 전환, 노드 순차 실행, 스냅샷 저장을 담당합니다.
3. **Node Strategy Layer (`app/core/nodes/`)**: 개별 노드(Input, LLM, Logic, Output 등)의 실제 동작 로직이 캡슐화된 계층입니다.
4. **Service & Integration Layer (`app/services/`)**: 외부 의존성을 가지는 구체적인 서비스 구현체입니다. (LLM 연동, OAuth 토큰 기반 외부 API 호출 등)

---

## 1.3 설계 제약사항 (Constraints)

1. **내부 통신 전용**: FastAPI 서버는 외부(Public Internet)에 직접 포트를 개방하지 않으며, 방화벽/VPC 설정 또는 인그레스 컨트롤러를 통해 Spring Boot에서만 접근할 수 있도록 격리합니다.
2. **무상태(Stateless) 워크플로우**: 각 실행(Execution)은 독립적이며, 메모리에 실행 상태를 장기 보관하지 않습니다. 모든 실행 이력과 스냅샷은 MongoDB에 기록하여 서버 재시작 시에도 롤백/복구가 가능하게 합니다.
3. **복호화된 토큰 수신**: 외부 서비스 연동을 위한 OAuth 토큰은 Spring Boot가 데이터베이스에서 조회하여 복호화한 후, 워크플로우 실행 요청 시 Payload에 포함하여 전달합니다. FastAPI는 토큰의 암호화/복호화 책임을 지지 않습니다.
4. **에러 격리**: 단일 노드의 실행 실패가 전체 서버 인스턴스의 크래시로 이어지지 않도록 철저한 예외 처리와 `WorkflowStateManager`를 통한 상태 관리를 강제합니다.
