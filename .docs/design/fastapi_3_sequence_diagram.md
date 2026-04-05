# 3. FastAPI 시퀀스 다이어그램 (Sequence Diagram)

> Spring Boot `5_sequence_diagram.md` 대응 문서
> FastAPI 서버 내부의 주요 실행 흐름을 시퀀스 다이어그램으로 정의합니다.

---

## 3.1 UC-E01: 워크플로우 전체 실행 (정상 흐름)

Spring Boot로부터 워크플로우 실행 요청을 받아 성공적으로 처리하는 정상 흐름입니다.

```mermaid
sequenceDiagram
    participant SB as Spring Boot
    participant MW as InternalAuthMiddleware
    participant API as WorkflowRouter
    participant Exec as WorkflowExecutor
    participant SM as WorkflowStateManager
    participant Factory as NodeFactory
    participant Snap as SnapshotManager
    participant Node as NodeStrategy
    participant DB as MongoDB

    SB->>MW: POST /api/v1/workflows/{id}/execute
    Note over MW: X-Internal-Token 검증
    Note over MW: X-User-ID 추출 → request.state
    MW->>API: 인증 통과

    API->>DB: workflow_executions에 초기 문서 생성 (status: pending)
    DB-->>API: execution_id 반환
    API-->>SB: HTTP 200 { execution_id, status: "running" }
    Note over API: 백그라운드 태스크로 실행 전환

    API->>Exec: await execute(workflow_definition, credentials)
    Exec->>SM: transition(RUNNING)

    loop 각 노드(Node) 순회
        Exec->>Factory: create(node.type, node.config)
        Factory-->>Exec: NodeStrategy 인스턴스

        Exec->>Snap: save(node_id, current_data)

        Note over Exec: 노드 실행 시작 시각 기록
        Exec->>Node: await execute(current_data)
        Node-->>Exec: next_data
        Note over Exec: 노드 실행 종료 시각 기록 + NodeLog 생성
    end

    Exec->>SM: transition(SUCCESS)
    Exec->>DB: workflow_executions 업데이트 (status: success, node_logs, finished_at)
    Exec-->>API: ExecutionResult
```

---

## 3.2 UC-E01-ERR: 워크플로우 실행 실패 및 롤백

노드 실행 중 오류 발생 시 FAILED 상태로 전환하고, 롤백 가능 상태로 전환하는 흐름입니다.

```mermaid
sequenceDiagram
    participant SB as Spring Boot
    participant API as ExecutionRouter
    participant Exec as WorkflowExecutor
    participant SM as WorkflowStateManager
    participant Node as NodeStrategy (node_3)
    participant Snap as SnapshotManager
    participant DB as MongoDB

    Note over Exec: node_1, node_2 정상 실행 완료

    Exec->>Snap: save("node_3", current_data)
    Exec->>Node: await execute(current_data)
    Node--xExec: Exception 발생 (외부 API 오류 등)

    Exec->>SM: transition(FAILED)
    Exec->>DB: workflow_executions 업데이트
    Note over DB: status: failed<br/>node_logs[2].status: failed<br/>node_logs[2].error: { code, message }

    Exec->>SM: transition(ROLLBACK_AVAILABLE)
    Exec->>DB: status → rollback_available 업데이트

    Note over SB: 프론트엔드에서 실행 상태 폴링 → 실패 확인

    SB->>API: POST /api/v1/executions/{exec_id}/rollback
    API->>DB: execution 조회 (상태 확인)
    API->>Snap: rollback_to("node_2")
    Snap-->>API: node_2 실행 직후의 snapshot 데이터

    API->>SM: transition(PENDING)
    API->>DB: status → pending, 롤백 지점 기록
    API-->>SB: HTTP 200 { status: "pending", rollback_point: "node_2" }
```

---

## 3.3 UC-A01: LLM 노드 실행 상세 흐름

워크플로우 내에서 `LLMNodeStrategy`가 호출되어 LangChain 및 OpenAI를 거쳐 결과를 반환하는 상세 흐름입니다.

```mermaid
sequenceDiagram
    participant Exec as WorkflowExecutor
    participant Node as LLMNodeStrategy
    participant LLM as LLMService
    participant LC as LangChain (LCEL)
    participant OAI as OpenAI API

    Exec->>Node: await execute(input_data)
    Note over Node: config에서 action 추출<br/>(summarize, classify, process 등)

    alt action == "summarize"
        Node->>LLM: await summarize(input_data["text"])
        LLM->>LC: PromptTemplate | ChatOpenAI | StrOutputParser
        Note over LC: 프롬프트: "다음 내용을 3줄로 요약해주세요: {text}"
    else action == "classify"
        Node->>LLM: await classify(input_data["text"], config["categories"])
        LLM->>LC: PromptTemplate | ChatOpenAI | StrOutputParser
        Note over LC: 프롬프트: "다음 내용을 [{categories}] 중 하나로 분류해주세요: {text}"
    else action == "process" (기본)
        Node->>LLM: await process(config["prompt"], context=input_data)
        LLM->>LC: PromptTemplate | ChatOpenAI | StrOutputParser
    end

    LC->>OAI: Async Completion Request
    OAI-->>LC: JSON/Text Response
    LC-->>LLM: Parsed Output (str)
    LLM-->>Node: 결과 문자열

    Node-->>Exec: { ...input_data, llm_result: "결과 문자열" }
```

---

## 3.4 UC-W02: LLM 기반 워크플로우 자동 생성

Spring Boot가 사용자의 자연어 프롬프트를 FastAPI에 전달하여, LLM이 워크플로우 구조(노드/엣지)를 자동 생성하는 흐름입니다.

```mermaid
sequenceDiagram
    participant SB as Spring Boot
    participant MW as InternalAuthMiddleware
    participant API as LLMRouter
    participant LLM as LLMService
    participant LC as LangChain (LCEL)
    participant OAI as OpenAI API

    SB->>MW: POST /api/v1/llm/generate-workflow
    Note over MW: X-Internal-Token 검증
    MW->>API: 인증 통과

    Note over API: Request Body:<br/>{ prompt: "지메일에 메일이 오면<br/>슬랙으로 요약해서 보내줘",<br/>context: "..." }

    API->>LLM: await generate_workflow(prompt, context)
    LLM->>LC: PromptTemplate | ChatOpenAI | JsonOutputParser
    Note over LC: 시스템 프롬프트:<br/>"당신은 워크플로우 설계 전문가입니다.<br/>사용자 요구사항을 분석하여<br/>nodes와 edges 구조로 변환하세요."

    LC->>OAI: Async Completion Request
    OAI-->>LC: JSON Response

    alt 유효한 JSON 응답
        LC-->>LLM: { nodes: [...], edges: [...] }
        LLM-->>API: 워크플로우 구조 dict
        API-->>SB: HTTP 200 { result: { nodes: [...], edges: [...] } }
    else JSON 파싱 실패 또는 잘못된 구조
        LC--xLLM: OutputParserException
        LLM--xAPI: FlowifyException(LLM_GENERATION_FAILED)
        API-->>SB: HTTP 422 { error_code: "LLM_GENERATION_FAILED", message: "..." }
    end
```

---

## 3.5 UC-P01: 트리거 기반 자동 실행

APScheduler를 통해 등록된 스케줄 트리거가 워크플로우를 자동 실행하는 흐름입니다.

```mermaid
sequenceDiagram
    participant SB as Spring Boot
    participant MW as InternalAuthMiddleware
    participant API as TriggerRouter
    participant Sched as SchedulerService
    participant Exec as WorkflowExecutor
    participant DB as MongoDB

    Note over SB: 워크플로우에 트리거 설정 시

    SB->>MW: POST /api/v1/triggers
    Note over MW: X-Internal-Token 검증
    MW->>API: 인증 통과

    Note over API: Request Body:<br/>{ workflow_id, user_id,<br/>type: "cron", config: { hour: 9, minute: 0 },<br/>workflow_definition, credentials }

    API->>Sched: add_cron_job(job_id, execute_func, hour=9, minute=0)
    Sched-->>API: 등록 완료
    API-->>SB: HTTP 200 { trigger_id, status: "active" }

    Note over Sched: 매일 09:00 트리거 발동

    Sched->>Exec: await execute(stored_workflow_definition, stored_credentials)
    Exec->>DB: 실행 로그 저장
    Note over Exec: 정상 실행 흐름 (3.1 참조)
```

---

## 3.6 외부 서비스 연동 흐름 (Input/Output 노드)

### 3.6.1 InputNodeStrategy - Google Drive 파일 수집

```mermaid
sequenceDiagram
    participant Exec as WorkflowExecutor
    participant Input as InputNodeStrategy
    participant GD as GoogleDriveService
    participant API as Google Drive API

    Exec->>Input: await execute(input_data)
    Note over Input: config.source == "google_drive"
    Note over Input: input_data.credentials.google → token 추출

    Input->>GD: await list_files(token, config.target_folder)
    GD->>API: GET https://www.googleapis.com/drive/v3/files
    Note over API: Authorization: Bearer {token}
    API-->>GD: File List JSON

    loop 각 파일
        Input->>GD: await download_file(token, file_id)
        GD->>API: GET .../files/{id}?alt=media
        API-->>GD: File Content
    end

    GD-->>Input: [{ name, content, mime_type }, ...]
    Input-->>Exec: { raw_files: [...], source: "google_drive", data_type: "FILE_LIST" }
```

### 3.6.2 OutputNodeStrategy - Slack 메시지 전송

```mermaid
sequenceDiagram
    participant Exec as WorkflowExecutor
    participant Output as OutputNodeStrategy
    participant Slack as SlackService
    participant API as Slack API

    Exec->>Output: await execute(input_data)
    Note over Output: config.target == "slack"
    Note over Output: input_data.credentials.slack → token 추출

    Output->>Slack: await send_message(token, config.channel, input_data.llm_result)
    Slack->>API: POST https://slack.com/api/chat.postMessage
    Note over API: Authorization: Bearer {token}<br/>Body: { channel, text }
    API-->>Slack: { ok: true, ts: "..." }

    Slack-->>Output: { sent: true, timestamp: "..." }
    Output-->>Exec: { ...input_data, output_result: { target: "slack", sent: true } }
```

---

## 3.7 에러 전파 흐름 (Exception Propagation)

```mermaid
sequenceDiagram
    participant Client as Spring Boot
    participant MW as InternalAuthMiddleware
    participant Handler as GlobalExceptionHandler
    participant Router as Any Router
    participant Service as Any Service

    alt 인증 실패
        Client->>MW: 요청 (잘못된 X-Internal-Token)
        MW-->>Client: HTTP 401 { error_code: "UNAUTHORIZED", message: "..." }
    else 비즈니스 예외
        Client->>MW: 요청 (유효한 토큰)
        MW->>Router: 인증 통과
        Router->>Service: 비즈니스 로직 호출
        Service--xRouter: FlowifyException(NODE_EXECUTION_FAILED)
        Router--xHandler: 예외 전파
        Handler-->>Client: HTTP 500 { success: false, error_code: "NODE_EXECUTION_FAILED", message: "..." }
    else 외부 API 오류
        Service--xRouter: FlowifyException(EXTERNAL_API_ERROR, detail={service: "google_drive"})
        Router--xHandler: 예외 전파
        Handler-->>Client: HTTP 502 { success: false, error_code: "EXTERNAL_API_ERROR", message: "...", detail: {...} }
    end
```
