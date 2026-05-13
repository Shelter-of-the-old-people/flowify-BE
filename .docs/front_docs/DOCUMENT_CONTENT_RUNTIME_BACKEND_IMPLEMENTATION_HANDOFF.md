# 문서 본문 런타임 Backend 구현 전달 문서

> 작성일: 2026-05-14  
> Backend 브랜치: `feat/26-runtime-document`  
> 전달 대상: Frontend 팀  
> 관련 문서:
> - `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_ANALYSIS_AND_IMPLEMENTATION_PLAN.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_FE_DESIGN_REVIEW.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_IMPLEMENTATION_REPORT.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`

---

## 1. 전달 요약

문서 본문 런타임 계약의 Backend 1차 구현이 완료되었다.

이번 구현은 FE가 문서 본문 상태를 일관되게 표시할 수 있도록 canonical payload와 error contract를 런타임 경로에 반영한 "계약/경로 안정화 MVP"다. 최종 보강으로 원문 1차 필수 파일군인 DOCX/PPTX/HWPX extractor도 함께 반영했다.

FE에서 기대할 수 있는 핵심 변화:

- `SINGLE_FILE`, `FILE_LIST.items[]`, Gmail attachment에 `content_status`, `content_error`, `content_metadata`가 포함된다.
- 기존 호환을 위해 `extracted_text`, `extraction_status`도 유지된다.
- preview response metadata에 실제 본문 포함 여부 기준 `content_policy`가 포함된다.
- `content_metadata.limits`가 기본 포함된다.
- 크기 제한 초과 시 `content_status=too_large`와 사용자 표시 가능한 `content_error`가 생성된다.
- Google Drive DOCX/PPTX/HWPX 파일도 본문 추출 대상에 포함된다.
- 문서 본문이 필요한 LLM action에서 본문 추출 실패가 빈 성공 결과처럼 처리되지 않고 `DOCUMENT_CONTENT_*` error로 실패한다.
- 실행 로그와 callback 경로에 저장되는 긴 `content`는 truncate될 수 있다.

---

## 2. FE 구현 시 기준으로 볼 필드

### 2.1 File payload 공통 필드

Backend는 파일 payload에 아래 필드를 공통으로 포함한다.

```json
{
  "filename": "report.pdf",
  "mime_type": "application/pdf",
  "size": 12345,
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

FE 권장 처리:

- 신규 표시는 `content_status`, `content_error`, `content_metadata`, `content`를 우선 사용한다.
- `content`가 없고 `extracted_text`가 있으면 legacy fallback으로 표시할 수 있다.
- Spring public API에서 camelCase로 변환될 수 있으므로 FE helper는 snake_case와 camelCase를 모두 읽는 것이 안전하다.

### 2.2 Content status

Backend 표준 상태는 아래 6개다.

| status | 의미 | FE 표시 권장 |
|--------|------|--------------|
| `available` | 본문 사용 가능 | 본문 읽기 완료 |
| `empty` | 추출 가능한 본문 없음 | 읽을 수 있는 본문 없음 |
| `unsupported` | 지원하지 않는 형식 | 지원하지 않는 파일 형식 |
| `too_large` | 크기 제한 초과 | 파일 크기 제한 초과 |
| `failed` | 추출 실패 | 본문 읽기 실패 |
| `not_requested` | 본문 추출 미요청 | 본문 미포함 |

요약/분석처럼 본문이 필요한 action에서는 `empty`, `unsupported`, `too_large`, `failed`, `not_requested`가 실패로 처리될 수 있다.

### 2.3 Content metadata

현재 Backend가 내려줄 수 있는 주요 metadata:

| field | 의미 |
|-------|------|
| `extraction_method` | 추출 방식. 예: `none`, `google_export`, `pdf_text`, `text_decode`, `csv_parse` |
| `content_kind` | 본문 종류. 예: `none`, `plain_text`, `table_text`, `slide_text` |
| `truncated` | 추출 단계에서 본문이 잘렸는지 여부 |
| `char_count` | 현재 content 길이 |
| `original_char_count` | 원본 추출 본문 길이 |
| `limits.max_download_bytes` | 다운로드/추출 전 byte 크기 제한 |
| `limits.max_extracted_chars` | 추출 후 content 최대 문자 수 |
| `limits.max_llm_input_chars` | LLM 입력 기준 최대 문자 수 |
| `truncated_for_log` | 실행 로그 저장 전 잘렸는지 여부 |
| `stored_content_truncated` | 저장/조회용 content가 잘렸는지 여부 |
| `stored_char_count` | 저장된 content 길이 |

FE 표시에서는 `truncated`, `stored_content_truncated` 중 하나라도 true이면 "본문 일부만 표시됨" 계열의 안내를 붙이는 것이 좋다.

---

## 3. Preview contract

### 3.1 Metadata-only preview

기본 source preview는 비용과 latency를 줄이기 위해 metadata-only다.

```json
{
  "metadata": {
    "preview_scope": "source_metadata",
    "content_policy": "metadata_only",
    "include_content": false
  },
  "data": {
    "type": "SINGLE_FILE",
    "content_status": "not_requested"
  }
}
```

FE 권장 표시:

- `preview_scope`는 기존 preview 범위 호환 필드로 유지한다.
- `content_policy`를 본문 포함 여부의 의미 필드로 사용한다.
- `metadata_only`이면 "본문 미포함 미리보기"로 표시한다.

### 3.2 Content-included preview

`include_content=true`로 preview가 호출되면 가능한 경우 본문 추출 결과가 포함된다. 다만 `content_policy=content_included`는 실제 `content`가 있거나 `content_status=available`일 때만 내려간다.

```json
{
  "metadata": {
    "preview_scope": "source_metadata",
    "content_policy": "content_included",
    "include_content": true
  },
  "data": {
    "type": "SINGLE_FILE",
    "filename": "report.pdf",
    "content": "문서 본문...",
    "content_status": "available",
    "content_error": null,
    "content_metadata": {
      "extraction_method": "pdf_text",
      "content_kind": "plain_text",
      "truncated": false,
      "char_count": 8,
      "original_char_count": 8,
      "limits": {
        "max_download_bytes": 10485760,
        "max_extracted_chars": 60000,
        "max_llm_input_chars": 60000
      }
    },
    "extracted_text": "문서 본문...",
    "extraction_status": "success"
  }
}
```

본문을 요청했지만 추출 결과가 `unsupported`, `too_large`, `failed`, `empty`, `not_requested`이면 `content_policy`는 `content_included`가 아니라 `content_status_only` 또는 `metadata_only`로 내려간다.

```json
{
  "metadata": {
    "preview_scope": "source_metadata",
    "content_policy": "content_status_only",
    "include_content": true
  },
  "data": {
    "type": "SINGLE_FILE",
    "filename": "archive.zip",
    "content": null,
    "content_status": "unsupported",
    "content_error": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."
  }
}
```

FE 1차 구현에서는 기존 설계대로 source preview의 기본값을 `includeContent=false`로 유지해도 된다. `본문 포함 미리보기` 버튼은 Backend/Spring public API 정책이 확정된 뒤 2차로 열어도 무방하다.

### 3.3 Content policy 값

현재 FE helper에서 수용해야 할 값:

| policy | 의미 |
|--------|------|
| `metadata_only` | 본문 미포함 |
| `content_included` | 본문 포함 |
| `content_status_only` | 본문 상태만 포함 |
| `content_required_but_unavailable` | 본문이 필요한 단계지만 현재 본문 없음 |
| `required_by_downstream` | Spring public alias 가능값 |

FastAPI raw 기준은 snake_case field와 `content_required_but_unavailable`이다. Spring public API가 `required_by_downstream`을 쓰는 경우 FE는 alias로 같이 수용하면 된다.

---

## 4. Gmail attachment contract

Gmail attachment도 파일 카드 helper로 처리할 수 있도록 content 상태 필드를 가진다.

metadata-only 상태 예시:

```json
{
  "filename": "attached.pdf",
  "mime_type": "application/pdf",
  "source": "gmail",
  "messageId": "msg_1",
  "attachmentId": "att_1",
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
  }
}
```

현재 1차 Backend 구현에는 Gmail attachment download + 공통 extractor 연결이 아직 후속 과제로 남아 있다. 따라서 FE는 Gmail attachment의 `not_requested` 또는 미지원 상태를 자연스럽게 표시하면 된다.

---

## 5. Error contract

Backend에 아래 error code를 추가했다.

| code | HTTP 성격 | FE fallback 문구 권장 |
|------|-----------|------------------------|
| `DOCUMENT_CONTENT_UNSUPPORTED` | 422 | 이 파일 형식은 아직 본문 읽기를 지원하지 않습니다. |
| `DOCUMENT_CONTENT_TOO_LARGE` | 413 | 파일이 너무 커서 본문을 읽을 수 없습니다. |
| `DOCUMENT_CONTENT_EMPTY` | 422 | 파일에서 읽을 수 있는 본문이 없습니다. |
| `DOCUMENT_CONTENT_EXTRACTION_FAILED` | 502 | 파일 본문을 읽는 중 오류가 발생했습니다. |
| `DOCUMENT_CONTENT_NOT_REQUESTED` | 409 | 본문이 필요한 작업이지만 본문 추출이 요청되지 않았습니다. |

실행 실패 시 Backend error detail에는 context가 포함될 수 있다.

```json
{
  "code": "DOCUMENT_CONTENT_UNSUPPORTED",
  "message": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다",
  "context": {
    "filename": "archive.zip",
    "content_status": "unsupported",
    "content_error": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."
  }
}
```

`content_error`는 FE에 표시 가능한 짧은 메시지로 정규화된다. raw parser exception, stack trace, 문서 일부 내용은 `content_error`로 내려가지 않는다.

FE 표시 우선순위 권장:

1. Spring public API가 내려준 사용자 친화적 message
2. `DOCUMENT_CONTENT_*` code 기반 FE fallback 문구
3. 기존 OAuth/column/not found/rate limit 등 기존 매핑
4. generic 실행 실패 문구

---

## 6. 현재 지원 범위와 후속 과제

이번 Backend 구현에서 안정화된 범위:

- canonical content status field 추가
- preview `content_policy` 추가
- `content_metadata.limits` 기본 포함
- 다운로드/추출 크기 제한 초과 시 `too_large` status 생성
- Google Drive TXT/CSV/TSV/PDF text/DOCX/PPTX/HWPX/Google Workspace export 계열 추출 경로 정리
- DOCX paragraph/table text 추출
- PPTX slide order/title/body/note text 추출
- HWPX zip XML body text 추출
- 텍스트 레이어 없는 PDF는 OCR 미지원 `unsupported`로 반환
- LLM content-dependent action의 본문 실패 처리
- execution log/callback payload truncate 경계 정리
- 사용자 표시 가능한 `content_error` 정규화
- 상태별 sample payload fixture 제공
- legacy `extracted_text`/`extraction_status` 병행 유지

아직 제품 안정화와 확장 지원을 위해 남은 범위:

- scan PDF OCR 실제 지원
- image OCR/vision 실제 지원
- Gmail attachment download + extractor 연결

Spring public API의 `DOCUMENT_CONTENT_*` error shape 변환은 Spring Boot 팀에서 완료된 상태로 정리한다.

FE fixture/sample payload는 `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`에 제공했다.

따라서 FE 문서나 UI 문구에서는 현재 범위를 "문서 본문 런타임 계약 1차 반영" 또는 "계약/경로 안정화 MVP + 원문 1차 필수 파일군 extractor 1차 구현"으로 부르는 것이 안전하다. "다양한 파일 완전 호환" 같은 표현은 Gmail attachment/OCR/vision 확장 전까지 피한다.

---

## 7. FE 구현 체크리스트

FE 쪽에서 바로 반영하면 좋은 항목:

- `content_status`, `content_error`, `content_metadata`, `content` helper 추가
- snake_case와 camelCase 동시 지원
- `content` 우선, `extracted_text`/`extractedText` fallback
- `SINGLE_FILE` 상태 표시
- `FILE_LIST.items[]` 상태 집계와 개별 상태 표시
- Gmail attachment 상태 표시
- preview metadata의 `contentPolicy`/`content_policy` 표시
- `DOCUMENT_CONTENT_*` error fallback 문구 매핑
- `truncated`/`stored_content_truncated` 안내 표시

1차에서 보수적으로 유지할 항목:

- source preview 기본 요청은 `includeContent=false`
- `본문 포함 미리보기` 버튼은 2차 확장
- AI 노드 preview는 Backend/Spring dry-run capability 확정 후 노출
- FE에서 파일 본문 직접 다운로드/파싱하지 않음

---

## 8. Backend 검증 결과

검증 환경:

- Conda env: `cse_2`
- 실행 방식: `/opt/homebrew/anaconda3/bin/conda run -n cse_2 ...`

검증 결과:

```text
py_compile: 통과
targeted regression suite: 140 passed in 0.33s
full test suite: 394 passed in 16.96s
```

참고:

- 최초 `cse_2` 환경에는 `feedparser`가 없어 설치 후 재실행했다.
- sandbox network 제한 상태에서는 MongoDB SRV DNS 조회 때문에 `tests/test_trigger_api.py` 6건이 error였으나, 네트워크 허용 재실행에서 전체 통과했다.

---

## 9. FE 팀에 요청하는 확인 사항

1. Spring public API에서 field casing이 최종적으로 camelCase인지, FastAPI raw snake_case가 일부 노출될 수 있는지 확인이 필요하다.
2. `content_required_but_unavailable`과 `required_by_downstream` 중 public API 대표값을 하나로 정하되, FE helper는 둘 다 수용하는 방향을 권장한다.
3. 실행 결과 화면에서 `content`는 전체 원문이 아니라 truncate될 수 있는 "본문 미리보기"로 표시해야 한다.
4. Gmail attachment는 1차에서 본문 추출 완료가 아니라 상태 표시 중심으로 처리하는 것이 맞다.
5. DOCX/PPTX/HWPX extractor는 Backend에 반영되었고, OCR/vision/Gmail attachment extraction은 후속 구현 후 fixture를 추가로 공유할 예정이다.
