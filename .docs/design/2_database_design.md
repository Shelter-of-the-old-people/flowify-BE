# 2. 데이터베이스 설계

---

## 2.1 데이터베이스 개요

| 항목 | 내용 |
|------|------|
| DBMS | MongoDB 7 |
| 드라이버 | Spring Data MongoDB |
| 데이터베이스명 | flowify |
| 접근 URI | `mongodb://localhost:27017/flowify` (개발 환경) |

---

## 2.2 컬렉션 설계

### 2.2.1 users 컬렉션

| 필드명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| `_id` | ObjectId | PK | 사용자 고유 식별자 |
| `email` | String | Unique, Not Null | Google 계정 이메일 |
| `name` | String | Not Null | Google 프로필 이름 |
| `picture` | String | | Google 프로필 사진 URL |
| `googleId` | String | Unique, Not Null | Google 고유 ID (sub claim) |
| `refreshToken` | String | | Flowify Refresh Token (로그아웃용) |
| `createdAt` | Instant | Auto (@CreatedDate) | 생성 일시 |
| `updatedAt` | Instant | Auto (@LastModifiedDate) | 수정 일시 |
| `lastLoginAt` | Instant | | 마지막 로그인 일시 |

**소유 서비스:** Spring Boot (읽기/쓰기 모두)

---

### 2.2.2 workflows 컬렉션

| 필드명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| `_id` | ObjectId | PK | 워크플로우 고유 식별자 |
| `name` | String | Not Null | 워크플로우 이름 |
| `description` | String | | 워크플로우 설명 |
| `userId` | String | Not Null, ref → users | 소유자 사용자 ID |
| `sharedWith` | List\<String\> | | 공유된 사용자 ID 목록 |
| `isTemplate` | Boolean | Default: false | 템플릿 여부 |
| `templateId` | String | Nullable, ref → templates | 원본 템플릿 ID |
| `nodes` | List\<NodeDefinition\> | | 노드 목록 (임베디드) |
| `nodes[].id` | String | Not Null | 노드 고유 ID (e.g., "node_1") |
| `nodes[].category` | String | Not Null | 노드 카테고리 (communication \| storage \| spreadsheet \| web_crawl \| calendar \| development \| ai \| processing) |
| `nodes[].type` | String | Not Null | 노드 타입 (카테고리별 하위 타입) |
| `nodes[].config` | Map\<String, Object\> | | 노드별 설정 |
| `nodes[].position` | Position | | 캔버스 좌표 {x, y} |
| `nodes[].dataType` | String | Nullable | 입력 데이터 타입 (FILE_LIST \| SINGLE_FILE \| TEXT \| SPREADSHEET_DATA \| EMAIL_LIST \| SINGLE_EMAIL \| API_RESPONSE \| SCHEDULE_DATA) |
| `nodes[].outputDataType` | String | Nullable | 출력 데이터 타입 (노드 처리 결과에 따라 변환될 수 있음). mapping_rules.json의 각 action에 정의된 output_data_type 값 |
| `nodes[].role` | String | Nullable | 노드 역할 (start \| end \| middle) — 가이드형 생성 흐름에서의 위치 |
| `nodes[].authWarning` | Boolean | Default: false | 미인증 서비스 경고 여부 (템플릿에서 가져온 노드용) |
| `edges` | List\<EdgeDefinition\> | | 엣지 목록 (임베디드) |
| `edges[].source` | String | Not Null | 출발 노드 ID |
| `edges[].target` | String | Not Null | 도착 노드 ID |
| `trigger` | TriggerConfig | Nullable | 실행 조건 설정 (null이면 수동 실행). 시작 노드 설정(UC-W01-A)에서 사용자의 선택에 따라 시스템이 내부적으로 결정한다. |
| `trigger.type` | String | | 실행 조건 유형 (manual \| schedule \| event) |
| `trigger.config` | Map\<String, Object\> | | 실행 조건 설정값 (cron, 이벤트 감시 대상 등) |
| `isActive` | Boolean | Default: true | 트리거 활성화 여부 |
| `createdAt` | Instant | Auto (@CreatedDate) | 생성 일시 |
| `updatedAt` | Instant | Auto (@LastModifiedDate) | 수정 일시 |

**소유 서비스:** Spring Boot (쓰기), Spring Boot + FastAPI (읽기)

---

### 2.2.3 oauth_tokens 컬렉션

| 필드명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| `_id` | ObjectId | PK | 토큰 고유 식별자 |
| `userId` | String | Not Null, ref → users | 소유 사용자 ID |
| `service` | String | Not Null | 서비스명 (google \| slack \| notion) |
| `accessToken` | String | Not Null | AES-256-GCM 암호화된 액세스 토큰 |
| `refreshToken` | String | | AES-256-GCM 암호화된 리프레시 토큰 |
| `tokenType` | String | Default: "Bearer" | 토큰 유형 |
| `expiresAt` | Instant | | 액세스 토큰 만료 시각 |
| `scopes` | List\<String\> | | 권한 범위 |
| `createdAt` | Instant | Auto (@CreatedDate) | 생성 일시 |
| `updatedAt` | Instant | Auto (@LastModifiedDate) | 수정 일시 |

**소유 서비스:** Spring Boot (읽기/쓰기 모두)

---

### 2.2.4 templates 컬렉션

| 필드명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| `_id` | ObjectId | PK | 템플릿 고유 식별자 |
| `name` | String | Not Null | 템플릿 이름 |
| `description` | String | | 템플릿 설명 |
| `category` | String | Not Null | 카테고리 (communication \| storage \| spreadsheet \| web_crawl \| calendar) |
| `icon` | String | | 아이콘 식별자 |
| `nodes` | List\<NodeDefinition\> | | 사전 정의된 노드 구성 |
| `edges` | List\<EdgeDefinition\> | | 엣지 구성 |
| `requiredServices` | List\<String\> | | 필요한 외부 서비스 목록 |
| `isSystem` | Boolean | Default: false | 시스템 제공 여부 |
| `authorId` | String | Nullable, ref → users | 사용자 생성 템플릿의 작성자 ID |
| `useCount` | Integer | Default: 0 | 사용 횟수 통계 |
| `createdAt` | Instant | Auto (@CreatedDate) | 생성 일시 |

**소유 서비스:** Spring Boot (읽기/쓰기 모두)

---

### 2.2.5 workflow_executions 컬렉션

| 필드명 | 타입 | 제약조건 | 설명 |
|--------|------|---------|------|
| `_id` | ObjectId | PK | 실행 고유 식별자 |
| `workflowId` | String | Not Null, ref → workflows | 워크플로우 ID |
| `userId` | String | Not Null, ref → users | 실행 요청 사용자 ID |
| `state` | String | Not Null | 실행 상태 (pending \| running \| success \| failed \| rollback_available) |
| `nodeLogs` | List\<NodeLog\> | | 노드별 실행 로그 (임베디드) |
| `nodeLogs[].nodeId` | String | | 노드 ID |
| `nodeLogs[].status` | String | | 노드 상태 (pending \| running \| success \| failed \| skipped) |
| `nodeLogs[].inputData` | Map\<String, Object\> | | 노드 입력 데이터 |
| `nodeLogs[].outputData` | Map\<String, Object\> | | 노드 출력 데이터 |
| `nodeLogs[].snapshot` | NodeSnapshot | Nullable | 실행 전 상태 스냅샷 (롤백용) |
| `nodeLogs[].snapshot.capturedAt` | Instant | | 스냅샷 캡처 시각 |
| `nodeLogs[].snapshot.stateData` | Map\<String, Object\> | | 스냅샷 상태 데이터 |
| `nodeLogs[].error` | ErrorDetail | Nullable | 오류 상세 (code, message, stackTrace) |
| `nodeLogs[].startedAt` | Instant | | 노드 실행 시작 시각 |
| `nodeLogs[].finishedAt` | Instant | | 노드 실행 종료 시각 |
| `startedAt` | Instant | | 전체 실행 시작 시각 |
| `finishedAt` | Instant | | 전체 실행 종료 시각 |

**소유 서비스:** 공유 — Spring Boot (조회), FastAPI (기록)

---

### 2.2.6 선택지 매핑 데이터 — JSON 설정 파일

선택지 매핑 규칙은 **DB가 아닌 JSON 설정 파일(`docs/mapping_rules.json`)**로 관리한다. 별도 컬렉션 불필요.

**파일 구조:**
```
{
  "_meta": { version, description, updated_at },
  "data_types": {
    "DATA_TYPE_ID": {
      "label": "표시 이름",
      "requires_processing_method": true/false,
      "processing_method": { question, options },
      "actions": [
        {
          "id": "선택지 ID",
          "label": "표시 텍스트",
          "node_type": "LOOP | CONDITION_BRANCH | AI | DATA_FILTER | AI_FILTER | PASSTHROUGH",
          "output_data_type": "출력 데이터 타입",
          "priority": 1~99,
          "applicable_when": { 조건 },
          "follow_up": { question, options },
          "branch_config": { question, options, multi_select }
        }
      ]
    }
  },
  "node_types": { 6가지 노드 타입 정의 },
  "service_fields": { 서비스별 필드 목록 }
}
```

**참조:** `ChoiceMappingService`(DC-C0801)가 이 파일을 읽어 동적 선택지를 제공한다.

---

## 2.3 인덱스 설계

| 컬렉션 | 인덱스 | 타입 | 용도 |
|--------|--------|------|------|
| `users` | `email` | Unique | 이메일 기반 사용자 조회 |
| `users` | `googleId` | Unique | Google ID 기반 사용자 조회 |
| `workflows` | `userId` | 일반 | 사용자별 워크플로우 목록 조회 |
| `workflows` | `userId` + `isTemplate` | Compound | 사용자별 템플릿 필터링 |
| `workflows` | `sharedWith` | Multikey | 공유된 워크플로우 조회 |
| `oauth_tokens` | `userId` + `service` | Unique Compound | 사용자별 서비스당 1개 토큰 보장 |
| `templates` | `category` | 일반 | 카테고리별 템플릿 필터링 |
| `templates` | `isSystem` | 일반 | 시스템/사용자 템플릿 구분 |
| `workflow_executions` | `workflowId` | 일반 | 워크플로우별 실행 이력 조회 |
| `workflow_executions` | `userId` | 일반 | 사용자별 실행 이력 조회 |

---

## 2.4 컬렉션 간 참조 관계

```
┌─────────────────┐
│     users       │
│  (_id, email,   │
│   googleId)     │
└──┬──┬──┬──┬─────┘
   │  │  │  │
   │  │  │  └──────────────────────────┐
   │  │  │                             │
   │  │  └──────────────┐              │
   │  │                 │              │
   │  ▼                 ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  workflows   │ │ oauth_tokens │ │  templates   │
│  (userId     │ │ (userId,     │ │  (authorId)  │
│   ref→users) │ │  service)    │ │              │
└──┬───────────┘ └──────────────┘ └──────────────┘
   │
   │ workflowId ref→workflows
   ▼
┌────────────────────┐
│ workflow_executions │
│ (workflowId,       │
│  userId ref→users) │
└────────────────────┘
```

---

## 2.5 컬렉션 소유 서비스 요약

| 컬렉션 | 소유 서비스 | 읽기 | 쓰기 |
|--------|-----------|------|------|
| `users` | Spring Boot | Spring Boot | Spring Boot |
| `workflows` | Spring Boot | Spring Boot + FastAPI | Spring Boot |
| `oauth_tokens` | Spring Boot | Spring Boot | Spring Boot |
| `templates` | Spring Boot | Spring Boot | Spring Boot |
| `workflow_executions` | 공유 | Spring Boot (조회) | FastAPI (기록) |
