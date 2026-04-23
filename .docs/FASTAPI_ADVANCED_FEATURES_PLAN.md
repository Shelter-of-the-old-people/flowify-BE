# FastAPI 개발 계획 3: 고급 기능 및 외부 연동 확장

> **문서 목적**: Phase 3, 4 개발 단계인 외부 서비스 연동, 스케줄링, 고급 로직 노드, 벡터 검색 등 확장 기능의 구현 계획을 정의합니다.

> **⚠️ v2 안내 (2026-04-23)**: 이 문서는 초기 계획 단계에서 작성되었습니다. 노드 시그니처, 데이터 흐름, 서비스 라우팅 방식이 v2 런타임 컨트랙트로 전면 교체되었습니다. 현재 구현 기준은 `FASTAPI_CONTRACT_SPEC.md`, `FASTAPI_IMPLEMENTATION_GUIDE.md`, `TASK_*.md` 파일을 참고하세요.

---

## 1. Phase 3: 외부 서비스 연동 확장

> **목표**: 핵심 엔진이 동작하기 시작하면, `PROJECT_ANALYSIS.md`에 정의된 다양한 외부 서비스(Google, Slack 등) 연동 기능을 추가하여 워크플로우의 활용도를 높입니다.

### 1.1. 연동 서비스 모듈 구조

- **신규 디렉토리**: `app/services/integrations/`
- **구현 방식**:
  - 각 외부 서비스에 대한 클라이언트 로직을 별도의 파일로 분리하여 관리합니다. (예: `google_drive.py`, `slack.py`, `notion.py`)
  - 각 파일은 Spring Boot로부터 전달받은 암호 해독된 OAuth 토큰을 사용하여 해당 서비스의 API를 호출하는 함수/클래스를 포함합니다.
  - 예를 들어, `google_drive.py`는 `list_files(token: str, folder_id: str)`와 같은 함수를 가집니다.

### 1.2. 입/출력 노드 확장

- **파일 위치**: `app/core/nodes/input_node.py`, `app/core/nodes/output_node.py`
- **구현 내용**:
  - `InputNodeStrategy`의 `execute` 메소드에서 `self.config['source']` 값 (예: 'google_drive', 'gmail')에 따라 `app/services/integrations/` 아래의 적절한 모듈을 호출하여 데이터를 가져옵니다.
  - `OutputNodeStrategy`의 `execute` 메소드에서 `self.config['target']` 값에 따라 적절한 모듈을 호출하여 데이터를 전송합니다.

### 1.3. 웹 수집기 구현

- **파일 위치**: `app/services/integrations/web_crawler.py`
- **구현 내용**: `BeautifulSoup`, `httpx` 등의 라이브러리를 사용하여 특정 웹사이트(쿠팡, 네이버 뉴스 등)의 HTML을 분석하고 필요한 정보를 추출하는 크롤러를 구현합니다. 이 기능은 `InputNodeStrategy`에서 `source`가 'web_crawl'일 때 사용됩니다.

---

## 2. Phase 4: 고급 기능 및 안정화

> **목표**: 핵심 기능 구현 후, 스케줄링, 조건 분기 등 고급 기능을 추가하고 서비스 안정성을 높입니다.

### 2.1. 스케줄링 기능 구현

- **파일 위치**: `app/services/scheduler_service.py`, `app/api/v1/endpoints/trigger.py`
- **구현 내용**:
  - `APScheduler`를 사용하여 시간 기반(cron, interval) 트리거를 관리하는 `SchedulerService`를 구현합니다.
  - 스케줄 등록/삭제를 위한 API 엔드포인트를 `trigger.py`에 구현합니다. 스케줄된 작업은 특정 워크플로우의 실행을 요청하는 내부 함수를 호출합니다.

### 2.2. 로직 노드 구현 (조건/반복)

- **파일 위치**: `app/core/nodes/logic_node.py`
- **구현 내용**:
  - `IfElseNodeStrategy`: `execute` 메소드에서 `input_data`와 `self.config`의 조건을 비교하여 'true' 또는 'false' 분기를 결정하는 로직을 구현합니다. 워크플로우 실행기(`executor`)는 이 결과에 따라 다음 실행할 노드를 결정해야 합니다. (Executor 수정 필요)
  - `LoopNodeStrategy`: `items_field`에 해당하는 리스트 데이터를 순회하며, 각 아이템에 대해 하위 노드 체인(sub-flow)을 실행하는 로직을 구현합니다. 이를 위해 `WorkflowExecutor`가 중첩된 실행을 처리할 수 있도록 수정이 필요할 수 있습니다.

### 2.3. 벡터 검색 및 RAG 구현

- **파일 위치**: `app/services/vector_service.py`
- **구현 내용**: `TODO`로 남아있는 `VectorService`를 `chromadb-client`와 `sentence-transformers`를 사용하여 구현합니다. 문서를 임베딩하여 ChromaDB에 저장하고, 유사도 검색을 통해 RAG(Retrieval-Augmented Generation) 파이프라인을 구축하는 기능을 제공합니다.

### 2.4. 롤백 및 로깅 강화

- **파일 위치**: `app/core/engine/snapshot.py`, `app/core/engine/executor.py`
- **구현 내용**: `WorkflowExecutor`가 각 노드를 실행하기 전에 `SnapshotManager`를 사용하여 현재 데이터의 스냅샷을 저장하도록 로직을 추가합니다. 노드 실행 실패 시, `WorkflowStateManager`의 상태를 `ROLLBACK_AVAILABLE`로 변경하고 관련 정보를 `workflow_executions` 로그에 남깁니다.
