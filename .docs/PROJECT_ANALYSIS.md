# Flowify Backend (FastAPI) - 프로젝트 분석 및 설계 문서

> 작성일: 2026-03-09
> 기반 문서: 주제제안서(김동현, 김민호, 윤동근, 최호림), 주제 결정 문서

---

## 1. 프로젝트 개요

**Flowify**는 비전문가가 AI 자동화 파이프라인을 쉽게 구축할 수 있도록 설계된 **노드 기반 워크플로우 플랫폼**이다.

### 핵심 컨셉
- **[입력 → AI 처리 → 출력]** 이라는 직관적인 3단계 구조
- 기존 자동화 도구(n8n, Zapier, Make)의 높은 진입 장벽을 극복
- 자연어 프롬프트로 AI 노드 동작 정의 (코드 불필요)
- 템플릿 기반으로 즉시 시작 가능

### 차별점
| 항목 | n8n / Zapier / Make | Flowify |
|------|-------------------|---------|
| 대상 사용자 | 개발자 / 기술 숙련자 | 비전문가 포함 전체 |
| AI 활용 | 부가 기능 | 핵심 노드 |
| 설정 방식 | 복잡한 데이터 매핑 | 자연어 프롬프트 |
| 진입 장벽 | 높음 | 낮음 (3단계 구조) |

---

## 2. 전체 시스템 아키텍처

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Frontend   │────▶│  Spring Boot     │────▶│   MongoDB       │
│  (React)    │     │  (메인 백엔드)      │     │  (Document DB)  │
└─────────────┘     └──────┬───────────┘     └─────────────────┘
                           │
                           ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │  FastAPI         │────▶│  Vector Store   │
                    │  (AI 서비스)      │     │  (FAISS/Chroma) │
                    └──────────────────┘     └─────────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │  LLM (EXAONE)   │
                    │  via LangChain  │
                    └──────────────────┘
```

### 역할 분리
- **Spring Boot**: 회원/인증 관리, 워크플로우 CRUD, 핵심 비즈니스 로직, OAuth 토큰 관리
- **FastAPI (이 레포)**: AI 모델 추론, LangChain 오케스트레이션, 비동기 파이프라인 실행, 벡터 검색
- **MongoDB**: 채팅 히스토리, 캔버스 노드 정보, 워크플로우 상태 등 비정형 데이터

---

## 3. FastAPI 서버의 담당 기능

### 3.1 LLM 처리 서비스
- 자연어 프롬프트 기반 데이터 처리 (요약, 분류, 질문 생성)
- LangChain을 통한 LLM 통합 인터페이스
- 프롬프트 템플릿 관리 및 체이닝
- 한국어 최적화 LLM(EXAONE 등) 연동

### 3.2 워크플로우 실행 엔진
- 노드 기반 파이프라인 실행 (Trigger → Input → AI처리 → Logic → Output)
- Strategy 패턴 기반 노드 실행 로직
- State 패턴 기반 워크플로우 상태 관리 (대기, 실행 중, 성공, 실패, 롤백)
- 비동기 실행 및 단계별 실시간 미리보기

### 3.3 외부 서비스 연동
- Google Drive / Sheets / Gmail API 연동
- Slack, Notion, GitHub API 연동
- 범용 REST API 호출 노드
- OAuth 토큰 기반 사용자별 서비스 접근

### 3.4 트리거 및 스케줄링
- 이벤트 트리거: Gmail 신규 메일, Google Drive 파일 업로드
- 시간 트리거: APScheduler 기반 스케줄 실행
- 웹훅 기반 실시간 이벤트 감지

### 3.5 벡터 검색 서비스
- FAISS / Chroma 기반 지식 베이스 구축
- 문서 임베딩 및 유사도 검색
- RAG(Retrieval-Augmented Generation) 파이프라인

---

## 4. FastAPI 프로젝트 구조 제안

```
flowify-BE/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 앱 진입점
│   ├── config.py                  # 환경 설정
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py          # v1 라우터 통합
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── workflow.py    # 워크플로우 실행 API
│   │   │   │   ├── llm.py         # LLM 처리 API
│   │   │   │   ├── trigger.py     # 트리거/스케줄 API
│   │   │   │   ├── integration.py # 외부 서비스 연동 API
│   │   │   │   └── health.py      # 헬스체크
│   │   │   └── deps.py            # 의존성 주입
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── executor.py        # 워크플로우 실행 엔진
│   │   │   ├── state.py           # State 패턴 - 상태 관리
│   │   │   └── snapshot.py        # 스냅샷 기반 롤백
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # 노드 추상 클래스 (Strategy)
│   │   │   ├── factory.py         # Factory 패턴 - 노드 생성
│   │   │   ├── input_node.py      # 입력 노드
│   │   │   ├── llm_node.py        # LLM 처리 노드
│   │   │   ├── logic_node.py      # 조건/반복 로직 노드
│   │   │   └── output_node.py     # 출력 노드
│   │   └── security.py            # 보안 유틸리티
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_service.py         # LangChain + LLM 서비스
│   │   ├── vector_service.py      # FAISS/Chroma 벡터 검색
│   │   ├── scheduler_service.py   # APScheduler 스케줄링
│   │   └── integrations/
│   │       ├── __init__.py
│   │       ├── google_drive.py    # Google Drive 연동
│   │       ├── google_sheets.py   # Google Sheets 연동
│   │       ├── gmail.py           # Gmail 연동
│   │       ├── slack.py           # Slack 연동
│   │       ├── notion.py          # Notion 연동
│   │       ├── github.py          # GitHub 연동
│   │       └── rest_api.py        # 범용 REST API 노드
│   ├── models/
│   │   ├── __init__.py
│   │   ├── workflow.py            # 워크플로우 모델
│   │   ├── node.py                # 노드 모델
│   │   ├── execution.py           # 실행 로그 모델
│   │   └── common.py              # 공통 DTO
│   └── db/
│       ├── __init__.py
│       └── mongodb.py             # MongoDB 연결
├── tests/
│   ├── __init__.py
│   ├── test_workflow.py
│   ├── test_llm.py
│   └── test_nodes.py
├── .env.example                   # 환경변수 예시
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml                 # 프로젝트 메타 + 의존성
├── requirements.txt               # pip 의존성
└── README.md
```

---

## 5. 핵심 설계 패턴

### 5.1 Strategy 패턴 - 노드 실행 로직
```python
# 각 노드 타입마다 별도 전략 클래스
class NodeStrategy(ABC):
    @abstractmethod
    async def execute(self, input_data: dict) -> dict:
        pass

class LLMNodeStrategy(NodeStrategy):
    async def execute(self, input_data: dict) -> dict:
        # LLM 호출 로직
        ...

class ConditionNodeStrategy(NodeStrategy):
    async def execute(self, input_data: dict) -> dict:
        # If/Else, Switch 분기 로직
        ...
```
- 새 노드 추가 시 기존 엔진 코드 수정 불필요 (OCP 준수)

### 5.2 State 패턴 - 워크플로우 상태 관리
- 상태: `PENDING` → `RUNNING` → `SUCCESS` / `FAILED` → `ROLLBACK_AVAILABLE`
- 각 상태 전환 규칙을 State 객체 내부에서 관리

### 5.3 Factory 패턴 - 노드 객체 생성
- 노드 타입 문자열 → 구체적인 Strategy 인스턴스 생성
- UI 에디터와 노드 클래스 간 결합도 최소화

### 5.4 Adapter 패턴 - 이기종 데이터 통합
- 외부 서비스별 상이한 JSON 구조를 공통 DTO로 정규화
- 노드 간 데이터 전달 시 일관된 인터페이스 보장

---

## 6. 주요 API 엔드포인트 설계 (안)

### 워크플로우 실행
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/workflows/{id}/execute` | 워크플로우 실행 |
| GET | `/api/v1/workflows/{id}/status` | 실행 상태 조회 |
| GET | `/api/v1/workflows/{id}/logs` | 실행 로그 조회 |
| POST | `/api/v1/workflows/{id}/rollback` | 특정 단계 롤백 |

### LLM 처리
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/llm/process` | LLM 프롬프트 처리 |
| POST | `/api/v1/llm/summarize` | 문서 요약 |
| POST | `/api/v1/llm/classify` | 데이터 분류 |
| GET | `/api/v1/llm/templates` | 프롬프트 템플릿 목록 |

### 외부 서비스 연동
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/integrations/{service}/auth` | OAuth 인증 |
| POST | `/api/v1/integrations/{service}/execute` | 서비스 동작 실행 |
| POST | `/api/v1/integrations/rest` | 범용 REST API 호출 |

### 트리거/스케줄
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/triggers/schedule` | 스케줄 트리거 등록 |
| POST | `/api/v1/triggers/webhook` | 웹훅 트리거 등록 |
| DELETE | `/api/v1/triggers/{id}` | 트리거 삭제 |

### 헬스체크
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/health` | 서버 상태 확인 |

---

## 7. 기술 스택 상세

| 구분 | 기술 | 용도 |
|------|------|------|
| 프레임워크 | FastAPI | 비동기 기반 REST API 서버 |
| AI 오케스트레이션 | LangChain | LLM 통합, 프롬프트 관리, 체이닝 |
| LLM | EXAONE (한국어 최적화) | 요약/분류/질문 생성 |
| 벡터 스토어 | FAISS, Chroma | 지식 베이스, 유사도 검색 |
| DB | MongoDB (Motor) | 비정형 데이터 비동기 접근 |
| 스케줄링 | APScheduler | 시간 기반 트리거 |
| 외부 연동 | google-api-python-client, slack-sdk, notion-client | 서비스 API 연동 |
| 문서 처리 | pdfminer.six, openpyxl, weasyprint | PDF/Excel 파싱 및 생성 |
| 컨테이너 | Docker | 환경 패키징 |
| 배포 | Cloudtype | 호스팅 |

---

## 8. 제약사항 및 고려사항

### 반드시 구현해야 할 안전장치
1. **무한 루프 방지**: Loop 노드에 Max Iterations + Timeout 필수 적용
2. **에러 핸들링**: 노드 실행 전후 스냅샷 저장, DB 기반 롤백 메커니즘
3. **토큰 보안**: 사용자별 OAuth 토큰 암호화 저장, user_id 기반 격리, 주기적 갱신
4. **LLM 응답 지연**: 비동기 처리 + 단계별 실시간 미리보기로 UX 보완
5. **워크플로우 소유권**: user_id 단위 소유권 관리

### 성능 최적화 방향
- FastAPI의 async/await 적극 활용
- LLM 호출은 비동기로 처리하여 파이프라인 지연 최소화
- 벡터 검색 결과 캐싱 고려

---

## 9. 개발 우선순위 제안

### Phase 1: 기반 구축 (3월)
- [x] FastAPI 프로젝트 초기 설정
- [ ] MongoDB 연결 설정
- [ ] 기본 API 라우터 구조
- [ ] 헬스체크 엔드포인트
- [ ] Docker 환경 구성

### Phase 2: 핵심 엔진 (4월 초)
- [ ] 노드 추상 클래스 및 Strategy 패턴 구현
- [ ] 워크플로우 실행 엔진 (순차 실행)
- [ ] State 패턴 기반 상태 관리
- [ ] LangChain + LLM 노드 연동

### Phase 3: 외부 연동 (4월 중)
- [ ] Google Drive / Sheets / Gmail 연동
- [ ] Notion, Slack 연동
- [ ] 범용 REST API 노드
- [ ] OAuth 토큰 관리

### Phase 4: 고급 기능 (5월)
- [ ] 트리거/스케줄링 시스템
- [ ] 조건/반복 로직 노드
- [ ] 스냅샷 기반 롤백 메커니즘
- [ ] 실행 로그 및 디버깅

### Phase 5: 안정화 (6월)
- [ ] 벡터 검색 서비스 (FAISS/Chroma)
- [ ] 성능 최적화 및 캐싱
- [ ] 통합 테스트
- [ ] Docker 배포 최적화

---

## 10. 팀 내 FastAPI 서버 역할 (윤동근 담당)

제안서 기준 담당 업무:
- FastAPI, Spring 서버 구축
- LangChain 연동
- MongoDB 설계
- 백엔드 인프라 구축

Spring Boot와의 통신은 내부 REST API 또는 메시지 큐를 통해 처리하며,
FastAPI는 AI/LLM 관련 요청을 전담하는 **마이크로서비스** 역할을 한다.
