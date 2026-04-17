# 작업자 A — 노드 통합 & 서비스 연동

> 작성일: 2026-04-17 | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/core/nodes/input_node.py` | ⚠️ TODO — 서비스 연결 필요 |
| `app/core/nodes/output_node.py` | ⚠️ TODO — 서비스 연결 필요 |
| `app/core/nodes/factory.py` | 🟡 ValueError → FlowifyException 변경 필요 |
| `app/services/integrations/rest_api.py` | 🐛 재시도 로직 우회 버그 |
| `tests/test_input_node.py` | ❌ 없음 — 신규 작성 |
| `tests/test_output_node.py` | ❌ 없음 — 신규 작성 |

---

## A-1. [🔴 Critical] InputNodeStrategy — 서비스 연결

**중간 발표 전 완료 필수**

### 현재 문제 (`app/core/nodes/input_node.py:7-10`)

```python
async def execute(self, input_data: dict) -> dict:
    source = self.config.get("source", "manual")
    # TODO: source 타입에 따라 Google Drive, Gmail 등에서 데이터 가져오기
    return {**input_data, "source": source, "raw_data": self.config.get("data", "")}
```

현재는 외부 서비스에 실제로 연결하지 않고 config의 값만 반환함. 워크플로우 실행 시 데이터가 실제로 수집되지 않음.

### 핵심 설계 사항

`executor.py:101`에서 service_tokens이 `input_data["credentials"]`에 담겨 전달됨:
```python
data: dict = {"credentials": service_tokens}
```

`service_tokens`의 구조는 Spring Boot에서 전달하는 형식을 따름. **Spring Boot 담당자와 아래 사항 확인 필요:**
- 키 이름: `{"gmail": "token"}` vs `{"google": "token"}` vs 다른 형식

현재 코드에서는 `credentials.get(source, "")` 방식으로 source 이름을 키로 사용한다고 가정.

### 구현해야 할 서비스 분기

| `config["source"]` 값 | 사용 클래스 및 메서드 | 파일 위치 |
|----------------------|-------------------|---------|
| `"gmail"` | `GmailService.list_messages()` | `app/services/integrations/gmail.py:14` |
| `"google_drive"` | `GoogleDriveService.list_files()` | `app/services/integrations/google_drive.py` |
| `"google_sheets"` | `GoogleSheetsService.get_spreadsheet()` | `app/services/integrations/google_sheets.py` |
| `"google_calendar"` | `GoogleCalendarService.list_events()` | `app/services/integrations/google_calendar.py` |
| `"web_crawl"` | `WebCrawlerService.crawl()` | `app/services/integrations/web_crawler.py` |
| `"rest_api"` | `RestAPIService.call()` | `app/services/integrations/rest_api.py` |
| `"manual"` | 현재 구현 유지 (config["data"] 반환) | — |

### 서비스별 config 스키마 (작업자 A가 결정 필요)

```python
# gmail
{"source": "gmail", "query": "is:unread", "max_results": 20}

# google_drive
{"source": "google_drive", "folder_id": "abc123", "max_results": 10}

# google_sheets
{"source": "google_sheets", "spreadsheet_id": "abc123", "range": "Sheet1!A1:Z100"}

# google_calendar
{"source": "google_calendar", "calendar_id": "primary", "max_results": 10}

# web_crawl
{"source": "web_crawl", "url": "https://news.naver.com", "selector": "article"}

# rest_api
{"source": "rest_api", "method": "GET", "url": "https://api.example.com/data"}

# manual (기존 유지)
{"source": "manual", "data": "직접 입력한 텍스트"}
```

### 구현 방향

```python
from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.google_calendar import GoogleCalendarService
from app.services.integrations.web_crawler import WebCrawlerService
from app.services.integrations.rest_api import RestAPIService

class InputNodeStrategy(NodeStrategy):
    async def execute(self, input_data: dict) -> dict:
        source = self.config.get("source", "manual")
        credentials = input_data.get("credentials", {})

        if source == "manual":
            return {**input_data, "source": source, "raw_data": self.config.get("data", "")}

        token = credentials.get(source, "")
        if not token:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{source}' 서비스 토큰이 없습니다.",
            )

        if source == "gmail":
            svc = GmailService()
            data = await svc.list_messages(
                token,
                query=self.config.get("query", ""),
                max_results=self.config.get("max_results", 20),
            )
        elif source == "google_drive":
            svc = GoogleDriveService()
            data = await svc.list_files(
                token,
                folder_id=self.config.get("folder_id"),
                max_results=self.config.get("max_results", 10),
            )
        elif source == "google_sheets":
            svc = GoogleSheetsService()
            data = await svc.get_spreadsheet(
                token,
                spreadsheet_id=self.config["spreadsheet_id"],
                range_=self.config.get("range", "Sheet1"),
            )
        elif source == "web_crawl":
            svc = WebCrawlerService()
            data = await svc.crawl(
                url=self.config["url"],
                selector=self.config.get("selector"),
            )
        elif source == "rest_api":
            svc = RestAPIService()
            data = await svc.call(
                method=self.config.get("method", "GET"),
                url=self.config["url"],
                token=token,
            )
        else:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"지원하지 않는 source 타입: {source}",
            )

        return {**input_data, "source": source, "raw_data": data}

    def validate(self) -> bool:
        return "source" in self.config
```

---

## A-2. [🔴 Critical] OutputNodeStrategy — 서비스 연결

**중간 발표 전 완료 필수**

### 현재 문제 (`app/core/nodes/output_node.py:7-10`)

```python
async def execute(self, input_data: dict) -> dict:
    target = self.config.get("target", "console")
    # TODO: target에 따라 Notion, Slack, Gmail 등으로 데이터 전송
    return {**input_data, "output_target": target, "delivered": True}
```

실제로 어디에도 데이터를 전송하지 않고 `delivered: True`만 반환함.

### 구현해야 할 서비스 분기

| `config["target"]` 값 | 사용 클래스 | 주요 메서드 |
|----------------------|-----------|-----------|
| `"slack"` | `SlackService` | `post_message(token, channel, text)` |
| `"notion"` | `NotionService` | `create_page(token, database_id, properties, content)` |
| `"gmail"` | `GmailService` | `send_message(token, to, subject, body)` |
| `"google_sheets"` | `GoogleSheetsService` | `append_rows(token, spreadsheet_id, range_, values)` |
| `"google_drive"` | `GoogleDriveService` | `upload_file(token, name, content, mime_type)` |
| `"console"` | 로그 출력만 | — |

### 서비스별 config 스키마

```python
# slack
{"target": "slack", "channel": "#general", "text_field": "llm_result"}

# notion
{"target": "notion", "database_id": "abc123", "title_field": "llm_result"}

# gmail
{"target": "gmail", "to": "user@gmail.com", "subject": "Flowify 결과", "body_field": "llm_result"}

# google_sheets
{"target": "google_sheets", "spreadsheet_id": "abc123", "range": "Sheet1!A:A", "value_field": "llm_result"}

# google_drive
{"target": "google_drive", "file_name": "output.txt", "content_field": "llm_result"}

# console (기본, 테스트용)
{"target": "console"}
```

### 핵심 패턴: 이전 노드 출력 참조

`input_data`에는 이전 노드들의 출력이 누적됨. 주요 키:
- `input_data["llm_result"]` — LLM 노드 출력
- `input_data["raw_data"]` — Input 노드 출력
- config의 `text_field`, `body_field` 등으로 어떤 값을 전송할지 지정

```python
# 이전 노드 데이터 참조 헬퍼
def _extract_content(self, input_data: dict, field_key: str = "text_field") -> str:
    field = self.config.get(field_key, "llm_result")
    value = input_data.get(field, "")
    return str(value) if value else ""
```

---

## A-3. [🟡 High] rest_api.py — 재시도 로직 우회 수정

### 현재 버그 (`app/services/integrations/rest_api.py`)

```python
async def call(self, method, url, ..., token: str = "") -> dict:
    if token:
        return await self._request(method, url, token, ...)  # 재시도 O

    # ⚠️ 토큰 없는 공개 API → BaseIntegrationService._request() 미사용
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(...)  # 재시도 없음, 에러 래핑 없음
```

공개 API 호출 실패 시 재시도 없이 즉시 실패하며, 에러 메시지도 `FlowifyException`으로 래핑되지 않음.

### 수정 방향

`BaseIntegrationService._request()`가 빈 토큰(`""`)을 처리할 수 있도록 수정하거나,
토큰 없는 경우에도 같은 경로를 통해 재시도 로직이 동작하도록 변경:

```python
async def call(self, method, url, ..., token: str = "") -> dict:
    # token 유무와 관계없이 _request() 사용 (재시도 로직 통일)
    return await self._request(
        method, url, token,
        params=params, json=body, headers=headers, timeout=timeout
    )
```

`base.py`에서 빈 토큰 처리:
```python
# base.py _request() 내 헤더 설정 부분
if token:
    headers["Authorization"] = f"Bearer {token}"
# token이 없으면 Authorization 헤더 미포함 (공개 API)
```

---

## A-4. [🟠 Medium] NodeFactory — ValueError → FlowifyException 변경

### 현재 문제 (`app/core/nodes/factory.py:22`)

```python
if node_class is None:
    raise ValueError(f"Unknown node type: {node_type}")
    # ← ValueError는 executor에서 잡히지 않음 → 500 에러 + 스택 트레이스 노출
```

### 수정

```python
from app.common.errors import ErrorCode, FlowifyException

if node_class is None:
    raise FlowifyException(
        ErrorCode.INVALID_REQUEST,
        detail=f"알 수 없는 노드 타입입니다: {node_type}",
        context={"node_type": node_type},
    )
```

### NodeFactory 확장 (선택적)

Spring Boot가 보내는 `type` 값이 `"gmail_input"`, `"slack_output"` 형식이라면 서비스별 전략 클래스 분리 필요. Spring Boot 명세 (`FASTAPI_SPRINGBOOT_API_SPEC.md`) 확인 후 결정.

---

## A-5. [🟠 Medium] 테스트 작성

### `tests/test_input_node.py` (신규)

```python
from unittest.mock import AsyncMock, patch
import pytest
from app.core.nodes.input_node import InputNodeStrategy
from app.common.errors import FlowifyException

@pytest.mark.asyncio
async def test_manual_source():
    node = InputNodeStrategy({"source": "manual", "data": "hello"})
    result = await node.execute({})
    assert result["raw_data"] == "hello"

@pytest.mark.asyncio
async def test_gmail_source_calls_service():
    node = InputNodeStrategy({"source": "gmail", "query": "is:unread"})
    credentials = {"gmail": "fake_token"}
    with patch("app.core.nodes.input_node.GmailService") as MockGmail:
        mock_svc = MockGmail.return_value
        mock_svc.list_messages = AsyncMock(return_value=[{"id": "1"}])
        result = await node.execute({"credentials": credentials})
    assert result["source"] == "gmail"
    mock_svc.list_messages.assert_called_once()

@pytest.mark.asyncio
async def test_missing_token_raises():
    node = InputNodeStrategy({"source": "gmail"})
    with pytest.raises(FlowifyException) as exc_info:
        await node.execute({"credentials": {}})
    assert "gmail" in exc_info.value.detail

def test_validate_requires_source():
    assert InputNodeStrategy({}).validate() is False
    assert InputNodeStrategy({"source": "gmail"}).validate() is True
```

### `tests/test_output_node.py` (신규)

```python
from unittest.mock import AsyncMock, patch
import pytest
from app.core.nodes.output_node import OutputNodeStrategy

@pytest.mark.asyncio
async def test_console_target():
    node = OutputNodeStrategy({"target": "console"})
    result = await node.execute({"llm_result": "요약 결과"})
    assert result["delivered"] is True

@pytest.mark.asyncio
async def test_slack_target_calls_service():
    node = OutputNodeStrategy({"target": "slack", "channel": "#test"})
    credentials = {"slack": "fake_token"}
    with patch("app.core.nodes.output_node.SlackService") as MockSlack:
        mock_svc = MockSlack.return_value
        mock_svc.post_message = AsyncMock(return_value={"ok": True})
        result = await node.execute({"credentials": credentials, "llm_result": "내용"})
    mock_svc.post_message.assert_called_once()
    assert result["delivered"] is True
```

---

## 잠재적 오류 & 주의사항

### 1. credentials 키 구조 미확정 (가장 중요)

`executor.py:101`에서 `service_tokens`를 그대로 `credentials`로 전달함. Spring Boot가 보내는 형식 확인 필수.

- `FASTAPI_SPRINGBOOT_API_SPEC.md` 내 `service_tokens` 필드 확인
- 키가 `"gmail"`, `"slack"` 등 서비스명인지, `"google"` 등 플랫폼명인지 확인
- 확인 전까지는 두 케이스 모두 처리하는 fallback 로직 고려:
  ```python
  token = credentials.get(source) or credentials.get("google") or ""
  ```

### 2. GmailService 토큰 형식

`GmailService`는 OAuth access token을 기대함. Spring Boot가 복호화한 토큰을 그대로 전달하는지 확인.

### 3. GoogleDriveService.download_file() 바이너리 버그

`app/services/integrations/google_drive.py`의 `download_file()`에서 `alt=media`로 바이너리 파일 다운로드 시 `_request()`가 `.json()`으로 파싱을 시도해 실패할 수 있음. Input 노드에서 파일 다운로드가 필요하다면 이 메서드도 함께 수정 필요.

### 4. 서비스 인스턴스 생성 비용

매 `execute()` 호출마다 서비스 인스턴스를 새로 생성하면 httpx 클라이언트도 매번 생성됨. 성능이 문제가 되면 노드 클래스 수준에서 싱글톤 관리 고려.

### 5. Web Crawler 토큰 불필요

`WebCrawlerService.crawl()`은 토큰이 필요 없는 공개 크롤링이므로 credentials 없이 호출해야 함. 토큰 없을 때 에러 처리 분기에서 web_crawl은 제외.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [ ] `input_node.py` 서비스 연결 구현 (gmail, drive, sheets, web_crawl 우선)
- [ ] `output_node.py` 서비스 연결 구현 (slack, notion 우선)
- [ ] `factory.py` ValueError → FlowifyException 변경
- [ ] Spring Boot 담당자에게 `service_tokens` 키 구조 확인

**최종 제출 (6/17) 전:**
- [ ] `rest_api.py` 재시도 로직 수정
- [ ] `tests/test_input_node.py` 작성
- [ ] `tests/test_output_node.py` 작성
- [ ] Google Calendar, Google Drive input/output 연결 추가
