# GitHub Node Design

> 작성일: 2026-05-16
> 대상 레포: `flowify-BE`
> 범위: GitHub 노드 1차 지원을 위한 FastAPI runtime 설계
> 관련 레포: `flowify-BE-spring`, `flowify-FE`

---

## 1. 목적

이 문서는 GitHub 노드 1차 지원을 위해 FastAPI runtime이 어떤 source를 구현하고,
어떤 payload를 만들며, 어떤 실행 정책을 가져야 하는지 정리한다.

이번 이슈의 실제 runtime 목표는 아래처럼 고정한다.

- GitHub는 **source node**만 지원한다.
- source mode는 **`new_pr`**만 지원한다.
- 연결 방식은 기존 Spring의 **manual token**을 그대로 사용한다.
- 출력은 우선 **`API_RESPONSE`**로 유지한다.
- GitHub에 다시 쓰는 sink/action은 지원하지 않는다.

즉 1차 FastAPI 책임은
"특정 저장소의 새 PR을 감지해서 Flowify의 기존 중간 처리/도착 노드로 보낼 수 있는 source runtime을 만드는 것"이다.

---

## 2. 현재 상태

### 2.1 이미 있는 것

현재 시스템에는 아래 준비가 일부 되어 있다.

- Spring manual token 검증
- Spring source catalog의 `github:new_pr`
- FE service key / choice 레벨의 GitHub 표시 흔적

즉 외부 계약과 UI 표현 일부는 존재한다.

### 2.2 아직 없는 것

FastAPI runtime 기준으로는 GitHub source가 아직 존재하지 않는다.

- `input_node.py`의 `SUPPORTED_SOURCES`에 `github`가 없다.
- GitHub integration service 파일이 없다.
- `new_pr`를 실제로 감지하는 fetch 전략이 없다.
- GitHub PR payload를 Flowify input payload로 normalize하는 코드가 없다.

즉 이번 이슈의 본체는 FastAPI runtime 구현이다.

---

## 3. 1차 범위

### 3.1 지원 source

1차에서 지원하는 source는 하나다.

- service: `github`
- mode: `new_pr`
- target: `owner/repo`

### 3.2 이번 범위에서 가능하게 만드는 자동화

이 source가 만들어지면 현재 구조에서 바로 가능한 자동화는 아래다.

- `GitHub -> Google Sheets`
- `GitHub -> AI -> Gmail`
- `GitHub -> AI -> Notion`


즉 1차 GitHub 노드는 "PR 감지 + 기록/요약/알림"에 맞춘다.

### 3.3 이번 범위 제외

이번 FastAPI 범위에 포함하지 않는 것은 아래와 같다.

- GitHub sink/action
  - comment 작성
  - review 작성
  - label/assignee 변경
  - issue/release 생성
- source mode 확장
  - issue
  - release
  - push
  - review
- webhook 기반 실시간 등록
- GitHub 전용 canonical type 신설
- partial success / destination별 retry

---

## 4. 실행 전략

## 4.1 polling + checkpoint

1차 `new_pr`는 제품 의미상 event source이지만,
runtime 구현은 **polling + checkpoint**가 가장 현실적이다.

권장 흐름:

1. `owner/repo` 입력을 파싱한다.
2. GitHub API에서 최근 PR 목록을 조회한다.
3. 저장된 checkpoint와 비교한다.
4. checkpoint 이후에 새로 열린 PR이 있으면 그 PR payload를 생성한다.
5. 없으면 기존 event source처럼 `no_new_items` 또는 skip 흐름으로 처리한다.

이 방식이 맞는 이유:

- 현재 Flowify source 구조와 잘 맞는다.
- webhook 등록/해제 lifecycle을 이번 이슈에 억지로 끌어오지 않아도 된다.
- GitHub source MVP를 가장 빠르게 안정화할 수 있다.

## 4.2 첫 실행 정책

첫 실행에서 과거 PR을 한꺼번에 흘려보내면 사용자 기대와 어긋날 가능성이 크다.

1차 권장 정책:

- **첫 실행은 checkpoint만 초기화하고 PR payload는 방출하지 않는다.**

즉, 첫 실행 이후 새로 열린 PR부터 감지한다.

이 정책의 장점:

- 기존 오래된 PR이 갑자기 Gmail/Sheets/Notion으로 쏟아지지 않는다.
- event source로서의 제품 의미가 더 자연스럽다.

## 4.3 `new_pr` 의미 정의

1차에서 `new_pr`는 아래 의미로 고정한다.

- `opened` 상태의 신규 PR만 감지
- `reopened`는 포함하지 않음
- 기존 PR의 `updated_at` 변경은 감지하지 않음
- draft -> ready for review 전환도 포함하지 않음

즉 1차 GitHub source는 "새로 열린 PR"만 처리하며,
기존 PR의 재활성화나 상태 전환은 후속 이슈로 분리한다.

## 4.4 API 선택

1차는 GitHub REST API 기반으로 충분하다.

후보:

- `GET /repos/{owner}/{repo}/pulls`

최소 조회 조건 예시:

- state: `open`
- sort: 최신순
- direction: `desc`
- per_page: 작은 값으로 제한

1차는 "새로 열린 PR" 감지만 하면 되므로,
복잡한 search API나 GraphQL까지 갈 필요는 없다.

## 4.5 auto-run 전제

GitHub `new_pr`는 제품 의미상 event source지만,
1차 구현은 webhook이 아니라 polling 기반이므로 **실질적으로는 auto-run / trigger settings와 함께 동작하는 source**다.

즉 아래를 문서에 명확히 남겨야 한다.

- 수동 실행: 현재 시점 기준 bootstrap 또는 새 PR 확인
- auto-run 활성화: 주기적으로 polling하며 새 PR 감지
- auto-run 비활성화: 지속 감지는 일어나지 않음

이 설명이 없으면 사용자는 "event source인데 왜 가만히 있지?"라고 느낄 수 있다.

---

## 5. checkpoint 설계

## 5.1 필요한 상태

중복 감지와 순서 보장을 위해 아래 상태를 권장한다.

- `last_seen_pr_number`
- `last_seen_pr_created_at`

두 값을 같이 두는 이유:

- PR 번호는 repo 내에서 monotonic이라 단순하고 빠르다.
- `created_at`은 시간 비교 보조값으로 안전하다.

1차에서는 둘 중 하나만으로도 구현 가능하지만,
실행 안정성을 위해 둘 다 저장하는 쪽이 좋다.

## 5.2 state 저장 위치

GitHub source checkpoint는 **기존 workflow node state 경로**를 재사용하는 것을 1차 기준으로 고정한다.

즉 아래 흐름을 따른다.

- Spring `WorkflowTranslator`가 source node state를 runtime source에 주입
- FastAPI source 실행 결과가 `node_state_update`를 반환
- executor가 `nodeStateUpdates`를 callback payload에 포함
- Spring이 `workflow_node_states`에 반영

이 방향을 택하는 이유:

- GitHub `new_pr`는 1차에서 단일 PR event source에 가깝다.
- 현재 `source_freshness_service`는 리스트형 new-item source 필터링 중심이다.
- GitHub는 `last_seen_pr_number`, `last_seen_pr_created_at` 같은 service-specific checkpoint를 node state로 다루는 편이 단순하다.

즉 1차 GitHub source는 `source_checkpoints` 컬렉션이 아니라,
기존 workflow node state 저장 흐름을 쓰는 것으로 설계하는 것이 맞다.

## 5.3 여러 PR이 한 번에 생겼을 때 정책

이 부분은 반드시 미리 고정해야 한다.

1차 권장 정책:

- **한 번의 workflow 실행에서는 PR 1건만 방출한다.**
- 여러 신규 PR이 있으면 **가장 오래된 unseen PR부터 1건** 처리한다.
- checkpoint도 이번 실행에서 실제로 방출한 PR 기준으로만 전진한다.

이 정책을 권장하는 이유:

- `new_pr`라는 이름과 잘 맞는다.
- payload를 단일 PR 기준으로 단순하게 유지할 수 있다.
- Gmail / Notion / AI 요약 흐름이 다루기 쉽다.

후속으로 여러 PR batch 처리 모드를 추가하는 것은 가능하지만,
1차는 "1회 실행 = PR 1건"이 가장 안전하다.

---

## 6. payload 설계

## 6.1 canonical type

1차 canonical output type은 **`API_RESPONSE`**를 유지한다.

이유:

- FE choice가 이미 `API_RESPONSE` 후속 흐름을 제공한다.
- `Google Sheets`, `Notion` sink가 `API_RESPONSE`를 직접 받을 수 있다.
- `AI`를 거쳐 `TEXT`로 바꾸는 현재 구조도 잘 맞는다.

## 6.2 최소 payload 필드

GitHub `new_pr` source가 내려줘야 하는 최소 필드는 아래를 권장한다.

- `source_service`: `github`
- `repository`
- `owner`
- `repo`
- `pr_number`
- `title`
- `author`
- `url`
- `state`
- `created_at`
- `updated_at`
- `base_branch`
- `head_branch`
- `requested_reviewers`
- `changed_files_count`
- `changed_files`

추가로 raw 데이터를 유지하려면 아래를 둘 수 있다.

- `raw`

이 정도면 기록/요약/알림 자동화에 충분하다.

## 6.3 changed files 전략

사용자 가치상 `changed_files`는 매우 중요하다.

이유:

- FE choice에도 GitHub 예시 필드가 `변경 파일`, `커밋 메시지`, `작성자`, `PR 링크` 중심이다.
- 리뷰 초안이나 요약 자동화에서 변경 파일 목록이 핵심 컨텍스트가 된다.

다만 1차에서 너무 무거워지지 않게 다음 중 하나를 권장한다.

1. PR detail API에서 얻을 수 있는 최소 파일 수만 먼저 지원
2. 추가 호출로 파일 목록까지 가져오되, 개수 제한을 둔다

권장 방향은 2번이지만,
상한선을 두어 payload 폭발을 막는 것이 좋다.

예:

- 파일 목록 50개까지만 포함
- 총 변경 파일 수는 `changed_files_count`로 별도 유지
- 상한 초과 시 잘린 사실을 표시하는 보조 필드를 둘 수 있다

## 6.4 payload에 포함하지 않는 것

1차 payload는 PR 메타데이터 중심으로 유지하고,
아래는 기본 포함 대상에서 제외하는 것이 좋다.

- 전체 diff 본문
- 파일별 patch 전문
- review thread / comments 전문
- commit diff 전체

이유:

- payload가 급격히 커진다.
- rate limit / 응답 시간 / AI 입력 비용이 불안정해진다.
- 1차 자동화 목표는 "감지 + 기록/요약/알림"이지 정밀 코드리뷰가 아니다.

---

## 7. InputNode 전략 변경

`input_node.py`에서 필요한 최소 변경은 아래다.

- `SUPPORTED_SOURCES`에 `github: {"new_pr"}` 추가
- service 분기에 `github` 추가
- `_fetch_github(...)` 구현

가능하면 Gmail / Google Sheets와 같은 패턴을 유지해,
새 source가 기존 strategy 구조를 깨지 않도록 해야 한다.

즉 GitHub source를 특별 취급하는 새 엔진보다는,
"source 하나 추가" 수준으로 들어가는 것이 좋다.

---

## 8. 에러 및 guard 정책

1차에서 명확히 해야 하는 에러는 아래다.

- 잘못된 `owner/repo`
- GitHub token 누락
- GitHub API 401 / 403
- repo 접근 권한 없음
- 새 PR 없음

token 정책도 문서에 명시하는 것이 좋다.

- classic PAT: 정식 지원 대상으로 본다
- fine-grained PAT: best effort로 본다

현재 검증 로직은 `X-OAuth-Scopes`와 classic scope 표현(`repo`, `public_repo`, `repo:*`)에 더 친화적이므로,
1차 가이드에서는 classic PAT를 권장하는 것이 안전하다.

또한 아래 guard는 유지해야 한다.

- source는 여전히 정상 graph 안에서만 실행된다.
- merge node 없는 fan-in graph는 허용하지 않는다.
- GitHub source가 들어왔다고 executor semantics를 바꾸지 않는다.

---

## 9. 테스트 관점

FastAPI 최소 테스트는 아래가 적절하다.

- `SUPPORTED_SOURCES`에 `github:new_pr`가 등록된다.
- 잘못된 target 형식이면 validation이 실패한다.
- 첫 실행은 checkpoint만 설정하고 item을 내보내지 않는다.
- 여러 신규 PR이 있으면 가장 오래된 unseen PR 1건만 방출한다.
- 새 PR이 생기면 payload 하나를 만든다.
- checkpoint 이전 PR은 다시 내보내지 않는다.
- `changed_files`가 payload에 포함된다.
- `changed_files`가 상한 초과 시 잘림 정책이 일관되다.
- `API_RESPONSE -> Google Sheets` 흐름이 깨지지 않는다.
- `API_RESPONSE -> AI -> Gmail` 흐름이 깨지지 않는다.

---

## 9.1 후속 품질 보정 원칙

GitHub 노드 1차 구현 이후 확인된 대표 품질 이슈는 아래 두 가지다.

- `GitHub -> Google Sheets`: raw 저장은 되지만, 예쁘게 고른 필드가 비어 들어갈 수 있음
- `GitHub -> AI -> Gmail`: 실행은 되지만, 요약이 PR 문맥보다 일반론으로 흐를 수 있음

이 문제를 해결할 때 가장 중요한 원칙은 **공용 로직 전면 수정 대신 GitHub 전용 보정만 추가하는 것**이다.

특히 아래 경로는 여러 서비스가 함께 사용하는 공용 런타임이므로,
GitHub 때문에 일반 규칙을 바꾸는 방식은 피해야 한다.

- `DataFilterNodeStrategy`
- `LLMNodeStrategy`
- `API_RESPONSE` 공용 처리 흐름

1차 후속 보정은 아래처럼 GitHub 전용으로만 제한한다.

1. DataFilter
- `source_service=github`일 때만 표시용 필드 라벨을 실제 payload key로 해석하는 alias fallback을 둔다.
- 예: `변경 파일 -> changed_files`, `작성자 -> author`, `PR 링크 -> url`

2. GitHub payload / LLM 입력 텍스트
- `source_service=github` + `event=new_pr`일 때만
  JSON 전체 대신 PR 문맥이 드러나는 정리된 텍스트를 만든다.
- 예: repository, PR 번호, 제목, 작성자, base/head branch, body, changed files

3. 공용 canonical type 유지
- `API_RESPONSE` 자체를 바꾸거나 GitHub 전용 canonical type을 새로 만들지 않는다.
- 기존 Flowify source/sink 조합과의 호환을 우선한다.

즉 1차 후속 품질 보정 기준은 아래 한 줄이다.

- **공용 규칙 변경보다 GitHub source 전용 보정을 우선한다.**

---

## 10. 최종 권고

FastAPI 기준 1차 GitHub 노드는 **"manual token 기반 `new_pr` polling source"**로 고정하는 것이 맞다.

핵심은 아래다.

1. GitHub source를 기존 source strategy 안에 자연스럽게 편입한다.
2. payload는 `API_RESPONSE`로 유지해 기존 노드 생태계를 재사용한다.
3. 첫 실행 bootstrap + checkpoint 정책으로 이벤트성 기대를 맞춘다.

즉 이번 이슈에서 FastAPI는
"GitHub 전체 연동"이 아니라
"새 PR 감지 source MVP"를 안정적으로 구현하는 데 집중하는 것이 가장 적절하다.

---

## 11. GitHub AI ?? ??

GitHub source ?? AI ??? ???? ?? ??? ????.

- ??/??/??? ??? ??? ?? ?? plain text digest? ???? ??.
- ??/??? ??? ?? ??? ?? ? ??? ??? ???? ???? ??.

### 11.1 TEXT ?? ?? ??

?? ??:

- Gmail
- Notion ??? ??

??:

- Markdown ??(`**`)? ?? ???? ???? ???.
- ???? ???? ???.
- ?? section label? `-` bullet? ????.
- body ??? ?? ???? ?? ?? ???? ?? ???? ????.

?? ??:

1. Basic info
2. One-line summary
3. Key changes
4. Review points

### 11.2 SPREADSHEET_DATA ?? ?? ??

?? ??:

- Google Sheets
- Notion DB? ??

??:

- ? ??? ???? ?? ?? ???? ????.
- ? ?? ?? ??/?? ??? ??? ????.
- 1? ?? ??? `GitHub -> ??? ??? ?? -> Google Sheets`? ??.

?? ??:

- `repository`
- `pr_number`
- `title`
- `author`
- `state`
- `draft`
- `created_at`
- `base_branch`
- `head_branch`
- `changed_files_count`
- `url`

### 11.3 ?? ??

- GitHub ?? ?? ????? `source_service=github`, `event=new_pr`, custom prompt ??, `TEXT` ??? ?? ????.
- ?? source? LLM ?? ??? ??? ???.
- ??? ??? ?? `DataFilter -> Sheets` ??? ???? ????.

### 11.4 도착 노드별 기본 출력 정책표

| 도착 노드 | 권장 출력 형식 | 기본 구조 | 길이/톤 가이드 | 비고 |
|---|---|---|---|---|
| `gmail` | plain text digest | `기본 정보 -> 한 줄 요약 -> 주요 변경점 -> 확인 포인트 -> 링크` | 짧고 바로 읽히는 요약형, `**` 같은 마크다운 강조 금지 | 메일 본문은 "한 번에 훑고 판단"하는 용도에 맞춘다. |
| `discord` | chat-short alert | `PR 번호/제목 -> 저장소/작성자 -> 한 줄 요약 -> 링크` | Gmail보다 더 짧고 즉시 읽히는 알림형 | 채팅창 전용으로 3~5줄 안쪽을 기본으로 본다. |
| `notion` 문서/페이지 | document summary | `제목 -> 기본 정보 -> 한 줄 요약 -> 주요 변경점 -> 확인 포인트 -> 링크` | 메일보다 약간 더 풍부하지만 여전히 짧은 문서형 | 나중에 다시 읽는 협업 문서 용도에 맞춘다. |

| `google_sheets` | structured table | 고정 컬럼 기반 row | 긴 문장보다 짧은 값 우선 | `DataFilter -> Sheets`를 기본 경로로 유지한다. |
| `notion` DB | structured record | 속성/컬럼 기반 record | Sheets와 동일하게 정렬/필터 친화적 구조 | 짧은 속성값과 선택적 `short_summary`만 권장한다. |

정리:

- `gmail`, `discord`, `notion` 문서는 사람이 읽는 결과물이므로 plain text 중심의 요약형이 맞다.
- `google_sheets`, `notion` DB는 정렬/필터/누적 기록 용도이므로 구조화된 컬럼형이 맞다.

