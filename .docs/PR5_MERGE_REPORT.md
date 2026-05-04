# PR #5 병합 보고서: feat/mail-summary-forward-backend

> **작성일:** 2026-05-04
> **PR:** #5 — 메일 요약 후 전달 런타임 및 프롬프트 처리 개선
> **작성자 (원본):** comboong2
> **병합 충돌 해결:** DG + Claude Opus 4.6
> **병합 순서:** PR #7 → PR #6 → **PR #5** (마지막)

---

## 1. 병합 배경

PR #5는 PR #7(파일 업로드 자동 공유), PR #6(폴더 문서 자동 요약)과 동일한 핵심 파일들을 수정했기 때문에, 병합 순서상 마지막에 처리되었다. PR #7과 #6이 먼저 main에 병합된 상태에서 충돌을 해결하고 병합하였다.

**충돌 발생 파일 (4건):**
- `app/core/nodes/input_node.py`
- `app/core/nodes/llm_node.py`
- `app/core/nodes/output_node.py`
- `tests/test_output_node.py`

**자동 병합 성공 파일 (3건):**
- `tests/test_input_node.py`
- `tests/test_llm_node.py`
- `.docs/MAIL_SUMMARY_SINGLE_RESULT_AGGREGATION_PLAN.md` (신규)

---

## 2. PR #5 원본 변경사항 (커밋 `031a9c3`)

PR #5가 원래 의도한 변경사항은 다음과 같다.

| # | 변경 내용 | 대상 파일 |
|---|----------|----------|
| 1 | Gmail `maxResults`를 노드 config에서 설정 가능하게 변경 (`_resolve_max_results`) | `input_node.py` |
| 2 | `EMAIL_LIST` → LLM 입력 시 메일 메타데이터 포함 (`[Email N]`, `From:`, `Date:`) | `llm_node.py` |
| 3 | Notion 페이지 제목 `title_template` 지원 (`_render_notion_title`) | `output_node.py` |
| 4 | 메일 요약 단일 결과 집계 설계 문서 | `.docs/MAIL_SUMMARY_SINGLE_RESULT_AGGREGATION_PLAN.md` |
| 5 | Gmail maxResults 설정 테스트 | `tests/test_input_node.py` |
| 6 | EMAIL_LIST 메타데이터 포함 테스트 | `tests/test_llm_node.py` |
| 7 | Notion title_template 테스트 | `tests/test_output_node.py` |

---

## 3. main과의 차이점 (PR #7, #6에서 추가된 변경사항)

PR #5 원본 대비, 현재 main에는 PR #7과 #6에서 추가된 아래 변경사항이 포함되어 있다.

### 3.1 코드 스타일 리팩토링 (PR #7)

전체 코드베이스에 걸친 정리 작업으로, PR #5의 기능과는 무관하다.

| 변경 | 예시 |
|------|------|
| docstring 한글 → 영어 | `"""입력 노드 — …"""` → `"""Fetch external source data…"""` |
| 주석 한글 → 영어 | `# Phase 1 지원 source 맵` → `# Phase 1 supported source modes only.` |
| 변수명 명확화 | `rs` → `runtime_source`, `f` → `drive_file`/`latest_file`, `m` → `msg`, `i` → `item` |
| `elif` → `if` (early return 패턴) | `elif service == "gmail":` → `if service == "gmail":` |
| `else: raise` → 탈출 후 `raise` | 불필요한 else 블록 제거 |
| 에러 메시지 세부 변경 | `'서비스 토큰이 없습니다'` → `'서비스의 토큰이 없습니다'` |
| logger f-string → % 포맷 | `f"외부 API 재시도 {attempt}…"` → `"External API retry %s/%s…"` |

**영향받는 파일:** `input_node.py`, `llm_node.py`, `base.py`

### 3.2 Google Drive 메타데이터 확장 (PR #7)

canonical payload에 새 필드가 추가되었다.

| 필드 | 설명 | 적용 위치 |
|------|------|----------|
| `file_id` | Drive 파일 ID | `SINGLE_FILE`, `FILE_LIST` item |
| `created_time` | 생성 시간 | `SINGLE_FILE`, `FILE_LIST` item |
| `modified_time` | 수정 시간 | `SINGLE_FILE`, `FILE_LIST` item |

**영향받는 파일:** `input_node.py`, 관련 테스트

### 3.3 Google Drive `list_files` 정렬 지원 (PR #6, #7)

| 변경 | 설명 |
|------|------|
| `order_by` 파라미터 추가 | `list_files(token, folder_id, max_results, order_by)` |
| `createdTime` 필드 추가 | fields에 `createdTime` 포함 |
| `folder_new_file` 모드 정렬 | `order_by="createdTime desc"` 사용 |

**영향받는 파일:** `google_drive.py`, `input_node.py`

### 3.4 Google Drive `download_file` content 정규화 (PR #7)

```python
# PR #5 원본 (변경 없음)
"content": content if isinstance(content, str) else str(content)

# 현재 main (PR #7 추가)
if isinstance(content, dict) and isinstance(content.get("text"), str):
    normalized_content = content["text"]
elif isinstance(content, str):
    normalized_content = content
else:
    normalized_content = str(content)
```

Drive API가 `{"text": "..."}` 형태로 응답하는 경우를 처리한다.

**영향받는 파일:** `google_drive.py`

### 3.5 LLM `SINGLE_FILE` 텍스트 추출 확장 (PR #7)

```python
# PR #5 원본
return input_data.get("content", "")

# 현재 main
parts = [
    f"Filename: {input_data.get('filename', '')}",
    f"MIME Type: {input_data.get('mime_type', '')}",
]
if input_data.get("created_time"):
    parts.append(f"Created Time: {input_data.get('created_time', '')}")
if input_data.get("url"):
    parts.append(f"Source URL: {input_data.get('url', '')}")
parts.append("")
parts.append(input_data.get("content", ""))
return "\n".join(parts).strip()
```

LLM에 파일 메타데이터를 컨텍스트로 함께 전달한다.

**영향받는 파일:** `llm_node.py`

### 3.6 LLM `FILE_LIST` 텍스트 추출 확장 (PR #7)

```python
# PR #5 원본
return "\n".join(f"- {i.get('filename', '')}" for i in items)

# 현재 main
return "\n".join(LLMNodeStrategy._format_file_list_item(item) for item in items)
```

`_format_file_list_item`은 filename 외에 mime_type, size, created_time, modified_time, url을 포함한다.

**영향받는 파일:** `llm_node.py`

### 3.7 LLM 출력 메타데이터 passthrough (PR #7)

```python
# PR #5 원본
return {"type": output_data_type, "content": result}

# 현재 main
return self._build_output_payload(output_data_type, result, input_data)
```

`_build_output_payload`는 `output_data_type == "TEXT"`일 때 입력의 `file_id`, `filename`, `mime_type`, `url`, `created_time`, `modified_time`을 출력에 복사한다.

**영향받는 파일:** `llm_node.py`

### 3.8 LLM `SPREADSHEET_DATA` 출력 지원 (PR #6)

| 추가 항목 | 설명 |
|----------|------|
| `LLMService.process_json()` | JSON 구조 출력을 기대하는 LLM 처리 메서드 |
| `LLMNodeStrategy._to_spreadsheet_payload()` | LLM JSON 결과를 `SPREADSHEET_DATA` canonical 형태로 정규화 |
| `output_data_type == "SPREADSHEET_DATA"` 분기 | LLM 노드에서 스프레드시트 출력을 별도 경로로 처리 |

**영향받는 파일:** `llm_node.py`, `llm_service.py`

### 3.9 `BaseIntegrationService` 정리 (PR #7)

docstring/주석 영어화 및 logger f-string → % 포맷 변환. 동작 변경 없음.

**영향받는 파일:** `base.py`

---

## 4. 충돌 해결 상세

### 4.1 `input_node.py` — elif → if 스타일 충돌

| PR #5 원본 | main (PR #7) | 해결 |
|-----------|-------------|------|
| `elif service == "gmail":` + `_resolve_max_results` | `if service == "gmail":` (maxResults 없음) | **main 스타일(`if`) + PR #5 기능(`_resolve_max_results`) 조합** |

PR #5의 `_resolve_max_results(config)` 호출은 그대로 유지하되, `elif` → `if` early return 패턴을 적용했다.

### 4.2 `llm_node.py` — EMAIL_LIST 포맷 충돌

| PR #5 원본 | main (PR #7) | 해결 |
|-----------|-------------|------|
| `[Email N]`, `From:`, `Date:` 포함 구조화 | 기존 단순 `Subject:\nBody` 유지 | **PR #5의 구조화 포맷 채택** |

PR #5의 EMAIL_LIST 포맷이 메일 요약 품질에 직접적으로 기여하므로 PR #5 버전을 채택했다.

### 4.3 `output_node.py` — Notion title 메서드 충돌

| PR #5 원본 | main (PR #7) | 해결 |
|-----------|-------------|------|
| `_render_notion_title(config, input_data)` — 항상 "Flowify Output" fallback | `_resolve_notion_title(config, input_data, default_title)` — data_type별 다른 기본 제목 | **main의 `_resolve_notion_title` 채택 + PR #5의 `subject` 키 추가** |

main의 `_resolve_notion_title`이 `default_title` 파라미터로 TEXT/SPREADSHEET_DATA별 다른 기본 제목을 지원하므로 더 유연하다. 여기에 PR #5의 `subject` 템플릿 변수를 추가하여 메일 요약 제목 생성이 가능하도록 했다.

최종 `replacements` 딕셔너리:
```python
replacements = {
    "date": ...,
    "filename": ...,
    "subject": ...,     # PR #5에서 추가
    "mime_type": ...,   # PR #7에서 추가
    "sheet_name": ...,  # PR #7에서 추가
    "source_url": ...,  # PR #7에서 추가
}
```

### 4.4 `tests/test_output_node.py` — title_template 테스트 충돌

| PR #5 원본 | main (PR #7) | 해결 |
|-----------|-------------|------|
| `{{subject}}` 기반 테스트 | `{{filename}}` 기반 테스트 | **두 테스트 모두 포함** |

- `test_notion_create_page_uses_title_template` → main의 `{{filename}}` 테스트
- `test_notion_title_template_with_subject` → PR #5의 `{{subject}}` 테스트 (이름 변경하여 추가)

---

## 5. PR #5 기능 보존 현황

| PR #5 기능 | 보존 여부 | 비고 |
|-----------|----------|------|
| `_resolve_max_results` (Gmail config 기반 maxResults) | 보존 | 그대로 유지 |
| `_fetch_gmail`에 `max_results` 파라미터 전달 | 보존 | 그대로 유지 |
| EMAIL_LIST 구조화 포맷 (`[Email N]`, `From:`, `Date:`) | 보존 | 그대로 유지 |
| Notion `title_template` — `{{subject}}` 변수 | 보존 | `_resolve_notion_title`에 통합 |
| Notion `title_template` — `{{date}}` 변수 | 보존 | 양쪽 PR 모두 포함 |
| `MAIL_SUMMARY_SINGLE_RESULT_AGGREGATION_PLAN.md` | 보존 | 자동 병합 성공 |
| Gmail maxResults 테스트 | 보존 | 자동 병합 성공 |
| EMAIL_LIST 메타데이터 테스트 | 보존 | 자동 병합 성공 |
| Notion subject 템플릿 테스트 | 보존 | 이름 변경하여 별도 테스트로 추가 |

---

## 6. 테스트 결과

```
224 passed in 12.49s
```

병합 전 PR #5 원본 기준 테스트 수와 비교:
- PR #5 원본: 기존 테스트 + 3건 추가
- 현재 main: PR #7 테스트 6건 + PR #6 테스트 4건 + PR #5 테스트 3건 + 충돌 해결 중 추가 1건 = 총 224건 통과

---

## 7. 요약

PR #5의 모든 기능(Gmail maxResults 설정, EMAIL_LIST 구조화 포맷, Notion title_template의 subject 지원)이 현재 main에 보존되었다. 충돌 해결 시 PR #7의 리팩토링 스타일과 PR #6의 스프레드시트 출력 기능을 기반으로 하되, PR #5의 고유 기능은 그대로 통합하는 방향으로 처리했다.

주요 차이점은 PR #7에서 도입된 코드 스타일 정리(docstring 영어화, 변수명 개선, early return 패턴)와 메타데이터 확장(file_id, created_time, modified_time)이며, 이들은 PR #5의 기능과 충돌 없이 공존한다.
