# Gmail attachment/OCR/Vision 구현 전달 문서

> 작성일: 2026-05-17  
> 전달 대상: Frontend 팀, Spring Boot 팀  
> 기준 브랜치: `feat/26-runtime-document`  
> 목적: Gmail attachment 본문 추출, scan PDF OCR, image OCR/vision 후속 작업의 실제 구현 방식과 연동 시 주의사항을 공유한다.

---

## 1. 구현 요약

기존 문서 본문 런타임 계약은 유지했다.

- 기존 top-level 필드인 `content`, `content_status`, `content_error`, `content_metadata`를 그대로 사용한다.
- Gmail attachment, image, scan PDF는 새 payload 계약을 만들지 않고 기존 file content contract에 metadata를 추가하는 방식으로 연결했다.
- 기능 플래그는 모두 기본 `false`다. 운영에서 명시적으로 켜기 전에는 기존 동작을 깨지 않고 `unsupported` 상태를 반환한다.
- OCR/vision provider는 1차 구현에서 기존 LLM 연동을 재사용하는 `openai_vision`만 지원한다.
- 원본 파일 bytes/base64는 응답 payload나 log에 저장하지 않는다.

검토 결과, 현재 변경분에서 차단급 이슈는 발견하지 못했다. 비용과 latency가 큰 기능이라 기본 off 정책, size/page/pixel limit, `unsupported` 정규화가 핵심 안전장치다.

---

## 2. 변경 파일

주요 구현 파일:

- `app/config.py`: OCR/vision/Gmail attachment feature flag와 limit 설정 추가.
- `app/core/document_content.py`: `content_metadata`에 service-specific metadata를 병합할 수 있도록 확장.
- `app/services/integrations/gmail.py`: Gmail attachment metadata 보강, attachment download, 공통 extractor adapter 추가.
- `app/services/integrations/google_drive.py`: byte 기반 공통 extractor, image OCR/vision, scan PDF OCR fallback 추가.
- `app/services/llm_service.py`: vision-capable model 호출용 `analyze_image()` 추가.
- `app/core/nodes/llm_node.py`: LLM 실행 직전 Gmail/Drive file content lazy extraction 연결.
- `app/core/engine/preview_executor.py`: `include_content=true` preview에서 Gmail attachment content 추출 연결.
- `app/core/nodes/input_node.py`: Gmail attachment alias field 보존.

테스트 파일:

- `tests/test_integrations/test_google_drive.py`
- `tests/test_integrations/test_gmail.py`
- `tests/test_input_node.py`
- `tests/test_llm_node.py`
- `tests/test_preview_executor.py`

의존성:

- `PyMuPDF>=1.24.0` 추가. scan PDF를 page image로 렌더링할 때 사용한다.

---

## 3. 설정값

FastAPI 설정에 아래 값이 추가됐다.

```text
ENABLE_GMAIL_ATTACHMENT_EXTRACTION=false
ENABLE_PDF_OCR=false
ENABLE_IMAGE_OCR=false
ENABLE_IMAGE_VISION=false
OCR_PROVIDER=openai_vision
VISION_PROVIDER=openai_vision
VISION_MODEL_NAME=
OCR_LANGUAGES=ko,en
MAX_OCR_PAGES=10
MAX_IMAGE_PIXELS=12000000
```

운영 의미:

- Gmail attachment 본문 추출은 `ENABLE_GMAIL_ATTACHMENT_EXTRACTION=true`일 때만 attachment bytes를 다운로드한다.
- scan PDF OCR은 `ENABLE_PDF_OCR=true`, `ENABLE_IMAGE_OCR=true`, `OCR_PROVIDER=openai_vision`, `LLM_API_KEY`가 모두 준비되어야 실제 OCR을 수행한다.
- image OCR은 `ENABLE_IMAGE_OCR=true`일 때만 수행한다.
- image description/vision은 `ENABLE_IMAGE_VISION=true`일 때만 수행한다.
- `VISION_MODEL_NAME`이 비어 있으면 기존 `LLM_MODEL_NAME`을 사용한다.

Spring Boot나 Frontend가 provider API key, provider 이름, page render 설정을 runtime payload로 넘길 필요는 없다. 이 값들은 FastAPI 서버 설정이다.

---

## 4. 공통 응답 계약

기존 file content contract를 유지한다.

```json
{
  "content": "추출된 텍스트 또는 이미지 설명",
  "content_status": "available",
  "content_error": null,
  "content_metadata": {
    "extraction_method": "pdf_text",
    "content_kind": "plain_text",
    "truncated": false,
    "char_count": 1234,
    "original_char_count": 1234,
    "limits": {
      "max_download_bytes": 10485760,
      "max_extracted_chars": 60000,
      "max_llm_input_chars": 60000,
      "max_ocr_pages": 10,
      "max_image_pixels": 12000000
    }
  }
}
```

신규 metadata는 optional이다.

| 필드 | 의미 |
|------|------|
| `source_service` | `gmail`, `google_drive` 등 원천 서비스 |
| `message_id` | Gmail message id |
| `attachment_id` | Gmail attachment id |
| `inline` | Gmail inline image 여부 |
| `provider` | OCR/vision provider 이름. 현재는 `openai_vision` |
| `languages` | OCR language hint. 기본 `["ko", "en"]` |
| `page_count` | PDF page 수 |
| `ocr_page_count` | OCR 결과가 나온 page 수 |
| `image_only_pdf` | PDF text layer가 없어 OCR fallback 대상인지 여부 |
| `partial` | 일부 page만 OCR 성공했는지 여부 |
| `image_width`, `image_height` | 확인 가능한 이미지 pixel size |

`extraction_method`는 파일 출처가 아니라 본문 생성 방식을 의미한다. Gmail attachment라도 `extraction_method`는 `pdf_text`, `docx_xml`, `csv_parse`, `ocr`, `vision`, `mixed`처럼 기록된다.

---

## 5. Gmail Attachment 구현

Gmail message parsing 단계에서 attachment item에 아래 alias를 모두 실어 보낸다.

- `messageId`, `message_id`
- `attachmentId`, `attachment_id`
- `mimeType`, `mime_type`
- `source`, `source_service`
- `inline`

본문 추출 흐름:

1. Gmail source가 attachment metadata를 만든다.
2. 기본 preview 또는 metadata-only 경로에서는 `content_status=not_requested`가 유지된다.
3. `include_content=true` preview 또는 LLM node에서 content-dependent action이 실행되면 attachment download를 시도한다.
4. Gmail API attachment body의 `data`를 base64url decode한다.
5. decode된 bytes를 Google Drive byte extractor와 같은 공통 extractor에 넘긴다.
6. TXT/CSV/PDF text/DOCX/PPTX/HWPX/image/scan PDF 처리는 모두 같은 결과 계약으로 반환된다.

inline image 정책:

- 1차 구현에서는 Gmail inline image를 attachment 본문 추출 대상에서 제외했다.
- 이유는 서명 이미지, 로고, tracking pixel이 많이 섞여 LLM 입력 품질과 비용을 해칠 수 있기 때문이다.
- inline이면 `content_status=unsupported`, `content_metadata.inline=true`가 내려갈 수 있다.

대용량 정책:

- Gmail attachment는 다운로드 전에 Gmail metadata의 `size`가 `MAX_DOWNLOAD_BYTES`를 넘으면 다운로드하지 않고 `too_large`로 반환한다.
- 다운로드 후 실제 bytes 크기도 다시 검사한다.

---

## 6. Image OCR/Vision 구현

이미지 판별:

- MIME이 `image/*`이거나 확장자가 `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`이면 image extractor 대상으로 본다.
- 현재 pixel size 직접 확인은 PNG/BMP/JPEG에 우선 적용된다. size를 읽을 수 없는 형식은 bytes size limit과 provider limit에 맡긴다.

action별 동작:

| action | provider mode | `extraction_method` | `content_kind` |
|--------|---------------|---------------------|----------------|
| `ocr` | OCR only | `ocr` | `ocr_text` |
| `describe_image` | Vision only | `vision` | `image_description` |
| `summarize`, `ai_analyze` | OCR + Vision mixed | `mixed` 또는 단일 성공 method | `mixed` 또는 단일 성공 kind |

`summarize`/`ai_analyze`를 mixed로 둔 이유:

- 캡처 이미지나 영수증처럼 텍스트가 중요한 경우 OCR이 필요하다.
- 차트, 사진, UI screenshot처럼 시각적 맥락이 중요한 경우 vision description이 필요하다.
- 둘 중 하나만 쓰면 결과 품질이 크게 흔들릴 수 있어 기본은 mixed로 결정했다.

provider disabled/key missing:

- 기능 플래그가 꺼져 있거나 `LLM_API_KEY`가 없으면 external API를 호출하지 않는다.
- 이 경우 `content_status=unsupported`로 반환한다.

---

## 7. Scan PDF OCR 구현

PDF 처리 순서:

1. 기존 `pypdf` text layer extraction을 먼저 실행한다.
2. 텍스트가 있으면 기존처럼 `extraction_method=pdf_text`로 성공 반환한다.
3. 텍스트가 없으면 scan PDF로 보고 OCR fallback을 검토한다.
4. `ENABLE_PDF_OCR=false`이면 기존과 동일하게 `unsupported` 반환.
5. `page_count > MAX_OCR_PAGES`이면 `too_large` 반환.
6. PyMuPDF로 page를 PNG image로 렌더링한다.
7. 각 page image를 image OCR provider에 넘긴다.
8. 성공한 page text를 `[Page N]` 구분자로 합쳐 반환한다.

중요한 운영 조건:

- scan PDF OCR은 PDF OCR flag만 켠다고 동작하지 않는다. image OCR provider도 켜져 있어야 한다.
- PyMuPDF가 설치되지 않은 환경에서는 page rendering을 할 수 없으므로 `unsupported`가 반환된다.
- 일부 page만 성공하면 `content_metadata.partial=true`가 붙을 수 있다.

---

## 8. LLM/Preview 연결

LLM node:

- `SINGLE_FILE` 또는 `FILE_LIST.items[]`에 `content`가 이미 있으면 그대로 사용한다.
- `content_status`가 `not_requested`이거나 없고, content-dependent action이면 lazy extraction을 수행한다.
- Google Drive file은 `GoogleDriveService.extract_file_text()`를 호출한다.
- Gmail attachment는 `GmailService.extract_attachment_text()`를 호출한다.
- `requires_content=true`인데 추출 실패 상태라면 기존 `DOCUMENT_CONTENT_*` error로 raise한다.
- error context에는 `filename`, `message_id`, `attachment_id`, `content_status`, `content_error`가 포함된다.

Preview:

- Google Drive single file preview는 기존처럼 `include_content=true`일 때만 본문 추출을 수행한다.
- Gmail `single_email`, `new_email`, `sender_email`, `starred_email`은 `include_content=true`일 때 해당 email의 attachment content 추출을 시도한다.
- Gmail `attachment_email`은 `FILE_LIST.items[]`에 attachment를 담고, `include_content=true`일 때 각 item에 content 결과를 붙인다.
- Gmail `label_emails`는 email list 중심 preview라 attachment 본문 추출을 자동 수행하지 않는다.

---

## 9. Frontend 팀 연동 가이드

Frontend는 기존 file card/content helper를 계속 재사용하면 된다.

필수 표시 기준:

- `content_status=available`: `content`를 본문 미리보기 또는 LLM 입력용 추출 결과로 표시한다.
- `content_status=not_requested`: 아직 본문을 요청하지 않은 상태로 표시한다.
- `content_status=unsupported`: 지원하지 않거나 feature flag/provider가 꺼진 상태로 안내한다.
- `content_status=too_large`: 크기/page/pixel 제한 초과로 안내한다.
- `content_status=empty`: 추출은 성공했지만 읽을 수 있는 텍스트가 없다고 안내한다.
- `content_status=failed`: provider/API/parsing 실패로 안내한다.

UI 주의사항:

- `content`는 전체 원문이 아니라 제한된 추출 본문 또는 미리보기일 수 있다.
- `content_error` 문구는 provider/정규화 경로에 따라 일반화될 수 있으므로, 화면 로직은 exact string이 아니라 `content_status` 중심으로 분기한다.
- Gmail attachment는 snake_case와 camelCase alias가 함께 올 수 있다. `message_id`/`messageId`, `attachment_id`/`attachmentId`, `mime_type`/`mimeType`를 모두 허용한다.
- `inline=true`인 Gmail image는 1차에서 추출 대상이 아니므로 attachment card에는 "inline image는 본문 추출 제외" 계열로 표시하면 된다.
- `content_metadata.content_kind=mixed`인 image 결과는 OCR 텍스트와 이미지 설명이 합쳐진 일반 텍스트로 표시하면 된다.
- provider 세부값은 사용자에게 직접 노출하기보다 debug/detail 영역에 두는 것을 권장한다.

권장 상태 문구:

| 상태 | 사용자 문구 예시 |
|------|------------------|
| `not_requested` | 본문은 아직 불러오지 않았습니다. |
| `unsupported` | 현재 이 파일의 본문 추출을 지원하지 않습니다. |
| `too_large` | 파일이 현재 처리 가능한 크기나 페이지 수를 초과했습니다. |
| `empty` | 읽을 수 있는 텍스트를 찾지 못했습니다. |
| `failed` | 본문을 추출하는 중 문제가 발생했습니다. |

---

## 10. Spring Boot 팀 연동 가이드

Spring Boot는 이번 기능의 provider 세부 구현을 알 필요가 없다. 핵심은 FastAPI에서 내려온 canonical payload와 error context를 손실 없이 보존하는 것이다.

보존해야 하는 필드:

- `content`
- `content_status`
- `content_error`
- `content_metadata`
- `content_metadata.limits.*`
- `nodeLogs[].error.code`
- `nodeLogs[].error.context`

Spring Boot에서 확인할 부분:

- public DTO에서 camelCase 대표 필드를 만들더라도 raw `content_metadata` map은 제거하지 않는다.
- unknown nested metadata field를 whitelist로 잘라내지 않는다.
- `message_id`, `attachment_id`, `page_count`, `ocr_page_count`, `provider`, `languages`, `image_width`, `image_height`를 그대로 저장/조회한다.
- `runtime_config.requires_content=true` 정책은 기존 content-dependent action 기준을 유지한다.
- OCR/vision provider 설정값이나 provider API key를 Spring runtime payload에 넣지 않는다.
- execution log/callback/public detail에서 `content`가 truncate될 수 있다는 기존 정책을 유지한다.

권장 테스트 fixture:

- Gmail attachment 추출 성공: `source_service=gmail`, `message_id`, `attachment_id`, `extraction_method=pdf_text` 보존.
- Gmail attachment 추출 실패: `nodeLogs[].error.context.message_id`, `attachment_id`, `filename` 보존.
- scan PDF page limit 초과: `content_status=too_large`, `limits.max_ocr_pages`, `page_count` 보존.
- image mixed 결과: `content_kind=mixed`, `provider`, `languages` 보존.
- provider disabled: `content_status=unsupported`를 실패 실행으로 과도하게 재분류하지 않는지 확인.

---

## 11. Error/Status Mapping

| 상황 | `content_status` | 비고 |
|------|------------------|------|
| feature flag off | `unsupported` | 다운로드/provider 호출 없음 |
| provider key missing | `unsupported` | OCR/vision provider 호출 없음 |
| unsupported file type | `unsupported` | 기존 정책 유지 |
| Gmail inline image | `unsupported` | 1차 범위 제외 |
| download bytes 초과 | `too_large` | `observed_size_bytes` 기록 |
| PDF OCR page 초과 | `too_large` | `observed_page_count`, `max_ocr_pages` 기록 |
| image pixel 초과 | `too_large` | `observed_image_pixels`, `max_image_pixels` 기록 |
| OCR 결과 없음 | `empty` | 추출은 실행됐지만 읽을 텍스트 없음 |
| provider/API/parsing 예외 | `failed` | error context 보존 |
| PDF text layer 존재 | `available` | OCR fallback 없이 `pdf_text` |

---

## 12. 검증 결과

변경 관련 테스트:

```text
python3 -m pytest tests/test_integrations/test_google_drive.py tests/test_integrations/test_gmail.py tests/test_input_node.py tests/test_llm_node.py tests/test_preview_executor.py
=> 93 passed
```

Scoped lint:

```text
python3 -m ruff check app/config.py app/core/document_content.py app/core/engine/preview_executor.py app/core/nodes/input_node.py app/core/nodes/llm_node.py app/services/integrations/gmail.py app/services/integrations/google_drive.py app/services/llm_service.py tests/test_input_node.py tests/test_integrations/test_gmail.py tests/test_integrations/test_google_drive.py tests/test_llm_node.py tests/test_preview_executor.py
=> All checks passed
```

Whitespace check:

```text
git diff --check
=> passed
```

전체 회귀:

```text
python3 -m pytest --ignore=tests/test_trigger_api.py
=> 403 passed, 17 warnings
```

`tests/test_trigger_api.py`는 로컬 sandbox에서 MongoDB SRV DNS/network 접근이 막히는 환경 이슈가 있어 별도 네트워크 가능 환경에서 확인이 필요하다.

---

## 13. 잔여 리스크

- OCR/vision은 비용과 latency가 크므로 운영 feature flag를 켤 때 rate limit과 timeout 관찰이 필요하다.
- `openai_vision` provider는 confidence score를 제공하지 않으므로 `confidence`는 비어 있을 수 있다.
- `GoogleDriveService`가 현재 공통 byte extractor 역할까지 맡고 있어 파일이 커졌다. 동작 안정화 후 별도 extractor module로 분리할 수 있다.
- Gmail `include_content=true` preview는 대상 email의 attachment를 순차 추출한다. attachment가 많은 email에서는 preview latency가 늘 수 있다.
- GIF/HEIC, multi-page TIFF 같은 확장 이미지 형식은 1차에서 provider/format 지원에 따라 `unsupported` 또는 provider 실패가 될 수 있다.

