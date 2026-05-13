# Fast Api 팀 문서 본문 런타임 구현 점검 보고서

> 작성일: 2026-05-14  
> 브랜치: `feat/26-runtime-document`  
> 기준 문서:
> - `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_ANALYSIS_AND_IMPLEMENTATION_PLAN.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_FE_DESIGN_REVIEW.md`

---

## 1. 구현 결론

계약/경로 안정화 MVP 기준 구현은 반영되었다.

이번 구현은 문서 본문 canonical contract가 런타임 경로에 안정적으로 흐르도록 만드는 1차 기반 작업이며, 최종 보강으로 원문 1차 필수 파일군인 DOCX/PPTX/HWPX extractor도 반영했다.

완료된 범위:

- `SINGLE_FILE`, `FILE_LIST.items[]`, Gmail attachment에 `content_status`, `content_error`, `content_metadata` 기본 필드 추가
- legacy `extracted_text`, `extraction_status` 병행 유지
- preview metadata에 실제 본문 포함 여부 기준 `content_policy` 추가
- Google Drive extraction result를 legacy shape와 신규 content shape로 동시 반환
- `content_metadata.limits` 기본 포함
- 다운로드/추출 크기 제한 초과 시 `content_status=too_large` 생성
- 사용자 표시 가능한 짧은 `content_error`만 payload에 노출
- DOCX paragraph/table text 추출
- PPTX slide order/title/body/note text 추출
- HWPX zip XML body text 추출
- 텍스트 레이어 없는 PDF는 OCR 미지원 `unsupported`로 반환
- LLM content-dependent action에서 본문 추출 실패를 빈 요약 성공으로 처리하지 않도록 변경
- `DOCUMENT_CONTENT_*` error code 추가
- 실행 로그 저장 전 긴 `content` truncate 처리 및 기존 `content_metadata` 보존
- `ErrorDetail.context`에 `content_status`, `content_error` 같은 실패 context 보존
- FE/Spring 계약 검토 문서 추가

---

## 2. 주요 변경 파일

### 신규 파일

- `app/core/document_content.py`
  - 문서 본문 상태 기본값, extraction result builder, legacy mapping, log truncate helper
- `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_FE_DESIGN_REVIEW.md`
  - FE 설계 검토 및 BE contract 정합성 문서
- `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`
  - FE/Spring contract test용 상태별 sample payload fixture
- `.docs/DOCUMENT_CONTENT_RUNTIME_IMPLEMENTATION_REPORT.md`
  - 본 보고서

### 수정 파일

- `app/common/errors.py`
  - `DOCUMENT_CONTENT_UNSUPPORTED`
  - `DOCUMENT_CONTENT_TOO_LARGE`
  - `DOCUMENT_CONTENT_EXTRACTION_FAILED`
  - `DOCUMENT_CONTENT_NOT_REQUESTED`
  - `DOCUMENT_CONTENT_EMPTY`
- `app/models/canonical.py`
  - file/email attachment canonical model에 content 상태 필드 추가
- `app/models/execution.py`
  - `ErrorDetail.context` 추가
- `app/core/nodes/input_node.py`
  - Google Drive file payload와 Gmail attachment payload에 content 상태 기본값 추가
- `app/core/engine/preview_executor.py`
  - preview metadata `content_policy` 추가
  - `include_content=true` 요청이어도 실제 content가 없으면 `content_status_only`/`metadata_only`로 보정
  - preview file payload content 상태 필드 추가
  - include_content extraction 결과를 신규/legacy field에 동시 반영
- `app/services/integrations/google_drive.py`
  - extraction result 표준화
  - 다운로드/추출 크기 제한 및 `too_large` status 생성
  - UTF-8 BOM/UTF-8/CP949 decode fallback
  - CSV/TSV table text representation 추가
  - DOCX/PPTX/HWPX zip XML extractor 추가
  - PDF/text/Google Workspace export 경로 metadata 기록
- `app/services/integrations/gmail.py`
  - attachment metadata에 content 상태 기본값 추가
- `app/core/nodes/llm_node.py`
  - `requires_content`/`requiresContent` 처리
  - content-dependent action fallback 판별
  - Drive lazy extraction 결과 payload 반영
  - `FILE_LIST.items[].content` LLM input 포함
  - 본문 실패 상태를 `DOCUMENT_CONTENT_*` 실패로 변환
- `app/core/engine/executor.py`
  - execution log/snapshot sanitize 시 긴 `content` truncate

---

## 3. 구현 점검 결과

### 3.1 Canonical payload

정상 반영됨.

metadata-only file payload는 아래 기본 필드를 가진다.

```json
{
  "content": null,
  "content_status": "not_requested",
  "content_error": null,
  "content_metadata": {
    "extraction_method": "none",
    "content_kind": "none",
    "truncated": false,
    "char_count": 0,
    "original_char_count": 0,
    "limits": {
      "max_download_bytes": 10485760,
      "max_extracted_chars": 60000,
      "max_llm_input_chars": 60000
    }
  },
  "extracted_text": null,
  "extraction_status": "not_requested"
}
```

### 3.2 Preview contract

정상 반영됨.

FastAPI preview metadata는 기존 `preview_scope`를 유지하면서 신규 `content_policy`를 추가한다.

```json
{
  "preview_scope": "source_metadata",
  "content_policy": "metadata_only",
  "include_content": false
}
```

`include_content=true` 요청이어도 `content_policy=content_included`는 실제 `content`가 있거나 `content_status=available`일 때만 내려간다.

본문이 비어 있거나 `unsupported`, `too_large`, `failed`, `empty`, `not_requested` 상태이면 `content_status_only` 또는 `metadata_only`로 보정한다.

### 3.3 LLM content-dependent failure

정상 반영됨.

요약/분석/추출 계열 action에서 파일 본문이 `unsupported`, `too_large`, `failed`, `empty`, `not_requested` 상태로 남으면 `DOCUMENT_CONTENT_*` error로 실패한다.

특히 기존처럼 unsupported 파일을 "File content could not be extracted" 문장으로 LLM에 넘긴 뒤 성공 요약처럼 처리하는 경로를 차단했다.

### 3.4 Log/callback sanitize

정상 반영됨.

FastAPI execution log에 저장되는 `inputData`, `outputData`, snapshot에는 긴 `content`가 4,000자 기준으로 truncate된다.

truncate 시 기존 `content_metadata`를 보존하면서 아래 필드를 `content_metadata` 내부에 병합한다.

```json
{
  "truncated_for_log": true,
  "stored_content_truncated": true,
  "stored_char_count": 4000
}
```

현재 Spring callback은 execution log의 마지막 output을 읽으므로 sanitized payload를 받는다.

### 3.5 FE contract

정상 반영됨.

FE 보강 설계와 맞춰 아래 방침을 문서화했다.

- FastAPI raw 표준값: `content_required_but_unavailable`
- Spring public alias 가능값: `required_by_downstream`
- FE는 두 값을 모두 수용
- `previewScope`와 `contentPolicy`는 역할 분리
- 받은 `content`는 전체 본문이 아니라 "본문 미리보기"로 표시

---

## 4. 보강 중 발견해 수정한 문제

1. `requires_content="false"` 문자열이 Python `bool("false") == True`로 처리될 수 있었다.
   - `_coerce_bool()`을 추가해 문자열 boolean을 안전하게 처리했다.
2. `ai_summarize`, `extract_info`, `ai_analyze` 같은 content-dependent action이 `validate()`에서 false가 될 수 있었다.
   - content-dependent action도 validate에서 허용하도록 수정했다.
3. `extract_info`, `ai_analyze`, `ocr`, `describe_image`가 prompt 없이 빈 요청으로 LLM `process()`에 들어갈 수 있었다.
   - action별 기본 prompt를 추가했다.
4. node error에 `content_status` context를 담을 곳이 없었다.
   - `ErrorDetail.context`를 추가했다.
5. `include_content=true` preview가 실제 본문이 없어도 `content_included`로 표시될 수 있었다.
   - preview payload를 재귀적으로 확인해 실제 content 또는 `content_status=available`일 때만 `content_included`를 내려주도록 수정했다.
6. metadata-only payload와 extraction result의 limits 기준이 일관되지 않았다.
   - 모든 `content_metadata` 기본값에 `limits.max_download_bytes`, `limits.max_extracted_chars`, `limits.max_llm_input_chars`를 포함했다.
7. `DOCUMENT_CONTENT_TOO_LARGE` code는 있었지만 실제 `too_large` status 생성 경로가 부족했다.
   - Google Drive extraction에서 알려진 파일 크기 또는 다운로드된 byte 크기가 제한을 넘으면 `content_status=too_large`를 반환하도록 보강했다.
8. raw parser exception이 `content_error`로 노출될 수 있었다.
   - `content_error`를 사용자 표시 가능한 짧은 메시지로 정규화했다. raw exception은 서버 로그/exception context 영역에만 남긴다.

---

## 5. 현재 미완료 또는 후속 과제

원문 요구사항 1차 필수 파일군 extractor는 반영되었다.

아직 제품 안정화와 확장 지원을 위해 남은 항목:

- scan PDF OCR 실제 지원
- image OCR/vision 실제 지원
- Gmail attachment download + 공통 extractor 연결

FE contract sample payload fixture는 `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`에 추가했다.

Spring public API의 `DOCUMENT_CONTENT_*` error shape 변환은 Spring Boot 팀에서 완료된 상태로 확인되어 FastAPI 후속 과제 목록에서 제외했다.

현재 구현은 "계약/경로 안정화 MVP + 원문 1차 필수 파일군 extractor 1차 구현"으로 볼 수 있다. 다만 Gmail attachment 본문 추출, OCR/vision, cross-service fixture는 후속으로 남아 있으므로 "다양한 파일 완전 호환"으로 표현하면 안 된다.

---

## 6. 검증 결과

실행한 검증:

```bash
/opt/homebrew/anaconda3/bin/conda run -n cse_2 python -m py_compile app/core/document_content.py app/common/errors.py app/models/canonical.py app/models/execution.py app/core/nodes/input_node.py app/core/engine/preview_executor.py app/services/integrations/google_drive.py app/services/integrations/gmail.py app/core/nodes/llm_node.py app/core/engine/executor.py tests/test_input_node.py tests/test_preview_executor.py tests/test_integrations/test_google_drive.py tests/test_llm_node.py tests/test_executor.py
```

결과:

- 통과

targeted regression suite:

```bash
/opt/homebrew/anaconda3/bin/conda run -n cse_2 python -m pytest tests/test_input_node.py tests/test_preview_executor.py tests/test_integrations/test_google_drive.py tests/test_llm_node.py tests/test_executor.py tests/test_spring_callback_service.py -q
```

결과:

- `140 passed in 0.33s`

full test suite:

```bash
/opt/homebrew/anaconda3/bin/conda run -n cse_2 python -m pytest -q
```

결과:

- sandbox network 제한 상태: `388 passed, 6 errors`
- 네트워크 허용 재실행: `394 passed in 16.96s`

사유:

- 최초 full suite의 6 errors는 `tests/test_trigger_api.py`가 FastAPI lifespan에서 MongoDB SRV DNS를 조회하다가 sandbox 네트워크 제한에 막힌 환경 이슈였다.
- 동일 명령을 네트워크 허용 상태에서 재실행했을 때 전체 테스트가 통과했다.

환경 보강:

```text
cse_2 환경에 feedparser가 없어 최초 테스트 수집이 실패했다.
/opt/homebrew/anaconda3/bin/conda run -n cse_2 python -m pip install 'feedparser>=6.0.11'
```

설치 후 targeted regression suite와 full test suite 모두 통과했다.

---

## 7. 최종 판단

현재 구현은 설계 문서의 핵심 경로를 반영한 상태다.

`cse_2` 환경 기준 targeted regression suite와 full test suite가 모두 통과했으므로, 현재 구현은 추가 보강 없이 다음 리뷰 단계로 넘길 수 있다.

다만 Gmail attachment 본문 추출, OCR/vision 계열, cross-service sample fixture는 아직 후속 과제로 남아 있다.
