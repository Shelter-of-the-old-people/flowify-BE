# FastAPI 개발 계획 2: 핵심 실행 엔진 구현

> **문서 목적**: Phase 2 개발 단계인 워크플로우 실행 엔진과 핵심 LLM 서비스의 구체적인 구현 계획을 정의합니다.

---

## 1. Phase 2: 워크플로우 실행 엔진 및 LLM 서비스 구현

> **목표**: Phase 1에서 구축한 기반 위에 실제 워크플로우를 순차적으로 실행하는 엔진을 만들고, 프로젝트의 핵심 기능인 LLM 연동을 구체화합니다.

### 1.1. 워크플로우 실행기 (Executor) 구현

- **파일 위치**: `app/core/engine/executor.py`
- **클래스명**: `WorkflowExecutor`
- **구현 내용**:
  - Spring Boot로부터 전달받은 워크플로우 정의(노드 리스트)를 순회합니다.
  - 각 노드 정의에서 `type`과 `config`를 추출합니다.
  - `NodeFactory.create(type, config)`를 호출하여 해당 노드의 `Strategy` 객체를 생성합니다.
  - 생성된 노드 객체의 `await node.execute(input_data)` 메소드를 호출합니다. 이전 노드의 출력이 현재 노드의 입력이 됩니다.
  - `WorkflowStateManager`를 사용하여 워크플로우 시작 시 `RUNNING`, 완료 시 `SUCCESS`, 예외 발생 시 `FAILED`로 상태를 변경합니다.
  - 각 노드 실행 결과와 최종 상태를 포함하는 결과를 반환합니다.

### 1.2. LLM 서비스 구체화

- **파일 위치**: `app/services/llm_service.py`
- **클래스명**: `LLMService`
- **구현 내용**:
  - 현재 `TODO`로 남아있는 부분을 LangChain을 사용하여 실제로 구현합니다.
  - `__init__`: `ChatOpenAI` 모델을 환경변수(`OPENAI_API_KEY`, `LLM_MODEL_NAME`)를 이용해 초기화합니다.
  - `process`: `PromptTemplate`, `ChatOpenAI`, `StrOutputParser`를 파이프(|)로 연결하는 LangChain Expression Language (LCEL) 체인을 구성하고 비동기로(`ainvoke`) 실행합니다.
  - `summarize`, `classify`: `process` 메소드를 호출하는 구체적인 프롬프트를 작성합니다. 예를 들어, `summarize`는 "다음 내용을 요약해주세요:" 와 같은 프롬프트를 사용합니다.

### 1.3. 핵심 노드 구현 (`llm_node`)

- **파일 위치**: `app/core/nodes/llm_node.py`
- **클래스명**: `LLMNodeStrategy`
- **구현 내용**:
  - `__init__`: `LLMService` 인스턴스를 주입받거나 생성합니다.
  - `execute`: `input_data`와 `self.config`에서 필요한 정보(프롬프트, 처리할 텍스트 등)를 조합하여 `LLMService`의 `process`, `summarize`, `classify` 등의 메소드를 호출합니다.
  - LLM 서비스의 결과를 받아 다음 노드로 전달할 `dict` 형태로 가공하여 반환합니다.

### 1.4. 워크플로우 실행 API 구현

- **파일 위치**: `app/api/v1/endpoints/workflow.py`
- **구현 내용**:
  - `POST /api/v1/workflows/{workflow_id}/execute` 엔드포인트의 실제 로직을 구현합니다.
  - Spring Boot로부터 워크플로우 정의와 서비스 토큰을 포함하는 요청 본문을 받습니다.
  - `WorkflowExecutor` 인스턴스를 생성하고 `execute` 메소드를 호출하여 워크플로우 실행을 시작합니다.
  - 실행 결과를 클라이언트(Spring Boot)에 반환합니다.
