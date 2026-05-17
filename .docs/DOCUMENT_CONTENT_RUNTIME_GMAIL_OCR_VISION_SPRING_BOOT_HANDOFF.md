# Gmail attachment/OCR/Vision 후속 결정 및 Spring Boot 전달 문서

> 작성일: 2026-05-17  
> 전달 대상: Spring Boot 팀  
> 관련 문서:
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_GMAIL_OCR_VISION_FOLLOWUP_PLAN.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_SPRING_FASTAPI_COMPATIBILITY_CHECK.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_BACKEND_IMPLEMENTATION_HANDOFF.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`

---

## 1. 전달 요약

Gmail attachment 본문 추출, scan PDF OCR, image OCR/vision 후속 구현에 앞서 남은 결정 사항을 아래처럼 확정한다.

핵심 방향은 기존 문서 본문 런타임 계약을 바꾸지 않고, FastAPI extractor를 확장하는 것이다. Spring Boot는 provider 세부 구현을 알 필요 없이 기존 `content`, `content_status`, `content_error`, `content_metadata`, `DOCUMENT_CONTENT_*` error context를 보존하면 된다.

Spring Boot 쪽에서 즉시 확인해야 하는 부분:

- `content_metadata` 안에 신규 OCR/vision/Gmail attachment metadata가 추가되어도 raw map을 손실 없이 저장/조회한다.
- public API에서 camelCase 대표값을 만들더라도 raw snake_case metadata를 함께 보존한다.
- `runtime_config.requires_content=true` 생성 경로는 기존 정책을 유지한다.
- OCR/vision provider 설정값이나 provider API key는 Spring runtime payload로 전달하지 않는다.
- 실행 로그와 callback/public 조회의 `content`는 계속 4,000자 기준으로 truncate될 수 있음을 FE/API 문구에서 유지한다.

---

## 2. 결정 사항

| 번호 | 항목 | 결정 |
|------|------|------|
| 1 | OCR/vision provider | FastAPI에 provider interface를 먼저 두고, MVP 기본 provider는 기존 LLM 연동을 재사용하는 `openai_vision`으로 둔다. provider가 없거나 비활성화되면 `unsupported`를 반환한다. |
| 2 | OCR 언어 | OCR 기본 지원 언어는 Korean/English로 둔다. 별도 사용자 설정은 1차에서 만들지 않는다. |
| 3 | scan PDF OCR page limit | 기본 `max_ocr_pages=10`으로 둔다. preview는 필요 시 더 작은 내부 제한을 둘 수 있으나 canonical metadata에는 실제 적용 제한을 기록한다. |
| 4 | image `summarize` 정책 | `summarize`/`ai_analyze`는 OCR + vision mixed를 기본으로 한다. `ocr` action은 OCR만, `describe_image` action은 vision만 사용한다. |
| 5 | Gmail inline image | 1차 attachment extraction 범위에서 inline image는 제외한다. 일반 첨부파일만 본문 추출 대상으로 둔다. |
| 6 | OCR/vision 로그 저장 | 기존 4,000자 execution log truncate 정책을 유지한다. LLM 입력용 추출 본문 제한은 기존 `max_extracted_chars`/`max_llm_input_chars`를 따른다. |

---

## 3. 결정 근거

### 3.1 Provider는 `openai_vision` MVP + interface

FastAPI는 이미 `LLM_API_KEY`, `LLM_API_BASE_URL`, `LLM_MODEL_NAME` 기반 LLM 연동을 가지고 있다. 따라서 1차 OCR/vision 구현에서 새 cloud OCR 계정, service account, Spring payload 변경을 요구하지 않는 `openai_vision`이 가장 구현 부담이 작다.

다만 OCR provider는 나중에 Google Cloud Vision, 자체 OCR, Tesseract 등으로 바뀔 수 있으므로 FastAPI 내부에는 provider interface를 먼저 둔다. Spring Boot는 provider 이름을 실행 요청에 넣지 않고, 결과 metadata의 `provider`, `extraction_method`, `content_kind`만 보존한다.

provider disabled 또는 API key 미설정 상태는 런타임 실패가 아니라 지원 범위 문제로 보고 `content_status=unsupported`와 `DOCUMENT_CONTENT_UNSUPPORTED` 계열 context로 정규화한다.

### 3.2 OCR 언어는 Korean/English 기본

현재 문서 본문 런타임은 UTF-8 BOM, CP949 등 한국어 문서 인코딩을 이미 주요 범위로 보고 있다. 실제 사용 문서도 한국어 강의자료, 영수증, 계약서와 영어 자료가 섞일 가능성이 높다.

따라서 OCR prompt/provider hint의 기본 언어를 Korean/English로 고정한다. 사용자별 언어 선택 UI나 Spring catalog field는 1차 범위에 넣지 않는다. 필요하면 이후 `runtime_config.ocr_languages` 같은 명시 옵션을 별도 이슈로 추가한다.

### 3.3 Scan PDF OCR page limit은 10페이지

OCR/vision은 PDF text extraction보다 비용과 latency가 크다. 현재 시스템의 LLM 처리 목표와 실행 안정성을 고려하면 scan PDF 전체를 무제한 OCR하는 것은 위험하다.

기본 제한은 `max_ocr_pages=10`으로 둔다. 10페이지를 넘는 scan PDF는 기본적으로 `content_status=too_large`로 처리하고, metadata에 `page_count`, `ocr_page_count`, `limits.max_ocr_pages`를 남긴다. 일부 page만 OCR하는 부분 성공 정책은 별도 제품 요구가 생기면 추가한다.

### 3.4 Image summarize는 mixed 기본

이미지 파일의 `summarize`/`ai_analyze`는 단순 문서 OCR뿐 아니라 캡처, 사진, 표, 안내 이미지처럼 시각 정보 자체가 의미를 갖는 경우가 많다. OCR만 사용하면 텍스트가 적은 이미지에서 빈 결과가 나오고, vision만 사용하면 이미지 안의 정확한 문구가 약해진다.

따라서 `summarize`/`ai_analyze`는 OCR 텍스트와 vision description을 함께 넣는 `content_kind=mixed`를 기본으로 한다. 단, action 의미가 명확한 경우는 분리한다.

- `ocr`: OCR 텍스트만 사용, `content_kind=ocr_text`, `extraction_method=ocr`
- `describe_image`: vision 설명만 사용, `content_kind=image_description`, `extraction_method=vision`
- `summarize`/`ai_analyze`: OCR + vision, `content_kind=mixed`, `extraction_method=vision` 또는 `mixed`

Spring/FE는 `content_kind=mixed`를 일반 텍스트처럼 표시하되, metadata에서 OCR/vision source를 구분할 수 있어야 한다.

### 3.5 Gmail inline image는 1차 제외

Gmail inline image에는 서명 이미지, 로고, 추적 픽셀, 장식 이미지가 많이 포함된다. 이를 첨부 본문 추출 대상으로 포함하면 사용자가 기대한 "첨부 문서 요약"과 다른 내용이 LLM 입력에 섞일 수 있고 비용도 커진다.

1차에서는 `Content-Disposition: attachment`이거나 일반 첨부로 판단 가능한 part만 추출한다. inline image는 metadata에 `inline=true` 또는 `content_status=not_requested|unsupported`로 남길 수 있지만, 본문 추출 대상에는 포함하지 않는다.

### 3.6 Log truncate는 기존 4,000자 유지

OCR/vision 결과는 이미지 안의 민감정보를 포함할 수 있다. 또한 긴 OCR 결과를 execution log, callback, public 조회에 그대로 저장하면 Mongo document 크기와 FE 표시 비용이 커진다.

따라서 기존 정책을 유지한다.

- extractor/LLM 입력용 content 최대: `content_metadata.limits.max_extracted_chars`, `max_llm_input_chars`
- execution log/callback/public 조회 저장 content 최대: 기존 4,000자
- truncate 시 metadata: `truncated_for_log=true`, `stored_content_truncated=true`, `stored_char_count=4000`

FE와 Spring public API는 조회된 `content`를 전체 원문이 아니라 "본문 미리보기"로 취급해야 한다.

---

## 4. FastAPI 변경 예정 사항

### 4.1 설정값 추가

FastAPI 설정에 아래 값을 추가한다. Spring Boot runtime payload로 전달하지 않는다.

```text
ENABLE_GMAIL_ATTACHMENT_EXTRACTION=false
ENABLE_PDF_OCR=false
ENABLE_IMAGE_OCR=false
ENABLE_IMAGE_VISION=false
OCR_PROVIDER=openai_vision
VISION_PROVIDER=openai_vision
VISION_MODEL_NAME=<LLM_MODEL_NAME 또는 별도 vision-capable model>
OCR_LANGUAGES=ko,en
MAX_OCR_PAGES=10
MAX_IMAGE_PIXELS=<FastAPI 기본값>
```

설정이 꺼져 있거나 provider key가 없으면 기존 런타임은 깨지지 않고 `unsupported`를 반환한다.

### 4.2 `content_metadata.limits` 확장

기존 limits는 유지하고 OCR/image 관련 optional field를 추가한다.

```json
{
  "content_metadata": {
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

Spring은 unknown nested field를 제거하지 않는다.

### 4.3 Gmail attachment metadata 추가

Gmail attachment 추출 결과에는 아래 metadata가 추가될 수 있다.

```json
{
  "content_metadata": {
    "source_service": "gmail",
    "message_id": "msg-1",
    "attachment_id": "att-1",
    "inline": false,
    "provider": "openai_vision"
  }
}
```

`extraction_method`는 `gmail_attachment`가 아니라 실제 본문 생성 방식인 `pdf_text`, `docx_xml`, `plain_text`, `ocr`, `vision`, `mixed` 등을 기록한다.

### 4.4 OCR/vision metadata 추가

OCR/vision 결과에는 아래 metadata가 추가될 수 있다.

```json
{
  "content_metadata": {
    "extraction_method": "ocr",
    "content_kind": "ocr_text",
    "provider": "openai_vision",
    "languages": ["ko", "en"],
    "page_count": 3,
    "ocr_page_count": 3,
    "image_width": 1200,
    "image_height": 800,
    "confidence": null
  }
}
```

`confidence`는 provider가 신뢰도를 제공할 때만 채운다. LLM vision provider처럼 confidence가 없는 경우 `null`이거나 생략될 수 있다.

### 4.5 Error/status 정책

| 상황 | content_status | error code 방향 |
|------|----------------|-----------------|
| provider disabled/key missing | `unsupported` | `DOCUMENT_CONTENT_UNSUPPORTED` |
| OCR 결과 빈 문자열 | `empty` | `DOCUMENT_CONTENT_EMPTY` |
| page/image limit 초과 | `too_large` | `DOCUMENT_CONTENT_TOO_LARGE` |
| provider timeout/rate limit/API failure | `failed` | `DOCUMENT_CONTENT_EXTRACTION_FAILED` 또는 외부 API error context |
| Gmail scope 부족 | 실행 실패 | OAuth scope 부족 error 유지 |

---

## 5. Spring Boot 변경/확인 요청

### 5.1 저장/조회 contract

Spring Boot는 아래 필드를 계속 손실 없이 저장/조회해야 한다.

- `content`
- `content_status`
- `content_error`
- `content_metadata`
- `content_metadata.limits.*`
- `nodeLogs[].error.code`
- `nodeLogs[].error.context`

신규 metadata field는 optional로 취급한다. public DTO에서 camelCase 대표값을 추가하더라도 raw snake_case map을 제거하지 않는다.

### 5.2 `requires_content` 정책 유지

아래 action은 기존처럼 content-dependent로 유지한다.

- `summarize`
- `extract_info`
- `translate`
- `classify_by_content`
- `describe_image`
- `ocr`
- `ai_summarize`
- `ai_analyze`

Spring은 OCR/vision provider 설정을 판단하지 않고, 사용자의 action 의도만 기준으로 `runtime_config.requires_content=true`를 내려준다. 실제 provider 활성/비활성 판단은 FastAPI가 한다.

### 5.3 Preview 요청 정책

source node preview 기본값은 metadata-only로 유지할 수 있다. 다만 image/PDF/Gmail attachment 뒤의 content-dependent node를 preview할 때는 기존 정책처럼 `includeContent=true` 또는 동등한 runtime flag를 전달한다.

Spring public metadata는 기존 `contentPolicy=metadata_only|content_included|content_status_only`를 유지한다.

### 5.4 Error context 보존 테스트

Spring test fixture에 아래 케이스를 추가하는 것을 권장한다.

- Gmail attachment OCR 실패 시 `message_id`, `attachment_id`, `filename` 보존
- scan PDF page limit 초과 시 `limits.max_ocr_pages`, `page_count` 보존
- image summarize mixed 결과에서 `content_kind=mixed`, `provider`, `languages` 보존
- execution detail/node data 조회에서 `nodeLogs[].error.code/context` 보존

### 5.5 사용자 표시 문구 주의

Spring/FE public 조회에서 `content`는 전체 원문이 아닐 수 있다. 기존과 동일하게 "전체 본문"이 아니라 "본문 미리보기" 또는 "추출 본문 일부"로 표현한다.

OCR/vision 비활성 상태에서는 기능 실패가 아니라 지원 범위 안내로 표시한다.

---

## 6. Spring Boot 관점 호환성 결론

이번 결정으로 Spring Boot와 FastAPI 사이의 요청/응답 top-level 계약은 바뀌지 않는다.

변경되는 것은 `content_metadata` 내부 optional field와 지원 가능한 extractor 범위다. Spring Boot는 기존처럼 raw payload와 error context를 보존하면 되고, provider 설정이나 OCR page rendering 같은 구현 세부사항을 알 필요가 없다.

따라서 Spring Boot의 필수 작업은 코드 대수술이 아니라 fixture/test 보강과 public 표시 문구 확인이다.

