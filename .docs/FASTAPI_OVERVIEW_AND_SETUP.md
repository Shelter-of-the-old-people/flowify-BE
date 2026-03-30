# FastAPI 개발 계획 1: 개요 및 기반 구축

> **문서 목적**: Flowify 전체 아키텍처 내에서 FastAPI 서버의 역할과 책임을 명확히 하고, Phase 1 개발 단계인 초기 프로젝트 설정 및 기반 구축 계획을 정의합니다.

---

## 1. FastAPI 서버의 역할과 책임 (Role & Responsibilities)

`PROJECT_ANALYSIS.md`에 명시된 바와 같이, FastAPI는 전체 시스템에서 **AI 처리 및 워크플로우 실행을 전담하는 마이크로서비스** 역할을 수행합니다.

- **단일 요청 진입점**: 프론트엔드(React)가 아닌 Spring Boot 메인 백엔드로부터 내부 API 호출을 받습니다. 외부에는 직접 노출되지 않습니다.
- **워크플로우 실행 엔진**: Spring Boot로부터 워크플로우 정의(노드, 엣지)와 암호화가 해제된 외부 서비스 토큰을 받아 실제 파이프라인을 실행합니다.
- **비동기 처리**: LLM 호출, 외부 API 연동 등 시간이 소요될 수 있는 작업들을 `async/await` 기반으로 처리하여 높은 처리량을 보장합니다.
- **상태 관리**: 워크플로우 실행의 각 단계(대기, 실행, 성공, 실패)를 관리하고, 실행 결과를 MongoDB의 `workflow_executions` 컬렉션에 기록합니다.

## 2. 핵심 설계 원칙 (Core Design Principles)

FastAPI 서버는 `PROJECT_ANALYSIS.md`의 핵심 설계 패턴을 충실히 따릅니다.

- **Strategy Pattern**: 각 노드의 실행 로직을 `NodeStrategy` 인터페이스 뒤로 캡슐화하여 노드 유형 확장에 유연하게 대응합니다. (`app/core/nodes/base.py`)
- **Factory Pattern**: 노드 타입 문자열(`llm`, `input` 등)로부터 실제 `NodeStrategy` 객체를 생성하여, 실행 엔진과 노드 구현 간의 결합을 낮춥니다. (`app/core/nodes/factory.py`)
- **State Pattern**: 워크플로우의 상태 변화 로직을 `WorkflowStateManager` 내에서 관리하여 복잡한 상태 전환 규칙을 체계적으로 다룹니다. (`app/core/engine/state.py`)
- **OCP (개방-폐쇄 원칙)**: 새로운 노드나 서비스가 추가되더라도 기존 실행 엔진(`WorkflowExecutor`) 코드는 수정할 필요가 없도록 설계합니다.

---

## 3. Phase 1: 기반 구축 및 초기 설정

> **목표**: 실제 기능 개발에 앞서, 프로젝트의 뼈대를 만들고 안정적인 개발 환경을 구축합니다.

### 3.1. 프로젝트 구조 확인 및 설정

- **디렉토리 구조**: `PROJECT_ANALYSIS.md`에 정의된 디렉토리 구조(`api`, `core`, `services`, `models`, `db`)를 유지하고 필요한 `__init__.py` 파일을 구성합니다.
- **환경 설정**: `app/config.py`를 통해 환경변수(OpenAI API 키, DB 연결 정보 등)를 관리합니다. `.env` 파일을 활용하여 민감 정보를 코드와 분리합니다.

### 3.2. 핵심 추상화 및 팩토리 구현

- `app/core/nodes/base.py`: 모든 노드 전략의 기반이 될 `NodeStrategy` 추상 클래스를 정의합니다. `execute`와 `validate` 메소드를 포함합니다.
- `app/core/nodes/factory.py`: `NodeFactory` 클래스를 구현하여 노드 타입 문자열을 받아 적절한 `NodeStrategy` 인스턴스를 반환하도록 합니다.

### 3.3. 상태 관리 및 API 기본 구조

- `app/core/engine/state.py`: `WorkflowState` Enum(열거형)과 상태 전환 로직을 담은 `WorkflowStateManager`를 구현합니다.
- `app/main.py`: FastAPI 앱의 생명주기(`lifespan`) 내에서 MongoDB 연결 및 종료 로직을 설정합니다.
- `app/api/v1/router.py`: v1 API 라우터들을 통합하고, `/api/v1` 접두사를 설정합니다.
- `app/api/v1/endpoints/health.py`: `GET /api/v1/health` 엔드포인트를 구현하여 서버의 상태를 확인할 수 있도록 합니다.

### 3.4. Docker 환경 구성

- `Dockerfile` 및 `docker-compose.yml`을 FastAPI 프로젝트에 맞게 구성하여, Spring Boot 및 MongoDB와 함께 일관된 로컬 개발 환경을 구축합니다.
