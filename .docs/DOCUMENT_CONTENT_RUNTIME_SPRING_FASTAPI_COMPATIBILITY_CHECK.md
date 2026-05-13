# 문서 본문 런타임 Spring Boot - FastAPI 정합성 확인 문서

> 작성일: 2026-05-14  
> Spring Boot 브랜치: `feat/30-runtime-document`  
> FastAPI 브랜치: `feat/26-runtime-document`  
> 기준:
> - `.docs/DOCUMENT_CONTENT_RUNTIME_REQUIREMENTS.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_ANALYSIS_AND_IMPLEMENTATION_PLAN.md`
> - `.docs/DOCUMENT_CONTENT_RUNTIME_IMPLEMENTATION_REPORT.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_BACKEND_IMPLEMENTATION_HANDOFF.md`
> - `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`

---

## 1. 검토 결론

현재 문서와 FastAPI 구현, 그리고 Spring Boot 팀의 추가 확인 결과 기준으로 Spring Boot와 FastAPI 사이에 차단급 계약 충돌은 없다.

Spring Boot 팀은 추가 검토 중 `nodeLogs[].error.context`가 public 조회에서 누락될 수 있는 부분을 발견했고, Spring `ErrorDetail.context` 필드와 execution detail/node data 조회 테스트를 보강했다. 따라서 문서 본문 런타임 error code/context 보존 경로는 Spring/FastAPI 양쪽에서 맞춰진 상태로 판단한다.

정합성이 맞는 것으로 판단되는 영역:

- Spring이 `runtime_config.requires_content` 또는 `runtime_config.requiresContent`를 내려주면 FastAPI가 둘 다 수용한다.
- FastAPI는 명시적 `requires_content=false`를 action fallback보다 우선한다.
- FastAPI는 `SINGLE_FILE`, `FILE_LIST.items[]`, Gmail attachment에 `content_status`, `content_error`, `content_metadata`, `content` 기본 필드를 제공한다.
- FastAPI는 preview metadata에 `content_policy`를 내려주고, 실제 본문 포함 여부 기준으로 `content_included`를 보정한다.
- FastAPI는 `DOCUMENT_CONTENT_*` error code를 구분 가능한 값으로 생성한다.
- FastAPI execution log에는 `ErrorDetail.code`, `ErrorDetail.context`가 저장된다.
- Spring public execution 조회 경로는 Mongo `nodeLogs[].error.code/context`를 보존한다.
- FastAPI callback/output 경로의 긴 `content`는 저장 전 truncate되고, 기존 `content_metadata`는 보존된다.
- DOCX/PPTX/HWPX extractor는 FastAPI에 반영되었다.

남은 리스크는 구현 부재보다 fixture 기반 회귀 테스트와 운영 문구 정리에 가깝다. 특히 Gmail attachment 본문 추출, scan PDF OCR, image OCR/vision은 아직 후속 범위로 남아 있으므로 제품 문구에서 완전 지원처럼 표현하지 않는다.

---

## 1.1 Spring Boot 확인 결과

Spring Boot 팀이 실제 코드 기준으로 확인 및 보강한 내용:

- `src/main/java/org/github/flowify/execution/entity/ErrorDetail.java`에 `context` 필드를 추가했다.
- `src/test/java/org/github/flowify/execution/ExecutionServiceTest.java`에 execution detail/node data 조회에서 `nodeLogs[].error.code/context`가 보존되는 테스트를 추가했다.
- FastAPI preview raw `workflow_id`, `node_id`, `output_data`, `preview_data`는 Spring `NodePreviewResponse`의 camelCase 필드로 매핑된다.
- metadata는 Spring public canonical 값으로 `contentPolicy=metadata_only|content_included|content_status_only`를 제공한다.
- FastAPI raw snake_case metadata도 함께 보존한다.
- `required_by_downstream`은 Spring 대표값으로 만들지 않는다. downstream 의미는 `contentRequired/contentRequiredReason`으로 표현한다.
- FastAPI `DOCUMENT_CONTENT_*` HTTP error body는 Spring public `ErrorCode`로 보존한다.
- completion callback top-level `error`는 문자열만 유지한다.
- 사용자 표시용 node-level code/context는 Mongo `nodeLogs[].error.code/context` 조회 경로에서 보존한다.
- `runtime_config.requires_content=true` 생성 경로는 `choiceActionId=summarize + action=process`, legacy `choiceSelections`, 명시적 false 우선순위까지 테스트로 고정했다.

Spring Boot 검증:

```bash
./gradlew test --tests org.github.flowify.execution.ExecutionServiceTest --tests org.github.flowify.execution.FastApiClientTest --tests org.github.flowify.workflow.WorkflowPreviewServiceTest --tests org.github.flowify.execution.WorkflowTranslatorTest
./gradlew test
```

결과:

- 둘 다 `BUILD SUCCESSFUL`

---

## 2. 계약 정합성 매트릭스

| 항목 | FastAPI 현재 계약 | Spring Boot 기대/보고 기준 | 판단 |
|------|-------------------|-----------------------------|------|
| 내부 요청 인증 | `X-Internal-Token`, `X-User-ID` | Spring이 내부 호출 시 헤더 전달 | 정합 |
| preview 요청 필드 | `include_content` | Spring public `includeContent`를 FastAPI raw로 변환 | 정합 |
| preview 응답 casing | raw `workflow_id`, `output_data`, `preview_data`, `content_policy` | Spring `NodePreviewResponse` camelCase 필드로 매핑 | 정합 |
| file payload casing | raw snake_case | FE는 snake/camel 모두 수용, Spring public 변환 가능 | 정합 |
| content status | `available/empty/unsupported/too_large/failed/not_requested` | 동일 상태 표시/저장 | 정합 |
| content metadata limits | `limits.max_download_bytes`, `max_extracted_chars`, `max_llm_input_chars` | Spring raw metadata 보존 | 정합 |
| content policy | `metadata_only/content_included/content_status_only` | Spring public canonical 대표값도 동일 | 정합 |
| downstream policy alias | FastAPI raw는 `required_by_downstream`을 만들지 않음 | Spring도 대표값으로 만들지 않고 `contentRequired*` 사용 | 정합 |
| content error | 사용자 표시 가능한 짧은 문구 | Spring public message 또는 FE fallback | 정합 |
| HTTP error body | `error_code`, `message`, `detail` | Spring public `ErrorCode`로 보존 | 정합 |
| execution log error | `nodeLogs[].error.code/context` | Spring 조회 API에서 보존/노출 | 정합 |
| callback error | 현재 callback payload는 `error` 문자열 중심 | callback은 문자열 유지, node-level code/context는 Mongo 조회 경로 사용 | 정합 |
| callback output | 마지막 성공 노드 `output` | Spring 저장/조회에서 nested content fields 보존 | 정합, fixture 회귀 테스트 권장 |
| Gmail attachment 본문 | metadata/status only, extraction 미연결 | Spring/FE도 본문 요약 미지원으로 표시 | 정합, 제품 문구 확인 필요 |

---

## 3. 확인 완료 및 잔여 확인 항목

### P0. Error code 전달 경로 확인 완료

FastAPI는 두 경로로 error 정보를 남긴다.

1. HTTP 예외 응답:

```json
{
  "success": false,
  "error_code": "DOCUMENT_CONTENT_UNSUPPORTED",
  "message": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다",
  "detail": {
    "filename": "archive.zip",
    "content_status": "unsupported",
    "content_error": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."
  }
}
```

2. Mongo execution log:

```json
{
  "error": {
    "code": "DOCUMENT_CONTENT_UNSUPPORTED",
    "message": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다",
    "context": {
      "filename": "archive.zip",
      "content_status": "unsupported",
      "content_error": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다."
    }
  }
}
```

Spring completion callback payload는 현재 `error` 문자열만 포함한다.

```json
{
  "status": "failed",
  "error": "이 파일 형식은 아직 본문 읽기를 지원하지 않습니다"
}
```

Spring 확인 결과:

- callback top-level error는 문자열만 유지한다.
- 사용자 표시용 node-level code/context는 Mongo `nodeLogs[].error.code/context` 조회 경로에서 보존한다.
- Spring `ErrorDetail.context` 필드와 execution detail/node data 조회 테스트가 추가되었다.

현재 판단:

- callback payload에 `errorCode/errorContext`를 즉시 추가할 필요는 없다.
- Spring public 조회 경로가 Mongo `nodeLogs[].error.code/context`를 계속 기준으로 삼는다는 계약은 유지해야 한다.

### P0. `requires_content` 생성 경로 확인 완료

FastAPI는 `runtime_config.requires_content`와 `runtime_config.requiresContent`를 모두 수용한다.

명시값이 있으면 action fallback보다 우선한다.

Spring 확인 결과:

- `choiceActionId=summarize + action=process` 경로가 테스트로 고정되었다.
- legacy `choiceSelections` 경로도 테스트로 고정되었다.
- 명시적 false 우선순위도 테스트로 고정되었다.

현재 판단:

- 이 영역은 Spring/FastAPI 정합성이 맞다.
- 향후 신규 content-dependent action을 추가할 때만 Spring translator test를 함께 추가하면 된다.

### P1. Preview casing 및 metadata 변환 확인 완료

FastAPI preview response는 raw snake_case다.

```json
{
  "workflow_id": "wf_1",
  "node_id": "node_1",
  "output_data": {},
  "preview_data": {},
  "metadata": {
    "preview_scope": "source_metadata",
    "content_policy": "metadata_only",
    "include_content": false
  }
}
```

Spring public API는 camelCase를 노출할 수 있다.

```json
{
  "workflowId": "wf_1",
  "nodeId": "node_1",
  "outputData": {},
  "previewData": {},
  "metadata": {
    "previewScope": "source_metadata",
    "contentPolicy": "metadata_only",
    "includeContent": false
  }
}
```

Spring 확인 결과:

- FastAPI preview raw `workflow_id`, `node_id`, `output_data`, `preview_data`는 Spring `NodePreviewResponse` camelCase 필드로 매핑된다.
- metadata는 Spring public canonical camelCase 값을 보강한다.
- FastAPI raw snake_case metadata도 함께 보존한다.

현재 판단:

- preview top-level casing 충돌은 없다.
- FE가 snake/camel fallback을 유지하면 전환기에도 안전하다.

### P1. `content_policy` 대표값과 alias 확인 완료

FastAPI raw 표준:

- `metadata_only`
- `content_included`
- `content_status_only`

Spring 확인 결과:

- Spring public canonical `contentPolicy` 대표값은 `metadata_only`, `content_included`, `content_status_only`다.
- `required_by_downstream`은 Spring 대표값으로 만들지 않는다.
- downstream 의미는 `contentRequired/contentRequiredReason`으로 표현한다.

현재 판단:

- FastAPI raw와 Spring public 대표값이 충돌하지 않는다.
- FE는 기존 방어 로직으로 `required_by_downstream`을 수용할 수 있지만, Spring 대표값으로 기대하지 않아도 된다.

### P1. Nested content metadata 보존 확인

FastAPI는 아래 metadata를 nested map으로 내려준다.

```json
{
  "content_metadata": {
    "extraction_method": "docx_xml",
    "content_kind": "plain_text",
    "truncated": false,
    "char_count": 1200,
    "original_char_count": 1200,
    "limits": {
      "max_download_bytes": 10485760,
      "max_extracted_chars": 60000,
      "max_llm_input_chars": 60000
    }
  }
}
```

Spring 확인 결과:

- Spring은 FastAPI raw metadata를 함께 보존한다.
- Spring public canonical camelCase 값을 보강한다.

잔여 권장:

- `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json` 기반으로 `content_metadata.limits` 보존 contract test를 유지한다.
- nested metadata를 public API에서 camelCase로 강제 변환할지 raw map으로 유지할지는 Spring 문서에 고정한다.

### P1. Callback output과 public 조회 API 경계 확인 완료

FastAPI callback은 마지막 성공 노드 output을 `output`에 담는다.

Spring 확인 결과:

- node-level 사용자 표시용 code/context는 Mongo `nodeLogs[].error.code/context` 조회 경로에서 보존한다.
- execution detail/node data 조회 테스트가 추가되었다.

잔여 권장:

- callback `output` 또는 Mongo `nodeLogs[].outputData` 중 public result 기준 경로를 Spring 문서에 명시한다.
- FastAPI callback output은 저장 전 sanitize/truncate된 payload이므로 Spring/FE가 이를 “전체 본문”으로 표현하지 않도록 한다.

### P1. 파일 지원 범위 표현 확인 필요

FastAPI 현재 지원:

- Google Drive TXT/CSV/TSV
- PDF text layer
- Google Workspace export
- DOCX
- PPTX
- HWPX

FastAPI 현재 후속:

- Gmail attachment download + extractor 연결
- scan PDF OCR 실제 지원
- image OCR/vision 실제 지원

잔여 확인 요청:

- Spring catalog/template/help text에서 Gmail attachment 본문 요약을 완료 기능처럼 표현하지 않는다.
- scan PDF/image는 OCR/vision 실제 구현 전까지 `unsupported` 표시를 전제로 둔다.
- “모든 문서 완전 호환” 같은 사용자 문구를 쓰지 않는다.

### P2. MIME type 및 extension fallback 확인 필요

FastAPI는 아래 방식으로 파일군을 판별한다.

| 파일군 | FastAPI 판별 |
|--------|--------------|
| DOCX | MIME `application/vnd.openxmlformats-officedocument.wordprocessingml.document` 또는 `.docx` |
| PPTX | MIME `application/vnd.openxmlformats-officedocument.presentationml.presentation` 또는 `.pptx` |
| HWPX | MIME `application/vnd.hancom.hwpx`, `application/x-hwpx` 또는 `.hwpx` |

잔여 확인 요청:

- Spring source catalog/file type branch에서 같은 MIME/extension 기준을 사용한다.
- Google Drive에서 MIME이 비거나 다르게 내려오는 경우 filename extension이 FastAPI까지 전달되는지 확인한다.

---

## 4. 함께 돌리면 좋은 Contract Test

Spring Boot 쪽에 아래 fixture 기반 테스트를 추가하는 것을 권장한다.

Fixture:

- `.docs/front_docs/DOCUMENT_CONTENT_RUNTIME_SAMPLE_PAYLOADS.json`

테스트 케이스:

| 케이스 | 확인 |
|--------|------|
| `metadata_only` | `contentPolicy=metadata_only`, `contentStatus=not_requested` 보존 |
| `content_included` | `contentPolicy=content_included`, `contentStatus=available`, `contentMetadata.limits` 보존 |
| `content_status_only` | 본문 없음 상태에서 `content_included`로 오표시하지 않음 |
| `too_large` | `DOCUMENT_CONTENT_TOO_LARGE`와 사용자 문구 매핑 |
| `unsupported` | `DOCUMENT_CONTENT_UNSUPPORTED`와 사용자 문구 매핑 |
| `empty` | content-dependent action에서 성공 요약으로 처리하지 않음 |
| `failed` | raw exception 없이 사용자 표시 문구만 노출 |
| `not_requested` | `DOCUMENT_CONTENT_NOT_REQUESTED`를 별도 code로 보존 |

통합 시나리오:

1. Spring이 `requires_content=true`인 LLM node를 포함한 workflow를 FastAPI에 전달한다.
2. FastAPI가 unsupported 파일에서 `DOCUMENT_CONTENT_UNSUPPORTED`로 실패한다.
3. Spring callback 수신 후 public execution 조회 API에서 동일 code/context를 확인한다.
4. FE가 동일 public response에서 사용자 문구와 file card 상태를 표시한다.

---

## 5. 팀별 전달 문구

### Spring Boot 팀

```text
Spring Boot 쪽 실제 코드 기준 확인 결과를 반영했습니다.

아래 항목은 확인 완료로 정리합니다.

1. FastAPI preview raw workflow_id/node_id/output_data/preview_data는 Spring NodePreviewResponse camelCase 필드로 매핑됩니다.
2. metadata는 Spring public canonical contentPolicy=metadata_only|content_included|content_status_only를 제공하고, FastAPI raw snake_case metadata도 함께 보존됩니다.
3. required_by_downstream은 Spring 대표값으로 만들지 않고, downstream 의미는 contentRequired/contentRequiredReason으로 표현합니다.
4. FastAPI HTTP error body의 DOCUMENT_CONTENT_* code는 Spring public ErrorCode로 보존됩니다.
5. callback top-level error는 문자열만 유지하되, 사용자 표시용 node-level code/context는 Mongo nodeLogs[].error.code/context 조회 경로에서 보존됩니다.
6. runtime_config.requires_content=true 생성 경로는 choiceActionId=summarize + action=process, legacy choiceSelections, 명시적 false 우선순위까지 테스트로 고정되었습니다.

잔여 권장은 아래 정도입니다.

1. content_status/content_error/content_metadata.limits가 Spring 저장/조회 public API까지 보존되는 fixture 기반 contract test를 유지해 주세요.
2. Spring catalog/template/help text에서 Gmail attachment 본문 요약, scan PDF OCR, image OCR/vision을 완료 기능처럼 표현하지 않도록 문구를 고정해 주세요.
3. MIME/extension fallback 기준이 FastAPI와 다르지 않은지 source catalog/file type branch에서 한 번 더 확인해 주세요.
```

### FastAPI 팀

```text
Spring Boot 쪽 실제 코드와 테스트 기준으로 확인했습니다.

현재 FastAPI 쪽에서 Spring과 맞춰야 할 추가 코드 변경은 즉시 보이지 않습니다.

확인된 정합성은 아래와 같습니다.

1. preview raw snake_case top-level 필드는 Spring DTO camelCase로 매핑됩니다.
2. metadata는 Spring canonical camelCase 값을 보강하면서 FastAPI raw metadata도 보존합니다.
3. contentPolicy 대표값은 metadata_only/content_included/content_status_only이며, downstream 의미는 contentRequired/contentRequiredReason으로 유지됩니다.
4. DOCUMENT_CONTENT_* HTTP error body는 Spring public ErrorCode로 보존됩니다.
5. completion callback top-level error는 문자열만 유지하지만, 사용자 표시용 node-level code/context는 Mongo nodeLogs[].error.code/context 조회 경로에서 보존됩니다.
6. Spring targeted test와 전체 ./gradlew test가 모두 통과했습니다.

따라서 FastAPI는 현재 계약을 유지하면 됩니다. 단, 향후 Spring이 callback-only 조회 경로를 새로 만들 경우에만 completion callback payload의 errorCode/errorContext 확장을 다시 협의하면 됩니다.
```

### FE 팀

```text
FE는 지금처럼 snake_case/camelCase를 모두 수용하는 방향이 안전합니다.

Spring public API 확인 전까지는 아래를 유지해 주세요.

1. contentStatus/content_status, contentMetadata/content_metadata 둘 다 읽기.
2. contentPolicy/content_policy 둘 다 읽기.
3. required_by_downstream과 content_required_but_unavailable 둘 다 수용하기.
4. content는 전체 본문이 아니라 truncate될 수 있는 preview body로 표시하기.
```

---

## 6. 최종 판단

현재 FastAPI 구현과 Spring Boot 실제 코드 확인 결과 기준으로는 Spring Boot - FastAPI 간 큰 충돌은 없다.

이번에 확인 완료된 핵심 포인트는 아래 3개다.

1. Spring이 FastAPI `DOCUMENT_CONTENT_*` code/context를 public execution 조회 API까지 보존한다.
2. Spring이 preview/raw payload의 snake_case 필드를 public camelCase 또는 FE 호환 형태로 변환한다.
3. Spring이 content-dependent node에서 `requires_content=true`를 내려주는 경로를 테스트로 고정했다.

남은 확인은 제품 범위 문구, Gmail attachment/OCR 후속 범위, sample fixture 기반 회귀 테스트에 가깝다.

따라서 현재 구현은 Spring/FastAPI/FE 통합 관점에서 안정적으로 다음 리뷰 단계로 넘길 수 있다.
