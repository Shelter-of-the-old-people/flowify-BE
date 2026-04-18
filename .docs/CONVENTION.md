# Flowify FastAPI — 개발 컨벤션

> 작성일: 2026-04-18  
> 적용 대상: `flowify-BE` (FastAPI) 레포지토리

---

## 목차

1. [언어 원칙](#1-언어-원칙)
2. [디렉토리 구조 & 파일 명명](#2-디렉토리-구조--파일-명명)
3. [Python 코딩 스타일](#3-python-코딩-스타일)
4. [Pydantic 모델](#4-pydantic-모델)
5. [API 엔드포인트](#5-api-엔드포인트)
6. [에러 처리](#6-에러-처리)
7. [서비스 클래스 & 외부 연동](#7-서비스-클래스--외부-연동)
8. [테스트](#8-테스트)
9. [브랜치 & 커밋 전략](#9-브랜치--커밋-전략)
10. [코드 포매터 (ruff)](#10-코드-포매터-ruff)
11. [PR 체크리스트](#11-pr-체크리스트)

---

## 1. 언어 원칙

**모든 텍스트는 한국어를 사용한다.**

| 항목 | 언어 | 예시 |
|------|------|------|
| docstring | 한국어 | `"""Gmail 메시지 목록을 조회합니다."""` |
| 로그 메시지 | 한국어 | `logger.warning("외부 API 재시도: %s", url)` |
| 커밋 메시지 | 한국어 | `feat(입력노드): Gmail 서비스 연결 구현` |
| 인라인 주석 | 한국어 | `# credentials 키: 서비스명(gmail, slack 등)` |
| 변수/함수/클래스명 | 영어 (Python 표준) | `execution_id`, `WorkflowExecutor` |
| 에러 메시지 (`detail`) | 한국어 | `"워크플로우를 찾을 수 없습니다."` |

> **예외**: 외부 라이브러리 API 키, 환경변수 이름은 영어 유지 (`MONGODB_URL`, `LLM_API_KEY` 등)

---

## 2. 디렉토리 구조 & 파일 명명

### 디렉토리 역할

```
app/
├── api/v1/
│   ├── endpoints/      # 엔드포인트 핸들러 — 파일 1개 = 도메인 1개
│   ├── deps.py         # FastAPI 의존성 주입 함수 (get_db, get_user_id)
│   ├── middleware.py   # 미들웨어 (InternalAuthMiddleware)
│   └── router.py       # 모든 엔드포인트 라우터 통합
├── core/
│   ├── engine/         # 워크플로우 실행 엔진 (executor, state, snapshot)
│   └── nodes/          # 노드 전략 패턴 (base, factory, *_node)
├── services/
│   ├── integrations/   # 외부 서비스 연동 (base + 서비스별 파일)
│   └── *.py            # 내부 서비스 (llm_service, scheduler_service 등)
├── models/             # Pydantic 스키마
│   ├── workflow.py     # 워크플로우 도메인 모델
│   ├── execution.py    # 실행 로그 모델 (MongoDB 저장용)
│   └── requests.py     # API 요청/응답 DTO
├── common/
│   └── errors.py       # ErrorCode, FlowifyException, 핸들러
├── db/
│   └── mongodb.py      # DB 연결 관리
├── config.py           # Settings (pydantic-settings)
└── main.py             # FastAPI 앱 진입점
```

### 파일 명명 규칙

| 종류 | 규칙 | 예시 |
|------|------|------|
| 엔드포인트 | `{도메인}.py` | `execution.py`, `trigger.py` |
| 노드 전략 | `{타입}_node.py` | `llm_node.py`, `input_node.py` |
| 통합 서비스 | `{서비스명}.py` | `gmail.py`, `google_drive.py` |
| 테스트 | `test_{대상}.py` | `test_executor.py`, `test_gmail.py` |
| 모델 | 도메인 단위 | `workflow.py`, `execution.py` |

### 새 파일 추가 시 위치 결정 기준

```
외부 API 호출?  → app/services/integrations/{서비스}.py
노드 전략?      → app/core/nodes/{타입}_node.py
라우트 핸들러?  → app/api/v1/endpoints/{도메인}.py
Pydantic 모델? → app/models/{관련도메인}.py
비즈니스 로직?  → app/services/{서비스명}_service.py
```

---

## 3. Python 코딩 스타일

### 3-1. 타입 힌트

**모든 public 함수/메서드에 파라미터 타입과 반환 타입을 명시한다.**

```python
# ✅ 올바른 예
async def list_messages(
    self, token: str, query: str = "", max_results: int = 20
) -> list[dict]:

# ❌ 잘못된 예
async def list_messages(self, token, query="", max_results=20):
```

- Union 타입: `str | None` (Python 3.10+ 스타일, `Optional[str]` 사용 금지)
- Generic: `list[str]`, `dict[str, str]` (소문자)
- 반환 없음: `-> None` 명시

### 3-2. Docstring

**모든 public 클래스와 public 메서드에 한 줄 이상의 docstring을 작성한다.**

```python
class GmailService(BaseIntegrationService):
    """Gmail API 연동 서비스."""

    async def list_messages(
        self, token: str, query: str = "", max_results: int = 20
    ) -> list[dict]:
        """Gmail 메시지 목록을 조회합니다.

        Args:
            token: OAuth 액세스 토큰
            query: Gmail 검색 쿼리 (예: "is:unread")
            max_results: 최대 조회 개수

        Returns:
            메시지 상세 정보 딕셔너리 리스트

        Raises:
            FlowifyException: 토큰 만료 또는 API 호출 실패 시
        """
```

**Docstring 스타일 규칙:**
- 한 줄 설명: 동사로 시작 (`"""메시지 목록을 조회합니다."""`)
- 여러 줄: Google 스타일 (`Args:`, `Returns:`, `Raises:` 섹션)
- 내부 함수(`_`로 시작): 선택적
- 자명한 코드에 docstring 강요 금지 (`def validate(self) -> bool: return True`)

### 3-3. Import 순서

`ruff`의 isort가 자동 정렬하므로 직접 순서를 신경 쓰지 않아도 됨. 단, 구조는 아래와 같이 유지:

```python
# 1. Python 표준 라이브러리
import asyncio
import logging
from datetime import datetime

# 2. 서드파티 라이브러리
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

# 3. 내부 모듈 (app.*)
from app.common.errors import ErrorCode, FlowifyException
from app.config import settings
```

### 3-4. 명명 규칙

| 종류 | 규칙 | 예시 |
|------|------|------|
| 함수/메서드 | `snake_case` | `list_messages`, `execute_workflow` |
| 변수 | `snake_case` | `execution_id`, `node_map` |
| 클래스 | `PascalCase` | `GmailService`, `WorkflowExecutor` |
| 상수 (모듈 레벨) | `UPPER_SNAKE_CASE` | `GMAIL_API`, `MAX_RETRIES` |
| 비공개 | `_` 접두사 | `_request`, `_extract_body` |
| Enum | `PascalCase` + 값은 `snake_case` | `WorkflowState.RUNNING = "running"` |

### 3-5. 비동기 패턴

- 외부 I/O (HTTP, DB)는 항상 `async def` + `await` 사용
- CPU 바운드 작업은 동기 함수로 작성 (`@staticmethod def _topological_sort(...)`)
- `asyncio.sleep()` 은 재시도 대기에서만 사용

### 3-6. 상수 정의

```python
# ✅ 모듈 상수: UPPER_SNAKE_CASE
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_LOOP_ITERATIONS = 1000

# ✅ 제한된 값 집합: Enum 또는 frozenset
_ROLLBACK_ALLOWED_STATES = frozenset({
    WorkflowState.ROLLBACK_AVAILABLE.value,
    WorkflowState.FAILED.value,
})

# ❌ 매직 넘버 직접 사용 금지
await asyncio.sleep(1.0)    # ❌
await asyncio.sleep(BASE_BACKOFF)  # ✅
```

---

## 4. Pydantic 모델

### 4-1. Spring Boot ↔ FastAPI 모델 (camelCase 변환)

Spring Boot에서 오는 요청 / 가는 응답 모델은 `alias_generator`로 자동 변환:

```python
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

class NodeDefinition(BaseModel):
    """노드 정의 모델 (Spring Boot camelCase JSON 자동 매핑)."""

    model_config = {"populate_by_name": True, "alias_generator": to_camel}

    id: str
    data_type: str | None = None       # JSON: "dataType"
    auth_warning: bool = False         # JSON: "authWarning"
```

**규칙:**
- Python 필드명: `snake_case`
- JSON 직렬화: `camelCase` (alias_generator가 자동 변환)
- `populate_by_name=True`: Python 필드명으로도 수신 가능

### 4-2. MongoDB 저장용 모델 (camelCase 필드명)

MongoDB에 직접 저장되는 모델은 Spring Boot와 동일한 camelCase 필드명 사용:

```python
class NodeExecutionLog(BaseModel):
    """노드 실행 로그 (MongoDB workflow_executions.nodeLogs에 저장)."""

    # 필드명 자체가 camelCase — alias 불필요
    nodeId: str
    status: str = "pending"
    inputData: dict = Field(default_factory=dict)
    startedAt: datetime = Field(default_factory=datetime.utcnow)
```

### 4-3. 내부 API 요청/응답 DTO

FastAPI 내부용 DTO는 `snake_case` 사용 (alias_generator 불필요):

```python
class WorkflowExecuteRequest(BaseModel):
    """워크플로우 실행 요청 DTO."""

    workflow: WorkflowDefinition
    service_tokens: dict[str, str] = Field(default_factory=dict)
```

### 4-4. Mutable 기본값

```python
# ✅ Field(default_factory=...) 사용
nodes: list[NodeDefinition] = Field(default_factory=list)
config: dict = Field(default_factory=dict)

# ❌ 가변 기본값 직접 사용 금지
nodes: list[NodeDefinition] = []   # ❌
```

---

## 5. API 엔드포인트

### 5-1. 응답 형식

**성공 응답**: 데이터를 직접 반환 (Pydantic 모델 또는 dict)  
**에러 응답**: `FlowifyException` → 핸들러가 자동으로 아래 형식으로 변환

```json
// 에러 응답 형식 (errors.py 핸들러 자동 처리)
{
  "success": false,
  "error_code": "WORKFLOW_NOT_FOUND",
  "message": "워크플로우를 찾을 수 없습니다.",
  "detail": { "workflow_id": "wf_abc123" }
}
```

성공 응답에 별도 래퍼(`{"success": true, "data": ...}`)를 사용하지 않는다.

### 5-2. response_model 지정

**모든 엔드포인트에 `response_model` 또는 반환 타입 힌트를 지정한다.**

```python
# ✅ Pydantic 모델 반환 시 response_model 지정
@router.post("/{workflow_id}/execute", response_model=ExecutionResult)
async def execute_workflow(...) -> ExecutionResult:

# ✅ dict 반환 시 반환 타입 힌트로 대체 가능
@router.get("/{execution_id}/status")
async def get_execution_status(...) -> dict:

# ❌ 둘 다 없는 경우 금지
@router.post("/generate")
async def generate_workflow(...):
```

### 5-3. 의존성 주입

```python
# 공통 의존성은 deps.py에서 관리
from app.api.v1.deps import get_db, get_user_id

@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> ExecutionResult:
```

### 5-4. 라우터 등록

새 엔드포인트 파일을 만들면 반드시 `app/api/v1/router.py`에 등록:

```python
from app.api.v1.endpoints import execution, health, llm, workflow, trigger

api_router.include_router(trigger.router, prefix="/triggers", tags=["트리거"])
```

---

## 6. 에러 처리

### 6-1. FlowifyException 사용

비즈니스 로직에서 발생하는 모든 에러는 `FlowifyException`으로 래핑한다.

```python
from app.common.errors import ErrorCode, FlowifyException

# ✅ 올바른 예
raise FlowifyException(
    ErrorCode.OAUTH_TOKEN_INVALID,
    detail="Gmail 서비스 토큰이 만료되었습니다.",
    context={"service": "gmail", "user_id": user_id},
)

# ❌ 잘못된 예 — 직접 ValueError/RuntimeError 사용 금지
raise ValueError("Unknown node type")
```

### 6-2. try/except 패턴

```python
try:
    result = await external_service.call(...)
except FlowifyException:
    raise  # FlowifyException은 그대로 전파
except httpx.HTTPStatusError as e:
    raise FlowifyException(
        ErrorCode.EXTERNAL_API_ERROR,
        detail=f"외부 서비스 연결 실패: {e.response.status_code}",
        context={"url": str(e.request.url)},
    ) from e
except Exception as e:
    raise FlowifyException(
        ErrorCode.INTERNAL_ERROR,
        detail=f"예상치 못한 오류가 발생했습니다.",
    ) from e
```

### 6-3. 로깅 레벨 기준

| 레벨 | 사용 시점 | 예시 |
|------|---------|------|
| `logger.debug()` | 상세 디버그 정보 (개발 환경) | 요청/응답 상세 데이터 |
| `logger.info()` | 정상 동작 기록 | "워크플로우 실행 시작" |
| `logger.warning()` | 복구 가능한 비정상 상황 | "API 재시도 중" |
| `logger.error()` | 복구 불가능한 실패 | "외부 API 최대 재시도 초과" |

```python
# ✅ 모듈 상단에 logger 초기화 (모듈당 1회)
import logging
logger = logging.getLogger(__name__)

# ✅ 레벨별 사용
logger.info("워크플로우 실행 시작: %s", execution_id)
logger.warning("외부 API 재시도 %d/%d: %s", attempt + 1, MAX_RETRIES, url)
logger.error("LLM API 최대 재시도 초과: %s", str(last_error))
```

### 6-4. 새 ErrorCode 추가 기준

기존 코드에 없는 에러 상황이 생기면 `app/common/errors.py`에 추가:

```python
class ErrorCode(Enum):
    # 추가 예시
    SCHEDULER_NOT_INITIALIZED = (500, "스케줄러가 초기화되지 않았습니다")
    LOOP_TIMEOUT = (408, "루프 노드 실행 시간이 초과되었습니다")
```

---

## 7. 서비스 클래스 & 외부 연동

### 7-1. 외부 서비스 — BaseIntegrationService 상속

모든 외부 API 연동 서비스는 `BaseIntegrationService`를 상속한다.

```python
from app.services.integrations.base import BaseIntegrationService

class NotionService(BaseIntegrationService):
    """Notion API 연동 서비스."""

    async def create_page(self, token: str, database_id: str, ...) -> dict:
        """Notion 데이터베이스에 새 페이지를 생성합니다."""
        return await self._request(
            "POST",
            f"{NOTION_API}/pages",
            token,
            json={...},
        )
```

**규칙:**
- HTTP 요청은 반드시 `self._request()` 사용 (재시도 + 에러 래핑 자동 적용)
- 토큰 없는 공개 API도 `self._request(token="")` 형태로 통일
- 서비스별 API URL 상수는 모듈 레벨에 정의

### 7-2. 노드 전략 — NodeStrategy 상속

새 노드 타입은 `NodeStrategy`를 상속하고 `NodeFactory`에 등록한다.

```python
from app.core.nodes.base import NodeStrategy

class SomeNodeStrategy(NodeStrategy):
    """특정 동작을 수행하는 노드 전략."""

    async def execute(self, input_data: dict) -> dict:
        """노드 실행 로직.

        Args:
            input_data: 이전 노드의 출력 데이터 + credentials

        Returns:
            다음 노드로 전달할 데이터 딕셔너리
        """
        result = ...
        return {**input_data, "result_key": result}

    def validate(self) -> bool:
        """필수 config 필드 검증."""
        return "required_field" in self.config
```

`factory.py`에 등록:
```python
_NODE_REGISTRY: dict[str, type[NodeStrategy]] = {
    ...
    "some_node": SomeNodeStrategy,
}
```

### 7-3. service_tokens 접근 패턴

```python
# executor가 credentials 키로 전달
credentials = input_data.get("credentials", {})
token = credentials.get("gmail", "")  # 서비스명이 키

if not token:
    raise FlowifyException(
        ErrorCode.OAUTH_TOKEN_INVALID,
        detail="'gmail' 서비스 토큰이 없습니다.",
        context={"service": "gmail"},
    )
```

---

## 8. 테스트

### 8-1. 파일 구조

```
tests/
├── conftest.py                    # 공용 fixture (mock_db, client 등)
├── test_{엔드포인트}.py           # 엔드포인트 테스트
├── test_{서비스}.py               # 서비스 단위 테스트
└── test_integrations/
    └── test_{서비스명}.py         # 외부 서비스 단위 테스트
```

### 8-2. 기본 패턴

```python
import pytest
from unittest.mock import AsyncMock, patch

# 비동기 테스트: @pytest.mark.asyncio (asyncio_mode = "auto"이므로 생략 가능)
# conftest.py의 asyncio_mode = "auto" 설정으로 자동 적용됨

class TestGmailService:
    """GmailService 단위 테스트."""

    @pytest.fixture()
    def gmail(self):
        """테스트용 GmailService 인스턴스."""
        return GmailService()

    async def test_list_messages_성공(self, gmail):
        """정상적인 메시지 목록 조회를 검증합니다."""
        with patch.object(gmail, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"messages": [{"id": "msg_1"}]}
            result = await gmail.list_messages("fake_token")
        assert isinstance(result, list)
        mock_req.assert_called_once()

    async def test_list_messages_토큰없음_에러(self, gmail):
        """토큰이 없을 때 FlowifyException 발생을 검증합니다."""
        with pytest.raises(FlowifyException) as exc_info:
            await gmail.list_messages("")
        assert exc_info.value.error_code == ErrorCode.OAUTH_TOKEN_INVALID
```

### 8-3. 테스트 네이밍

```
test_{동작}_{조건}_{기대결과}

# 예시
test_execute_workflow_선형_성공
test_build_branch_map_if_else_노드만_처리
test_list_messages_토큰없음_에러발생
test_rollback_실패상태에서만_허용
```

### 8-4. Mock 사용 규칙

```python
# ✅ 외부 서비스 호출은 반드시 mock
with patch.object(service, "_request", new_callable=AsyncMock):
    ...

# ✅ 클래스 생성자 mock (LLM 등 초기화 비용 큰 경우)
with patch("app.services.llm_service.ChatOpenAI"):
    svc = LLMService()

# ✅ conftest.py의 공용 fixture 활용
async def test_something(mock_db, service_tokens):  # conftest fixture
    executor = WorkflowExecutor(mock_db)
    ...

# ❌ 실제 외부 API 호출 금지 (테스트 환경에서)
```

### 8-5. conftest.py 공용 fixture

`tests/conftest.py`에 정의된 공용 fixture를 우선 사용한다:

| Fixture | 설명 |
|---------|------|
| `client` | 인증 헤더 포함 TestClient |
| `mock_db` | workflow_executions mock DB |
| `linear_workflow` | 단순 선형 워크플로우 (input→llm→output) |
| `if_else_workflow` | 분기 워크플로우 |
| `service_tokens` | 테스트용 서비스 토큰 딕셔너리 |
| `make_nodes()` | NodeDefinition 리스트 생성 헬퍼 |
| `make_edges()` | EdgeDefinition 리스트 생성 헬퍼 |

---

## 9. 브랜치 & 커밋 전략

### 9-1. 브랜치 전략

```
main                            # 안정 버전 (항상 동작해야 함)
feat/{기능명}                    # 새 기능 개발
fix/{버그명}                     # 버그 수정
docs/{문서명}                    # 문서 작성/수정
refactor/{대상}                  # 리팩토링
test/{대상}                      # 테스트 추가/수정
chore/{작업명}                   # 빌드, 설정, 의존성 등
```

**브랜치 네이밍 예시:**
```
feat/input-node-service-integration
fix/mongodb-index-fieldname
feat/trigger-api-endpoint
docs/convention-guide
```

**작업 흐름:**
```
1. main에서 브랜치 생성: git checkout -b feat/xxx
2. 작업 후 커밋: git commit -m "feat(입력노드): Gmail 서비스 연결 구현"
3. main 최신화 후 병합: git pull origin main && git merge main
4. GitHub PR 생성 → 팀원 리뷰 → main 병합
```

### 9-2. 커밋 메시지 (Conventional Commits — 한국어)

**형식:**
```
{타입}({스코프}): {설명}

{본문 — 선택사항}
```

**타입 목록:**

| 타입 | 사용 시점 | 예시 |
|------|---------|------|
| `feat` | 새 기능 추가 | `feat(입력노드): Gmail 서비스 연결 구현` |
| `fix` | 버그 수정 | `fix(DB): 인덱스 필드명 camelCase로 수정` |
| `docs` | 문서 추가/수정 | `docs(컨벤션): 브랜치 전략 추가` |
| `test` | 테스트 추가/수정 | `test(루프노드): 타임아웃 케이스 테스트 추가` |
| `refactor` | 기능 변경 없는 리팩토링 | `refactor(실행기): branch_map IfElse 타입 필터링` |
| `chore` | 빌드, 설정, 의존성 | `chore(ruff): line-length 100으로 설정` |

**스코프 (선택):**
```
feat(입력노드), fix(실행기), test(LLM서비스), docs(API명세)
```

**커밋 메시지 예시:**
```
feat(입력노드): Gmail/Drive/Sheets 서비스 연결 구현

- source별 분기 처리 (gmail, google_drive, google_sheets, web_crawl)
- credentials["서비스명"] 으로 토큰 접근
- 토큰 없을 때 OAUTH_TOKEN_INVALID 에러 발생
```

**나쁜 커밋 예시:**
```
❌ "update"
❌ "fix bug"
❌ "작업분담 ABC"
❌ "mini update"
```

---

## 10. 코드 포매터 (ruff)

### 10-1. 설정

`pyproject.toml`에 설정 완료. 별도 수정 불필요.

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "SIM"]
ignore = ["E501", "N818", "B008", "SIM108"]
```

### 10-2. 주요 명령어

```bash
# 린트 검사 (수정 없음)
ruff check .

# 린트 검사 + 자동 수정 가능한 것 수정
ruff check --fix .

# 코드 포매팅
ruff format .

# 전체 (포매팅 + 린트 수정)
ruff format . && ruff check --fix .
```

### 10-3. 커밋 전 필수 실행

PR을 올리기 전 아래 두 명령을 반드시 실행한다:

```bash
ruff format .
ruff check --fix .
```

> **팁**: IDE에 ruff 플러그인을 설치하면 저장 시 자동 포매팅 가능  
> VS Code: `ruff` 익스텐션 설치 + `"editor.formatOnSave": true`

---

## 11. PR 체크리스트

PR을 올리기 전 아래 항목을 확인한다:

### 필수 ✅

- [ ] `ruff format .` 실행 완료 (포매팅)
- [ ] `ruff check .` 경고 없음 (린트)
- [ ] 새 기능에 대한 테스트 작성
- [ ] `pytest tests/` 전체 통과
- [ ] 모든 public 함수/클래스에 한국어 docstring 작성
- [ ] 에러 발생 시 `FlowifyException` 사용

### 권장 ✅

- [ ] PR 제목이 커밋 메시지 형식(`feat:`, `fix:` 등)을 따름
- [ ] 새 노드 타입 추가 시 `NodeFactory`에 등록됨
- [ ] 새 엔드포인트 추가 시 `router.py`에 등록됨
- [ ] `response_model` 또는 반환 타입 힌트 지정됨
- [ ] 새 ErrorCode 추가 시 `errors.py`에 정의됨

---

*이 문서는 프로젝트 진행 중 업데이트될 수 있습니다.*
