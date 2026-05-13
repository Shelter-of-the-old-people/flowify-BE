# 문서 본문 읽기/요약 자동화 문제 분석 및 해결 요구사항

> 작성일: 2026-05-13  
> 대상: Google Drive/Gmail 파일 입력 -> LLM 요약/분석 -> Slack/Gmail/Sheets/Drive 등 후속 자동화  
> 관련 문서:
> - `docs/FOLDER_DOCUMENT_SUMMARY_TEMPLATE_DESIGN.md`
> - `docs/WORKFLOW_NODE_PREVIEW_DRY_RUN_DESIGN.md`
> - `docs/WORKFLOW_FILE_TYPE_BRANCH_FRONTEND_DESIGN.md`
> - `docs/GMAIL_NODE_OPTION_C_IMPLEMENTATION_PLAN.md`
> - `docs/backend/FASTAPI_RUNTIME_CONTRACT_REQUEST.md`

---

## 1. 문제 요약

현재 사용자가 문서 요약, 문서 내부 읽기, 문서 내용을 기반으로 한 자동화를 구성하면 LLM 또는 후속 노드가 문서 본문을 제대로 사용하지 못하는 것으로 보인다.

가장 유력한 원인은 파일이 워크플로우로 전달되더라도 canonical payload 안에 실제 문서 본문 또는 추출 텍스트가 포함되지 않거나, 본문 포함 여부가 런타임 계약에서 명확하지 않은 것이다.

---

## 2. 분석 방법

분석은 아래 순서로 진행한다.

1. 사용자 시나리오를 데이터 흐름으로 분해한다.
   - Google Drive 폴더/파일 source
   - Gmail 첨부파일 source
   - `FILE_LIST -> LOOP -> SINGLE_FILE -> LLM`
   - `SINGLE_FILE -> LLM`
   - `SINGLE_EMAIL -> LLM`
2. FE가 저장하는 노드 config와 edge 계약을 확인한다.
   - source node의 `source_mode`, `target`, `canonical_input_type`
   - choice wizard의 `choiceActionId`, `choiceNodeType`, `choiceSelections`
   - loop/branch edge label과 sourceHandle
3. Spring이 FE config를 FastAPI runtime payload로 변환할 때 본문 추출 요구가 보존되는지 확인한다.
   - `runtime_source`
   - `runtime_config`
   - `dataType`, `outputDataType`
4. FastAPI source/loop/LLM 전략이 canonical payload의 어떤 필드를 읽는지 확인한다.
   - `FILE_LIST.items[]`
   - `SINGLE_FILE.content`
   - `SINGLE_EMAIL.body`
   - Gmail attachment metadata/content
5. preview와 실제 실행 결과를 비교한다.
   - preview `includeContent=false/true`
   - 최신 실행 node data의 `inputData`, `outputData`
   - LLM 노드 input에 본문 필드가 존재하는지

---

## 3. 현재 FE 기준 관찰

### 3.1 FE는 파일 본문을 직접 읽지 않는다

FE의 source 설정은 파일/폴더/라벨 같은 target을 저장하고, 실제 외부 파일 다운로드나 본문 추출은 Spring/FastAPI 런타임에 위임하는 구조다.

따라서 FE만으로 문서 내부를 읽는 문제를 해결할 수 없고, 런타임 canonical payload 계약이 필요하다.

### 3.2 choice wizard는 LLM 의도를 저장하지만 본문 포함 정책은 저장하지 않는다

문서 요약 액션을 선택하면 AI 노드에는 주로 아래 값이 저장된다.

```json
{
  "choiceActionId": "summarize",
  "choiceNodeType": "AI",
  "choiceSelections": {
    "summarize": "brief"
  },
  "isConfigured": true
}
```

이 config는 “요약하라”는 의미는 담지만, “Google Drive 파일을 다운로드하고 본문을 추출해서 LLM input으로 넣어라”는 실행 정책은 담지 않는다.

### 3.3 preview API에는 `includeContent`가 있지만 기본값은 metadata 중심이다

기존 dry-run 설계는 preview request에 `includeContent`를 두고, 1차 구현 기본값을 `false`로 정의했다.

```json
{
  "limit": 50,
  "includeContent": false
}
```

따라서 preview에서 파일 카드만 보이고 본문이 비어 있는 것은 설계상 가능한 상태다. 다만 실제 실행에서도 동일하게 본문이 누락되면 LLM 요약은 정상 동작할 수 없다.

### 3.4 기존 Gmail 계획에서는 attachment content 전달이 제외되어 있다

Gmail 선택지 C 계획에서 `attachment content download/전달`은 명시적으로 1차 제외 범위다. 그러므로 Gmail 첨부 문서 요약은 현재 계약만으로는 동작 보장이 어렵다.

---

## 4. 원인 가설

### 4.1 1순위: source payload가 본문 없는 metadata-only 형태로 전달됨

`FILE_LIST` 또는 `SINGLE_FILE` payload가 아래처럼 파일 식별자와 메타데이터만 포함하면 LLM은 문서 내용을 알 수 없다.

```json
{
  "type": "SINGLE_FILE",
  "file_id": "file_1",
  "filename": "report.pdf",
  "mime_type": "application/pdf",
  "url": "https://drive.google.com/file/d/file_1"
}
```

LLM 요약 가능 payload는 최소한 아래처럼 추출 텍스트가 있어야 한다.

```json
{
  "type": "SINGLE_FILE",
  "file_id": "file_1",
  "filename": "report.pdf",
  "mime_type": "application/pdf",
  "content": "문서에서 추출된 텍스트...",
  "content_status": "available"
}
```

### 4.2 2순위: `FILE_LIST -> LOOP` 변환에서 item content가 보존되지 않음

폴더 기반 자동화는 대개 `FILE_LIST`를 받은 뒤 loop가 한 파일씩 `SINGLE_FILE`로 넘긴다. 이때 source가 content를 포함했더라도 loop가 item metadata만 복사하면 LLM input에서 본문이 사라진다.

### 4.3 3순위: LLM strategy가 파일 payload의 본문 필드를 읽지 않음

LLM strategy가 `TEXT.content`나 `SINGLE_EMAIL.body`만 읽고 `SINGLE_FILE.content`, `text`, `extracted_text` 같은 필드를 읽지 않으면, source가 본문을 내려도 요약에 사용되지 않는다.

### 4.4 4순위: 파일 타입별 추출 전략이 미정

파일 종류마다 본문 추출 방식이 다르다.

- Google Docs: export text/plain 또는 Docs API
- PDF: PDF text extraction 또는 OCR fallback
- CSV/TSV: 인코딩 감지 후 text/table 형태로 파싱
- PowerPoint: slide text, speaker note, alt text 추출
- Word: paragraph/table/header/footer text 추출
- HWPX: XML 기반 본문 텍스트 추출
- TXT/Markdown: 인코딩 감지 후 원문 text 사용
- 이미지: OCR 또는 vision 모델
- 기타 바이너리: unsupported 처리

파일 타입별 지원 범위와 실패 응답이 없으면 “파일은 받았지만 읽지 못함” 상태가 사용자에게 설명되지 않는다.

### 4.5 5순위: Gmail 첨부파일은 content download 범위 밖

Gmail `attachment_email` 또는 첨부파일 기반 source가 attachment metadata만 반환하면, Drive 파일과 달리 원본 다운로드 경로가 없어 LLM이 문서를 읽을 수 없다.

---

## 5. 해결 요구사항

### 5.1 Canonical payload에 문서 본문 필드를 표준화한다

`SINGLE_FILE`은 아래 필드를 표준으로 가진다.

```json
{
  "type": "SINGLE_FILE",
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
    "original_char_count": 0
  }
}
```

`FILE_LIST.items[]`는 `SINGLE_FILE`과 같은 item shape를 사용한다. 목록 preview에서는 content를 생략할 수 있지만, 실제 실행에서 LLM 또는 content-dependent action으로 연결될 때는 본문 추출이 수행되어야 한다.

### 5.1.1 1차 지원 대상 파일 타입

문서 요약/본문 읽기 자동화는 최소 아래 파일군을 호환 대상으로 둔다.

| 파일군 | 대표 확장자 | 대표 MIME type | 추출 방식 | 1차 등급 | 1차 기대 |
|--------|-------------|----------------|-----------|-----------|----------|
| PDF text layer | `.pdf` | `application/pdf` | text layer 추출 | 필수 지원 | 텍스트 PDF는 `content_status=available` |
| PDF scan | `.pdf` | `application/pdf` | OCR fallback | 조건부 지원 | OCR 미구현이면 `unsupported`, 구현 시 `ocr` 기록 |
| CSV/TSV | `.csv`, `.tsv` | `text/csv`, `text/tab-separated-values` | delimiter/encoding 감지 후 text 또는 table summary input 생성 | 필수 지원 | UTF-8, UTF-8 BOM, CP949 대응 |
| PowerPoint modern | `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | slide text/note/alt text 추출 | 필수 지원 | slide 순서 유지 |
| PowerPoint legacy | `.ppt` | `application/vnd.ms-powerpoint` | 변환 가능 시 추출 | 조건부 지원 | 미구현이면 `unsupported` |
| HWPX | `.hwpx` | `application/hwp+zip`, `application/x-hwpx` | zip 내부 XML 파싱 후 본문 추출 | 필수 지원 | `.hwpx` 본문 text 추출 |
| Word modern | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | paragraph/table/header/footer text 추출 | 필수 지원 | paragraph와 table text 포함 |
| Word legacy | `.doc` | `application/msword` | 변환 가능 시 추출 | 조건부 지원 | 미구현이면 `unsupported` |
| Plain text | `.txt`, `.md`, `.log` | `text/plain`, `text/markdown` | encoding 감지 후 원문 사용 | 필수 지원 | UTF-8, UTF-8 BOM, CP949 대응 |
| Image common | `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff` | `image/*` | OCR 또는 vision 모델 기반 text/description 추출 | 조건부 지원 | OCR/vision 미구현이면 `unsupported` |
| Image animated/HEIC | `.gif`, `.heic` | `image/gif`, `image/heic` | 대표 frame 추출 또는 변환 후 OCR/vision | 조건부 지원 | 미구현이면 `unsupported` |
| Google Workspace | Google Docs/Slides/Sheets | Google Drive export MIME | text/plain, csv, pptx 등으로 export 후 추출 | 필수 지원 | export 가능한 파일 우선 지원 |

지원하지 못하는 확장자 또는 MIME type은 `content_status=unsupported`로 응답하고, 사용자에게 표시 가능한 `content_error`를 함께 내려야 한다.

1차 등급 의미:

- 필수 지원: 1차 완료 기준에 포함한다. 성공 또는 명확한 파일별 실패 사유가 필요하다.
- 조건부 지원: 1차에서 extractor를 구현하지 않아도 되지만, 지원 여부와 실패 상태를 명확히 반환해야 한다.

### 5.1.2 파일 타입 판별 기준

런타임은 확장자만으로 파일 타입을 확정하지 않는다. 아래 순서로 판별한다.

1. Google Drive/Gmail이 제공하는 MIME type
2. 파일 확장자
3. 파일 signature 또는 archive 내부 구조
4. 추출기 실행 결과

MIME type과 확장자가 충돌하면 MIME type을 우선하되, 추출 실패 시 확장자 기반 fallback을 시도한다.

### 5.1.3 추출 결과 정규화

파일 타입별 원본 구조가 달라도 LLM input에는 일관된 text representation을 전달한다.

- PDF/Word/HWPX/TXT: 본문 문단 순서를 유지한다.
- CSV/TSV: header와 주요 row를 읽을 수 있는 text/table 형태로 변환한다.
- PPTX: slide 번호, slide title, body, speaker note를 구분 가능한 text로 변환한다.
- 이미지: OCR 텍스트와 image description을 구분한다.
- Google Sheets export CSV는 row/column 구조가 사라지지 않도록 header를 포함한다.

추출된 본문이 너무 길면 truncate하되, `content_metadata.truncated=true`, `char_count`, `original_char_count`를 내려야 한다.

`content_kind` 의미:

- `plain_text`: 일반 문서 본문
- `table_text`: CSV/TSV/Sheets처럼 표 구조에서 만든 text representation
- `slide_text`: PPTX/Slides처럼 slide 단위로 만든 text representation
- `ocr_text`: 이미지 또는 스캔 문서에서 OCR로 추출한 텍스트
- `image_description`: vision 모델이 생성한 이미지 설명
- `mixed`: OCR 텍스트와 image description 등 여러 결과를 합친 입력
- `none`: 본문이 없거나 추출하지 않은 상태

### 5.2 Runtime은 content-dependent action을 판별해야 한다

아래 action은 본문이 필요한 작업으로 본다.

- `summarize`
- `extract_info`
- `translate`
- `classify_by_content`
- `describe_image`
- `ocr`
- `ai_summarize`
- `ai_analyze`

책임 분리는 아래처럼 둔다.

- Spring은 `choiceActionId`, `choiceNodeType`, `dataType`, `outputDataType`를 바탕으로 `runtime_config.requires_content`를 생성한다.
- FastAPI는 `runtime_config.requires_content=true`인 노드 실행 또는 preview에서 source/loop/LLM 직전 본문 추출을 수행한다.
- FastAPI는 `requires_content=true`인데 본문을 만들 수 없으면 빈 요약을 생성하지 않고 `content_status`와 실행/preview error를 명확히 반환한다.

### 5.3 `FILE_LIST -> LOOP -> SINGLE_FILE`에서 content 보존을 보장한다

Loop strategy는 `FILE_LIST.items[]`의 각 item을 `SINGLE_FILE`로 전달할 때 아래 필드를 유지해야 한다.

- `file_id`
- `filename`
- `mime_type`
- `url`
- `content`
- `content_status`
- `content_error`
- `content_metadata`

만약 list 단계에서 content가 없고 다음 노드가 content-dependent action이면 loop 또는 다음 LLM 단계에서 lazy extraction을 수행해야 한다.

### 5.4 LLM strategy는 파일/메일 canonical input을 명시적으로 지원한다

LLM strategy는 입력 타입별 본문 필드를 아래 우선순위로 읽는다.

- `TEXT`: `content`
- `SINGLE_FILE`: `content`
- `SINGLE_EMAIL`: `body`, `bodyPreview`, `body_preview`, `snippet`
- `EMAIL_LIST`: 각 item의 `body`, `bodyPreview`, `body_preview`, `snippet`
- `FILE_LIST`: 각 item의 `content`, 없으면 filename/mime/url metadata만 보조 정보로 사용

본문이 필요한 action인데 `content_status`가 `unsupported`, `failed`, `too_large`, `not_requested`이면 성공처럼 빈 요약을 만들지 않고 명시적 실패 또는 부분 성공으로 응답해야 한다.

### 5.5 Preview와 실행의 content 정책을 분리하되 표시를 명확히 한다

preview 기본값은 metadata-only로 유지할 수 있다. 다만 사용자가 문서 요약 노드를 preview할 때는 다음 중 하나를 만족해야 한다.

- FE가 LLM 노드 preview 요청 시 `includeContent: true`를 보낸다.
- Spring/FastAPI가 content-dependent node preview에서는 자동으로 content extraction을 수행한다.
- 본문 추출을 하지 않는 경우 `reason` 또는 `metadata.preview_scope`로 “본문 미포함 preview”임을 명시한다.

### 5.6 Gmail 첨부파일 content 지원 범위를 별도 계약으로 추가한다

Gmail 첨부 문서 요약을 지원하려면 Gmail source payload에 아래 필드가 필요하다.

```json
{
  "type": "SINGLE_EMAIL",
  "email": {
    "subject": "string",
    "body": "string|null",
    "attachments": [
      {
        "attachment_id": "string",
        "filename": "string",
        "mime_type": "string",
        "size": "number|string|null",
        "content": "string|null",
        "content_status": "available|unsupported|too_large|failed|not_requested",
        "content_error": "string|null",
        "content_metadata": {
          "extraction_method": "gmail_attachment|pdf_text|csv_parse|pptx_text|word_text|hwpx_xml|plain_text|ocr|vision|none",
          "content_kind": "plain_text|table_text|slide_text|ocr_text|image_description|mixed|none",
          "truncated": false,
          "char_count": 0,
          "original_char_count": 0
        }
      }
    ]
  }
}
```

1차에서 Gmail attachment content를 지원하지 않는다면, Gmail 첨부 문서 요약 템플릿 또는 선택지는 “첨부파일 이름/메타데이터만 사용 가능”으로 제한해야 한다.

### 5.7 파일 크기와 보안 제한을 정의한다

본문 추출은 외부 파일 데이터를 다루므로 제한이 필요하다.

- 최대 다운로드 크기
- 최대 추출 문자 수
- LLM input 최대 문자 수
- 추출 결과 truncate 정책
- OAuth scope 부족 시 error code
- Google Drive 권한 없음/파일 삭제/바이러스 스캔 제한 파일 처리
- 민감 파일 로깅 금지

MVP에서는 구체 수치를 백엔드에서 정할 수 있으나, 적용된 제한값은 반드시 응답 metadata에 포함한다.

```json
{
  "content_metadata": {
    "limits": {
      "max_download_bytes": 0,
      "max_extracted_chars": 0,
      "max_llm_input_chars": 0
    }
  }
}
```

제한에 걸린 경우:

- 다운로드 크기 초과: `content_status=too_large`
- 추출 결과 truncate: `content_status=available`, `content_metadata.truncated=true`
- LLM input truncate: LLM 결과 metadata에 truncate 여부를 남긴다.

---

## 6. 백엔드 요청사항

### 6.1 Spring Boot

- FE config의 `choiceActionId`, `choiceNodeType`, `choiceSelections`를 FastAPI `runtime_config`에 안정적으로 전달한다.
- content-dependent action 판별 로직 위치를 FastAPI와 합의한다.
- `runtime_config.requires_content`를 생성해 FastAPI에 전달한다.
- preview 요청에서 target node가 content-dependent이면 `includeContent=true` 또는 이에 준하는 runtime flag를 전달한다.
- source/LLM 실행 실패를 raw exception이 아니라 사용자 표시 가능한 error code로 변환한다.
- 실행 node data에 `content_status`, `content_error`, `content_metadata`를 보존한다.

### 6.2 FastAPI

- Google Drive source에서 `SINGLE_FILE.content` 추출을 구현하거나 현재 지원 범위를 명확히 응답한다.
- Google Drive `FILE_LIST.items[]`에 content 포함이 필요한 경우 lazy extraction 또는 eager extraction 정책을 제공한다.
- Loop strategy에서 file item content 필드를 보존한다.
- LLM strategy가 `SINGLE_FILE.content`와 `FILE_LIST.items[].content`를 읽도록 보장한다.
- PDF, CSV, PPTX, HWPX, TXT, Word, image, Google Workspace, unsupported 파일별 `content_status`를 반환한다.
- 파일 타입별 extractor를 모듈화하고, extractor 선택 결과를 `content_metadata.extraction_method`에 기록한다.
- `content_metadata.content_kind`, `char_count`, `original_char_count`, `limits`를 반환한다.
- CSV/TXT 계열은 UTF-8, UTF-8 BOM, CP949 같은 한국어 문서에서 자주 나오는 인코딩을 처리한다.
- 이미지 계열은 OCR 가능 여부와 vision fallback 여부를 명확히 반환한다.
- Gmail attachment content는 지원 여부를 명시하고, 미지원이면 `content_status=not_requested|unsupported`로 반환한다.

---

## 7. FE 후속 요구사항

FE는 런타임 계약이 정리된 뒤 아래 항목을 반영한다.

- LLM 노드 preview 요청 시 content-dependent action이면 `includeContent: true`를 전달한다.
- `DataPreviewBlock`에서 `SINGLE_FILE.content_status`, `content_error`, `content_metadata.truncated`를 표시한다.
- `FILE_LIST` preview에서 item별 content 상태를 표시한다.
- Gmail 첨부파일 preview에서 attachment content 상태를 표시한다.
- content 미지원 파일에 대해 “파일은 받았지만 본문을 읽을 수 없음” 상태를 사용자 문구로 표시한다.
- 문서 요약 템플릿 설명에서 지원 파일 타입과 제한을 실제 런타임 기준으로 맞춘다.

---

## 8. 검증 시나리오

### 8.1 Google Drive 단일 문서 요약

1. Google Drive `single_file` source로 Google Docs 문서를 선택한다.
2. 다음 노드로 AI `summarize`를 선택한다.
3. AI 노드 preview 또는 실행 결과에서 inputData에 `SINGLE_FILE.content`가 있는지 확인한다.
4. outputData가 문서 본문 기반 요약인지 확인한다.

### 8.2 Google Drive 폴더 신규 파일 요약

1. Google Drive `folder_new_file` 또는 `folder_all_files` source를 설정한다.
2. `FILE_LIST -> LOOP -> AI summarize` 흐름을 만든다.
3. Loop output이 `SINGLE_FILE.content` 또는 lazy extraction 가능한 file id를 유지하는지 확인한다.
4. AI output이 파일명/메타데이터 요약이 아니라 본문 요약인지 확인한다.

### 8.3 PDF 요약

1. 텍스트가 포함된 PDF를 선택한다.
2. AI `summarize`를 실행한다.
3. `content_metadata.extraction_method=pdf_text`가 기록되는지 확인한다.
4. 스캔 PDF라면 OCR 지원 여부에 따라 `available` 또는 `unsupported`가 명확히 내려오는지 확인한다.

### 8.4 CSV 요약

1. UTF-8 CSV와 CP949 CSV를 각각 선택한다.
2. AI `summarize` 또는 `ai_analyze`를 실행한다.
3. header와 row 내용이 LLM input에 포함되는지 확인한다.
4. `content_metadata.extraction_method=csv_parse`가 기록되는지 확인한다.

### 8.5 PPTX 요약

1. `.pptx` 파일을 선택한다.
2. AI `summarize`를 실행한다.
3. slide title/body/note가 순서대로 추출되는지 확인한다.
4. `.ppt` 파일은 지원 또는 미지원 상태가 명확히 표시되는지 확인한다.

### 8.6 HWPX 요약

1. `.hwpx` 파일을 선택한다.
2. AI `summarize`를 실행한다.
3. XML 기반 본문 텍스트가 추출되는지 확인한다.
4. 암호화/손상 파일은 `content_status=failed|unsupported`로 응답하는지 확인한다.

### 8.7 Word 요약

1. `.docx` 파일을 선택한다.
2. AI `summarize`를 실행한다.
3. paragraph/table/header/footer 중 최소 본문 paragraph와 table text가 포함되는지 확인한다.
4. `.doc` 파일은 변환 가능 여부에 따라 `available` 또는 `unsupported`가 명확히 표시되는지 확인한다.

### 8.8 TXT/Markdown 요약

1. UTF-8, UTF-8 BOM, CP949 텍스트 파일을 각각 선택한다.
2. AI `summarize`를 실행한다.
3. 글자가 깨지지 않고 `content_metadata.extraction_method=plain_text`가 기록되는지 확인한다.

### 8.9 이미지 OCR/설명 생성

1. `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif` 파일을 선택한다.
2. OCR 또는 image description action을 실행한다.
3. OCR 가능 이미지는 추출 텍스트가 포함되는지 확인한다.
4. OCR 불가 이미지는 vision description 또는 `unsupported` 상태가 명확히 표시되는지 확인한다.

### 8.10 Gmail 첨부파일 요약

1. 첨부파일이 있는 Gmail source를 설정한다.
2. AI `summarize`를 연결한다.
3. 현재 범위에서 attachment content가 미지원이면 사용자에게 제한이 표시되는지 확인한다.
4. 지원 범위에 포함되면 `attachments[].content`가 LLM input으로 전달되는지 확인한다.

### 8.11 Preview와 실제 실행 비교

1. source node preview를 metadata-only로 확인한다.
2. AI node preview를 content 포함 모드로 확인한다.
3. 실제 workflow 실행 후 latest execution node data를 확인한다.
4. preview와 실행이 같은 canonical payload 필드를 사용하고 있는지 비교한다.

---

## 9. 완료 기준

- `SINGLE_FILE` canonical payload의 content 계약이 Spring/FastAPI/FE 문서에 반영되어 있다.
- PDF, CSV, PPTX, HWPX, TXT, Word, image, Google Workspace 파일의 지원/미지원 기준이 문서화되어 있다.
- 필수 지원 파일군은 1차 완료 기준에 포함되고, 조건부 지원 파일군은 `unsupported` 상태와 사용자 표시 가능한 사유가 반환된다.
- Spring은 content-dependent action에 `runtime_config.requires_content=true`를 전달한다.
- Google Drive 문서 요약에서 LLM input에 실제 본문이 들어간다.
- `FILE_LIST -> LOOP -> AI` 경로에서 본문 또는 lazy extraction key가 손실되지 않는다.
- content 추출 실패가 빈 요약 성공으로 처리되지 않는다.
- preview와 실제 실행 모두에서 본문 포함/미포함 상태가 구분된다.
- Gmail 첨부파일 요약은 지원 또는 미지원 범위가 명확히 표시된다.
