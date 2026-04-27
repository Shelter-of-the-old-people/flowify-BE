# FastAPI Canvas LMS Source 구현 가이드

> 작성일: 2026-04-28
> 발신: Spring Backend (flowify-BE-spring)
> 수신: FastAPI Team (flowify-BE)
> 목적: Canvas LMS를 InputNodeStrategy source로 추가하기 위해 FastAPI 팀이 수정/추가해야 할 내용을 정리한다.
> 선행 조건: `FASTAPI_CONTRACT_SPEC.md`, `FASTAPI_IMPLEMENTATION_GUIDE.md` 숙지

---

## 1. 변경 개요

Canvas LMS(금오공대 LMS 등)에서 강의자료를 가져와 Google Drive에 업로드하는 자동화를 지원한다.

**Spring Boot에서 완료된 작업:**
- `source_catalog.json`에 `canvas_lms` 서비스 추가 (3개 source mode)
- `CanvasLmsConnector` 구현 (직접 토큰 저장 방식, GitHub/Notion과 동일 패턴)
- `application.yml`에 `app.oauth.canvas-lms.api-url`, `token` 설정 추가
- `service_tokens`에 `"canvas_lms": "<Canvas API Token>"` 형태로 전달됨

**FastAPI에서 해야 할 작업:**
- `CanvasLmsSourceHandler` 구현
- `InputNodeStrategy.SOURCE_HANDLERS`에 등록
- Validation 코드에 `canvas_lms` 추가

---

## 2. Source Catalog 정의 (Spring 측 확정)

```json
{
  "key": "canvas_lms",
  "label": "Canvas LMS",
  "auth_required": true,
  "source_modes": [
    {
      "key": "course_files",
      "label": "특정 과목 강의자료 전체",
      "canonical_input_type": "FILE_LIST",
      "trigger_kind": "manual",
      "target_schema": { "type": "text_input", "placeholder": "과목 ID (예: 12345)" }
    },
    {
      "key": "course_new_file",
      "label": "과목에 새 자료가 올라올 때",
      "canonical_input_type": "SINGLE_FILE",
      "trigger_kind": "event",
      "target_schema": { "type": "text_input", "placeholder": "과목 ID (예: 12345)" }
    },
    {
      "key": "term_all_files",
      "label": "학기 전체 과목 자료",
      "canonical_input_type": "FILE_LIST",
      "trigger_kind": "manual",
      "target_schema": { "type": "text_input", "placeholder": "학기명 (예: 2026-1학기)" }
    }
  ]
}
```

---

## 3. Runtime Payload 예시

Spring이 FastAPI에 전달하는 실행 요청의 canvas_lms 노드 형태:

```json
{
  "id": "n1",
  "category": "service",
  "type": "canvas_lms",
  "label": "LMS 강의자료",
  "config": { "source_mode": "course_files", "target": "12345" },
  "dataType": null,
  "outputDataType": "FILE_LIST",
  "role": "start",
  "runtime_type": "input",
  "runtime_source": {
    "service": "canvas_lms",
    "mode": "course_files",
    "target": "12345",
    "canonical_input_type": "FILE_LIST"
  }
}
```

```json
"service_tokens": {
  "canvas_lms": "7236~AbCdEfGh...",
  "google_drive": "ya29.a0AfH6SMBx..."
}
```

- `service_tokens["canvas_lms"]`는 Canvas Personal Access Token (평문)
- `Authorization: Bearer {token}` 형태로 Canvas API에 사용

---

## 4. Canvas API 호출 가이드

### 4.1 인증

```
Authorization: Bearer {service_tokens["canvas_lms"]}
```

### 4.2 Base URL

환경변수 또는 하드코딩: `https://canvas.kumoh.ac.kr/api/v1`

> Canvas 인스턴스마다 URL이 다르다. 현재는 금오공대(`canvas.kumoh.ac.kr`) 고정.
> 향후 확장 시 runtime_source에 `api_url` 필드를 추가할 수 있다.

### 4.3 mode별 API 호출

#### `course_files` — 특정 과목 강의자료 전체

```
GET /api/v1/courses/{target}/files
Authorization: Bearer {token}
```

- `target` = 과목 ID (예: `12345`)
- 응답: 파일 객체 배열

```json
// Canvas API 응답 예시
[
  {
    "id": 67890,
    "display_name": "Week01_Introduction.pdf",
    "filename": "Week01_Introduction.pdf",
    "url": "https://canvas.kumoh.ac.kr/files/67890/download?...",
    "content-type": "application/pdf",
    "size": 1048576,
    "created_at": "2026-03-02T09:00:00Z",
    "updated_at": "2026-03-02T09:00:00Z"
  }
]
```

**페이지네이션:** Canvas는 `Link` 헤더로 다음 페이지를 알려준다. `per_page=100` 파라미터 사용 권장.

```
GET /api/v1/courses/{target}/files?per_page=100
Link: <https://canvas.kumoh.ac.kr/api/v1/courses/12345/files?page=2&per_page=100>; rel="next"
```

→ `rel="next"` 링크가 없을 때까지 반복 요청.

**Canonical Payload 변환 (FILE_LIST):**

```json
{
  "type": "FILE_LIST",
  "items": [
    {
      "filename": "Week01_Introduction.pdf",
      "mime_type": "application/pdf",
      "size": 1048576,
      "url": "https://canvas.kumoh.ac.kr/files/67890/download?..."
    }
  ]
}
```

#### `course_new_file` — 과목에 새 자료가 올라올 때

```
GET /api/v1/courses/{target}/files?sort=created_at&order=desc&per_page=1
Authorization: Bearer {token}
```

- 가장 최근 업로드된 파일 1개 반환
- event trigger 기반: 주기적 폴링 또는 webhook 연동으로 변경 감지

**Canonical Payload 변환 (SINGLE_FILE):**

```json
{
  "type": "SINGLE_FILE",
  "filename": "Week05_Midterm_Review.pdf",
  "content": null,
  "mime_type": "application/pdf",
  "url": "https://canvas.kumoh.ac.kr/files/67891/download?..."
}
```

> `content` 필드: 파일 크기가 작으면 (< 10MB) base64 인코딩하여 포함할 수 있고,
> 크면 `url`만 전달하고 OutputNodeStrategy(google_drive sink)에서 스트리밍 다운로드 → 업로드 처리.

#### `term_all_files` — 학기 전체 과목 자료

이 mode는 2단계 API 호출이 필요하다:

**Step 1: 사용자 수강 과목 목록 조회**

```
GET /api/v1/courses?enrollment_state=active&include[]=term&per_page=100
Authorization: Bearer {token}
```

응답에서 `target` 값(학기명)과 `term.name` 을 매칭:

```python
# target = "2026-1학기"
matching_courses = [
    c for c in courses
    if c.get("term", {}).get("name") == target
]
```

**Step 2: 각 과목의 파일 조회**

```python
all_files = []
for course in matching_courses:
    files = fetch_course_files(course["id"], token)
    for f in files:
        all_files.append({
            "filename": f"{course['name']}/{f['display_name']}",
            "mime_type": f.get("content-type", "application/octet-stream"),
            "size": f.get("size", 0),
            "url": f["url"]
        })
```

**Canonical Payload 변환 (FILE_LIST):**

```json
{
  "type": "FILE_LIST",
  "items": [
    {
      "filename": "소프트웨어공학/Week01_Intro.pdf",
      "mime_type": "application/pdf",
      "size": 1048576,
      "url": "https://canvas.kumoh.ac.kr/files/67890/download?..."
    },
    {
      "filename": "데이터베이스/ER_Diagram.png",
      "mime_type": "image/png",
      "size": 204800,
      "url": "https://canvas.kumoh.ac.kr/files/67892/download?..."
    }
  ]
}
```

> `filename`에 `과목명/파일명` 형태로 경로를 포함하면,
> google_drive sink에서 폴더 구조를 자동으로 생성할 수 있다.

---

## 5. 파일 다운로드 처리

Canvas의 `url` 필드는 **인증이 필요한 다운로드 URL**이다.

```python
import httpx

async def download_canvas_file(url: str, token: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=True  # Canvas는 S3 등으로 리다이렉트할 수 있음
        )
        response.raise_for_status()
        return response.content
```

**Google Drive에 업로드할 때:**
- 파일 크기가 작으면 (`< 5MB`): canonical payload의 `content`에 base64로 포함
- 파일 크기가 크면: `url`만 전달하고, `GoogleDriveSinkHandler`에서 스트리밍 처리

```python
# GoogleDriveSinkHandler에서 FILE_LIST 처리 시
for item in input_data["items"]:
    if item.get("content"):
        # base64 디코딩 후 업로드
        file_bytes = base64.b64decode(item["content"])
    elif item.get("url"):
        # URL에서 스트리밍 다운로드 (canvas_lms 토큰 필요)
        file_bytes = await download_from_url(item["url"], service_tokens)
```

> **중요:** `url`로 다운로드할 때 Canvas 토큰이 필요하다.
> `service_tokens`에 `canvas_lms` 토큰이 있으므로 이를 사용한다.
> Google Drive sink에서 Canvas URL을 다운로드해야 하는 상황이므로,
> OutputNodeStrategy에 `service_tokens` 전체를 전달하는 기존 구조를 활용한다.

---

## 6. 수정해야 할 코드 위치

### 6.1 CanvasLmsSourceHandler 생성 (신규)

```python
# 예상 위치: app/strategies/sources/canvas_lms_handler.py

class CanvasLmsSourceHandler:
    CANVAS_API_BASE = "https://canvas.kumoh.ac.kr/api/v1"

    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    async def fetch(self, mode: str, target: str) -> dict:
        match mode:
            case "course_files":
                return await self._fetch_course_files(target)
            case "course_new_file":
                return await self._fetch_course_new_file(target)
            case "term_all_files":
                return await self._fetch_term_all_files(target)
            case _:
                raise UnsupportedRuntimeSourceError("canvas_lms", mode)

    async def _fetch_course_files(self, course_id: str) -> dict:
        """과목의 전체 파일을 FILE_LIST로 반환"""
        files = await self._paginated_get(f"/courses/{course_id}/files")
        items = [
            {
                "filename": self._safe_filename(f["display_name"]),
                "mime_type": f.get("content-type", "application/octet-stream"),
                "size": f.get("size", 0),
                "url": f["url"]
            }
            for f in files
        ]
        return {"type": "FILE_LIST", "items": items}

    async def _fetch_course_new_file(self, course_id: str) -> dict:
        """과목의 최신 파일 1개를 SINGLE_FILE로 반환"""
        url = f"{self.CANVAS_API_BASE}/courses/{course_id}/files"
        params = {"sort": "created_at", "order": "desc", "per_page": 1}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            files = resp.json()

        if not files:
            raise NodeExecutionError("canvas_lms", "No files found in course")

        f = files[0]
        return {
            "type": "SINGLE_FILE",
            "filename": self._safe_filename(f["display_name"]),
            "content": None,
            "mime_type": f.get("content-type", "application/octet-stream"),
            "url": f["url"]
        }

    async def _fetch_term_all_files(self, term_name: str) -> dict:
        """학기 전체 과목의 파일을 FILE_LIST로 반환"""
        # Step 1: 수강 과목 조회
        courses = await self._paginated_get("/courses", params={
            "enrollment_state": "active",
            "include[]": "term"
        })

        # Step 2: 학기명으로 필터링
        matching = [
            c for c in courses
            if c.get("term", {}).get("name") == term_name and c.get("name")
        ]

        if not matching:
            raise NodeExecutionError("canvas_lms", f"No courses found for term: {term_name}")

        # Step 3: 각 과목 파일 수집
        all_items = []
        for course in matching:
            try:
                files = await self._paginated_get(f"/courses/{course['id']}/files")
                for f in files:
                    all_items.append({
                        "filename": f"{course['name']}/{self._safe_filename(f['display_name'])}",
                        "mime_type": f.get("content-type", "application/octet-stream"),
                        "size": f.get("size", 0),
                        "url": f["url"]
                    })
            except Exception as e:
                # 과목 접근 권한 없는 경우 등 — 건너뛰고 계속 진행
                logger.warning(f"Failed to fetch files for course {course['name']}: {e}")
                continue

        return {"type": "FILE_LIST", "items": all_items}

    async def _paginated_get(self, path: str, params: dict = None) -> list:
        """Canvas API 페이지네이션 처리"""
        results = []
        url = f"{self.CANVAS_API_BASE}{path}"
        p = {"per_page": 100, **(params or {})}

        async with httpx.AsyncClient() as client:
            while url:
                resp = await client.get(url, headers=self.headers, params=p)
                resp.raise_for_status()
                results.extend(resp.json())

                # Link 헤더에서 next URL 파싱
                link_header = resp.headers.get("link", "")
                url = self._parse_next_link(link_header)
                p = None  # 이후 페이지는 URL에 파라미터 포함됨

        return results

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        """Link 헤더에서 rel='next' URL을 추출"""
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    @staticmethod
    def _safe_filename(name: str) -> str:
        """파일명에서 특수문자 제거"""
        return "".join(c for c in name if c not in '<>:"/\\|?*').strip()
```

### 6.2 InputNodeStrategy에 등록

```python
# 기존 SOURCE_HANDLERS에 추가
SOURCE_HANDLERS = {
    "google_drive": GoogleDriveSourceHandler,
    "gmail": GmailSourceHandler,
    "google_sheets": GoogleSheetsSourceHandler,
    "slack": SlackSourceHandler,
    "canvas_lms": CanvasLmsSourceHandler,  # 추가
}
```

### 6.3 Validation 코드에 추가

```python
# validate_input_node() 의 SUPPORTED_SOURCES에 추가
SUPPORTED_SOURCES = {
    "google_drive": {"single_file", "file_changed", "new_file", "folder_new_file", "folder_all_files"},
    "gmail": {"single_email", "new_email", "sender_email", "starred_email", "label_emails", "attachment_email"},
    "google_sheets": {"sheet_all", "new_row", "row_updated"},
    "slack": {"channel_messages"},
    "canvas_lms": {"course_files", "course_new_file", "term_all_files"},  # 추가
}
```

### 6.4 Capability API 업데이트 (선택)

```json
{
  "supported_sources": {
    "canvas_lms": ["course_files", "course_new_file", "term_all_files"]
  }
}
```

---

## 7. LMS → Google Drive 전체 워크플로우 예시

### 7.1 워크플로우 구조

```
[Canvas LMS]          [Google Drive]         [Gmail]
 course_files    →     파일 업로드      →     결과 이메일
 (input/source)        (output/sink)          (output/sink)
```

### 7.2 실행 요청 전체 Payload

```json
{
  "workflow": {
    "id": "wf_lms_backup",
    "name": "LMS 강의자료 → Google Drive 백업",
    "userId": "user-abc",
    "nodes": [
      {
        "id": "n1",
        "category": "service",
        "type": "canvas_lms",
        "label": "LMS 강의자료",
        "config": { "source_mode": "course_files", "target": "12345" },
        "dataType": null,
        "outputDataType": "FILE_LIST",
        "role": "start",
        "runtime_type": "input",
        "runtime_source": {
          "service": "canvas_lms",
          "mode": "course_files",
          "target": "12345",
          "canonical_input_type": "FILE_LIST"
        }
      },
      {
        "id": "n2",
        "category": "service",
        "type": "google_drive",
        "label": "Google Drive 업로드",
        "config": { "folder_id": "1AbCdEfGh_folder_id", "file_format": "original" },
        "dataType": "FILE_LIST",
        "outputDataType": null,
        "role": "end",
        "runtime_type": "output",
        "runtime_sink": {
          "service": "google_drive",
          "config": {
            "folder_id": "1AbCdEfGh_folder_id",
            "file_format": "original"
          }
        }
      }
    ],
    "edges": [
      { "id": "e1", "source": "n1", "target": "n2" }
    ],
    "trigger": { "type": "manual", "config": {} }
  },
  "service_tokens": {
    "canvas_lms": "7236~AbCdEfGhIjKlMnOpQrStUvWxYz...",
    "google_drive": "ya29.a0AfH6SMBx..."
  }
}
```

### 7.3 실행 흐름

```
Step 1: InputNodeStrategy (canvas_lms)
  → GET /api/v1/courses/12345/files (Canvas API)
  → FILE_LIST canonical payload 생성
  → { "type": "FILE_LIST", "items": [{ "filename": "Week01.pdf", "url": "..." }, ...] }

Step 2: OutputNodeStrategy (google_drive)
  → FILE_LIST의 각 item에 대해:
     1. item.url에서 파일 다운로드 (Canvas 토큰 사용)
     2. Google Drive에 업로드 (Drive 토큰 사용)
     3. folder_id에 저장

Step 3: 실행 완료
  → MongoDB에 state="completed" 기록
  → Spring 콜백: POST /api/internal/executions/{execId}/complete
```

---

## 8. Google Drive Sink의 URL 기반 파일 다운로드 처리

기존 `GoogleDriveSinkHandler`는 `content` (base64) 기반 업로드만 고려되어 있을 수 있다.
Canvas LMS에서 온 FILE_LIST는 `url`만 있고 `content`는 null이다.

**추가 필요 로직:**

```python
class GoogleDriveSinkHandler:

    async def send(self, config: dict, input_data: dict, service_tokens: dict) -> dict:
        folder_id = config["folder_id"]
        drive_token = self.token

        if input_data["type"] == "FILE_LIST":
            results = []
            for item in input_data["items"]:
                file_bytes = await self._get_file_content(item, service_tokens)
                uploaded = await self._upload_to_drive(
                    file_bytes, item["filename"], item.get("mime_type"), folder_id, drive_token
                )
                results.append(uploaded)
            return {"status": "sent", "uploaded_count": len(results)}

    async def _get_file_content(self, item: dict, service_tokens: dict) -> bytes:
        """content가 있으면 base64 디코딩, 없으면 url에서 다운로드"""
        if item.get("content"):
            return base64.b64decode(item["content"])

        if item.get("url"):
            # URL에서 다운로드 — 어떤 서비스의 URL인지에 따라 토큰이 다를 수 있음
            # Canvas URL이면 canvas_lms 토큰 사용
            token = self._resolve_download_token(item["url"], service_tokens)
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    item["url"],
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                    follow_redirects=True
                )
                resp.raise_for_status()
                return resp.content

        raise ValueError(f"File item has no content or url: {item['filename']}")

    def _resolve_download_token(self, url: str, service_tokens: dict) -> str | None:
        """URL의 도메인으로 어떤 서비스 토큰을 사용할지 결정"""
        if "canvas" in url:
            return service_tokens.get("canvas_lms")
        if "googleapis.com" in url:
            return service_tokens.get("google_drive")
        return None
```

---

## 9. 에러 처리

| 상황 | error_code | HTTP | 설명 |
|------|-----------|------|------|
| Canvas API 401 | `TOKEN_EXPIRED` | 401 | Canvas 토큰이 만료 또는 유효하지 않음 |
| Canvas API 403 | `EXTERNAL_SERVICE_ERROR` | 502 | 과목 접근 권한 없음 |
| Canvas API 404 | `EXTERNAL_SERVICE_ERROR` | 502 | 과목 ID가 존재하지 않음 |
| 파일 다운로드 실패 | `NODE_EXECUTION_FAILED` | 500 | Canvas 파일 URL 다운로드 실패 |
| 학기 매칭 실패 | `NODE_EXECUTION_FAILED` | 500 | 지정 학기에 해당하는 과목 없음 |

```python
# Canvas API 에러 처리 예시
async def _handle_canvas_error(self, response: httpx.Response, context: str):
    if response.status_code == 401:
        raise TokenExpiredError("canvas_lms", "Canvas API token is invalid or expired")
    if response.status_code == 403:
        raise ExternalServiceError("canvas_lms", f"Access denied: {context}")
    if response.status_code == 404:
        raise ExternalServiceError("canvas_lms", f"Not found: {context}")
    response.raise_for_status()
```

---

## 10. 테스트 체크리스트

### 단위 테스트

| # | 테스트 | 검증 항목 |
|---|--------|----------|
| 1 | `canvas_lms` + `course_files` | FILE_LIST 반환, items[*].filename/url 존재 |
| 2 | `canvas_lms` + `course_new_file` | SINGLE_FILE 반환, filename/url 존재 |
| 3 | `canvas_lms` + `term_all_files` | FILE_LIST 반환, filename에 `과목명/파일명` 형태 포함 |
| 4 | 존재하지 않는 과목 ID | `EXTERNAL_SERVICE_ERROR` 에러 |
| 5 | 잘못된 Canvas 토큰 | `TOKEN_EXPIRED` 에러 |
| 6 | 페이지네이션 | 파일 100개 이상 과목에서 전체 수집 확인 |

### E2E 테스트

```
[Canvas LMS: course_files] → [Google Drive: 업로드]

1. Spring POST /api/workflows/{id}/execute
2. FastAPI가 Canvas API에서 파일 목록 조회
3. FILE_LIST canonical payload 생성
4. Google Drive sink에서 각 파일 URL 다운로드 → 업로드
5. MongoDB state="completed", nodeLogs 기록 확인
```

---

## 11. 변경 파일 요약

| 작업 | 파일 (예상 경로) | 변경 내용 |
|------|----------------|----------|
| **신규** | `app/strategies/sources/canvas_lms_handler.py` | CanvasLmsSourceHandler 클래스 |
| 수정 | `app/strategies/input_node_strategy.py` | SOURCE_HANDLERS에 `"canvas_lms"` 추가 |
| 수정 | `app/validation/` | SUPPORTED_SOURCES에 `"canvas_lms"` 3개 mode 추가 |
| 수정 | `app/strategies/outputs/google_drive_handler.py` | URL 기반 파일 다운로드 로직 추가 (`_get_file_content`) |
| 수정 (선택) | `app/api/capabilities.py` | supported_sources에 canvas_lms 추가 |

---

## 12. 주의사항

1. **Canvas API Rate Limit**: Canvas는 분당 약 700 요청 제한. `term_all_files`에서 과목이 많을 경우 주의.
2. **파일 크기**: 대용량 파일(수백 MB)은 메모리 부족 가능. 스트리밍 다운로드/업로드 권장.
3. **파일 URL 유효기간**: Canvas의 `url` 필드는 일시적(temporary) URL일 수 있음. 받자마자 즉시 다운로드해야 한다.
4. **Canvas 인스턴스 URL**: 현재 `canvas.kumoh.ac.kr` 하드코딩. 타 대학 지원 시 설정으로 분리 필요.
5. **인코딩**: 한글 파일명이 포함될 수 있으므로 `_safe_filename()`에서 한글은 유지하되 특수문자만 제거.
