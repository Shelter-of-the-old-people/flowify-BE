# 8. 요구사항 추적 매트릭스 (Requirements Traceability)

> Spring Boot `7_requirements_traceability.md` 대응 문서
> 각 요구사항이 FastAPI 서버의 어떤 클래스/메소드에 구현되는지 추적합니다.

---

## 8.1 기능 요구사항 (SFR) 추적

### SFR-04: AI 처리 노드

| 요구사항 | Use Case | FastAPI 구현 클래스 | 메소드 | 상태 |
|---------|----------|-------------------|--------|------|
| AI 텍스트 요약 | UC-A01 | LLMNodeStrategy | execute() | Placeholder |
| AI 텍스트 분류 | UC-A01 | LLMNodeStrategy | execute() | Placeholder |
| AI 범용 프롬프트 처리 | UC-A01 | LLMNodeStrategy | execute() | Placeholder |
| LangChain LCEL 체인 | UC-A01 | LLMService | process(), summarize(), classify() | Placeholder |
| 워크플로우 자동 생성 | UC-W02 | LLMService | generate_workflow() | 미구현 |

### SFR-03: 서비스 커넥터 노드

| 요구사항 | Use Case | FastAPI 구현 클래스 | 메소드 | 상태 |
|---------|----------|-------------------|--------|------|
| Google Drive 파일 수집 | UC-S02 | InputNodeStrategy, GoogleDriveService | _fetch_from_google_drive() | Placeholder |
| Gmail 메일 수집 | UC-S01 | InputNodeStrategy, GmailService | _fetch_from_gmail() | 미구현 |
| Google Sheets 데이터 조회 | UC-S03 | InputNodeStrategy, GoogleSheetsService | _fetch_from_google_sheets() | 미구현 |
| Google Calendar 일정 조회 | UC-S05 | InputNodeStrategy, GoogleCalendarService | _fetch_from_google_calendar() | 미구현 |
| 웹 크롤링 (쿠팡, 네이버 등) | UC-S04 | InputNodeStrategy, WebCrawlerService | _fetch_from_web_crawl() | 미구현 |
| Slack 메시지 전송 | UC-S01 | OutputNodeStrategy, SlackService | _send_to_slack() | 미구현 |
| Notion 페이지 생성 | UC-S02 | OutputNodeStrategy, NotionService | _send_to_notion() | 미구현 |
| Gmail 메일 전송 | UC-S01 | OutputNodeStrategy, GmailService | _send_to_gmail() | 미구현 |
| Google Sheets 데이터 작성 | UC-S03 | OutputNodeStrategy, GoogleSheetsService | _write_to_google_sheets() | 미구현 |
| Google Drive 파일 업로드 | UC-S02 | OutputNodeStrategy, GoogleDriveService | _save_to_google_drive() | 미구현 |
| Google Calendar 일정 생성 | UC-S05 | OutputNodeStrategy, GoogleCalendarService | _create_calendar_event() | 미구현 |

### SFR-05: 워크플로우 실행

| 요구사항 | Use Case | FastAPI 구현 클래스 | 메소드 | 상태 |
|---------|----------|-------------------|--------|------|
| 워크플로우 순차 실행 | UC-E01 | WorkflowExecutor | execute() | 구조 존재 |
| 노드별 상태 관리 | UC-E01 | WorkflowStateManager | transition() | 구현 완료 |
| 실행 로그 MongoDB 저장 | UC-E01 | WorkflowExecutor | _save_execution_log() | Placeholder |
| 실행 상태 조회 | UC-E02 | ExecutionRouter (신규) | GET /executions/{id}/status | 미구현 |
| 실행 로그 조회 | UC-E02 | ExecutionRouter (신규) | GET /executions/{id}/logs | 미구현 |
| 스냅샷 기반 롤백 | UC-E01 | SnapshotManager, ExecutionRouter | rollback_to(), POST /rollback | 구조 존재 |

### SFR-06: 처리/로직 노드

| 요구사항 | Use Case | 내부 노드 타입 | FastAPI 구현 클래스 | 메소드 | 상태 |
|---------|----------|-------------|-------------------|--------|------|
| 트리거 기반 자동 실행 | UC-P01 | - | SchedulerService, TriggerRouter (신규) | add_cron_job() | 구조 존재 |
| 필터링 및 중복 제거 | UC-P02 | DATA_FILTER | DataFilterNodeStrategy (신규) | execute(), _apply_filter(), _remove_duplicates() | 미구현 |
| AI 기반 필터링 | UC-P02 | AI_FILTER | AIFilterNodeStrategy (신규) | execute(), _filter_with_ai() | 미구현 |
| 반복 처리 (Loop) | UC-P03 | LOOP | LoopNodeStrategy | execute() | Placeholder |
| 조건 분기 | UC-P04 | CONDITION_BRANCH | IfElseNodeStrategy | execute() | 기본 구현 |
| 다중 출력 | UC-P05 | CONDITION_BRANCH | IfElseNodeStrategy | _build_multi_branch() | 미구현 |
| 데이터 처리 (변환/집계) | UC-P06 | AI | LLMNodeStrategy | execute() | Placeholder |
| 출력 포맷 지정 | UC-P07 | PASSTHROUGH | PassthroughNodeStrategy (신규) | execute() | 미구현 |
| 조기 종료 | UC-P08 | - | LoopNodeStrategy | _check_early_stop() | 미구현 |
| 알림 | UC-P09 | - | OutputNodeStrategy | _send_to_slack(), _send_to_gmail() | 미구현 |
| 데이터 패스스루 | - | PASSTHROUGH | PassthroughNodeStrategy (신규) | execute() | 미구현 |

---

## 8.2 비기능 요구사항 (SPR) 추적

| 요구사항 ID | 내용 | FastAPI 구현 | 상태 |
|------------|------|-------------|------|
| SPR-01 | API 응답 시간 <500ms | 비동기 처리 (async/await) | 설계 반영 |
| SPR-01 | LLM 처리 <30s (비동기) | BackgroundTasks + 상태 폴링 | 설계 반영 |
| SPR-02 | 트리거 시작 <3s | APScheduler 비동기 실행 | 설계 반영 |
| SPR-02 | 동시 워크플로우 20+ | asyncio 기반 비동기 처리 | 설계 반영 |
| SPR-03 | LLM 호출 당 메모리 <200MB | 스트리밍 응답 + 메모리 모니터링 | 미구현 |

---

## 8.3 예외 요구사항 (EXR) 추적

| 요구사항 ID | 설명 | FastAPI 구현 | 에러 코드 | 상태 |
|------------|------|-------------|----------|------|
| EXR-01 | 외부 서비스 API 연결 오류 | Integration Services + 재시도 | EXTERNAL_API_ERROR | 미구현 |
| EXR-02 | OAuth 토큰 만료/무효 | Node Strategies (토큰 검증) | OAUTH_TOKEN_INVALID | 미구현 |
| EXR-03 | LLM API 호출 오류 | LLMService + 재시도 | LLM_API_ERROR | 미구현 |
| EXR-04 | LLM 자동 생성 실패 | LLMService.generate_workflow | LLM_GENERATION_FAILED | 미구현 |
| EXR-05 | 워크플로우 유효성 검증 | Spring Boot 담당 (FastAPI는 기본 검증만) | INVALID_REQUEST | - |
| EXR-06 | 실행 중 노드 오류 | WorkflowExecutor + SnapshotManager | NODE_EXECUTION_FAILED | 구조 존재 |
| EXR-07 | 웹 수집 오류 | WebCrawlerService + 재시도 | CRAWL_FAILED | 미구현 |
| EXR-08 | 이기종 데이터 변환 오류 | 노드 간 dict 변환 | DATA_CONVERSION_FAILED | 미구현 |

---

## 8.4 수용 테스트 (FT) 추적

### 실행 관련 테스트

| 테스트 ID | 테스트 내용 | FastAPI 구현 | 상태 |
|----------|-----------|-------------|------|
| FT-E01 | 워크플로우 실행 시작 | POST /workflows/{id}/execute | Placeholder |
| FT-E02 | 실행 중 상태 조회 | GET /executions/{id}/status | 미구현 |
| FT-E03 | 실행 완료 후 결과 조회 | GET /executions/{id}/logs | 미구현 |
| FT-E04 | 노드 실패 시 롤백 | POST /executions/{id}/rollback | 미구현 |
| FT-E05 | 실행 이력 조회 | GET /executions/{id}/logs | 미구현 |

### AI 노드 테스트

| 테스트 ID | 테스트 내용 | FastAPI 구현 | 상태 |
|----------|-----------|-------------|------|
| FT-A01 | LLM 텍스트 요약 | LLMNodeStrategy + LLMService.summarize | Placeholder |
| FT-A02 | LLM 텍스트 분류 | LLMNodeStrategy + LLMService.classify | Placeholder |

### 처리 노드 테스트

| 테스트 ID | 테스트 내용 | FastAPI 구현 | 상태 |
|----------|-----------|-------------|------|
| FT-P01 | 트리거 기반 자동 실행 | SchedulerService + TriggerRouter | 구조 존재 |
| FT-P02 | 데이터 필터링 및 중복 제거 | DataFilterNodeStrategy | 미구현 |
| FT-P02-AI | AI 기반 필터링 | AIFilterNodeStrategy + LLMService | 미구현 |
| FT-P03 | 반복 처리 동작 | LoopNodeStrategy | Placeholder |
| FT-P04 | 조건 분기 동작 | IfElseNodeStrategy | 기본 구현 |
| FT-P07 | 출력 포맷 지정 | PassthroughNodeStrategy | 미구현 |
| FT-P08 | 조기 종료 | LoopNodeStrategy._check_early_stop | 미구현 |

### 서비스 커넥터 테스트

| 테스트 ID | 테스트 내용 | FastAPI 구현 | 상태 |
|----------|-----------|-------------|------|
| FT-S01 | Google Drive 파일 수집 | GoogleDriveService | Placeholder |
| FT-S01-GM | Gmail 메일 수집 | GmailService | 미구현 |
| FT-S02 | Slack 메시지 전송 | SlackService | 미구현 |
| FT-S03 | Notion 페이지 생성 | NotionService | 미구현 |
| FT-S04 | 웹 크롤링 | WebCrawlerService | 미구현 |
| FT-S05 | Google Sheets 데이터 조회/작성 | GoogleSheetsService | 미구현 |
| FT-S06 | Google Calendar 일정 조회/생성 | GoogleCalendarService | 미구현 |
| FT-S07 | Gmail 메일 전송 | GmailService | 미구현 |

---

## 8.5 클래스 다이어그램 ↔ 설계 클래스 교차 참조

| 다이어그램 ID | 설계 클래스 ID | 클래스명 | 파일 위치 |
|-------------|-------------|---------|-----------|
| PK-F01 | DC-F0101 | WorkflowExecutor | `app/core/engine/executor.py` |
| PK-F01 | DC-F0102 | WorkflowStateManager | `app/core/engine/state.py` |
| PK-F01 | DC-F0103 | WorkflowState | `app/core/engine/state.py` |
| PK-F01 | DC-F0104 | SnapshotManager | `app/core/engine/snapshot.py` |
| PK-F02 | DC-F0201 | NodeStrategy (ABC) | `app/core/nodes/base.py` |
| PK-F02 | DC-F0202 | NodeFactory | `app/core/nodes/factory.py` |
| PK-F02 | DC-F0203 | InputNodeStrategy | `app/core/nodes/input_node.py` |
| PK-F02 | DC-F0204 | LLMNodeStrategy | `app/core/nodes/llm_node.py` |
| PK-F02 | DC-F0205 | IfElseNodeStrategy | `app/core/nodes/logic_node.py` |
| PK-F02 | DC-F0206 | LoopNodeStrategy | `app/core/nodes/logic_node.py` |
| PK-F02 | DC-F0207 | OutputNodeStrategy | `app/core/nodes/output_node.py` |
| PK-F02 | DC-F0208 | DataFilterNodeStrategy | `app/core/nodes/filter_node.py` (신규) |
| PK-F02 | DC-F0209 | AIFilterNodeStrategy | `app/core/nodes/filter_node.py` (신규) |
| PK-F02 | DC-F0210 | PassthroughNodeStrategy | `app/core/nodes/passthrough_node.py` (신규) |
| PK-F03 | DC-F0301 | LLMService | `app/services/llm_service.py` |
| PK-F03 | DC-F0302 | SchedulerService | `app/services/scheduler_service.py` |
| PK-F03 | DC-F0303 | VectorService | `app/services/vector_service.py` |
| PK-F04 | DC-F0401 | GoogleDriveService | `app/services/integrations/google_drive.py` |
| PK-F04 | DC-F0402 | SlackService | `app/services/integrations/slack.py` (신규) |
| PK-F04 | DC-F0403 | NotionService | `app/services/integrations/notion.py` (신규) |
| PK-F04 | DC-F0404 | WebCrawlerService | `app/services/integrations/web_crawler.py` (신규) |
| PK-F04 | DC-F0405 | RestAPIService | `app/services/integrations/rest_api.py` |
| PK-F04 | DC-F0406 | GmailService | `app/services/integrations/gmail.py` (신규) |
| PK-F04 | DC-F0407 | GoogleSheetsService | `app/services/integrations/google_sheets.py` (신규) |
| PK-F04 | DC-F0408 | GoogleCalendarService | `app/services/integrations/google_calendar.py` (신규) |
| PK-F05 | DC-F0501 | InternalAuthMiddleware | `app/api/v1/middleware.py` (신규) |
| PK-F06 | DC-F0601 | ErrorCode | `app/common/errors.py` (신규) |
| PK-F06 | DC-F0602 | FlowifyException | `app/common/errors.py` (신규) |
| PK-F06 | DC-F0603 | GlobalExceptionHandler | `app/common/errors.py` (신규) |

---

## 8.6 구현 현황 요약

| 상태 | 개수 | 비율 |
|------|------|------|
| 구현 완료 | 3 | 7% |
| 구조 존재 (Placeholder) | 8 | 19% |
| 미구현 | 31 | 74% |
| **합계** | **42** | **100%** |

> 신규 클래스(DataFilterNodeStrategy, AIFilterNodeStrategy, PassthroughNodeStrategy, GmailService, GoogleSheetsService, GoogleCalendarService) 추가 및 SFR-06 UC-P01~P09 세분화로 항목이 증가하였습니다.

### 다음 구현 우선순위

1. **Phase B-1~2**: InternalAuthMiddleware + ErrorCode/FlowifyException (기반 인프라)
2. **Phase B-4~5**: LLMService + LLMNodeStrategy (핵심 AI 기능)
3. **Phase B-6**: WorkflowExecutor 강화 (실행 로그 + 스냅샷)
4. **Phase B-7**: Execution/Trigger 엔드포인트 (API 완성)
5. **Phase B-8**: DataFilterNodeStrategy + AIFilterNodeStrategy + PassthroughNodeStrategy (신규 노드)
6. **Phase C**: 외부 서비스 연동 (Google Drive/Gmail/Sheets/Calendar, Slack, Notion, WebCrawler)
