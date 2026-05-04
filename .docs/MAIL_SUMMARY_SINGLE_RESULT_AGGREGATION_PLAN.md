# 메일 요약 단일 결과 집계 백엔드 수정안

> **작성일:** 2026-05-04  
> **대상:** FastAPI, Spring  
> **관련 이슈:** `메일 요약 후 전달` 템플릿 3종 고도화  
> **관련 화면:** `/templates`, `/templates/:id`, 워크플로우 실행  

---

## 1. 개요

`메일 요약 후 전달` 템플릿 3종은 현재 모두 Gmail 메일 목록을 입력으로 받고 있지만, 실제 런타임은 메일 여러 개를 한 번에 LLM으로 보내 하나의 자유형 텍스트를 만드는 구조에 가깝다.

이 구조는 다음 문제를 만든다.

- 메일 일부가 요약에서 빠질 수 있다.
- 템플릿 설명의 `메일별 정리`와 실제 동작이 다르다.
- Slack, Notion 결과물이 실행마다 크게 흔들린다.

이 문서는 **결과는 1개로 유지하되, 메일별 정보가 생략되지 않도록** 백엔드 구조를 바꾸는 기준을 정리한다.

---

## 2. 목표 동작

목표는 아래 한 줄로 정리할 수 있다.

`메일별 구조화 -> 구조화 결과 집계 -> 최종 결과 1개 생성`

최종 결과 예시는 다음과 같다.

```text
읽지 않은 메일 요약 8건

1. 발신자: Slack
- 제목: 확인 코드
- 핵심: 이메일 확인용 코드 안내
- 액션: 코드 입력 필요

2. 발신자: Postman
- 제목: 플랜 업데이트 예정
- 핵심: 요금제 개편 예정 안내
- 액션: 없음
```

이 구조에서는:

- Slack은 메시지 1개를 전송한다.
- Notion은 페이지 1개를 생성한다.
- 하지만 내부적으로는 각 메일이 최소 한 번씩 개별 처리된다.

---

## 3. 현재 구조 문제

### 3.1 Gmail fetch 개수와 템플릿 의도 불일치

- Spring 템플릿 시드는 `maxIterations = 100`을 의도한다.
- 하지만 FastAPI Gmail fetch는 현재 `max_results = 20` 하드코딩이다.

관련 위치:

- [app/core/nodes/input_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/input_node.py:199)
- [app/services/integrations/gmail.py](/C:/Users/김민호/CD2/flowify-BE/app/services/integrations/gmail.py:13)

### 3.2 Loop가 실제 fan-out을 하지 않음

- 현재 `LoopNodeStrategy`는 메일을 하나씩 downstream에 보내지 않는다.
- 입력 `items`를 그대로 묶어 반환한다.

관련 위치:

- [app/core/nodes/logic_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/logic_node.py:51)

### 3.3 LLM이 메일 목록 전체를 자유 요약함

- `EMAIL_LIST`가 들어오면 메일 목록 전체를 문자열 하나로 합쳐서 LLM에 넣는다.
- 그 결과 어떤 실행에서는 메일 일부가 빠지고, 어떤 실행에서는 한 메일만 대표로 남는다.

관련 위치:

- [app/core/nodes/llm_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/llm_node.py:79)

### 3.4 Slack, Notion sink는 최종 텍스트 1개만 기대함

- Slack은 현재 `text` 1개를 그대로 보낸다.
- Notion도 현재는 `content` 문자열 1개를 페이지 본문으로 저장한다.

관련 위치:

- [app/services/integrations/slack.py](/C:/Users/김민호/CD2/flowify-BE/app/services/integrations/slack.py:14)
- [app/core/nodes/output_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/output_node.py:146)

---

## 4. 권장 구조

### 4.1 실행 흐름

권장 실행 흐름은 아래와 같다.

1. Gmail에서 메일 목록을 가져온다.
2. Loop가 메일을 `SINGLE_EMAIL` 단위로 fan-out 한다.
3. LLM이 각 메일을 고정 형식으로 구조화한다.
4. 구조화 결과를 다시 리스트로 모은다.
5. 최종 집계 단계에서 결과 1개 텍스트를 만든다.
6. Slack 또는 Notion으로 최종 결과 1개를 보낸다.

즉 구조는 다음과 같이 바뀐다.

- 현재:
  - `Gmail(EMAIL_LIST) -> Loop(EMAIL_LIST 유지) -> LLM 1회 -> Sink 1회`
- 목표:
  - `Gmail(EMAIL_LIST) -> Loop -> SINGLE_EMAIL * N -> LLM * N -> SUMMARY_LIST -> Aggregate -> Sink 1회`

### 4.2 구조화 포맷

LLM이 메일마다 아래 필드를 반환하도록 강제하는 방식을 권장한다.

- `sender`
- `subject`
- `summary`
- `action_required`
- `date`

최종 집계 단계는 이 구조화 결과를 사람이 읽는 텍스트로만 바꾼다.

이렇게 해야:

- 메일별 누락이 줄고
- Slack/Notion 최종 결과는 여전히 1개로 유지된다.

---

## 5. FastAPI 수정안

### 5.1 Gmail fetch 개수 설정화

현재 하드코딩 `20`을 없애고 노드 config 기반으로 읽어야 한다.

권장 규칙:

- `maxResults`가 있으면 그 값을 사용
- 없으면 기본값 `20`
- 템플릿 기본값은 Spring 시드에서 `100`

수정 대상:

- [app/core/nodes/input_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/input_node.py:199)
- [app/services/integrations/gmail.py](/C:/Users/김민호/CD2/flowify-BE/app/services/integrations/gmail.py:13)

### 5.2 Loop fan-out 지원

`LoopNodeStrategy`가 실제로 `items`를 하나씩 downstream에 보내도록 바꿔야 한다.

권장 방향:

- 입력이 `EMAIL_LIST`이면 `SINGLE_EMAIL` 목록으로 fan-out
- executor가 loop downstream을 메일 개수만큼 반복 실행
- 반복 결과를 다시 `SUMMARY_LIST` 또는 `TEXT_LIST`로 모음

수정 대상:

- [app/core/nodes/logic_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/logic_node.py:51)
- [app/core/engine/executor.py](/C:/Users/김민호/CD2/flowify-BE/app/core/engine/executor.py:139)

### 5.3 LLM 구조화 출력 지원

현재 자유 텍스트 요약 대신, 메일 1개 입력일 때는 구조화 결과를 반환하도록 바꾸는 것이 좋다.

권장 방향:

- `SINGLE_EMAIL` 입력 처리 추가
- 메일 요약 전용 prompt 템플릿 추가
- 가능하면 JSON 형태 구조화 응답 사용

수정 대상:

- [app/core/nodes/llm_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/llm_node.py:57)
- [app/services/llm_service.py](/C:/Users/김민호/CD2/flowify-BE/app/services/llm_service.py:1)

### 5.4 집계 단계 추가

최종 결과 1개를 만들려면 집계 단계가 필요하다.

권장 방식은 2가지다.

1. `AggregateNodeStrategy`를 새로 추가
2. 또는 output node 직전에 `SUMMARY_LIST -> TEXT` 변환 로직을 추가

1차 구현은 범위상 2번이 더 빠를 수 있다.

권장 출력 포맷:

- 상단 헤더
  - 예: `중요 메일 요약 8건`
- 메일마다 번호
- 메일별 고정 항목
  - 발신자
  - 제목
  - 핵심
  - 액션

### 5.5 Sink 입력 타입 확장

Slack, Notion sink가 `SUMMARY_LIST` 또는 `TEXT_LIST`를 받아 집계 텍스트로 바꿀 수 있게 하는 것이 좋다.

권장 방향:

- Slack:
  - 리스트 입력이면 집계 텍스트 생성 후 전송
- Notion:
  - 리스트 입력이면 집계 텍스트 생성 후 페이지 저장

수정 대상:

- [app/core/nodes/output_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/output_node.py:88)

---

## 6. Spring 수정안

### 6.1 템플릿 설명과 config 보정

템플릿 시드가 현재 구조를 더 정확히 반영하도록 조정해야 한다.

권장 수정:

- 설명을 `메일 목록 요약` 기준으로 우선 보정
- Gmail start config에 `maxResults = 100` 추가
- LLM config에 구조화 요약용 prompt 추가
- 필요하면 output config에 `result_mode = single_aggregated` 같은 메타값 추가

관련 위치:

- `src/main/java/org/github/flowify/config/TemplateSeeder.java`

### 6.2 FE와 계약할 설정값 명시

FE가 이후 설정 패널에서 다룰 수 있도록 아래 값을 시드/스키마에 명시하는 것이 좋다.

- `maxResults`
- `summaryFormat`
- `resultMode`

---

## 7. FE와의 계약

FE는 최종 결과를 1개로 유지하되, 아래 기대를 갖는다.

- 템플릿 설명이 실제 동작과 다르지 않을 것
- 메일이 여러 개여도 결과 1개 안에서 메일별 항목이 구분될 것
- Slack, Notion 입력은 ID 수동 입력보다 picker UX로 개선될 것

즉 백엔드가 먼저 보장해야 하는 것은:

- 메일별 구조화 결과 생성
- 최종 단일 결과 집계
- 설정 가능한 fetch 개수

---

## 8. 1차 구현 우선순위

1. Gmail fetch 개수 설정화
2. LLM prompt를 메일별 구조화 형식으로 강화
3. 최종 결과 1개 집계 포맷 추가
4. 이후 loop fan-out 구조 개편

이 순서로 가면:

- 빠르게 품질을 올릴 수 있고
- 이후 진짜 메일별 처리형으로도 자연스럽게 확장 가능하다

---

## 9. 참고: Google Drive 새 폴더 생성 구현 상태

Slack, Notion picker 및 생성 UX를 논의할 때 기준선으로 삼아야 할 구현이 이미 하나 있다.

바로 `Google Drive 새 폴더 생성` 흐름이다.

확인 결과는 다음과 같다.

- FE 현재 브랜치:
  - Google Drive `folder_picker` 탐색 UI는 남아 있다.
  - 하지만 `새 폴더 만들기` 액션은 현재 코드에서 확인되지 않았다.
  - 즉 머지 이후 FE 생성 액션이 빠졌을 가능성이 있다.
- Spring:
  - Google Drive 폴더 생성 API는 살아 있다.
  - [CatalogController.java](/C:/Users/김민호/CD2/flowify-BE-spring/src/main/java/org/github/flowify/catalog/controller/CatalogController.java:1)
    - `POST /catalog/sinks/google_drive/folders`
  - [GoogleDriveTargetOptionProvider.java](/C:/Users/김민호/CD2/flowify-BE-spring/src/main/java/org/github/flowify/catalog/service/picker/GoogleDriveTargetOptionProvider.java:1)
    - `createFolder()` 구현 존재

이 말은 곧:

- `Google Drive 새 폴더 생성`은 백엔드가 없는 기능이 아니라
- 이미 있는 Spring 구현을 FE가 호출하도록 다시 연결하면 되는 상태라는 뜻이다.

또한 Slack, Notion 개선 때도 이 구현을 참조 패턴으로 삼을 수 있다.

- Spring reference:
  - 목록 조회 provider
  - 별도 생성 endpoint
- FE reference:
  - remote picker
  - 선택된 label과 실제 ID 분리 저장

다만 제약 차이는 있다.

- Google Drive:
  - 새 폴더 생성이 비교적 자유롭다.
- Slack:
  - 새 채널 생성은 추가 scope와 워크스페이스 권한이 필요하다.
- Notion:
  - 권한 있는 부모 페이지 아래 생성 방식만 현실적이다.

따라서 Slack, Notion은 Google Drive와 동일한 UX를 그대로 복제하기보다:

1. 1차로는 목록 선택 UX
2. 필요 시 생성 UX를 별도 검토

순서로 가는 것이 맞다.

---

## 10. 결론

`결과 1개를 유지하면서 메일 내용 생략을 줄이기`의 핵심은 자유 요약이 아니라 아래 구조다.

`메일별 구조화 -> 구조화 결과 집계 -> 최종 결과 1개 생성`

이 구조로 가야 템플릿 설명과 실제 동작의 차이를 줄이고, Slack/Notion 결과 품질을 안정적으로 끌어올릴 수 있다.

---

## 11. 현재 남아 있는 품질 이슈

2026-05-04 기준으로 템플릿 시드 프롬프트와 `EMAIL_LIST` 입력 포맷은 이미 보강되었다.
하지만 실제 실행 결과를 보면, 메일 수가 많을 때 Slack/Notion 최종 결과가 여전히 중간에서 잘리거나 일부 메일만 포함되는 현상이 남아 있다.

대표 증상:

- Slack 요약 메시지가 몇 개 메일까지만 정리하고 끝난다.
- Notion 기록용 요약이 특정 메일 번호 중간에서 끊긴다.
- 프롬프트는 `모든 메일을 빠짐없이 포함`하라고 지시하지만, 출력 길이 한계 때문에 결과가 완전하지 않다.

### 11.1 현재 원인

1. `EMAIL_LIST -> LLM 1회 -> 결과 1개` 구조가 그대로다.
   - 메일이 많을수록 입력 컨텍스트가 커지고, 한 번의 응답으로 모든 메일을 담기 어려워진다.

2. LLM 출력 길이가 현재 고정 `max_tokens = 2048`이다.
   - 위치:
     - [app/services/llm_service.py](/C:/Users/김민호/CD2/flowify-BE/app/services/llm_service.py:24)
   - 메일 수가 많고 출력 형식을 자세히 강제할수록 중간 잘림 가능성이 커진다.

3. 템플릿 기본 `maxResults = 100`은 무료 티어/짧은 출력 한도와 조합될 때 과할 수 있다.
   - 메일 수가 많아질수록 응답 길이와 quota 부담이 동시에 증가한다.

### 11.2 단기 대응

1. `maxResults`를 더 낮은 기본값으로 조정하거나, 상한을 동적으로 제한한다.
   - 예: 기본 10~20, 고급 설정에서만 상향

2. 출력 형식을 더 압축한다.
   - 예: `발신자 / 제목 / 핵심 1줄 / 액션 필요 여부`만 유지

3. 모델/제공자가 허용한다면 `max_tokens`를 상향한다.
   - 다만 이 방법만으로는 입력이 너무 많은 문제를 완전히 해결하지 못한다.

### 11.3 장기 대응

가장 권장되는 방향은 메일을 한 번에 모두 자유 요약하지 않고, 아래처럼 나누는 것이다.

`메일 목록 -> 10개 이하 chunk -> chunk별 구조화 -> 최종 1개 결과로 집계`

또는 더 정교하게는:

`메일별 구조화 -> 구조화 결과 리스트 -> 최종 집계`

이 방식으로 가야:

- 각 메일이 실제로 한 번씩 처리되고
- 최종 결과는 1개로 유지하면서도
- 일부 메일 누락이나 중간 잘림을 크게 줄일 수 있다.

### 11.4 문서상 주의

현재 템플릿 설명은 이미 `메일 목록 요약형`으로 보정되어 있지만,
실제 출력 품질은 여전히 입력 메일 수와 LLM 출력 한도에 영향을 받는다.

따라서 백엔드 구현/운영 관점에서는 다음을 함께 기억해야 한다.

- `프롬프트 강화`만으로는 이 문제가 완전히 해결되지 않는다.
- `maxResults`, `max_tokens`, chunking/aggregation 구조를 같이 봐야 한다.
