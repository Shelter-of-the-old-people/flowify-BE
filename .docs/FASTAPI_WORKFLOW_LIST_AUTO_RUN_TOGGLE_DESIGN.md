# FastAPI Workflow List Auto-Run Toggle Design

> **작성일:** 2026-05-10
> **대상 저장소:** `flowify-BE`
> **범위:** workflow list auto-run toggle 기능의 FastAPI 관점 정리
> **관련 저장소:** `flowify-FE`, `flowify-BE-spring`

---

## 1. 목적

이 문서는 워크플로우 목록에서 자동 실행 on/off 토글을 추가할 때 FastAPI가 무엇을 하지 않아야 하는지 명확히 한다.

핵심은 다음과 같다.

- auto-run 토글의 source of truth는 계속 Spring `Workflow.active`다.
- FastAPI는 목록 토글 기능 때문에 새 API를 추가하지 않는다.
- execution stop/run과 schedule on/off는 다른 책임이라는 점을 유지한다.

---

## 2. 책임 경계

### 2.1 목록 토글이 바꾸는 것

목록의 자동 실행 토글은 결국 Spring workflow update API로 아래 값만 바꾼다.

- `workflow.trigger`
- `workflow.active`

FastAPI는 이 변경을 직접 받지 않는다.

### 2.2 FastAPI가 계속 담당하는 것

- 현재 실행 중인 execution의 시작
- 현재 실행 중인 execution의 중지
- 실행 결과와 callback 저장

즉 목록 row의 `run/stop` 버튼은 FastAPI 관련 액션이고, `자동 실행 켜기/끄기`는 Spring 관련 액션이다.

---

## 3. 구현 판단

이번 기능 때문에 FastAPI에서 새로 필요한 런타임 변경은 없다.

- 새 endpoint 불필요
- 새 scheduler 로직 불필요
- trigger payload 모델 변경 불필요

필요하다면 문서와 테스트에서 아래 사실만 다시 명시한다.

- schedule owner는 Spring이다.
- FastAPI는 schedule fire 이후의 execution만 처리한다.

---

## 4. 테스트 관점

FastAPI는 이번 follow-up에서 아래만 유지 확인하면 충분하다.

- 목록에서 auto-run을 꺼도 이미 시작된 execution run/stop API는 기존대로 동작한다.
- 이후 schedule fire가 오지 않는 것은 Spring 쪽 책임이다.
- manual workflow 실행과 schedule workflow 실행은 여전히 같은 execute path를 사용한다.

---

## 5. 한 줄 요약

이번 목록 auto-run 토글 기능은 FastAPI 구현 변경 없이도 성립하며, FastAPI는 계속 execution runtime에만 집중한다.
