# ?묒뾽??A ???몃뱶 ?듯빀 & ?쒕퉬???곕룞

> ?묒꽦?? 2026-04-17 | **v2 ?낅뜲?댄듃: 2026-04-23** | 以묎컙 諛쒗몴: 2026-04-29 | 理쒖쥌 ?쒖텧: 2026-06-17

---

## v2 ?고???而⑦듃?숉듃 蹂寃??붿빟

> **?듭떖**: v2 ?댁쟾??`config["source"]` / `config["target"]` 湲곕컲 ?쇱슦?낆씠 **`runtime_source` / `runtime_sink` 湲곕컲**?쇰줈 ?꾨㈃ 援먯껜?섏뿀?듬땲?? ?꾨옒 ???쒖떆????ぉ? ?대? 援ы쁽 ?꾨즺?섏뿀?쇰ŉ, ?묒뾽??A???⑥? ??ぉ??吏묒쨷?섎㈃ ?⑸땲??

### ?щ씪吏??듭떖 ?ы빆

| ??ぉ | v1 (?댁쟾) | v2 (?꾩옱) |
|------|-----------|-----------|
| ?몃뱶 ?쒓렇?덉쿂 | `execute(input_data: dict)` | `execute(node, input_data, service_tokens)` |
| ?좏겙 ?묎렐 | `input_data["credentials"]` | `service_tokens` ?뚮씪誘명꽣 (蹂꾨룄 ?꾨떖) |
| ?낅젰 ?쇱슦??| `config["source"]` | `node["runtime_source"]["service"]` + `mode` |
| 異쒕젰 ?쇱슦??| `config["target"]` | `node["runtime_sink"]["service"]` + `config` |
| 諛섑솚媛??뺤떇 | ?꾩쓽 dict ?꾩쟻 | **Canonical Payload** (`type` ?꾨뱶 ?꾩닔) |
| ?⑺넗由?| `factory.create(type, config)` | `factory.create_from_node_def(node_def)` |
| validate ?쒓렇?덉쿂 | `validate() -> bool` | `validate(node: dict) -> bool` |

---

## ?대떦 ?뚯씪

| ?뚯씪 | ?곹깭 |
|------|------|
| `app/core/nodes/input_node.py` | ??**?꾨즺** ??runtime_source 湲곕컲 ?쇱슦??(4 ?쒕퉬?? 15 紐⑤뱶) |
| `app/core/nodes/output_node.py` | ??**?꾨즺** ??runtime_sink 湲곕컲 ?쇱슦??(6 ?쒕퉬?? |
| `app/core/nodes/factory.py` | ??**?꾨즺** ??FlowifyException + create_from_node_def |
| `app/services/integrations/rest_api.py` | ?맀 ?ъ떆??濡쒖쭅 ?고쉶 踰꾧렇 |
| `tests/test_input_node.py` | ???묒꽦 ?꾨즺 ??v2 source contract + attachment_email |
| `tests/test_output_node.py` | ???묒꽦 ?꾨즺 ??v2 sink contract + draft/update/Drive branches |

---

## ??A-1. [?꾨즺] InputNodeStrategy ???쒕퉬???곌껐

**v2 而⑦듃?숉듃濡??꾨㈃ ?ъ옉???꾨즺.** ?묒뾽??A?????뚯씪???섏젙???꾩슂 ?놁씠, ?숈옉???댄빐?섍퀬 ?뚯뒪?몃? ?묒꽦?섎㈃ ?⑸땲??

### ?꾩옱 援ы쁽 援ъ“ (`app/core/nodes/input_node.py`)

```python
async def execute(
    self,
    node: dict[str, Any],
    input_data: dict[str, Any] | None,
    service_tokens: dict[str, str],
) -> dict[str, Any]:
    runtime_source = node.get("runtime_source")
    service = runtime_source["service"]  # "google_drive", "gmail", "google_sheets", "slack"
    mode = runtime_source["mode"]        # "single_file", "new_email", "sheet_all" ??
    target = runtime_source.get("target", "")
    token = service_tokens.get(service, "")
```

### 吏???쒕퉬??& 紐⑤뱶 (Phase 1)

| ?쒕퉬??| 紐⑤뱶 | 諛섑솚 Canonical Type |
|--------|------|-------------------|
| `google_drive` | single_file, file_changed, new_file, folder_new_file | SINGLE_FILE |
| `google_drive` | folder_all_files | FILE_LIST |
| `gmail` | single_email, new_email, sender_email, starred_email | SINGLE_EMAIL |
| `gmail` | label_emails | EMAIL_LIST |
| `gmail` | attachment_email | FILE_LIST |
| `google_sheets` | sheet_all, new_row, row_updated | SPREADSHEET_DATA |
| `slack` | channel_messages | TEXT |

### ?좑툘 ?묒뾽??A 李멸퀬: 湲곗〈 臾몄꽌? ?щ씪吏???

- `credentials.get(source)` ??**?ъ슜?섏? ?딆쓬**. `service_tokens.get(service)`濡?吏곸젒 ?묎렐
- `config["source"]` ??**?ъ슜?섏? ?딆쓬**. `node["runtime_source"]`?먯꽌 `service`, `mode`, `target` 異붿텧
- 諛섑솚媛믪씠 `{**input_data, "source": ..., "raw_data": ...}` ?뺥깭媛 ?꾨땶 **Canonical Payload** (`{"type": "SINGLE_FILE", "filename": ..., "content": ...}`)

---

## ??A-2. [?꾨즺] OutputNodeStrategy ???쒕퉬???곌껐

**v2 而⑦듃?숉듃濡??꾨㈃ ?ъ옉???꾨즺.**

### ?꾩옱 援ы쁽 援ъ“ (`app/core/nodes/output_node.py`)

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

### 吏???쒕퉬??& ?낅젰 ????명솚

| ?쒕퉬??| ?덉슜 ?낅젰 ???| ?꾩닔 config |
|--------|-------------|------------|
| `slack` | TEXT | channel |
| `gmail` | TEXT, SINGLE_FILE, FILE_LIST | to, subject, action |
| `notion` | TEXT, SPREADSHEET_DATA, API_RESPONSE | target_type, target_id |
| `google_drive` | TEXT, SINGLE_FILE, FILE_LIST, SPREADSHEET_DATA | folder_id |
| `google_sheets` | TEXT, SPREADSHEET_DATA, API_RESPONSE | spreadsheet_id, write_mode |
| `google_calendar` | TEXT, SCHEDULE_DATA | calendar_id, event_title_template, action |

---

## A-3. [?윞 High] rest_api.py ???ъ떆??濡쒖쭅 ?고쉶 ?섏젙

### ?꾩옱 踰꾧렇 (`app/services/integrations/rest_api.py`)

```python
async def call(self, method, url, ..., token: str = "") -> dict:
    if token:
        return await self._request(method, url, token, ...)  # ?ъ떆??O

    # ?좑툘 ?좏겙 ?녿뒗 怨듦컻 API ??BaseIntegrationService._request() 誘몄궗??
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(...)  # ?ъ떆???놁쓬, ?먮윭 ?섑븨 ?놁쓬
```

### ?섏젙 諛⑺뼢

```python
async def call(self, method, url, ..., token: str = "") -> dict:
    # token ?좊Т? 愿怨꾩뾾??_request() ?ъ슜 (?ъ떆??濡쒖쭅 ?듭씪)
    return await self._request(
        method, url, token,
        params=params, json=body, headers=headers, timeout=timeout
    )
```

`base.py`?먯꽌 鍮??좏겙 泥섎━:
```python
if token:
    headers["Authorization"] = f"Bearer {token}"
```

---

## ??A-4. [?꾨즺] NodeFactory ??ValueError ??FlowifyException 蹂寃?

`factory.py`?먯꽌 `FlowifyException`?쇰줈 蹂寃??꾨즺. 異붽?濡?`create_from_node_def()` 硫붿꽌?쒓? 異붽???

---

## A-5. [?윝 Medium] ?뚯뒪???묒꽦

> **以묒슂**: v2 ?쒓렇?덉쿂 湲곗??쇰줈 ?묒꽦?댁빞 ?⑸땲?? 湲곗〈 臾몄꽌???뚯뒪??肄붾뱶??**?ъ슜 遺덇?** ???꾨옒 ?덉떆瑜?李멸퀬?섏꽭??

### `tests/test_input_node.py` (?좉퇋)

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

### `tests/test_output_node.py` (?좉퇋)

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

## ?좎옱???ㅻ쪟 & 二쇱쓽?ы빆

### 1. service_tokens ??援ъ“ (?뺤젙??

v2 而⑦듃?숉듃?먯꽌 `service_tokens`??**?쒕퉬????낆쓣 ??*濡??ъ슜:
```json
{
  "google_drive": "ya29.xxx",
  "gmail": "ya29.xxx",
  "slack": "xoxb-xxx",
  "notion": "ntn_xxx"
}
```
Spring Boot `WorkflowTranslator`媛 ?쒕퉬????낅퀎濡?蹂듯샇?뷀븯???꾨떖. ?ㅻ뒗 `runtime_source.service` / `runtime_sink.service` 媛믨낵 ?쇱튂.

### 2. GoogleDriveService.download_file() 諛붿씠?덈━ 踰꾧렇

`download_file()`?먯꽌 `alt=media`濡?諛붿씠?덈━ ?뚯씪 ?ㅼ슫濡쒕뱶 ??`_request()`媛 `.json()`?쇰줈 ?뚯떛???쒕룄???ㅽ뙣?????덉쓬. Input ?몃뱶?먯꽌 ?뚯씪 ?ㅼ슫濡쒕뱶媛 ?꾩슂?섎떎硫???硫붿꽌?쒕룄 ?④퍡 ?섏젙 ?꾩슂.

### 3. ?쒕퉬???몄뒪?댁뒪 ?앹꽦 鍮꾩슜

留?`execute()` ?몄텧留덈떎 ?쒕퉬???몄뒪?댁뒪瑜??덈줈 ?앹꽦?? ?깅뒫??臾몄젣媛 ?섎㈃ ?몃뱶 ?대옒???섏??먯꽌 ?깃???愿由?怨좊젮.

---

## ?묒뾽 泥댄겕由ъ뒪??

**以묎컙 諛쒗몴 (4/29) ??**
- [x] `input_node.py` ?쒕퉬???곌껐 援ы쁽 ??v2 ?꾨즺
- [x] `output_node.py` ?쒕퉬???곌껐 援ы쁽 ??v2 ?꾨즺
- [x] `factory.py` ValueError ??FlowifyException ??v2 ?꾨즺
- [x] Spring Boot `service_tokens` ??援ъ“ ?뺤씤 ??v2 而⑦듃?숉듃?먯꽌 ?뺤젙

**理쒖쥌 ?쒖텧 (6/17) ??**
- [x] `rest_api.py` retry path fixed before this Task A alignment.
- [x] `tests/test_input_node.py` covers v2 source contract, including Gmail attachment_email.
- [x] `tests/test_output_node.py` covers v2 sink contract, including draft/update/Drive branches.

**2026-04-25 Task A alignment update**
- [x] Gmail `attachment_email` returns FILE_LIST attachment metadata.
- [x] Gmail sink `action=draft` calls the Gmail draft API.
- [x] Google Calendar sink branches `action=create/update`.
- [x] Google Drive sink handles FILE_LIST uploads and SPREADSHEET_DATA CSV uploads.
