# 문서 본문 런타임 요구사항 분석 및 구현 계획

> 작성일: 2026-05-14  
> 기준 문서: `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`  
> 대상 범위: FastAPI 런타임, Spring runtime contract, FE preview 표시 계약  
> 핵심 시나리오: Google Drive/Gmail 파일 입력 -> LLM 요약/분석 -> Slack/Gmail/Sheets/Drive 후속 자동화

---

## 1. 결론 요약

현재 Flowify FastAPI 런타임은 Google Drive 파일을 canonical payload로 전달하고, LLM 노드에서 Google Drive 단일 파일 본문을 lazy extraction으로 읽는 일부 경로를 이미 갖고 있다.

그러나 요구사항 문서의 완료 기준을 만족하기에는 아래 간극이 남아 있다.

1. `SINGLE_FILE` 본문 상태 계약이 표준화되어 있지 않다.
   - 현재: `extracted_text`, `extraction_status=success|truncated|unsupported|failed|not_requested`
   - 요구: `content`, `content_status=available|empty|unsupported|too_large|failed|not_requested`, `content_error`, `content_metadata`
2. Google Drive extractor 지원 범위가 좁다.
   - 현재: Google Docs/Sheets/Slides export, text mime, PDF text layer 중심
   - 요구: PDF, CSV/TSV, PPTX, HWPX, DOCX, TXT/MD, Google Workspace 필수 지원 및 이미지/legacy 문서 명확한 미지원 처리
3. `FILE_LIST` preview와 실행에서 item content 정책이 아직 metadata 중심이다.
   - loop는 item 필드를 보존하지만, list 단계에서 content 표준 필드가 없으면 LLM은 lazy extraction 조건에 의존한다.
4. LLM 노드는 `SINGLE_FILE.content`와 Google Drive lazy extraction을 지원하지만, `FILE_LIST.items[].content`는 현재 포맷에 포함하지 않는다.
5. Gmail 첨부파일은 metadata만 전달되며 attachment content download/extraction 계약은 없다.
6. preview는 `include_content`를 지원하지만 source node preview 중심이고, content-dependent AI preview 자동 판별은 아직 없다.

따라서 1차 구현 목표는 "문서 본문 canonical contract 정규화 + Google Drive 필수 파일군 extractor + LLM/Loop/Preview 경로 보존"으로 잡는 것이 안전하다. Gmail 첨부 본문 읽기는 별도 2차 범위 또는 명시적 미지원 상태로 두는 것을 권장한다.

---

## 2. 현재 코드 기준 관찰

### 2.1 Workflow 모델

`app/models/workflow.py`는 Spring이 전달하는 `runtime_source`, `runtime_config`, `runtime_action`을 수용한다.

`RuntimeConfig`는 `extra="allow"`이므로 Spring이 `requires_content` 같은 신규 필드를 추가해도 FastAPI 모델에서 버려지지 않는다.

```json
{
  "runtime_config": {
    "node_type": "llm",
    "action": "summarize",
    "output_data_type": "TEXT",
    "requires_content": true
  }
}
```

즉 모델 계층은 확장 가능하고, 병목은 실행 전략과 payload shape에 있다.

### 2.1.1 Canonical 모델

`app/models/canonical.py`에는 `SingleFilePayload`, `FileItem`, `FileListPayload`, `EmailAttachment` 모델이 있지만 현재 파일 본문 상태 필드는 없다.

현재 모델:

- `SingleFilePayload`: `filename`, `content`, `mime_type`, `url`
- `FileItem`: `filename`, `mime_type`, `size`, `url`
- `EmailAttachment`: `filename`, `mime_type`, `size`

실제 런타임 코드는 대부분 dict payload를 직접 만들고 있어 당장 모델 validation에 막히지는 않는다. 다만 canonical contract 문서와 타입 모델이 계속 어긋나면 Spring/FE/API 문서가 서로 다른 payload를 상정하게 된다.

따라서 구현 시 `app/models/canonical.py`도 아래 방향으로 확장한다.

- `SingleFilePayload`에 `source_service`, `file_id`, `content_status`, `content_error`, `content_metadata` 추가
- `FileItem`에도 같은 content 상태 필드 추가
- `EmailAttachment`에 `attachment_id`, `message_id`, `content`, `content_status`, `content_error`, `content_metadata` 추가
- 기존 필드명 `mimeType`, `messageId`, `attachmentId`처럼 camelCase로 들어오는 runtime payload는 dict 단계에서 유지하되, 모델에는 snake_case alias를 둔다.

### 2.2 Google Drive source

`app/core/nodes/input_node.py`의 Google Drive source는 단일 파일과 폴더 파일 목록을 생성한다.

현재 단일 파일 payload:

```json
{
  "type": "SINGLE_FILE",
  "source_service": "google_drive",
  "file_id": "file_1",
  "filename": "report.pdf",
  "content": null,
  "extracted_text": null,
  "extraction_status": "not_requested",
  "mime_type": "application/pdf",
  "size": "1024",
  "url": "https://drive.google.com/file/d/file_1"
}
```

현재 `folder_all_files` payload는 `FILE_LIST.items[]`에 metadata만 담는다. 이 item은 `source_service`, `file_id`, `filename`, `mime_type`, `url`을 포함하므로 LLM lazy extraction의 최소 key는 유지된다.

### 2.3 Google Drive extractor

`app/services/integrations/google_drive.py`에는 `extract_file_text()`가 있다.

현재 지원:

- Google Docs: `text/plain` export
- Google Sheets: `text/csv` export
- Google Slides: `text/plain` export
- `text/*`, `application/json`, `application/xml`: UTF-8 decode
- PDF: `pypdf` text extraction
- 기타: `unsupported`

현재 한계:

- CP949/BOM 인코딩 감지 없음
- CSV/TSV table representation 없음
- PPTX/DOCX/HWPX extractor 없음
- 이미지 OCR/vision 없음
- 다운로드 크기 제한 metadata 없음
- `status=success|truncated`가 요구사항의 `content_status=available`과 다름
- `content_metadata.extraction_method`, `content_kind`, `char_count`, `original_char_count`, `limits` 없음

### 2.4 Loop

`WorkflowExecutor._to_loop_item_payload()`는 `FILE_LIST -> SINGLE_FILE` 변환 시 `dict(item)`을 복사한 뒤 `type="SINGLE_FILE"`을 추가한다.

따라서 item 안에 `content`, `content_status`, `content_error`, `content_metadata`가 있으면 보존된다. Loop 자체는 요구사항과 충돌하지 않는다.

남은 일은 source/list/lazy extraction이 표준 필드를 채우도록 하는 것이다.

### 2.5 LLM 노드

`app/core/nodes/llm_node.py`는 `SINGLE_FILE` 입력에서 아래 순서로 본문을 찾는다.

1. `extracted_text`
2. `content`
3. `source_service=google_drive`와 `file_id`가 있으면 `GoogleDriveService.extract_file_text()` lazy 호출
4. 실패하면 filename/mime/url metadata 사용

좋은 점:

- 단일 Drive 파일 요약은 이미 metadata-only source 뒤에서도 lazy extraction 가능하다.
- 테스트도 lazy extraction 경로를 검증한다.

문제점:

- extraction 실패를 LLM input의 문장으로 넣고 계속 요약할 수 있다. 요구사항은 content-dependent action에서 빈 요약 성공처럼 처리하지 말고 명시적 실패 또는 부분 성공으로 응답하라고 한다.
- `FILE_LIST` 포맷터는 현재 filename/mime/size/url만 포함하고 item `content`를 넣지 않는다.
- `SINGLE_EMAIL`은 `body`와 `bodyPreview`를 읽지만 attachment content는 읽지 않는다.

### 2.6 Preview

`app/core/engine/preview_executor.py`는 `include_content`를 받아 Google Drive 단일 파일 preview에서 `extract_file_text()`를 호출할 수 있다.

현재 preview content 필드:

- `content`: 항상 `None`
- `extracted_text`: include_content=true일 때 추출 텍스트
- `extraction_status`: `success|truncated|unsupported|failed|not_requested`

문제점:

- 요구사항의 `content_status/content_metadata`와 다르다.
- `folder_all_files` preview에서 item별 include_content extraction이 없다.
- AI 노드 preview는 아직 `PREVIEW_NOT_IMPLEMENTED`다.

### 2.7 Gmail attachment

`app/services/integrations/gmail.py`는 첨부파일 metadata를 재귀적으로 추출하지만 content download는 하지 않는다.

현재 attachment item:

```json
{
  "filename": "report.pdf",
  "mime_type": "application/pdf",
  "size": 12345,
  "source": "gmail",
  "messageId": "msg_1",
  "attachmentId": "att_1",
  "content": null,
  "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_1/attachments/att_1"
}
```

따라서 Gmail 첨부 문서 요약은 현재 metadata 요약만 가능하다.

---

## 3. 표준 Canonical Contract

### 3.1 `SINGLE_FILE`

FastAPI 내부 canonical payload는 아래 shape를 표준으로 삼는다.

```json
{
  "type": "SINGLE_FILE",
  "source_service": "google_drive|gmail|upload|url",
  "file_id": "string",
  "filename": "string",
  "mime_type": "string",
  "size": "number|string|null",
  "url": "string|null",
  "content": "string|null",
  "content_status": "available|empty|unsupported|too_large|failed|not_requested",
  "content_error": "string|null",
  "content_metadata": {
    "extraction_method": "google_export|pdf_text|csv_parse|pptx_text|word_text|hwpx_xml|plain_text|ocr|vision|gmail_attachment|none",
    "content_kind": "plain_text|table_text|slide_text|ocr_text|image_description|mixed|none",
    "truncated": false,
    "char_count": 0,
    "original_char_count": 0,
    "limits": {
      "max_download_bytes": 0,
      "max_extracted_chars": 0,
      "max_llm_input_chars": 0
    }
  }
}
```

하위 호환을 위해 1차 구현 동안은 기존 필드를 병행 유지한다.

- `extracted_text`: `content`와 같은 값
- `extraction_status`: 기존 테스트 보호용 legacy status
- `extraction_error`: `content_error` alias

### 3.1.1 상태값 의미와 legacy mapping

`content_status`는 사용자 표시와 실행 제어에 쓰는 표준 상태다.

| `content_status` | 의미 | LLM content-dependent action 처리 |
|------------------|------|-----------------------------------|
| `available` | 본문 추출 성공. truncate 가능성은 metadata로 표시 | 실행 가능 |
| `empty` | 파일은 읽었지만 추출 가능한 텍스트가 없음 | 기본 실패, 사용자가 허용한 경우만 부분 성공 |
| `unsupported` | 파일 타입 또는 추출 방식 미지원 | 실패 |
| `too_large` | 다운로드/추출/입력 제한 초과 | 실패 |
| `failed` | 권한, 손상, parser exception 등 예기치 않은 실패 | 실패 |
| `not_requested` | preview 또는 metadata-only 경로에서 아직 추출하지 않음 | lazy extraction 가능하면 재시도, 불가하면 실패 |

기존 `extraction_status`와의 매핑:

| legacy `extraction_status` | 표준 `content_status` |
|----------------------------|-----------------------|
| `success` | `available` |
| `truncated` | `available` + `content_metadata.truncated=true` |
| `unsupported` | `unsupported` |
| `failed` | `failed` |
| `not_requested` | `not_requested` |

`content_status=available`이면서 `content=""`인 payload는 만들지 않는다. 텍스트가 비어 있으면 `empty`를 사용한다.

### 3.2 `FILE_LIST`

`FILE_LIST.items[]`는 `SINGLE_FILE`에서 `type`만 생략 가능한 같은 item shape를 사용한다.

metadata-only preview에서는 아래처럼 content 미요청 상태를 명확히 둔다.

```json
{
  "type": "FILE_LIST",
  "items": [
    {
      "source_service": "google_drive",
      "file_id": "file_1",
      "filename": "report.pdf",
      "mime_type": "application/pdf",
      "content": null,
      "content_status": "not_requested",
      "content_error": null,
      "content_metadata": {
        "extraction_method": "none",
        "content_kind": "none",
        "truncated": false,
        "char_count": 0,
        "original_char_count": 0
      }
    }
  ]
}
```

### 3.3 Gmail attachments

Gmail 첨부파일도 `FILE_LIST.items[]`로 전달될 수 있으므로 같은 file item shape를 사용한다.

1차에서 attachment download/extraction을 구현하지 않을 경우:

- metadata-only source/preview: `content_status="not_requested"`
- content-dependent 실행에서 download/extraction 미구현: `content_status="unsupported"`
- `content_error`: `"Gmail attachment content extraction is not supported yet."`
- 사용자에게 "첨부파일 본문은 아직 읽지 않고 메타데이터만 사용한다"는 상태를 보여준다.

---

## 4. Content-Dependent Action 판별

본문이 필요한 action:

- `summarize`
- `extract_info`
- `extract`
- `translate`
- `classify_by_content`
- `describe_image`
- `ocr`
- `ai_summarize`
- `ai_analyze`

권장 책임:

- Spring: FE choice config를 해석해 `runtime_config.requires_content=true`를 전달한다.
- FastAPI: `requires_content`가 없더라도 action 이름으로 보수적으로 재판별한다.
- Preview API: target node가 content-dependent이면 `include_content=true`와 같은 효과를 적용하거나, metadata-only preview임을 `metadata.preview_scope`에 명확히 표시한다.

FastAPI fallback 판별 예:

```python
CONTENT_DEPENDENT_ACTIONS = {
    "summarize",
    "extract",
    "extract_info",
    "translate",
    "classify_by_content",
    "describe_image",
    "ocr",
    "ai_summarize",
    "ai_analyze",
}
```

### 4.1 실행 시점별 책임

본문 추출은 어느 한 레이어에만 몰아넣지 않고 아래 순서로 보장한다.

| 시점 | 책임 | 비고 |
|------|------|------|
| Source 실행 | metadata와 lazy extraction key 보존 | `source_service`, `file_id`, `mime_type`, `url` 필수 |
| Source preview | 기본 metadata-only, 요청 시 content 포함 | `include_content=false`면 `not_requested` |
| Loop 변환 | item payload 필드 손실 금지 | `dict(item)` 복사 방식 유지 |
| LLM 직전 | `requires_content=true` 또는 content-dependent action이면 lazy extraction | source가 metadata-only여도 여기서 마지막 보장 |
| Output 실행 | 원본 파일 bytes가 필요한 sink는 기존 download 경로 사용 | 본문 추출용 text와 파일 전송용 bytes를 혼동하지 않음 |

핵심 원칙:

- source는 항상 "나중에 읽을 수 있는 key"를 남긴다.
- LLM은 본문이 필요할 때 metadata만으로 성공하지 않는다.
- preview는 빠른 metadata preview와 content 포함 preview를 명확히 구분한다.

---

## 5. 구현 계획

### Phase 1. Canonical payload 정규화

대상 파일:

- `app/models/canonical.py`
- `app/core/nodes/input_node.py`
- `app/core/engine/preview_executor.py`
- `app/services/integrations/google_drive.py`
- `app/core/nodes/llm_node.py`

작업:

1. file content 기본값 builder를 추가한다.
   - `content=None`
   - `content_status="not_requested"`
   - `content_error=None`
   - `content_metadata.extraction_method="none"`
   - `content_metadata.content_kind="none"`
2. Google Drive source/preview의 `SINGLE_FILE`, `FILE_LIST.items[]`에 표준 필드를 추가한다.
3. 기존 `extracted_text`, `extraction_status`는 compatibility field로 유지한다.
4. Loop 테스트에 `content_status/content_metadata` 보존 케이스를 추가한다.
5. `app/models/canonical.py`의 `SingleFilePayload`, `FileItem`, `EmailAttachment`를 표준 contract와 맞춘다.

완료 기준:

- metadata-only source payload만 봐도 "본문 미요청" 상태를 구분할 수 있다.
- 기존 테스트는 깨지지 않는다.

### Phase 2. Google Drive extraction result 표준화

대상 파일:

- `app/services/integrations/google_drive.py`
- 신규 후보: `app/services/document_extractors/*`

작업:

1. `extract_file_text()` 반환값을 표준 shape로 확장한다.
2. legacy 반환 필드도 당분간 유지한다.
3. `success/truncated`를 `content_status=available`로 매핑한다.
4. 빈 텍스트는 `empty`로 처리한다.
5. `MAX_EXTRACTED_TEXT_CHARS` 기반 truncate 시 metadata에 `truncated=true`, `char_count`, `original_char_count`를 기록한다.
6. `limits`를 metadata에 포함한다.

권장 반환 예:

```json
{
  "text": "문서 본문",
  "status": "success",
  "truncated": false,
  "error": null,
  "content": "문서 본문",
  "content_status": "available",
  "content_error": null,
  "content_metadata": {
    "extraction_method": "pdf_text",
    "content_kind": "plain_text",
    "truncated": false,
    "char_count": 5,
    "original_char_count": 5,
    "limits": {
      "max_download_bytes": 0,
      "max_extracted_chars": 60000,
      "max_llm_input_chars": 0
    }
  }
}
```

완료 기준:

- preview와 LLM lazy extraction이 같은 extraction result contract를 사용한다.
- 추출 실패가 단순 metadata 요약 성공으로 숨겨지지 않는다.

### Phase 2.1 Extractor registry 분리

`GoogleDriveService.extract_file_text()`가 모든 parser를 직접 들고 있으면 Drive/Gmail/URL 업로드가 같은 extractor를 재사용하기 어렵다.

권장 구조:

```text
app/services/document_extractors/
  __init__.py
  models.py
  registry.py
  text.py
  csv.py
  pdf.py
  docx.py
  pptx.py
  hwpx.py
```

권장 인터페이스:

```python
class DocumentExtractionResult(TypedDict):
    content: str | None
    content_status: str
    content_error: str | None
    content_metadata: dict
    text: str
    status: str
    truncated: bool
    error: str | None
```

`registry.extract(raw, filename, mime_type, source_hint)`는 MIME type, 확장자, file signature 순서로 extractor를 고르고, 실패 시 fallback 가능성을 기록한다.

Google Drive는 다운로드/export만 담당하고, 본문 해석은 registry에 위임한다. Gmail attachment를 2차로 구현할 때도 같은 registry를 사용한다.

### Phase 3. 필수 파일군 extractor 추가

필수 지원 우선순위:

1. TXT/MD/LOG
   - UTF-8, UTF-8 BOM, CP949 decode fallback
   - `extraction_method=plain_text`
2. CSV/TSV
   - UTF-8, UTF-8 BOM, CP949 decode fallback
   - delimiter 감지 또는 MIME/확장자 기반 분기
   - header와 row를 LLM이 읽을 수 있는 table text로 변환
   - `extraction_method=csv_parse`, `content_kind=table_text`
3. PDF text layer
   - 기존 `pypdf` 유지
   - text가 비면 `empty` 또는 scan PDF `unsupported` 판단
   - `extraction_method=pdf_text`
4. DOCX
   - `python-docx` 또는 zip/XML 직접 파싱
   - paragraph/table 우선
   - `extraction_method=word_text`
5. PPTX
   - `python-pptx` 또는 zip/XML 직접 파싱
   - slide 번호/title/body/note 순서 유지
   - `extraction_method=pptx_text`, `content_kind=slide_text`
6. HWPX
   - zip 내부 XML에서 body text 추출
   - `extraction_method=hwpx_xml`
7. Google Workspace
   - 기존 export 유지
   - Docs는 plain text, Sheets는 csv_parse, Slides는 가능하면 slide_text 또는 plain_text

의존성 가이드:

- PDF: 이미 사용 중인 `pypdf` 유지
- DOCX/PPTX: 신규 dependency를 추가하기 전, zip/XML 직접 파싱으로 MVP 요구를 만족할 수 있는지 먼저 검토
- CSV/TSV/TXT/HWPX: 표준 라이브러리로 구현 가능
- OCR/vision: provider 결정 전까지 dependency 추가 금지

조건부 지원:

- `.ppt`, `.doc`: 변환기 없으면 `unsupported`
- image: OCR/vision 미구현이면 `unsupported`
- scan PDF: OCR 미구현이면 `unsupported` 또는 `empty`가 아니라 scan/OCR 미지원 사유를 `content_error`에 기록

완료 기준:

- 필수 파일군은 성공 또는 명확한 실패 사유를 반환한다.
- 조건부 파일군은 미지원 상태가 사용자 표시 가능한 메시지를 갖는다.

### Phase 4. LLM 입력 정책 강화

대상 파일:

- `app/core/nodes/llm_node.py`

작업:

1. `SINGLE_FILE`은 `content`를 우선하고, legacy `extracted_text`를 fallback으로 둔다.
2. `FILE_LIST.items[]` 포맷터가 item content를 포함한다.
3. `content_status in {"unsupported", "too_large", "failed"}`이고 action이 content-dependent이면 `FlowifyException`으로 실패 처리한다.
4. `content_status="not_requested"`이고 lazy extraction key가 있으면 extraction을 시도한다.
5. `content_status="empty"`이고 action이 요약/분석/추출처럼 본문 의미가 필요한 작업이면 실패 처리한다.
6. metadata-only action 또는 파일 라우팅/분류처럼 본문 없이도 의미 있는 action은 `empty`를 부분 성공으로 허용할 수 있지만, 결과 metadata에 `content_status=empty`를 남긴다.
7. lazy extraction 결과를 LLM input에만 쓰는 대신 가능하면 payload에도 표준 content 필드를 반영하는 helper를 둔다.
8. Gmail attachment content는 1차 미지원이면 LLM input에 "첨부 본문 미지원" 상태를 명확히 포함하거나 content-dependent action에서 실패 처리한다.
9. `SINGLE_EMAIL`의 attachment content가 지원되는 경우, 본문 입력은 `email.body` 다음에 attachment별 filename/content/status를 구분해 붙인다.

완료 기준:

- 본문이 필요한 요약/분석 action이 filename만 보고 성공 요약을 만들지 않는다.
- 요약/분석/추출 action에서 `unsupported`, `too_large`, `failed`, `empty` 상태가 명시적 실패 또는 사용자 표시 가능한 부분 실패로 기록된다.
- metadata-only action은 본문 실패를 숨기지 않고 payload metadata에 남긴다.
- `FILE_LIST -> LOOP -> AI`와 `SINGLE_FILE -> AI`가 동일한 content contract를 사용한다.

### Phase 5. Preview 정책 정리

대상 파일:

- `app/core/engine/preview_executor.py`
- Spring preview request translator
- FE `DataPreviewBlock`

작업:

1. source preview metadata에는 기존 호환 필드 `preview_scope="source_metadata"`를 유지한다.
2. `include_content=true`일 때는 `content`, `content_status`, `content_metadata`를 채운다.
3. folder preview에서 `include_content=true`인 경우 limit 범위 item별 extraction을 수행할지 결정한다.
4. AI 노드 preview는 별도 구현 전까지 `PREVIEW_NOT_IMPLEMENTED` 대신 "source preview만 가능" 이유를 유지하되, content-dependent target preview 설계를 문서화한다.
5. FE는 `content_status`, `content_error`, `truncated`를 표시한다.
6. preview 응답 metadata에 신규 의미 필드 `content_policy`를 추가한다.
   - `metadata_only`
   - `content_included`
   - `content_status_only`
   - `content_required_but_unavailable`

FE 호환 메모:

- FE 설계에서 `required_by_downstream`이라는 표시값이 제안될 수 있으나, FastAPI 표준값은 `content_required_but_unavailable`로 둔다.
- Spring public API가 `required_by_downstream`을 쓰기로 결정한다면 public alias로만 허용하고, FastAPI raw response에는 쓰지 않는다.
- FE helper는 `content_required_but_unavailable`과 `required_by_downstream`을 모두 수용한다. 두 값을 같은 문구로 합치거나, "본문 필요하지만 미포함"과 "다음 단계에서 본문 필요"처럼 구분 표시해도 된다.

호환 필드와 신규 필드 병행 규칙:

| 필드 | 형식 | 목적 | 유지 기간 |
|------|------|------|-----------|
| `metadata.preview_scope` | snake_case | 기존 FastAPI preview response 호환 | 기존 FE/Spring 전환 완료까지 유지 |
| `metadata.previewScope` | camelCase 선택 | Spring public API가 camelCase로 재직렬화할 때 사용 가능 | Spring 응답 정책에 따름 |
| `metadata.content_policy` | snake_case | FastAPI 내부/테스트 기준 신규 의미 필드 | 표준 필드 |
| `metadata.contentPolicy` | camelCase 선택 | Spring public API/FE 표시용 신규 의미 필드 | Spring 응답 정책에 따름 |

권장 preview metadata 예:

```json
{
  "preview_scope": "source_metadata",
  "content_policy": "metadata_only",
  "include_content": false
}
```

Spring이 public API에서 camelCase만 노출한다면 아래처럼 변환한다.

```json
{
  "previewScope": "source_metadata",
  "contentPolicy": "metadata_only",
  "includeContent": false
}
```

완료 기준:

- preview에서 본문이 빠진 상태와 추출 실패 상태가 구분된다.

### Phase 6. Gmail attachment 범위 결정

선택지:

- Option A: 1차 미지원으로 명시
  - attachment item에 `content_status="unsupported"`
  - FE 템플릿/preview에 제한 표시
- Option B: Gmail attachment download + 공통 extractor 연결
  - Gmail API `messages.attachments.get` 호출
  - base64url decode
  - Google Drive와 같은 extractor registry 사용

권장:

- 1차는 Option A로 명확히 막고, Google Drive 필수 파일군을 먼저 안정화한다.
- 2차에서 Option B를 구현한다.

### Phase 7. 보안, 로깅, 저장 정책

본문 추출은 민감한 문서 내용을 다루므로 실행 로그와 callback payload 정책을 명확히 둔다.

권장 정책:

1. 노드 실행 중 in-memory payload는 다음 노드 실행에 필요한 full `content`를 가질 수 있다.
2. FastAPI가 실행 로그를 저장하기 전 `_sanitize_for_log()`에서 긴 `content`를 제한 길이로 truncate한다.
3. FastAPI가 Spring callback payload를 만들 때도 저장 로그와 같은 sanitized payload를 보낸다. full content를 callback으로 보내지 않는다.
4. Spring은 callback 수신 후 다시 저장/조회용 sanitize를 적용할 수 있지만, 1차 책임 경계는 FastAPI 반환 전 sanitize다.
5. truncate된 로그에는 `content_metadata.truncated_for_log=true` 또는 별도 `log_metadata`를 남긴다.
6. 원본 파일 bytes는 저장하지 않는다.
7. extractor exception에는 파일 본문 일부를 넣지 않는다.
8. `content_error`는 사용자 표시 가능한 메시지로 제한하고, 상세 stack trace는 서버 로그에만 남긴다.
9. OAuth scope/권한 문제는 `content_status=failed`, `content_error="파일을 읽을 권한이 없습니다."`처럼 사용자 행동이 가능한 메시지로 변환한다.

경계 요약:

| 경로 | full content 허용 여부 | 정책 |
|------|------------------------|------|
| 노드 실행 중 in-memory payload | 허용 | 다음 LLM/후속 노드 실행에 필요할 수 있음 |
| MongoDB execution log | 비허용 | sanitize 후 preview 길이만 저장 |
| FastAPI -> Spring callback | 비허용 | sanitize된 log payload만 전송 |
| Spring public 조회 API | 비허용 | 저장된 sanitized payload를 그대로 또는 추가 마스킹 후 반환 |
| 서버 debug log | 비허용 | content 본문 직접 출력 금지 |

### Phase 8. 에러 코드와 관측성

FastAPI error code 후보:

- `DOCUMENT_CONTENT_UNSUPPORTED`
- `DOCUMENT_CONTENT_TOO_LARGE`
- `DOCUMENT_CONTENT_EXTRACTION_FAILED`
- `DOCUMENT_CONTENT_NOT_REQUESTED`
- `DOCUMENT_CONTENT_EMPTY`

Spring public API 매핑 권장:

| FastAPI error code | HTTP status | node status | 사용자 문구 예 | 비고 |
|--------------------|-------------|-------------|----------------|------|
| `DOCUMENT_CONTENT_UNSUPPORTED` | 422 | `failed` 또는 `partial_failed` | 이 파일 형식은 아직 본문 읽기를 지원하지 않습니다. | 조건부 지원 파일군/미지원 MIME |
| `DOCUMENT_CONTENT_TOO_LARGE` | 413 | `failed` | 파일이 현재 처리 가능한 크기를 초과했습니다. | limit metadata 함께 표시 |
| `DOCUMENT_CONTENT_EXTRACTION_FAILED` | 502 또는 500 | `failed` | 파일 본문을 읽는 중 오류가 발생했습니다. | 외부 API 실패는 502, parser 내부 실패는 500 |
| `DOCUMENT_CONTENT_NOT_REQUESTED` | 409 | `failed` | 본문이 필요한 작업이지만 본문 추출이 요청되지 않았습니다. | translator/config 오류 가능성 |
| `DOCUMENT_CONTENT_EMPTY` | 422 | `failed` 또는 `partial_failed` | 파일에서 읽을 수 있는 텍스트를 찾지 못했습니다. | 스캔 PDF/OCR 미지원과 구분 |
| `OAUTH_TOKEN_INVALID` | 401 | `failed` | 파일을 읽기 위한 인증이 만료되었습니다. | 기존 OAuth error와 통합 |
| `EXTERNAL_API_ERROR` | 502 | `failed` | 외부 파일 서비스에서 파일을 가져오지 못했습니다. | Drive/Gmail API 실패 |

Spring은 raw exception message를 그대로 FE에 노출하지 않고, `error_code`, 사용자 문구, node id, content status 정도만 public response에 포함한다. 상세 stack trace와 extractor 내부 error는 서버 로그 또는 internal metadata로 제한한다.

관측성 metadata:

```json
{
  "content_metadata": {
    "source": "google_drive",
    "detected_mime_type": "application/pdf",
    "declared_mime_type": "application/pdf",
    "extension": ".pdf",
    "extraction_method": "pdf_text",
    "duration_ms": 123,
    "attempts": ["mime:application/pdf", "extension:.pdf"]
  }
}
```

이 metadata는 디버깅용이지만 사용자에게 그대로 노출하지 않아도 된다. FE에는 `content_status`, `content_error`, `truncated`, `char_count` 정도만 표시한다.

---

## 6. 테스트 계획

### Unit tests

추가/수정 대상:

- `app/models/canonical.py`
- `tests/test_preview_executor.py`
- `tests/test_llm_node.py`
- `tests/test_executor.py`
- `tests/test_integrations/test_google_drive.py`

필수 케이스:

1. Google Drive single_file metadata-only preview
   - `content_status="not_requested"`
   - `content_metadata.extraction_method="none"`
2. Google Drive single_file include_content preview
   - `content="문서 본문"`
   - `content_status="available"`
   - legacy `extracted_text`도 유지
3. `FILE_LIST -> LOOP -> SINGLE_FILE`
   - item의 `content_status/content_metadata` 보존
4. LLM `SINGLE_FILE.content` 우선 사용
5. LLM legacy `extracted_text` fallback 사용
6. LLM Google Drive lazy extraction result의 표준 metadata 처리
7. LLM `FILE_LIST.items[].content` 포함
8. unsupported/failed file content-dependent action 실패 처리
9. TXT UTF-8/UTF-8 BOM/CP949 extraction
10. CSV UTF-8/CP949 table text extraction
11. PDF text layer extraction
12. DOCX paragraph/table text extraction
    - paragraph 순서 유지
    - table cell text 포함
    - `extraction_method=word_text`
13. PPTX slide text extraction
    - slide 번호 순서 유지
    - title/body/note 또는 추출 가능한 placeholder text 포함
    - `content_kind=slide_text`
14. HWPX XML body extraction
    - zip 내부 XML body text 추출
    - 손상/암호화 파일은 `failed|unsupported`
    - `extraction_method=hwpx_xml`
15. Gmail attachment metadata-only 미지원 상태
16. `app/models/canonical.py` 모델이 표준 file content field를 수용하는지
17. log sanitize가 긴 `content`를 제한하고 metadata를 보존하는지

### Integration-like tests

외부 API는 mock으로 둔다.

1. `single_file -> llm summarize`
   - source output은 metadata-only
   - LLM에서 lazy extraction 호출
   - LLM input에 본문 포함
2. `folder_all_files -> loop -> llm summarize`
   - item별 file_id/mime_type 유지
   - body iteration에서 lazy extraction 호출
3. `attachment_email -> llm summarize`
   - 1차 미지원 선택 시 사용자 표시 가능한 failure 또는 partial failure

### Contract tests

Spring/FE와 맞출 계약 테스트를 별도로 둔다.

1. Spring이 `runtime_config.requires_content=true`를 보낸 payload를 FastAPI가 수용한다.
2. preview request의 `include_content=true`가 source preview 결과의 `content_status`를 `available|empty|unsupported|failed|too_large` 중 하나로 만든다.
3. execution log callback payload에서 `content_status/content_error/content_metadata`가 보존된다.
4. legacy field가 있는 payload와 신규 field가 있는 payload를 모두 LLM이 처리한다.
5. callback payload의 긴 `content`가 truncate되어 Spring에 전달된다.
6. FastAPI error code가 Spring public error shape로 매핑된다.

---

## 7. Spring/FE 요청사항

### Spring

1. `runtime_config.requires_content`를 생성한다.
2. `choiceActionId`, `choiceNodeType`, `choiceSelections`를 FastAPI runtime payload에 유지한다.
3. preview target이 content-dependent이면 `includeContent=true`를 전달하거나, FastAPI가 판단할 수 있는 target node context를 전달한다.
4. 실행 로그의 `inputData/outputData`에서 `content_status`, `content_error`, `content_metadata`를 제거하지 않는다.

#### Spring requiresContent 판별 보강

Spring Boot 팀 책임으로 아래 우선순위에 따라 `runtime_config.requires_content`를 생성한다.

1. 명시 필드 우선
   - FE 또는 template이 이미 `requiresContent`/`requires_content`를 저장했다면 그 값을 우선한다.
2. `choiceActionId`
   - `summarize`, `ai_summarize`, `extract_info`, `translate`, `classify_by_content`, `describe_image`, `ocr`, `ai_analyze`는 true.
3. `choiceSelections`
   - `choiceSelections.summarize`, `choiceSelections.extract_info`, `choiceSelections.translate`처럼 action key가 있으면 true.
   - `choiceSelections.follow_up`만 있고 action이 `filter_fields`, `filter_metadata`이면 false. 이는 필드 projection이지 본문 의미 분석이 아니다.
4. node/action fallback
   - `runtime_config.action`, `config.action`, `dataType`, `outputDataType`를 확인한다.
   - LLM 계열 action이 content-dependent 목록에 있으면 true.
5. prompt fallback
   - template migration 데이터에서 action id가 누락된 경우에만 사용한다.
   - prompt에 "요약", "summarize", "본문", "문서 내용", "extract", "translate", "OCR" 같은 강한 키워드가 있고 입력 타입이 `SINGLE_FILE|FILE_LIST|SINGLE_EMAIL`이면 true로 둘 수 있다.
   - prompt fallback은 false positive 위험이 있으므로 `runtime_config.requires_content_inferred=true`, `requires_content_reason="prompt_keyword"` 같은 추론 metadata를 함께 남긴다.

Spring pseudo-code:

```java
boolean requiresContent(Node node) {
    if (node.hasExplicitRequiresContent()) return node.getRequiresContent();

    String actionId = node.config("choiceActionId");
    if (CONTENT_ACTIONS.contains(actionId)) return true;

    Map<String, Object> selections = node.config("choiceSelections");
    if (containsAnyKey(selections, CONTENT_ACTIONS)) return true;
    if (isMetadataOnlyChoice(actionId, selections)) return false;

    String action = firstNonBlank(
        node.runtimeConfig("action"),
        node.config("action")
    );
    if (CONTENT_ACTIONS.contains(action)) return true;

    return inferFromPromptOnlyForLegacyTemplates(node);
}
```

FastAPI도 방어적으로 action 기반 fallback을 갖되, Spring이 보낸 명시 `requires_content`를 가장 신뢰한다.

#### Spring public error shape

Spring public API는 FastAPI 내부 error를 아래 shape로 정규화한다.

```json
{
  "errorCode": "DOCUMENT_CONTENT_UNSUPPORTED",
  "message": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다.",
  "nodeId": "node_ai_1",
  "nodeStatus": "failed",
  "contentStatus": "unsupported",
  "retryable": false
}
```

`retryable` 권장값:

- `DOCUMENT_CONTENT_TOO_LARGE`: false
- `DOCUMENT_CONTENT_UNSUPPORTED`: false
- `DOCUMENT_CONTENT_EMPTY`: false
- `DOCUMENT_CONTENT_EXTRACTION_FAILED`: true if external/transient, false if parser/file damage
- `DOCUMENT_CONTENT_NOT_REQUESTED`: false, translator/config 수정 필요
- `OAUTH_TOKEN_INVALID`: true after re-auth

### FE

1. source preview는 metadata-only일 수 있음을 표시한다.
2. AI 요약/분석 preview는 content 포함 preview를 요청한다.
3. `SINGLE_FILE`과 `FILE_LIST.items[]`에 대해 아래 상태를 표시한다.
   - `available`: 본문 읽기 완료
   - `empty`: 파일은 읽었지만 추출 가능한 텍스트 없음
   - `not_requested`: 미리보기에서 본문 미포함
   - `unsupported`: 지원하지 않는 파일
   - `too_large`: 크기 제한 초과
   - `failed`: 추출 실패
4. 템플릿 설명에 Gmail 첨부 본문 지원 여부를 실제 런타임 기준으로 맞춘다.

---

## 8. 결정 필요사항

아래 항목은 구현 전에 팀 결정이 필요하다.

1. Gmail 첨부파일 본문 읽기를 1차에 포함할지
   - 권장: 1차 미지원 명시, 2차 구현
2. 이미지 OCR/vision을 1차에 포함할지
   - 권장: 1차 미지원 명시, OCR/vision provider 확정 후 구현
3. 최대 다운로드 크기
   - 임시 권장: 20MB
4. 최대 추출 문자 수
   - 현재 코드: 60,000 chars
   - 권장: 유지하되 `content_metadata.limits.max_extracted_chars=60000` 기록
5. LLM input 최대 문자 수
   - 권장: 모델별 제한과 별도 product limit 중 작은 값 적용
6. 추출 실패 시 workflow 실패로 볼 action 범위
   - 권장: `requires_content=true`이면 실패, metadata-only action이면 부분 성공 허용
7. legacy field 제거 시점
   - 권장: FE/Spring 반영 후 한 릴리즈 이상 병행 유지
8. 로그에 본문을 얼마나 저장할지
   - 권장: 실행 디버깅용으로 짧은 preview만 저장하고, 전체 content는 저장하지 않음
9. DOCX/PPTX 구현 방식
   - 권장: dependency 추가 전 zip/XML 직접 파싱 MVP 검토
10. `content_status=empty` 처리
   - 권장: 요약/분석에서는 실패, 파일 분류/라우팅에서는 부분 성공 허용 가능

---

## 9. 권장 구현 순서

1. `content_status/content_metadata` helper 추가
2. `app/models/canonical.py`를 표준 필드에 맞게 확장
3. Google Drive source/preview payload에 표준 필드 추가
4. Google Drive extractor 반환 shape 확장
5. Extractor registry를 분리하고 TXT/CSV/PDF를 먼저 연결
6. LLM node가 표준 field를 우선 사용하도록 수정
7. `FILE_LIST` formatter에 item content 포함
8. unsupported/failed/empty 상태에서 content-dependent action 실패 처리
9. DOCX/PPTX/HWPX extractor 추가
10. Gmail attachment는 미지원 상태 명시 또는 download 구현
11. 로그 sanitize와 error code 정리
12. FE/Spring contract 문서와 preview 표시 반영

---

## 10. 완료 기준 분리

이 문서는 두 종류의 완료 기준을 명확히 구분한다.

### 10.1 계약/경로 안정화 MVP

이 기준은 런타임 경로와 canonical contract를 먼저 안정화하기 위한 중간 마일스톤이다. 원문 요구사항의 1차 완료와 동일하지 않다.

계약/경로 안정화 MVP는 아래를 모두 만족하면 완료로 본다.

- `SINGLE_FILE`과 `FILE_LIST.items[]`에 `content_status`, `content_error`, `content_metadata`가 항상 존재한다.
- Google Drive 단일 문서 요약에서 LLM input에 실제 본문이 들어간다.
- `FILE_LIST -> LOOP -> AI summarize` 경로에서 본문 또는 lazy extraction key가 손실되지 않는다.
- TXT/CSV/PDF/Google Workspace는 본문 추출 성공 또는 명확한 실패 사유를 반환한다.
- DOCX/PPTX/HWPX가 아직 미구현이면 `unsupported`로 명확히 응답하고, 문서/릴리즈 노트에 "원문 1차 완료 미달"로 표시한다.
- Gmail 첨부파일 요약은 지원 여부가 preview와 실행 결과에 명확히 표시된다.
- 추출 실패가 빈 요약 성공으로 처리되지 않는다.
- preview와 실제 실행 모두에서 본문 포함/미포함 상태가 구분된다.
- 저장 로그와 Spring callback payload에는 full content가 남지 않는다.

### 10.2 원문 요구사항 1차 완료

원문 `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`의 1차 필수 지원군까지 완료하려면 계약/경로 안정화 MVP에 더해 아래가 모두 필요하다.

- DOCX extractor가 paragraph와 table text를 추출한다.
- PPTX extractor가 slide 순서를 유지하고 title/body/note 또는 추출 가능한 placeholder text를 추출한다.
- HWPX extractor가 zip 내부 XML body text를 추출한다.
- DOCX/PPTX/HWPX 손상/암호화/파싱 실패 파일이 `failed|unsupported`와 사용자 표시 가능한 `content_error`를 반환한다.
- DOCX/PPTX/HWPX unit test와 integration-like test가 통과한다.
- Spring public API가 FastAPI document content error code를 사용자 표시 가능한 error shape로 변환한다.
- FE preview가 필수 지원 파일군의 `available|empty|unsupported|too_large|failed|not_requested` 상태를 모두 표시할 수 있다.

DOCX/PPTX/HWPX를 뒤로 미루는 릴리즈는 "계약/경로 안정화 MVP"로만 부르고, "문서 본문 원문 요구사항 1차 완료" 또는 "필수 파일군 지원 완료"라고 표기하지 않는다.
