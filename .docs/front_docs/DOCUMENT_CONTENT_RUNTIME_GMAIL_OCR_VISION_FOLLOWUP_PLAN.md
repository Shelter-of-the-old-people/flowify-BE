# Gmail attachment/OCR/Vision 문서 본문 런타임 후속 계획

> 작성일: 2026-05-17
> 목적: 기존 문서 본문 런타임 계약 위에 아직 남아 있는 Gmail attachment 본문 추출, scan PDF OCR, image OCR/vision 처리를 구현 가능한 단위로 분해한다.
> 기준 문서:
> - `docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `docs/backend/DOCUMENT_CONTENT_RUNTIME_BACKEND_IMPLEMENTATION_HANDOFF.md`
> - `docs/backend/DOCUMENT_CONTENT_RUNTIME_IMPLEMENTATION_REPORT.md`
> - `docs/backend/DOCUMENT_CONTENT_RUNTIME_FINAL_IMPLEMENTATION_REVIEW.md`
> - `docs/backend/DOCUMENT_CONTENT_RUNTIME_FRONTEND_INTEGRATION_REVIEW.md`
> - `docs/backend/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`
> - `docs/GMAIL_NODE_OPTION_C_IMPLEMENTATION_PLAN.md`
> - `docs/WORKFLOW_FILE_TYPE_BRANCH_FRONTEND_DESIGN.md`
> - `docs/WORKFLOW_NODE_PREVIEW_DRY_RUN_DESIGN.md`
> - `docs/FOLDER_DOCUMENT_SUMMARY_TEMPLATE_DESIGN.md`
> - `docs/FILE_UPLOAD_AUTO_SHARE_TEMPLATE_DESIGN.md`

---

## 1. 현재 판단

문서 본문 런타임의 계약/경로 안정화와 Google Drive 기반 주요 문서 extractor는 완료된 것으로 본다. 현재 완료 범위에는 `SINGLE_FILE`, `FILE_LIST.items[]`, Gmail attachment 공통 content 상태 필드, `DOCUMENT_CONTENT_*` error contract, TXT/CSV/TSV/PDF text/DOCX/PPTX/HWPX/Google Workspace 추출 경로가 포함된다.

남은 항목은 기능 자체의 부재다.

| 항목 | 현재 상태 | 사용자 영향 |
|------|-----------|-------------|
| Gmail attachment 본문 추출 | attachment metadata와 content status field는 있으나 attachment download + extractor 연결이 없음 | Gmail 첨부 문서 요약이 파일명/상태 표시에서 멈춤 |
| scan PDF OCR | 텍스트 레이어 없는 PDF는 OCR 미지원 `unsupported`로 명확히 실패 | 스캔본 강의자료/영수증/계약서 PDF를 요약할 수 없음 |
| image OCR/vision | image file은 상태 표시 가능하지만 OCR/vision extractor 없음 | 이미지 branch 뒤의 `ocr`, `describe_image` action이 실제 본문/설명을 만들지 못함 |

따라서 후속 작업의 목표는 새 payload 계약을 다시 만드는 것이 아니라, 이미 합의된 `content`, `content_status`, `content_error`, `content_metadata` 계약에 실제 추출기를 연결하는 것이다.

---

## 2. 관련 문서에서 확인한 공백

### 2.1 Gmail attachment

`GMAIL_NODE_OPTION_C_IMPLEMENTATION_PLAN.md`는 Gmail source/sink/OAuth 진입을 열어두되, `attachment content download/전달`을 후속 범위로 명시한다.

`DOCUMENT_CONTENT_RUNTIME_BACKEND_IMPLEMENTATION_HANDOFF.md`는 Gmail attachment가 파일 카드 helper로 처리될 수 있도록 `content_status`, `content_error`, `content_metadata`를 가진다고 정리했지만, 현재 1차 구현은 attachment download와 공통 extractor 연결을 포함하지 않는다.

필요한 보강:

- Gmail API에서 attachment bytes를 가져오는 downloader.
- `messageId`, `attachmentId`, `filename`, `mime_type`, `size`를 common file extraction input으로 변환하는 adapter.
- Gmail attachment를 기존 Drive file extractor와 같은 registry로 보내는 경로.
- attachment content가 필요한 action에서 `not_requested`를 빈 성공으로 넘기지 않는 실패 처리.
- Gmail readonly scope 부족, attachment 없음, inline image, 대용량 attachment, base64url decode 실패에 대한 error mapping.

### 2.2 Scan PDF OCR

`DOCUMENT_CONTENT_RUNTIME_IMPLEMENTATION_REPORT.md`와 `DOCUMENT_CONTENT_RUNTIME_FINAL_IMPLEMENTATION_REVIEW.md`는 PDF text layer 추출은 완료됐지만, 텍스트 레이어 없는 PDF는 OCR 미지원 `unsupported`로 반환한다고 정리한다.

필요한 보강:

- PDF text extraction 결과가 비어 있거나 너무 적은 경우 scan PDF로 판별하는 기준.
- PDF page를 이미지로 렌더링하는 단계.
- OCR provider 연결.
- page count, render DPI, max image pixels, max OCR pages 같은 제한값.
- OCR 결과를 page 순서대로 합쳐 `content_kind=ocr_text` 또는 `mixed`로 반환하는 정규화.

### 2.3 Image OCR/Vision

`WORKFLOW_FILE_TYPE_BRANCH_FRONTEND_DESIGN.md`는 PDF/image/other 분기와 image branch 뒤의 AI 설명 생성 흐름을 전제로 한다. `DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`도 image common file을 OCR 또는 vision 모델 기반 text/description 추출의 조건부 지원군으로 둔다.

필요한 보강:

- 이미지 파일 판별과 안전한 decode/normalize.
- `ocr` action과 `describe_image` action의 결과 의미 분리.
- OCR 텍스트는 `content_kind=ocr_text`, vision 설명은 `content_kind=image_description`, 둘을 합치면 `mixed`.
- animated GIF/HEIC/TIFF multi-page 같은 확장 형식의 1차 지원 여부 결정.
- vision description을 OCR 결과처럼 확정 텍스트로 오해하지 않도록 metadata에 extraction source를 남김.

---

## 3. 목표 계약

기존 canonical field는 유지한다.

```json
{
  "content": "추출 텍스트 또는 이미지 설명",
  "content_status": "available|empty|unsupported|too_large|failed|not_requested",
  "content_error": null,
  "content_metadata": {
    "extraction_method": "pdf_text|docx_xml|pptx_xml|hwpx_xml|plain_text|csv_parse|ocr|vision|none",
    "content_kind": "plain_text|ocr_text|image_description|mixed|none",
    "truncated": false,
    "char_count": 0,
    "original_char_count": 0,
    "limits": {
      "max_download_bytes": 10485760,
      "max_extracted_chars": 60000,
      "max_llm_input_chars": 60000
    }
  }
}
```

후속 구현에서는 아래 metadata를 추가할 수 있다. FE는 표시 필수값으로 보지 않고 디버깅/상태 설명용으로만 사용한다.

```json
{
  "content_metadata": {
    "source_service": "gmail",
    "message_id": "msg-1",
    "attachment_id": "att-1",
    "page_count": 3,
    "ocr_page_count": 3,
    "image_width": 1200,
    "image_height": 800,
    "provider": "configured_ocr_provider",
    "confidence": 0.92
  }
}
```

주의:

- `content`는 계속 LLM/UI용 canonical text representation이다.
- 원본 attachment bytes나 base64는 `content`에 넣지 않는다.
- Gmail attachment 여부는 `extraction_method`가 아니라 `source_service=gmail`, `message_id`, `attachment_id`로 표현한다. `extraction_method`는 실제 본문을 만든 parser/provider를 기록한다.
- preview 기본값은 계속 metadata-only이며, `include_content=true` 또는 `requires_content=true` 실행 경로에서만 실제 추출을 수행한다.

---

## 4. 구현 순서

### Phase 0. 계약/설정 정리

목표: 기능을 붙이기 전에 provider, limit, fixture, error behavior를 고정한다.

작업:

1. FastAPI document content 설정에 OCR/vision 관련 flag를 추가한다.
   - `enable_gmail_attachment_extraction`
   - `enable_pdf_ocr`
   - `enable_image_ocr`
   - `enable_image_vision`
   - `max_ocr_pages`
   - `max_image_pixels`
2. `content_metadata.limits`에 OCR/image 관련 제한값을 optional로 추가한다.
3. `DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`에 아래 fixture를 추가한다.
   - Gmail attachment available
   - Gmail attachment too_large
   - scan PDF OCR available
   - image OCR available
   - image vision available
   - image OCR/vision unsupported
4. error code는 기존 `DOCUMENT_CONTENT_*`를 우선 재사용한다.
5. provider가 꺼져 있으면 `content_status=unsupported`, 사용자 문구는 “현재 OCR/이미지 분석을 지원하지 않습니다.” 계열로 통일한다.

완료 기준:

- 설정값이 없어도 기존 문서 본문 런타임이 깨지지 않는다.
- 기능 비활성 상태에서 status/error가 기존 FE 표시 계약으로 자연스럽게 내려간다.

### Phase 1. Gmail attachment download + common extractor 연결

목표: Gmail 첨부파일을 Drive 파일과 같은 extractor registry로 보낸다.

작업:

1. Gmail message part traversal을 구현한다.
   - nested `parts`에서 filename이 있고 attachment id가 있는 part 수집.
   - inline image와 일반 attachment를 구분하되 1차는 일반 attachment만 본문 추출 대상으로 둔다.
2. Gmail attachment downloader를 구현한다.
   - `messageId`, `attachmentId`로 attachment body 조회.
   - base64url decode.
   - 다운로드 전후 size limit 검증.
3. attachment file object를 common extractor input으로 변환한다.
   - `source_service=gmail`
   - `message_id`
   - `attachment_id`
   - `filename`
   - `mime_type`
   - `size`
   - `bytes`
4. 기존 TXT/CSV/PDF text/DOCX/PPTX/HWPX extractor를 attachment에도 적용한다.
5. `attachment_email` source의 `FILE_LIST.items[]`와 `SINGLE_EMAIL.email.attachments[]` shape를 같은 content contract로 맞춘다.
6. `requires_content=true`이고 attachment extraction이 실패하면 `DOCUMENT_CONTENT_*` error context에 filename/messageId/attachmentId를 포함한다.

완료 기준:

- Gmail attachment PDF text/DOCX/TXT/CSV가 `content_status=available`로 내려온다.
- metadata-only preview에서는 `not_requested`가 유지된다.
- content 요청 또는 실행 경로에서는 attachment body를 다운로드해 extractor를 수행한다.
- Gmail 첨부 요약이 attachment filename 요약이 아니라 본문 기반 요약이 된다.

### Phase 2. Image OCR/Vision core

목표: 이미지 단일 파일을 텍스트 또는 설명으로 변환하는 공통 엔진을 만든다. Scan PDF OCR도 이 엔진을 재사용한다.

작업:

1. image extractor registry를 추가한다.
   - 1차 대상: `png`, `jpg`, `jpeg`, `webp`, `bmp`, `tif`, `tiff`.
   - `gif`, `heic`은 1차에서 `unsupported`로 둘 수 있다.
2. 이미지 decode/normalize 단계를 만든다.
   - EXIF orientation 반영.
   - 최대 pixel 제한.
   - 필요 시 RGB 변환.
3. action별 처리 정책을 분리한다.
   - `ocr`: OCR provider 호출, `content_kind=ocr_text`, `extraction_method=ocr`.
   - `describe_image`: vision provider 호출, `content_kind=image_description`, `extraction_method=vision`.
   - `summarize`/`ai_analyze`: OCR 우선, OCR 결과가 없고 vision enabled이면 description fallback 또는 `mixed`.
4. provider disabled/timeout/rate limit을 `unsupported` 또는 `failed`로 정규화한다.
5. OCR 결과가 빈 문자열이면 `empty`로 처리한다.

완료 기준:

- image branch 뒤 `ocr` action은 이미지 안의 텍스트를 LLM input으로 전달한다.
- image branch 뒤 `describe_image` action은 이미지 설명을 LLM input으로 전달한다.
- OCR과 vision 결과가 metadata에서 구분된다.
- provider 미설정 환경에서도 기존 runtime은 실패하지 않고 명확한 `unsupported`를 반환한다.

### Phase 3. Scan PDF OCR fallback

목표: 텍스트 레이어가 없는 PDF를 page image OCR로 처리한다.

작업:

1. PDF text extraction 후 scan 판별 기준을 추가한다.
   - text char count가 0이거나 page 대비 너무 적으면 OCR fallback 대상.
   - 파일이 image-only PDF인지 metadata에 기록.
2. PDF page render 단계를 추가한다.
   - max page count 제한.
   - render DPI 제한.
   - page별 image size 제한.
3. Phase 2의 OCR core를 page별로 호출한다.
4. page 순서와 page separator를 유지해 content를 합친다.
5. 일부 page OCR 실패 시 정책을 정한다.
   - 모든 page 실패: `failed` 또는 `empty`.
   - 일부 성공: `available`, `content_metadata.partial=true` optional.
6. 텍스트 레이어와 OCR 결과가 섞인 PDF는 `content_kind=mixed`로 둘 수 있다.

완료 기준:

- 텍스트 레이어 없는 scan PDF가 OCR provider 활성 상태에서 `content_status=available`이 된다.
- OCR 비활성 상태에서는 기존처럼 `unsupported`가 유지된다.
- 너무 큰 PDF나 page 제한 초과는 `too_large`로 실패한다.
- page 순서가 LLM input에서 보존된다.

### Phase 4. 통합 검증과 문구 정리

목표: 새 기능이 문서/파일 템플릿, Gmail source, 파일 종류 분기 UX와 모순 없이 동작하는지 확인한다.

작업:

1. FastAPI unit test 추가.
   - Gmail attachment download/decode.
   - attachment -> common extractor.
   - image OCR/vision success/empty/unsupported/failed.
   - scan PDF OCR success/too_large/unsupported.
2. LLM integration-like test 추가.
   - Gmail attachment PDF -> AI summarize.
   - Image -> OCR -> AI summarize.
   - Image -> describe_image.
   - Scan PDF -> AI summarize.
3. Spring contract test 확인.
   - 기존 `DOCUMENT_CONTENT_*` mapping이 신규 OCR/Gmail context를 보존하는지 확인.
   - 필요 시 `content_metadata` nested field 보존 fixture 추가.
4. FE fixture/rendering test 확장.
   - `DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json` 신규 fixture 기준.
   - Gmail attachment card에서 available/too_large/unsupported 표시.
   - image/PDF OCR 결과가 “본문 일부만 표시” 정책과 충돌하지 않는지 확인.
5. 템플릿/도움말 문구 갱신.
   - OCR/vision이 켜진 경우와 꺼진 경우의 지원 범위를 과장하지 않는다.

완료 기준:

- 세 기능 모두 sample payload, unit test, integration-like test가 있다.
- 사용자는 미지원/비활성 상태를 빈 요약 성공으로 보지 않는다.
- 문서 요약 템플릿과 파일 종류 분기 흐름에서 PDF/image branch가 실제 extractor 결과를 downstream으로 전달한다.

---

## 5. 우선순위

권장 순서는 다음과 같다.

1. **Gmail attachment download + common extractor 연결**
   - 새 OCR provider 없이도 기존 DOCX/PPTX/HWPX/PDF text/TXT/CSV extractor를 즉시 재사용할 수 있다.
   - Gmail 첨부 문서 요약이라는 사용자 흐름을 가장 빨리 복구한다.
2. **Image OCR/Vision core**
   - scan PDF OCR이 page image OCR을 재사용할 수 있으므로 먼저 공통 이미지 처리 계층을 만든다.
3. **Scan PDF OCR fallback**
   - PDF render와 page orchestration이 추가로 필요하므로 image OCR core 이후가 안전하다.
4. **Cross-service E2E와 FE fixture 확장**
   - 기능별 extractor가 붙은 뒤 Spring/FastAPI/FE 계약 회귀를 고정한다.

---

## 6. 수용 기준

### 6.1 Gmail attachment

- `attachment_email` source가 attachment metadata-only preview와 content-included execution을 구분한다.
- 지원 파일 attachment는 `content_status=available`과 추출된 `content`를 가진다.
- 미지원/대용량/권한 부족/다운로드 실패는 `DOCUMENT_CONTENT_*` 또는 OAuth error로 구분된다.
- `messageId:attachmentId` 기준으로 error context와 debug trace를 추적할 수 있다.

### 6.2 Scan PDF OCR

- text layer PDF는 기존 `pdf_text` 경로를 유지한다.
- scan PDF는 OCR enabled일 때 `ocr` 경로로 fallback한다.
- OCR disabled일 때는 `unsupported`와 사용자 표시 가능한 사유를 반환한다.
- page limit, render limit, char limit이 metadata에 남는다.

### 6.3 Image OCR/Vision

- `ocr` action은 OCR 텍스트를 생성한다.
- `describe_image` action은 이미지 설명을 생성한다.
- `summarize`/`ai_analyze`는 image content를 사용할 때 OCR/vision 결과의 출처를 metadata에 남긴다.
- image branch 결과가 `FILE_LIST -> LOOP -> AI` 경로에서 손실되지 않는다.

---

## 7. PR/릴리즈 표현

기능 완료 전까지 피해야 할 표현:

- “Gmail 첨부파일 본문 추출 완료”
- “스캔 PDF OCR 완료”
- “이미지 OCR/vision 완료”
- “모든 파일 완전 호환”

기능별 완료 후 사용할 수 있는 표현:

- “Gmail attachment를 공통 문서 extractor에 연결했습니다.”
- “텍스트 레이어 없는 PDF에 OCR fallback을 추가했습니다.”
- “이미지 파일의 OCR/vision 기반 content extraction을 추가했습니다.”
- “OCR/vision 비활성 또는 미지원 상태를 `DOCUMENT_CONTENT_*` contract로 명확히 반환합니다.”

---

## 8. 남은 결정 사항

1. OCR/vision provider를 무엇으로 둘지 결정해야 한다.
   - 자체 OCR, cloud OCR, LLM vision 등 provider를 바꿀 수 있도록 interface를 먼저 둔다.
2. Korean/English OCR 언어 설정을 기본 지원 범위에 포함할지 결정해야 한다.
3. scan PDF OCR의 page limit 기본값을 정해야 한다.
4. image `summarize`에서 OCR만 사용할지, OCR + vision mixed를 기본으로 할지 결정해야 한다.
5. Gmail inline image를 attachment extraction 범위에 포함할지 결정해야 한다.
6. OCR/vision 결과를 실행 로그에 얼마나 저장할지, 기존 4,000자 truncate 정책으로 충분한지 확인해야 한다.

---

## 9. 한 줄 결론

현재 남은 작업은 계약 재설계가 아니라 extractor 확장이다. Gmail attachment는 기존 extractor를 재사용하는 downloader/adapter 작업으로 먼저 처리하고, image OCR/vision core를 만든 뒤 그 위에 scan PDF OCR fallback을 얹는 순서가 가장 안전하다.
