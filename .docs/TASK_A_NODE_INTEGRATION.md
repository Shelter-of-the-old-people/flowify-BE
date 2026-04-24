# 작업자 A — 노드 통합 & 서비스 연동

> 작성일: 2026-04-17 | **v2 업데이트: 2026-04-23** | 중간 발표: 2026-04-29 | 최종 제출: 2026-06-17

---

## v2 런타임 컨트랙트 변경 요약

> **핵심**: v2 이전의 `config["source"]` / `config["target"]` 기반 라우팅이 **`runtime_source` / `runtime_sink` 기반**으로 전면 교체되었습니다. 아래 ✅ 표시된 항목은 이미 구현 완료되었으며, 작업자 A는 남은 항목에 집중하면 됩니다.

### 달라진 핵심 사항

| 항목 | v1 (이전) | v2 (현재) |
|------|-----------|-----------|
| 노드 시그니처 | `execute(input_data: dict)` | `execute(node, input_data, service_tokens)` |
| 토큰 접근 | `input_data["credentials"]` | `service_tokens` 파라미터 (별도 전달) |
| 입력 라우팅 | `config["source"]` | `node["runtime_source"]["service"]` + `mode` |
| 출력 라우팅 | `config["target"]` | `node["runtime_sink"]["service"]` + `config` |
| 반환값 형식 | 임의 dict 누적 | **Canonical Payload** (`type` 필드 필수) |
| 팩토리 | `factory.create(type, config)` | `factory.create_from_node_def(node_def)` |
| validate 시그니처 | `validate() -> bool` | `validate(node: dict) -> bool` |

---

## 담당 파일

| 파일 | 상태 |
|------|------|
| `app/core/nodes/input_node.py` | ✅ **완료** — runtime_source 기반 라우팅 (4 서비스, 15 모드) |
| `app/core/nodes/output_node.py` | ✅ **완료** — runtime_sink 기반 라우팅 (6 서비스) |
| `app/core/nodes/factory.py` | ✅ **완료** — FlowifyException + create_from_node_def |
| `app/services/integrations/rest_api.py` | 🐛 재시도 로직 우회 버그 |
| `tests/test_input_node.py` | ❌ 없음 — 신규 작성 (v2 시그니처 기준) |
| `tests/test_output_node.py` | ❌ 없음 — 신규 작성 (v2 시그니처 기준) |

---

## ✅ A-1. [완료] InputNodeStrategy — 서비스 연결

**v2 컨트랙트로 전면 재작성 완료.** 작업자 A는 이 파일을 수정할 필요 없이, 동작을 이해하고 테스트를 작성하면 됩니다.

### 현재 구현 구조 (`app/core/nodes/input_node.py`)

```python
async def execute(
    self,
    node: dict[str, Any],
    input_data: dict[str, Any] | None,
    service_tokens: dict[str, str],
) -> dict[str, Any]:
    runtime_source = node.get("runtime_source")
    service = runtime_source["service"]  # "google_drive", "gmail", "google_sheets", "slack"
    mode = runtime_source["mode"]        # "single_file", "new_email", "sheet_all" 등
    target = runtime_source.get("target", "")
    token = service_tokens.get(service, "")
```

### 지원 서비스 & 모드 (Phase 1)

| 서비스 | 모드 | 반환 Canonical Type |
|--------|------|-------------------|
| `google_drive` | single_file, file_changed, new_file, folder_new_file | SINGLE_FILE |
| `google_drive` | folder_all_files | FILE_LIST |
| `gmail` | single_email, new_email, sender_email, starred_email | SINGLE_EMAIL |
| `gmail` | label_emails | EMAIL_LIST |
| `gmail` | attachment_email | FILE_LIST |
| `google_sheets` | sheet_all, new_row, row_updated | SPREADSHEET_DATA |
| `slack` | channel_messages | TEXT |

### ⚠️ 작업자 A 참고: 기존 문서와 달라진 점

- `credentials.get(source)` → **사용하지 않음**. `service_tokens.get(service)`로 직접 접근
- `config["source"]` → **사용하지 않음**. `node["runtime_source"]`에서 `service`, `mode`, `target` 추출
- 반환값이 `{**input_data, "source": ..., "raw_data": ...}` 형태가 아닌 **Canonical Payload** (`{"type": "SINGLE_FILE", "filename": ..., "content": ...}`)

---

## ✅ A-2. [완료] OutputNodeStrategy — 서비스 연결

**v2 컨트랙트로 전면 재작성 완료.**

### 현재 구현 구조 (`app/core/nodes/output_node.py`)

```python
async def execute(
    self,
    node: dict[str, Any],
    input_data: dict[str, Any] | None,
    service_tokens: dict[str, str],
) -> dict[str, Any]:
    runtime_sink = node.get("runtime_sink")
    service = runtime_sink["service"]      # "slack", "gmail", "notion", ...
    sink_config = runtime_sink.get("config", {})
    token = service_tokens.get(service, "")
```

### 지원 서비스 & 입력 타입 호환

| 서비스 | 허용 입력 타입 | 필수 config |
|--------|-------------|------------|
| `slack` | TEXT | channel |
| `gmail` | TEXT, SINGLE_FILE, FILE_LIST | to, subject, action |
| `notion` | TEXT, SPREADSHEET_DATA, API_RESPONSE | target_type, target_id |
| `google_drive` | TEXT, SINGLE_FILE, FILE_LIST, SPREADSHEET_DATA | folder_id |
| `google_sheets` | TEXT, SPREADSHEET_DATA, API_RESPONSE | spreadsheet_id, write_mode |
| `google_calendar` | TEXT, SCHEDULE_DATA | calendar_id, event_title_template, action |

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

### 수정 방향

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
if token:
    headers["Authorization"] = f"Bearer {token}"
```

---

## ✅ A-4. [완료] NodeFactory — ValueError → FlowifyException 변경

`factory.py`에서 `FlowifyException`으로 변경 완료. 추가로 `create_from_node_def()` 메서드가 추가됨.

---

## A-5. [🟠 Medium] 테스트 작성

> **중요**: v2 시그니처 기준으로 작성해야 합니다. 기존 문서의 테스트 코드는 **사용 불가** — 아래 예시를 참고하세요.

### `tests/test_input_node.py` (신규)

```python
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from app.core.nodes.input_node import InputNodeStrategy
from app.common.errors import FlowifyException


@pytest.mark.asyncio
async def test_google_drive_single_file():
    node = InputNodeStrategy({})
    node_dict = {
        "runtime_source": {
            "service": "google_drive",
            "mode": "single_file",
            "target": "file_123",
            "canonical_input_type": "SINGLE_FILE",
        }
    }
    service_tokens = {"google_drive": "fake_token"}
    with patch("app.core.nodes.input_node.GoogleDriveService") as MockDrive:
        mock_svc = MockDrive.return_value
        mock_svc.download_file = AsyncMock(return_value={
            "name": "test.txt", "content": "hello", "mimeType": "text/plain"
        })
        result = await node.execute(node_dict, None, service_tokens)
    assert result["type"] == "SINGLE_FILE"
    assert result["filename"] == "test.txt"


@pytest.mark.asyncio
async def test_gmail_new_email():
    node = InputNodeStrategy({})
    node_dict = {
        "runtime_source": {
            "service": "gmail",
            "mode": "new_email",
            "target": "",
            "canonical_input_type": "SINGLE_EMAIL",
        }
    }
    service_tokens = {"gmail": "fake_token"}
    with patch("app.core.nodes.input_node.GmailService") as MockGmail:
        mock_svc = MockGmail.return_value
        mock_svc.list_messages = AsyncMock(return_value=[{
            "subject": "Test", "from": "a@b.com", "date": "2026-01-01", "body": "Hello"
        }])
        result = await node.execute(node_dict, None, service_tokens)
    assert result["type"] == "SINGLE_EMAIL"
    assert result["subject"] == "Test"


@pytest.mark.asyncio
async def test_missing_token_raises():
    node = InputNodeStrategy({})
    node_dict = {
        "runtime_source": {"service": "gmail", "mode": "new_email", "target": ""}
    }
    with pytest.raises(FlowifyException):
        await node.execute(node_dict, None, {})


def test_validate():
    node = InputNodeStrategy({})
    assert node.validate({"runtime_source": {"service": "gmail", "mode": "new_email"}}) is True
    assert node.validate({"runtime_source": {"service": "unknown", "mode": "x"}}) is False
    assert node.validate({}) is False
```

### `tests/test_output_node.py` (신규)

```python
from unittest.mock import AsyncMock, patch
import pytest
from app.core.nodes.output_node import OutputNodeStrategy
from app.common.errors import FlowifyException


@pytest.mark.asyncio
async def test_slack_send():
    node = OutputNodeStrategy({})
    node_dict = {
        "runtime_sink": {"service": "slack", "config": {"channel": "#test"}}
    }
    service_tokens = {"slack": "fake_token"}
    input_data = {"type": "TEXT", "content": "Hello Slack"}
    with patch("app.core.nodes.output_node.SlackService") as MockSlack:
        mock_svc = MockSlack.return_value
        mock_svc.send_message = AsyncMock(return_value={"ok": True})
        result = await node.execute(node_dict, input_data, service_tokens)
    assert result["status"] == "sent"
    assert result["service"] == "slack"


@pytest.mark.asyncio
async def test_unsupported_sink_raises():
    node = OutputNodeStrategy({})
    node_dict = {
        "runtime_sink": {"service": "unknown_service", "config": {}}
    }
    with pytest.raises(FlowifyException):
        await node.execute(node_dict, {"type": "TEXT", "content": ""}, {"unknown_service": "t"})


@pytest.mark.asyncio
async def test_incompatible_input_type_raises():
    node = OutputNodeStrategy({})
    node_dict = {
        "runtime_sink": {"service": "slack", "config": {"channel": "#test"}}
    }
    service_tokens = {"slack": "fake_token"}
    input_data = {"type": "SPREADSHEET_DATA", "headers": [], "rows": []}
    with pytest.raises(FlowifyException):
        await node.execute(node_dict, input_data, service_tokens)


def test_validate():
    node = OutputNodeStrategy({})
    assert node.validate({
        "runtime_sink": {"service": "slack", "config": {"channel": "#test"}}
    }) is True
    assert node.validate({
        "runtime_sink": {"service": "slack", "config": {}}
    }) is False
    assert node.validate({}) is False
```

---

## 잠재적 오류 & 주의사항

### 1. service_tokens 키 구조 (확정됨)

v2 컨트랙트에서 `service_tokens`는 **서비스 타입을 키**로 사용:
```json
{
  "google_drive": "ya29.xxx",
  "gmail": "ya29.xxx",
  "slack": "xoxb-xxx",
  "notion": "ntn_xxx"
}
```
Spring Boot `WorkflowTranslator`가 서비스 타입별로 복호화하여 전달. 키는 `runtime_source.service` / `runtime_sink.service` 값과 일치.

### 2. GoogleDriveService.download_file() 바이너리 버그

`download_file()`에서 `alt=media`로 바이너리 파일 다운로드 시 `_request()`가 `.json()`으로 파싱을 시도해 실패할 수 있음. Input 노드에서 파일 다운로드가 필요하다면 이 메서드도 함께 수정 필요.

### 3. 서비스 인스턴스 생성 비용

매 `execute()` 호출마다 서비스 인스턴스를 새로 생성함. 성능이 문제가 되면 노드 클래스 수준에서 싱글톤 관리 고려.

---

## 작업 체크리스트

**중간 발표 (4/29) 전:**
- [x] `input_node.py` 서비스 연결 구현 ✅ v2 완료
- [x] `output_node.py` 서비스 연결 구현 ✅ v2 완료
- [x] `factory.py` ValueError → FlowifyException ✅ v2 완료
- [x] Spring Boot `service_tokens` 키 구조 확인 ✅ v2 컨트랙트에서 확정

**최종 제출 (6/17) 전:**
- [x] `rest_api.py` 재시도 로직 수정 ✅ 이전 커밋에서 완료 확인
- [x] `tests/test_input_node.py` 작성 (v2 시그니처 기준) ✅ 11개 테스트 통과
- [x] `tests/test_output_node.py` 작성 (v2 시그니처 기준) ✅ 9개 테스트 통과
