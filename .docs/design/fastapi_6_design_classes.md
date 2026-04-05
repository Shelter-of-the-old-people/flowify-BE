# 6. Design Classes (클래스 설계)

> Spring Boot `6_design_classes.md` 대응 문서
> FastAPI 서버의 모든 클래스에 대한 상세 속성, 메소드, 책임을 정의합니다.

---

## PK-F01: 워크플로우 실행 엔진 (core/engine/)

### DC-F0101: WorkflowExecutor

| 항목 | 내용 |
|------|------|
| **클래스 다이어그램 식별자** | PK-F01 |
| **클래스 식별자** | DC-F0101 |
| **클래스 명** | WorkflowExecutor |
| **파일 위치** | `app/core/engine/executor.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _state_manager | private | WorkflowStateManager | 워크플로우 상태 관리자 |
| _factory | private | NodeFactory (class ref) | 노드 팩토리 클래스 참조 |
| _snapshot_manager | private | SnapshotManager | 스냅샷 관리자 |
| _db | private | Database | MongoDB 데이터베이스 인스턴스 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | workflow_definition: dict, credentials: dict | ExecutionResult | 워크플로우 전체 실행. 노드 순회 → 각 노드 execute → 상태 전환 → DB 저장 |
| _execute_node | private async | node: NodeStrategy, input_data: dict, node_def: dict | dict | 단일 노드 실행. 스냅샷 저장 → 노드 실행 → NodeLog 생성 |
| _save_execution_log | private async | execution: WorkflowExecution | None | MongoDB `workflow_executions` 컬렉션에 실행 로그 저장 |
| _build_node_log | private | node_def: dict, status: str, input_data: dict, output_data: dict, duration_ms: int, error: ErrorDetail \| None | NodeLog | NodeLog 객체 생성 |
| _strip_credentials | private | data: dict | dict | 로그 저장 전 credentials 필드 제거 (보안) |

---

### DC-F0102: WorkflowStateManager

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0102 |
| **클래스 명** | WorkflowStateManager |
| **파일 위치** | `app/core/engine/state.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _state | private | WorkflowState | 현재 워크플로우 상태 |
| _TRANSITIONS | private (class) | dict[WorkflowState, list] | 유효한 상태 전환 맵 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| transition | public | new_state: WorkflowState | None | 상태 전환. 유효하지 않으면 InvalidStateTransition 발생 |
| state | public (property) | - | WorkflowState | 현재 상태 반환 |
| is_terminal | public | - | bool | 현재 상태가 종료 상태(SUCCESS)인지 확인 |

**상태 전환 규칙:**

| 현재 상태 | 전환 가능 상태 |
|-----------|---------------|
| PENDING | RUNNING |
| RUNNING | SUCCESS, FAILED |
| FAILED | ROLLBACK_AVAILABLE, PENDING |
| ROLLBACK_AVAILABLE | PENDING |
| SUCCESS | (종료 - 전환 불가) |

---

### DC-F0103: WorkflowState

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0103 |
| **클래스 명** | WorkflowState (Enum) |
| **파일 위치** | `app/core/engine/state.py` |

**값:** `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `ROLLBACK_AVAILABLE`

---

### DC-F0104: SnapshotManager

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0104 |
| **클래스 명** | SnapshotManager |
| **파일 위치** | `app/core/engine/snapshot.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _snapshots | private | dict[str, dict] | node_id → {data, timestamp} 스냅샷 저장소 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| save | public | node_id: str, data: dict | None | 노드 실행 전 데이터를 deep copy하여 스냅샷 저장 |
| get_snapshot | public | node_id: str | dict \| None | 특정 노드의 스냅샷 조회 |
| rollback_to | public | node_id: str | dict | 해당 노드의 스냅샷 데이터 반환 (롤백용). 없으면 예외 |
| get_all_snapshots | public | - | dict | 전체 스냅샷 반환 |

---

## PK-F02: 노드 전략 (core/nodes/)

### DC-F0201: NodeStrategy (Abstract Base Class)

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0201 |
| **클래스 명** | NodeStrategy (ABC) |
| **파일 위치** | `app/core/nodes/base.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| config | protected | dict | 노드별 설정값 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async (abstract) | input_data: dict | dict | 노드 실행 로직. 하위 클래스에서 구현 |
| validate | public (abstract) | - | bool | 노드 설정 유효성 검증 |

---

### DC-F0202: NodeFactory

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0202 |
| **클래스 명** | NodeFactory |
| **파일 위치** | `app/core/nodes/factory.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _NODE_REGISTRY | private (class) | dict[str, type] | 노드 타입 → 클래스 매핑 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| create | public (classmethod) | node_type: str, config: dict | NodeStrategy | 노드 타입에 해당하는 Strategy 인스턴스 생성. 미등록 타입 시 ValueError |
| register | public (classmethod) | node_type: str, node_class: type | None | 새 노드 타입 등록 |
| get_registered_types | public (classmethod) | - | list[str] | 등록된 노드 타입 목록 반환 |

**등록 테이블:**

| 키 | 클래스 | 내부 노드 타입 |
|----|--------|-------------|
| `input` | InputNodeStrategy | - |
| `llm` | LLMNodeStrategy | AI |
| `if_else` | IfElseNodeStrategy | CONDITION_BRANCH |
| `loop` | LoopNodeStrategy | LOOP |
| `data_filter` | DataFilterNodeStrategy | DATA_FILTER |
| `ai_filter` | AIFilterNodeStrategy | AI_FILTER |
| `passthrough` | PassthroughNodeStrategy | PASSTHROUGH |
| `output` | OutputNodeStrategy | - |

---

### DC-F0203: InputNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0203 |
| **클래스 명** | InputNodeStrategy |
| **파일 위치** | `app/core/nodes/input_node.py` |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | config.source에 따라 적절한 서비스 호출. credentials에서 토큰 추출 |
| validate | public | - | bool | source 필드 존재 여부 확인 |
| _fetch_from_google_drive | private async | token: str, folder_id: str | dict | GoogleDriveService.list_files → download_file |
| _fetch_from_gmail | private async | token: str | dict | Gmail API를 통한 메일 수집 |
| _fetch_from_web_crawl | private async | url: str, selectors: dict | dict | WebCrawlerService.crawl |
| _fetch_from_google_sheets | private async | token: str, spreadsheet_id: str | dict | Google Sheets 데이터 조회 |
| _fetch_from_google_calendar | private async | token: str, calendar_id: str | dict | Google Calendar 일정 조회 |

**source → 서비스 매핑:**

| config.source | 호출 서비스 | output_data_type | 관련 UC |
|---------------|-----------|-----------------|---------|
| `google_drive` | GoogleDriveService | FILE_LIST | UC-S02 |
| `gmail` | GmailService | EMAIL_LIST | UC-S01 |
| `web_crawl` | WebCrawlerService | API_RESPONSE | UC-S04 |
| `google_sheets` | GoogleSheetsService | SPREADSHEET_DATA | UC-S03 |
| `google_calendar` | GoogleCalendarService | SCHEDULE_DATA | UC-S05 |

---

### DC-F0204: LLMNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0204 |
| **클래스 명** | LLMNodeStrategy |
| **파일 위치** | `app/core/nodes/llm_node.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _llm_service | private | LLMService | LLM 서비스 인스턴스 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | config.action에 따라 LLMService의 적절한 메소드 호출. 결과를 input_data에 llm_result로 추가 |
| validate | public | - | bool | action 또는 prompt 필드 존재 확인 |

**action → LLMService 메소드 매핑:**

| config.action | LLMService 메소드 | 설명 |
|---------------|------------------|------|
| `summarize` | summarize(text) | 텍스트 요약 |
| `classify` | classify(text, categories) | 텍스트 분류 |
| `process` (기본) | process(prompt, context) | 범용 프롬프트 처리 |

---

### DC-F0205: IfElseNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0205 |
| **클래스 명** | IfElseNodeStrategy |
| **파일 위치** | `app/core/nodes/logic_node.py` |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | input_data[condition_field]를 expected_value와 비교. 결과에 따라 `branch: "true"` 또는 `"false"` 추가. Executor가 분기 처리 |
| validate | public | - | bool | condition_field, expected_value 필드 존재 확인 |

---

### DC-F0206: LoopNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0206 |
| **클래스 명** | LoopNodeStrategy |
| **파일 위치** | `app/core/nodes/logic_node.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| MAX_LOOP_ITERATIONS | private (class) | int | 최대 반복 횟수 (1000) |
| DEFAULT_TIMEOUT_SECONDS | private (class) | int | 기본 타임아웃 (300초) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | items_field의 리스트를 순회하며 내부 노드 체인 실행. 무한 루프 방지 |
| validate | public | - | bool | items_field 필드 존재 확인 |

---

### DC-F0208: DataFilterNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0208 |
| **클래스 명** | DataFilterNodeStrategy |
| **파일 위치** | `app/core/nodes/filter_node.py` (신규) |

> 내부 노드 타입 `DATA_FILTER`에 대응합니다. UC-P02(필터링 및 중복 제거)에서 사용자의 선택에 따라 시스템이 내부적으로 생성합니다.

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | 필터 조건 적용 + 중복 제거. 결과를 input_data에 filtered_items로 추가 |
| validate | public | - | bool | conditions 또는 unique_field 필드 존재 확인 |
| _apply_filter | private | items: list, conditions: list[dict] | list | 각 아이템에 대해 조건식(field, operator, value) 평가. 조건을 만족하는 아이템만 반환 |
| _remove_duplicates | private | items: list, unique_field: str | list | unique_field 기준으로 중복 아이템 제거 |
| _evaluate_condition | private | item: dict, condition: dict | bool | 단일 조건식 평가. 지원 연산자: eq, ne, gt, lt, gte, lte, contains, not_contains |

**config 예시:**

```json
{
  "conditions": [
    { "field": "price", "operator": "lte", "value": 50000 },
    { "field": "category", "operator": "eq", "value": "electronics" }
  ],
  "unique_field": "product_id",
  "logic": "and"
}
```

---

### DC-F0209: AIFilterNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0209 |
| **클래스 명** | AIFilterNodeStrategy |
| **파일 위치** | `app/core/nodes/filter_node.py` (신규) |

> 내부 노드 타입 `AI_FILTER`에 대응합니다. UC-P02에서 "조건에 맞는 것만 골라내기 (AI 판단)" 선택 시 시스템이 내부적으로 생성합니다.

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _llm_service | private | LLMService | LLM 서비스 인스턴스 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | 각 아이템을 LLM에 전달하여 필터 기준 충족 여부 판단. 통과한 아이템만 반환 |
| validate | public | - | bool | criteria 필드 존재 확인 |
| _filter_with_ai | private async | items: list, criteria: str | list | 각 아이템에 대해 LLM 판단 호출. True/False 응답으로 필터링 |
| _build_filter_prompt | private | item: dict, criteria: str | str | 아이템 데이터와 필터 기준을 결합한 프롬프트 생성 |

**config 예시:**

```json
{
  "criteria": "긍정적인 리뷰만 남기기",
  "batch_size": 10
}
```

---

### DC-F0210: PassthroughNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0210 |
| **클래스 명** | PassthroughNodeStrategy |
| **파일 위치** | `app/core/nodes/passthrough_node.py` (신규) |

> 내부 노드 타입 `PASSTHROUGH`에 대응합니다. "그대로 전달" 선택 시 데이터를 변환 없이 다음 노드로 전달합니다. UC-P07(출력 포맷 지정) 시 config 기반으로 포맷 변환을 수행할 수 있습니다.

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | config에 format이 있으면 포맷 변환, 없으면 input_data를 그대로 반환 |
| validate | public | - | bool | 항상 True (설정 불필요) |

---

### DC-F0207: OutputNodeStrategy

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0207 |
| **클래스 명** | OutputNodeStrategy |
| **파일 위치** | `app/core/nodes/output_node.py` |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| execute | public async | input_data: dict | dict | config.target에 따라 외부 서비스로 데이터 전송 |
| validate | public | - | bool | target 필드 존재 확인 |
| _send_to_slack | private async | token: str, channel: str, message: str | dict | SlackService.send_message |
| _send_to_notion | private async | token: str, page_id: str, content: str | dict | NotionService.create_page |
| _send_to_gmail | private async | token: str, to: str, subject: str, body: str | dict | Gmail API 전송 |
| _send_to_google_sheets | private async | token: str, spreadsheet_id: str, data: list | dict | Google Sheets 데이터 작성 |

**target → 서비스 매핑:**

| config.target | 호출 서비스 | 관련 UC |
|---------------|-----------|---------|
| `slack` | SlackService | UC-S01 |
| `notion` | NotionService | UC-S02 |
| `gmail` | GmailService | UC-S01 |
| `google_sheets` | GoogleSheetsService | UC-S03 |
| `google_drive` | GoogleDriveService | UC-S02 |
| `google_calendar` | GoogleCalendarService | UC-S05 |

---

## PK-F03: 서비스 레이어 (services/)

### DC-F0301: LLMService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0301 |
| **클래스 명** | LLMService |
| **파일 위치** | `app/services/llm_service.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _model | private | ChatOpenAI | LangChain ChatOpenAI 인스턴스 |
| _model_name | private | str | 모델명 (환경변수 LLM_MODEL_NAME) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| process | public async | prompt: str, context: str \| None | str | LCEL 체인으로 범용 프롬프트 처리. PromptTemplate \| ChatOpenAI \| StrOutputParser |
| summarize | public async | text: str | str | "다음 내용을 3줄로 요약해주세요" 프롬프트로 process 호출 |
| classify | public async | text: str, categories: list[str] | str | 분류 프롬프트로 process 호출 |
| generate_workflow | public async | prompt: str, context: str \| None | dict | 워크플로우 자동 생성. JsonOutputParser 사용. 실패 시 LLM_GENERATION_FAILED |

---

### DC-F0302: SchedulerService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0302 |
| **클래스 명** | SchedulerService |
| **파일 위치** | `app/services/scheduler_service.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _scheduler | private | AsyncIOScheduler | APScheduler 비동기 스케줄러 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| start | public | - | None | 스케줄러 시작 |
| shutdown | public | - | None | 스케줄러 종료 |
| add_cron_job | public | job_id: str, func: Callable, hour: int, minute: int | None | cron 기반 반복 작업 등록 |
| add_interval_job | public | job_id: str, func: Callable, seconds: int | None | 주기 기반 반복 작업 등록 |
| remove_job | public | job_id: str | None | 작업 제거 |
| get_jobs | public | - | list | 등록된 모든 작업 목록 |

---

### DC-F0303: VectorService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0303 |
| **클래스 명** | VectorService |
| **파일 위치** | `app/services/vector_service.py` |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| _client | private | ChromaClient | ChromaDB 클라이언트 |
| _collection | private | Collection | 기본 벡터 컬렉션 |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| add_documents | public async | documents: list[str], metadata: list[dict] | None | 문서를 임베딩하여 벡터 저장소에 추가 |
| search | public async | query: str, top_k: int = 5 | list[dict] | 유사도 검색 (RAG 파이프라인) |
| delete_collection | public async | - | None | 컬렉션 전체 삭제 |

---

## PK-F04: 외부 연동 서비스 (services/integrations/)

### DC-F0401: GoogleDriveService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0401 |
| **클래스 명** | GoogleDriveService |
| **파일 위치** | `app/services/integrations/google_drive.py` |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| list_files | public async | token: str, folder_id: str | list[dict] | Google Drive API files.list 호출 |
| download_file | public async | token: str, file_id: str | dict | 파일 다운로드. {name, content, mime_type} 반환 |
| upload_file | public async | token: str, name: str, content: bytes, folder_id: str | dict | 파일 업로드 |

---

### DC-F0402: SlackService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0402 |
| **클래스 명** | SlackService |
| **파일 위치** | `app/services/integrations/slack.py` (신규) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| send_message | public async | token: str, channel: str, text: str | dict | Slack chat.postMessage API 호출 |
| list_channels | public async | token: str | list[dict] | Slack conversations.list API 호출 |

---

### DC-F0403: NotionService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0403 |
| **클래스 명** | NotionService |
| **파일 위치** | `app/services/integrations/notion.py` (신규) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| create_page | public async | token: str, parent_id: str, title: str, content: str | dict | Notion API pages.create 호출 |
| update_page | public async | token: str, page_id: str, content: str | dict | Notion API pages.update 호출 |
| get_page | public async | token: str, page_id: str | dict | Notion API pages.retrieve 호출 |

---

### DC-F0404: WebCrawlerService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0404 |
| **클래스 명** | WebCrawlerService |
| **파일 위치** | `app/services/integrations/web_crawler.py` (신규) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| crawl | public async | url: str, selectors: dict | dict | 단일 URL 크롤링. BeautifulSoup으로 파싱 |
| crawl_multiple | public async | urls: list[str], selectors: dict | list[dict] | 복수 URL 크롤링 |

---

### DC-F0405: RestAPIService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0405 |
| **클래스 명** | RestAPIService |
| **파일 위치** | `app/services/integrations/rest_api.py` |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| call | public async | url: str, method: str, headers: dict, params: dict, body: dict, timeout: int | dict | 범용 HTTP 요청 실행 |

---

### DC-F0406: GmailService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0406 |
| **클래스 명** | GmailService |
| **파일 위치** | `app/services/integrations/gmail.py` (신규) |

> UC-S01(커뮤니케이션 노드)에서 Gmail 메일 수집 및 전송을 담당합니다.

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| list_messages | public async | token: str, query: str, max_results: int = 20 | list[dict] | Gmail API messages.list + messages.get 호출. query로 검색 필터 적용 |
| get_message | public async | token: str, message_id: str | dict | 단일 메일 상세 조회. {id, subject, from, body, date} 반환 |
| send_message | public async | token: str, to: str, subject: str, body: str | dict | Gmail API messages.send 호출. MIME 메시지 구성 후 전송 |
| watch_inbox | public async | token: str | dict | Gmail push notification 등록 (이벤트 트리거용) |

---

### DC-F0407: GoogleSheetsService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0407 |
| **클래스 명** | GoogleSheetsService |
| **파일 위치** | `app/services/integrations/google_sheets.py` (신규) |

> UC-S03(스프레드시트 노드)에서 Google Sheets 데이터 조회 및 작성을 담당합니다.

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| read_range | public async | token: str, spreadsheet_id: str, range: str | list[list] | Sheets API spreadsheets.values.get 호출. 2D 배열 반환 |
| write_range | public async | token: str, spreadsheet_id: str, range: str, values: list[list] | dict | Sheets API spreadsheets.values.update 호출 |
| append_rows | public async | token: str, spreadsheet_id: str, range: str, values: list[list] | dict | Sheets API spreadsheets.values.append 호출 |
| list_sheets | public async | token: str, spreadsheet_id: str | list[dict] | 스프레드시트 내 시트 목록 조회 |

---

### DC-F0408: GoogleCalendarService

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0408 |
| **클래스 명** | GoogleCalendarService |
| **파일 위치** | `app/services/integrations/google_calendar.py` (신규) |

> UC-S05(캘린더 노드)에서 Google Calendar 일정 조회 및 생성을 담당합니다.

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| list_events | public async | token: str, calendar_id: str, time_min: str, time_max: str | list[dict] | Calendar API events.list 호출. ISO 8601 형식의 시간 범위로 필터링 |
| create_event | public async | token: str, calendar_id: str, event: dict | dict | Calendar API events.insert 호출. {summary, start, end, description} |
| list_calendars | public async | token: str | list[dict] | 사용자 캘린더 목록 조회 |

---

## PK-F05: API 레이어 (api/)

### DC-F0501: InternalAuthMiddleware

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0501 |
| **클래스 명** | InternalAuthMiddleware |
| **파일 위치** | `app/api/v1/middleware.py` (신규) |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| app | private | ASGIApp | ASGI 애플리케이션 |
| _internal_token | private | str | 검증할 내부 토큰 (환경변수 INTERNAL_API_SECRET) |
| _exclude_paths | private | list[str] | 인증 제외 경로 (["/api/v1/health", "/docs", "/redoc"]) |

**메소드:**

| 메소드명 | 가시성 | 파라미터 | 반환값 | 설명 |
|----------|--------|---------|--------|------|
| __call__ | public async | scope, receive, send | None | ASGI 미들웨어 진입점. X-Internal-Token 헤더 검증. X-User-ID를 scope["state"]에 주입 |

---

### DC-F0502: Dependencies (함수 모듈)

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0502 |
| **파일 위치** | `app/api/v1/deps.py` |

**함수:**

| 함수명 | 파라미터 | 반환값 | 설명 |
|--------|---------|--------|------|
| get_db | - | Database | MongoDB 데이터베이스 인스턴스 반환 |
| get_user_id | request: Request | str | request.state에서 X-User-ID 추출. 없으면 401 |

---

## PK-F06: 공통 모듈 (common/)

### DC-F0601: ErrorCode

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0601 |
| **클래스 명** | ErrorCode (Enum) |
| **파일 위치** | `app/common/errors.py` (신규) |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| http_status | public | int | HTTP 상태 코드 |
| message | public | str | 기본 에러 메시지 |

**enum 값:**

| 코드 | HTTP Status | 메시지 | 관련 예외 요구사항 |
|------|-------------|--------|----------------|
| INTERNAL_ERROR | 500 | 내부 서버 오류 | - |
| INVALID_REQUEST | 400 | 잘못된 요청 | - |
| UNAUTHORIZED | 401 | 인증되지 않은 요청 | - |
| WORKFLOW_NOT_FOUND | 404 | 워크플로우를 찾을 수 없습니다 | - |
| EXECUTION_NOT_FOUND | 404 | 실행 이력을 찾을 수 없습니다 | - |
| INVALID_STATE_TRANSITION | 400 | 잘못된 상태 전환 | - |
| NODE_EXECUTION_FAILED | 500 | 노드 실행 실패 | EXR-06 |
| LLM_API_ERROR | 502 | LLM API 호출 오류 | EXR-03 |
| LLM_GENERATION_FAILED | 422 | LLM 워크플로우 자동 생성 실패 | EXR-04 |
| EXTERNAL_API_ERROR | 502 | 외부 서비스 API 오류 | EXR-01 |
| OAUTH_TOKEN_INVALID | 400 | OAuth 토큰이 유효하지 않습니다 | EXR-02 |
| CRAWL_FAILED | 502 | 웹 수집 오류 | EXR-07 |
| DATA_CONVERSION_FAILED | 422 | 데이터 변환 오류 | EXR-08 |
| ROLLBACK_UNAVAILABLE | 400 | 롤백할 수 없는 상태 | - |

---

### DC-F0602: FlowifyException

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0602 |
| **클래스 명** | FlowifyException (Exception 상속) |
| **파일 위치** | `app/common/errors.py` (신규) |

**속성:**

| 속성명 | 가시성 | 타입 | 설명 |
|--------|--------|------|------|
| error_code | public | ErrorCode | 에러 코드 |
| detail | public | str | 상세 에러 메시지 |
| context | public | dict \| None | 추가 컨텍스트 정보 |

---

### DC-F0603: GlobalExceptionHandler (함수)

| 항목 | 내용 |
|------|------|
| **클래스 식별자** | DC-F0603 |
| **파일 위치** | `app/common/errors.py` (신규) |

**함수:**

| 함수명 | 파라미터 | 반환값 | 설명 |
|--------|---------|--------|------|
| flowify_exception_handler | request: Request, exc: FlowifyException | JSONResponse | FlowifyException을 ApiErrorResponse 형식으로 변환하여 반환 |
| generic_exception_handler | request: Request, exc: Exception | JSONResponse | 미처리 예외를 INTERNAL_ERROR로 변환. 운영 환경에서는 스택 트레이스 숨김 |

> FastAPI의 `app.add_exception_handler()`를 통해 `main.py`에서 등록합니다.

---

## Pydantic 모델 상세

### DC-F0701: NodeDefinition

| 항목 | 내용 |
|------|------|
| **파일 위치** | `app/models/workflow.py` |

| 속성명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| id | str | (필수) | 노드 고유 ID |
| type | str | (필수) | 실행 타입 (input, llm, if_else, loop, data_filter, ai_filter, passthrough, output) |
| config | dict | (필수) | 노드별 설정값 |
| position | dict | {"x": 0, "y": 0} | 캔버스 좌표 |
| category | str \| None | None | 카테고리 (storage, communication, ai 등) |
| data_type | str \| None | None | 입력 데이터 타입 |
| output_data_type | str \| None | None | 출력 데이터 타입 |
| role | str \| None | None | 노드 역할 (start, end, middle) |
| auth_warning | bool | False | 미인증 서비스 경고 여부 |

### DC-F0702: EdgeDefinition

| 항목 | 내용 |
|------|------|
| **파일 위치** | `app/models/workflow.py` |

| 속성명 | 타입 | 설명 |
|--------|------|------|
| source | str | 출발 노드 ID |
| target | str | 도착 노드 ID |

### DC-F0703: WorkflowExecution

| 항목 | 내용 |
|------|------|
| **파일 위치** | `app/models/execution.py` |

| 속성명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| id | str \| None | None | MongoDB _id |
| workflow_id | str | (필수) | 워크플로우 ID |
| user_id | str | (필수) | 사용자 ID |
| state | WorkflowState | PENDING | 실행 상태 |
| node_logs | list[NodeLog] | [] | 노드별 실행 로그 |
| error_message | str \| None | None | 최종 에러 메시지 |
| started_at | datetime | (자동) | 실행 시작 시각 |
| finished_at | datetime \| None | None | 실행 종료 시각 |

### DC-F0704: NodeLog

| 항목 | 내용 |
|------|------|
| **파일 위치** | `app/models/execution.py` |

| 속성명 | 타입 | 기본값 | 설명 |
|--------|------|--------|------|
| node_id | str | (필수) | 노드 ID |
| status | str | (필수) | 실행 상태 (pending, running, success, failed, skipped) |
| input_data | dict | {} | 입력 데이터 (credentials 제외) |
| output_data | dict | {} | 출력 데이터 |
| snapshot | NodeSnapshot \| None | None | 실행 전 스냅샷 |
| error | ErrorDetail \| None | None | 오류 상세 |
| duration_ms | int | 0 | 실행 소요 시간 (ms) |
| started_at | datetime | (자동) | 시작 시각 |
| finished_at | datetime \| None | None | 종료 시각 |

### DC-F0705: 요청/응답 모델

| 모델명 | 파일 위치 | 용도 |
|--------|----------|------|
| WorkflowExecuteRequest | `app/models/requests.py` (신규) | 워크플로우 실행 요청 |
| ExecutionResult | `app/models/requests.py` (신규) | 실행 결과 응답 |
| LLMProcessRequest | `app/models/requests.py` (신규) | LLM 처리 요청 |
| LLMProcessResponse | `app/models/requests.py` (신규) | LLM 처리 응답 |
| GenerateWorkflowRequest | `app/models/requests.py` (신규) | 워크플로우 생성 요청 |
| GenerateWorkflowResponse | `app/models/requests.py` (신규) | 워크플로우 생성 응답 |
| TriggerCreateRequest | `app/models/requests.py` (신규) | 트리거 생성 요청 |
| TriggerResponse | `app/models/requests.py` (신규) | 트리거 응답 |
| ApiErrorResponse | `app/common/errors.py` (신규) | 에러 응답 |
