# 문서 본문 런타임 FE 반영 설계 검토

> 작성일: 2026-05-14  
> 검토 대상 FE 설계: 문서 본문 런타임 FE 반영 설계  
> 기준 백엔드 문서:
> - `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_ANALYSIS_AND_IMPLEMENTATION_PLAN.md`

---

## 1. 검토 결론

FE 설계 방향은 백엔드 런타임 계약과 대체로 일치한다.

단, 이 검토의 기준은 "현재 FastAPI 코드가 이미 모두 구현한 동작"이 아니라 `.docs/DOCUMENT_CONTENT_RUNTIME_ANALYSIS_AND_IMPLEMENTATION_PLAN.md`에서 정의한 목표 계약이다. 현재 코드에는 `content_status`, `content_metadata`, `content_policy`, `DOCUMENT_CONTENT_*` error code가 아직 완전히 구현되어 있지 않으므로, FE 구현은 backend contract 반영 시점과 맞춰 순차 적용해야 한다.

특히 아래 판단은 백엔드 계약과 맞다.

- FE가 파일 본문을 직접 다운로드하거나 파싱하지 않는다.
- `SINGLE_FILE`, `FILE_LIST.items[]`, Gmail attachment의 `content_status`, `content_error`, `content_metadata`를 표시 계층에서 수용한다.
- source preview는 1차에서 metadata-only 기본값을 유지한다.
- AI 노드 preview는 backend dry-run capability가 열릴 때까지 UI에 무리하게 노출하지 않는다.
- legacy `extracted_text`/`extractedText` fallback을 둔다.
- `DOCUMENT_CONTENT_*` error code를 사용자 문구로 매핑한다.
- full content 복원/별도 저장을 FE 범위에서 제외한다.

다만 아래 항목은 백엔드 계약과 정확히 맞추도록 보정이 필요하다.

1. FastAPI raw response의 `content_policy` 표준값은 `content_required_but_unavailable`을 기준으로 둔다.
2. Spring public API가 `required_by_downstream`을 노출할 수 있다면 public alias로 명시하고, FE는 두 값을 모두 수용한다.
3. `previewScope`는 기존 호환 필드, `contentPolicy`는 신규 의미 필드로 분리한다.
4. Spring public API가 camelCase를 노출하더라도 FastAPI 내부 기준은 snake_case다.
5. FE 문서 경로의 `docs/backend/*`는 이 repo 기준으로는 `.docs/*`에 대응한다.

---

## 2. FE 설계와 백엔드 계약 정합성

### 2.1 Content 상태 타입

FE 설계의 `DocumentContentStatus`는 백엔드 표준 상태와 일치한다.

```ts
type DocumentContentStatus =
  | "available"
  | "empty"
  | "unsupported"
  | "too_large"
  | "failed"
  | "not_requested";
```

백엔드 의미:

| status | FE 표시 방향 | 백엔드 처리 |
|--------|--------------|-------------|
| `available` | 본문 읽기 완료 | content 사용 가능 |
| `empty` | 읽을 수 있는 본문 없음 | 요약/분석은 실패 또는 부분 실패 |
| `unsupported` | 지원하지 않는 파일 형식 | content-dependent action 실패 |
| `too_large` | 파일 크기 제한 초과 | content-dependent action 실패 |
| `failed` | 본문 읽기 실패 | content-dependent action 실패 |
| `not_requested` | 본문 미포함 | preview metadata-only 또는 lazy extraction 전 상태 |

### 2.2 Content metadata camel/snake 호환

FE helper가 snake_case와 camelCase를 모두 읽는 설계는 타당하다.

FastAPI 내부 payload:

```json
{
  "content_status": "available",
  "content_error": null,
  "content_metadata": {
    "extraction_method": "pdf_text",
    "content_kind": "plain_text",
    "truncated": false,
    "char_count": 1000,
    "original_char_count": 1000
  }
}
```

Spring public API에서 camelCase로 변환될 수 있는 payload:

```json
{
  "contentStatus": "available",
  "contentError": null,
  "contentMetadata": {
    "extractionMethod": "pdf_text",
    "contentKind": "plain_text",
    "truncated": false,
    "charCount": 1000,
    "originalCharCount": 1000
  }
}
```

FE helper는 두 형태를 모두 수용해야 한다.

### 2.3 Preview metadata

FE 설계의 metadata helper 방향은 맞다. 다만 FastAPI raw contract와 Spring public API alias를 아래처럼 구분한다.

현재 FastAPI preview response는 `metadata.preview_scope`와 `metadata.include_content`만 내려준다. `content_policy`/`contentPolicy`는 추가 예정 필드다.

| FastAPI raw `content_policy` | Spring public `contentPolicy` | FE 표시 |
|------------------------------|-------------------------------|---------|
| `metadata_only` | `metadata_only` | 본문 미포함 미리보기 |
| `content_included` | `content_included` | 본문 포함 미리보기 |
| `content_status_only` | `content_status_only` | 본문 상태만 포함 |
| `content_required_but_unavailable` | `content_required_but_unavailable` | 본문이 필요한 단계지만 현재 미리보기에는 본문이 포함되지 않음 |
| alias only | `required_by_downstream` | 다음 단계에서 본문 필요 |

`required_by_downstream`은 FastAPI raw 표준값이 아니다. Spring public API에서 쓰기로 결정한다면 alias로 문서화하고, FE helper에서 함께 수용한다.

권장 helper 동작:

```ts
const canonicalPolicy =
  rawPolicy === "required_by_downstream"
    ? "content_required_but_unavailable"
    : rawPolicy;

// 표시 문구는 rawPolicy를 우선 볼 수 있게 보존한다.
// 예: required_by_downstream -> "다음 단계에서 본문 필요"
// 예: content_required_but_unavailable -> "본문이 필요한 단계지만 현재 미리보기에는 본문이 포함되지 않음"
```

`previewScope`와 `contentPolicy`는 역할이 다르다.

- `previewScope`: 기존 preview 범위 호환 필드. 예: `source_metadata`
- `contentPolicy`: 본문 포함/미포함/상태-only 의미 필드

둘 중 하나로 합치지 않는다.

### 2.4 Preview 요청 정책

FE 1차에서 `includeContent=false`를 기본으로 유지하는 것은 백엔드 정책과 맞다.

이유:

- source preview에서 full content extraction을 자동 실행하면 비용과 latency가 증가한다.
- backend 문서는 metadata-only preview와 content-included preview를 분리한다.
- AI 노드 preview는 현재 FastAPI `WorkflowPreviewExecutor`에서 source node 중심이다.

다만 FE가 2차로 `본문 포함 미리보기` 버튼을 추가할 경우, 요청은 기존 `includeContent: true`를 사용하면 된다.

### 2.5 Error UX

FE 설계의 `DOCUMENT_CONTENT_*` mapping은 백엔드 계획 문서의 Spring public error shape 제안과 맞다. 현재 코드에 해당 error code가 모두 존재한다는 뜻은 아니다.

추가로 FE는 아래 필드를 우선순위로 읽는다.

1. Spring이 내려준 user-friendly `message`
2. `errorCode` 또는 `error_code` 기반 FE fallback 문구
3. raw `message`가 없으면 generic 문구

권장 code mapping:

| code | FE fallback 문구 |
|------|------------------|
| `DOCUMENT_CONTENT_UNSUPPORTED` | 이 파일 형식은 아직 본문 읽기를 지원하지 않습니다. |
| `DOCUMENT_CONTENT_TOO_LARGE` | 파일이 너무 커서 본문을 읽을 수 없습니다. |
| `DOCUMENT_CONTENT_EMPTY` | 파일에서 읽을 수 있는 본문이 없습니다. |
| `DOCUMENT_CONTENT_EXTRACTION_FAILED` | 파일 본문을 읽는 중 오류가 발생했습니다. |
| `DOCUMENT_CONTENT_NOT_REQUESTED` | 본문이 필요한 작업이지만 본문 추출이 요청되지 않았습니다. |

---

## 3. BE 프로젝트 관점 보강 설계

이 BE repo에서는 FE 코드를 직접 수정할 수 없으므로, 백엔드 계약 문서와 API 응답 설계에서 FE가 구현하기 쉬운 형태를 보장한다.

현재 구현과 목표 계약의 차이는 아래와 같다.

| 항목 | 현재 FastAPI 코드 | 목표 계약 |
|------|-------------------|-----------|
| preview metadata | `preview_scope`, `include_content` | `preview_scope` 유지 + `content_policy` 추가 |
| Drive single file preview | `extracted_text`, `extraction_status` 중심 | `content`, `content_status`, `content_metadata` 중심 + legacy 병행 |
| Drive folder preview | item metadata 중심 | item별 content 상태 기본값 포함 |
| Gmail attachment | attachment metadata 중심 | attachment에도 file content 상태 필드 포함 |
| document content error | 기존 generic/Flowify error 중심 | `DOCUMENT_CONTENT_*` code 추가 |

### 3.1 FastAPI preview metadata

FastAPI preview response metadata는 snake_case를 기준으로 유지한다. 현재 필드에 `content_policy`를 추가하는 방식으로 확장한다.

```json
{
  "preview_scope": "source_metadata",
  "content_policy": "metadata_only",
  "include_content": false
}
```

Spring이 public API에서 camelCase로 변환할 수 있다.

```json
{
  "previewScope": "source_metadata",
  "contentPolicy": "metadata_only",
  "includeContent": false
}
```

FastAPI는 두 값을 혼동하지 않는다.

### 3.2 File payload

FE가 표시할 수 있도록 모든 file payload에는 기본 content 상태를 둔다. 이는 목표 계약이며, 현재 코드의 기존 `extracted_text`/`extraction_status` payload에서 확장되어야 한다.

```json
{
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
```

legacy 호환:

- `extracted_text`는 `content` fallback으로 유지 가능
- `extraction_status`는 기존 테스트/FE 전환 기간 동안 유지 가능

### 3.3 Gmail attachment

Gmail attachment도 FE의 `FileItemCard`가 같은 helper로 처리할 수 있게 file item shape를 맞춘다.

metadata-only source/preview의 1차 미지원 상태:

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
    "original_char_count": 0
  }
}
```

content-dependent 실행에서 attachment extraction이 미지원이면 `unsupported`로 바꾼다.

### 3.4 Sanitized content

FE 설계의 "full content를 임의로 복원하지 않는다"는 방향은 맞다.

백엔드 경계:

- 노드 실행 중 in-memory payload: full content 가능
- MongoDB execution log: sanitized/truncated content만 저장
- FastAPI -> Spring callback: sanitized/truncated content만 전송
- Spring public API: sanitized/truncated content만 반환
- FE: 받은 content가 전체라고 가정하지 않고 `truncated`, `storedContentTruncated`, `charCount`, `originalCharCount`를 표시

---

## 4. 보강 후 재검토 결과

프론트 보강안은 기존 검토에서 지적한 대부분의 항목을 반영했다.

반영 확인:

1. `limits.maxDownloadBytes|maxExtractedChars|maxLlmInputChars`를 helper 타입에 포함했다.
2. snake_case/camelCase 동시 지원 범위를 content status, metadata, limits까지 확장했다.
3. `storedContentTruncated`와 `storedCharCount`를 표시 계층에서 수용한다.
4. 본문이 표시되더라도 truncate 상태면 전체 본문이 아닐 수 있음을 표시한다.
5. `content_metadata.limits`는 항상 나열하지 않고 `too_large`/truncate 상황에서만 보조 문구로 사용한다.
6. `DataStateNotice`와 `getExecutionStatusNotice`에서 같은 error helper를 재사용하는 방향을 잡았다.
7. `Google Drive source preview content included` QA를 1차 필수가 아니라 확장 검증으로 내렸다.

남은 정합성 메모:

1. FastAPI raw 표준값은 `content_required_but_unavailable`로 유지한다.
2. Spring public API가 `required_by_downstream`을 쓴다면 alias로 명시한다.
3. `contentIncluded`, `contentStatusScope`는 backend 표준 필드가 아니므로 FE fallback으로만 읽는다.
4. backend에서 내려온 `content`는 저장/조회용으로 이미 truncate됐을 수 있으므로 FE는 "전체 본문"이라고 표현하지 않는다. 표시 문구는 "본문 미리보기"가 안전하다.

---

## 5. 이 repo에서의 후속 작업

FE 설계와 맞추기 위해 FastAPI/Spring 계약 문서와 구현은 아래를 보장해야 한다.

1. `content_status/content_error/content_metadata` 기본값 builder 추가
2. preview metadata에 `preview_scope`와 `content_policy` 병행 제공
3. document content error code와 Spring public error shape 문서화
4. execution log/callback sanitize 경계 구현
5. Gmail attachment metadata-only 상태에도 content 상태 필드 추가
6. FE contract sample payload를 테스트 fixture 또는 문서에 유지

---

## 6. 최종 판단

보강된 FE 설계는 채택 가능하다.

다만 `contentPolicy` 값 이름은 FastAPI raw 표준값과 Spring public alias를 구분해서 진행해야 한다. 이 repo에서는 FE 구현 자체가 아니라 backend contract와 sample payload를 맞추는 방식으로 설계를 진행한다.
