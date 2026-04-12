# 워크플로우 리스트 페이지 구조 리팩토링 문서

> **작성일**: 2026-04-13
> **이슈**: #79
> **브랜치**: `refector#79-workflow-list-refector`
> **대상 화면**: `/workflows`
> **선행 문서**: [WORKFLOW_LIST_PAGE_DESIGN.md](./WORKFLOW_LIST_PAGE_DESIGN.md)
> **목적**: 워크플로우 리스트 페이지를 `docs/CONVENTION.md`의 `Page -> Section -> focused model hooks -> ui` 기준에 맞춰 정리하고, page slice 내부에서 관심사를 분리하되 실제 상태/로직/UI 연결은 section 내부에서 담당하도록 리팩토링한다.

---

## 목차

1. [개요](#1-개요)
2. [리팩토링 목표](#2-리팩토링-목표)
3. [구조 설계](#3-구조-설계)
4. [파일별 역할](#4-파일별-역할)
5. [진행 원칙](#5-진행-원칙)
6. [제외 범위](#6-제외-범위)
7. [검증 기준](#7-검증-기준)
8. [후속 작업](#8-후속-작업)

---

## 1. 개요

기존 리팩토링 방향에서는 `WorkflowsPage.tsx`에서 page model 훅을 호출하고, 그 결과를 하위 UI 컴포넌트에 props로 전달하는 구조를 사용했다.

이 구조도 책임 분리 자체는 가능하지만, 현재 프로젝트의 컨벤션 기준으로 보면 페이지가 여전히 너무 많은 연결 책임을 가지고 있다.

참고 기준:

- `seed-fe`의 `mypage`
  - 페이지는 섹션만 조합
  - 섹션이 state/query와 하위 UI를 내부에서 연결
- 현재 프로젝트의 `docs/CONVENTION.md`
  - 기본값은 `Page -> Section -> focused model hooks -> ui`
  - 화면 전용 섹션은 우선 `pages/<route>` 내부에 유지
  - section 전용 책임을 하나의 큰 facade hook으로 몰지 않는다
  - 재사용 근거가 생길 때만 `entities`, `features`, `widgets`로 승격

이번 리팩토링은 이 기준을 워크플로우 리스트 페이지에 맞추는 것을 목표로 한다.

즉, 페이지는 더 얇아지고 section이 실제 화면 단위 컨테이너 역할을 담당한다. 또한 현재 단계에서는 화면 전용 구조를 `widgets`로 올리지 않고, `pages/workflows` 내부에서 완결되는 page slice 구조를 유지한다. section 내부에서는 하나의 `useWorkflowListSection` facade hook에 모든 책임을 몰기보다, 데이터/액션/스크롤을 책임별로 나눈 hook을 조합하는 방향을 채택한다.

---

## 2. 리팩토링 목표

- `WorkflowsPage.tsx`는 페이지 외곽 레이아웃과 section 조합만 담당한다.
- 목록 조회, 무한 스크롤, 필터 상태, 생성/상세 이동/활성 토글 핸들러는 section 내부에서 사용한다.
- 페이지가 직접 `WorkflowFilterTabs`, `WorkflowRow`, model hook들을 연결하지 않도록 정리한다.
- `WorkflowListSection`이 리스트 영역의 실질적인 화면 컨테이너가 되도록 구성한다.
- 세부 UI 컴포넌트는 현재처럼 표현 중심으로 유지한다.
- 화면 전용 조합은 우선 `pages/workflows` 안에 유지하고, 재사용 근거 없는 `widgets` 승격은 하지 않는다.
- `row`, `badge` 같은 표현 요소는 우선 같은 page slice 안에 두고, 다른 화면에서 반복될 때만 `entities` 승격을 검토한다.
- `useWorkflowListSection`처럼 section 전용 값을 한 번에 감싸는 facade hook은 제거하거나 아주 얇게 유지한다.
- 데이터, 액션, observer는 서로 다른 model hook으로 분리한다.
- `docs/CONVENTION.md` 기준의 import, props 타입, Chakra UI 규칙을 유지한다.

---

## 3. 구조 설계

### 3.1 목표 디렉토리 구조

```text
src/pages/workflows/
├─ WorkflowsPage.tsx
├─ index.ts
├─ model/
│  ├─ constants.ts
│  ├─ index.ts
│  ├─ types.ts
│  ├─ useWorkflowListData.ts
│  ├─ useWorkflowListActions.ts
│  ├─ useWorkflowListInfiniteScroll.ts
│  └─ workflow-list.ts
└─ ui/
   ├─ index.ts
   ├─ ServiceBadge.tsx
   ├─ WorkflowFilterTabs.tsx
   ├─ WorkflowListHeader.tsx
   ├─ WorkflowRow.tsx
   └─ section/
      ├─ index.ts
      └─ WorkflowListSection.tsx
```

### 3.2 레이어 책임

- `WorkflowsPage.tsx`
  - 페이지 외곽 레이아웃만 담당
  - `WorkflowListSection`만 조합
- `ui/section/WorkflowListSection.tsx`
  - 리스트 화면 단위 조합
  - 책임별 model hook 호출 및 조합
  - `WorkflowListHeader`, `WorkflowFilterTabs`, `WorkflowRow` 연결
  - 로딩/에러/빈 상태 UI 처리
- `model/useWorkflowListData.ts`
  - 목록 조회
  - 정렬
  - 필터 상태
- `model/useWorkflowListActions.ts`
  - 생성/상세 이동/활성 토글 핸들러
- `model/useWorkflowListInfiniteScroll.ts`
  - 무한 스크롤 observer
  - `loadMoreRef`
- `model/workflow-list.ts`
  - 상대 시간 라벨
  - 구축 진행 상태 계산
  - 경고 메시지 추출
  - 시작/종료 노드 추출
  - 서비스 아이콘 키 매핑
- `ui/*`
  - props 기반 표현 중심 UI 컴포넌트
  - fetch/query 직접 호출 지양
  - 현재 단계에서는 page slice 내부에 유지

### 3.3 승격 기준

- 기본값은 `pages/workflows` 내부 유지다.
- `WorkflowListSection` 같은 화면 단위 조합은 재사용 근거가 생기기 전까지 `widgets`로 승격하지 않는다.
- `WorkflowRow`, `ServiceBadge` 같은 표현 요소는 다른 화면에서 반복되기 시작하면 `entities/workflow/ui` 승격을 검토한다.
- 생성, 삭제, 실행처럼 여러 화면에서 재사용되는 사용자 액션 흐름은 `features/...` 승격을 검토한다.
- 승격 근거가 모호하면 더 낮은 레이어에 둔 채 시작하고, 반복이 확인된 뒤 올린다.

### 3.4 hook 분리 기준

- `useWorkflowListData`
  - 서버 목록 데이터
  - 정렬/필터링 파생값
  - `activeFilter`, `setActiveFilter`
  - `isLoading`, `isError`, `hasNextPage`, `fetchNextPage`, `isFetchingNextPage`
- `useWorkflowListActions`
  - 워크플로우 생성
  - 상세 화면 이동
  - 활성 토글
  - `togglingWorkflowId`
- `useWorkflowListInfiniteScroll`
  - `loadMoreRef`
  - observer 등록/해제
  - `fetchNextPage` 트리거

즉 section이 필요한 것을 모두 직접 조합하되, 하나의 hook이 조회/액션/observer를 동시에 들고 있지 않도록 정리한다.

---

## 4. 파일별 역할

| 파일 | 역할 |
|------|------|
| `src/pages/workflows/WorkflowsPage.tsx` | 페이지 조합 전용 진입점 |
| `src/pages/workflows/ui/section/WorkflowListSection.tsx` | 리스트 section 컨테이너 |
| `src/pages/workflows/model/useWorkflowListData.ts` | 리스트 조회/정렬/필터 상태 |
| `src/pages/workflows/model/useWorkflowListActions.ts` | 생성/이동/토글 액션 |
| `src/pages/workflows/model/useWorkflowListInfiniteScroll.ts` | 무한 스크롤 observer |
| `src/pages/workflows/model/workflow-list.ts` | 순수 계산 로직 |
| `src/pages/workflows/ui/WorkflowListHeader.tsx` | 제목/설명/생성 버튼 UI |
| `src/pages/workflows/ui/WorkflowFilterTabs.tsx` | 상태 필터 탭 UI |
| `src/pages/workflows/ui/WorkflowRow.tsx` | 워크플로우 row UI |
| `src/pages/workflows/ui/ServiceBadge.tsx` | 서비스 배지 UI |

---

## 5. 진행 원칙

### 5.1 `mypage`를 그대로 복제하지 않고, 현재 컨벤션에 맞게 해석

이번 작업은 `seed-fe`의 `mypage` 구조를 참고하되, 현재 프로젝트의 컨벤션에 맞게 해석한다.

- 페이지는 섹션만 import
- 섹션이 state/query와 하위 UI를 내부에서 연결
- item 컴포넌트는 props 기반 표현 컴포넌트로 유지
- 화면 전용 section은 우선 `pages/workflows` 안에 둔다
- 재사용 근거 없는 `widgets` 승격은 하지 않는다
- 하나의 큰 section facade hook 대신 책임별 hook 조합을 우선한다

즉 `WorkflowsPage -> WorkflowListSection -> useWorkflowListData / useWorkflowListActions / useWorkflowListInfiniteScroll -> WorkflowListHeader / WorkflowFilterTabs / WorkflowRow` 흐름으로 정리한다.

### 5.2 페이지 책임 최소화

페이지에서는 아래를 하지 않는다.

- 목록 query 호출
- 필터 상태 보유
- 무한 스크롤 observer 연결
- 목록 row 렌더링 반복
- 로딩/에러/빈 상태 분기

이 책임은 모두 section 내부로 이동한다.

### 5.3 section 내부 hook도 과도하게 비대해지지 않게 유지

section 안에 있다고 해서 하나의 hook이 모든 책임을 가져도 된다는 뜻은 아니다.

- 조회/파생값
- 사용자 액션
- observer/effect

는 가능한 한 서로 다른 hook으로 유지한다.

즉 `section`은 조합의 중심이고, `model hook`은 책임별 단위라는 기준을 따른다.

### 5.4 표현 컴포넌트는 과도하게 비대해지지 않게 유지

`WorkflowListHeader`, `WorkflowRow`, `WorkflowFilterTabs`, `ServiceBadge`는 데이터 fetch를 직접 하지 않고, 현재처럼 표현 중심 컴포넌트로 유지한다.

즉 “모든 컴포넌트가 hook을 직접 갖는 구조”가 아니라, “섹션 컨테이너가 내부에서 필요한 것들을 조합하는 구조”를 목표로 한다.

### 5.5 승격은 반복이 확인된 뒤 수행

- `WorkflowRow`, `ServiceBadge`가 다른 화면에서도 반복되기 전까지는 `entities`로 올리지 않는다.
- `WorkflowListSection`은 여러 페이지에서 동일한 복합 블록으로 재사용되기 전까지는 `widgets`로 올리지 않는다.
- 현재 리팩토링은 page slice 내부 경계를 명확히 하는 데 집중하고, 상위 레이어 승격은 후속 판단으로 남긴다.

---

## 6. 제외 범위

이번 리팩토링에서는 아래 항목은 포함하지 않는다.

- 목록 우측 액션 버튼의 실제 실행 API 연동
- 서비스 SVG 아이콘의 별도 폴더 분리
- 백엔드 목록 조회 방식을 페이지네이션에서 커서 기반 무한 스크롤로 변경
- 목록 row UI 디자인 변경
- `warnings` 모델 자체 변경
- 재사용 근거 없는 `entities` 또는 `widgets` 승격

즉 이번 작업은 구조 리팩토링에 집중하고, 동작 변경은 최소화한다.

---

## 7. 검증 기준

- `pnpm run lint` 통과
- `pnpm run build` 통과
- `/workflows` 화면에서 아래 동작 유지 확인
  - 목록 조회
  - 최근 업데이트순 정렬
  - `전체 / 실행 / 중지됨` 필터
  - 무한 스크롤
  - 워크플로우 생성
  - 리스트 row hover 경고 메시지
  - 상세 화면 이동

---

## 8. 후속 작업

- 목록 row 액션 버튼의 의미(`active` 토글 vs 실제 실행 API)를 백엔드 스펙과 다시 정리
- 서비스 SVG 아이콘을 공용 아이콘 폴더로 정리
- 필요 시 `ui` 컴포넌트 단위 테스트 또는 스냅샷 테스트 도입
- `WorkflowRow`, `ServiceBadge`가 다른 화면에도 반복되면 `entities/workflow` 승격 여부 검토
- 백엔드 목록 조회가 무한 스크롤 친화적으로 바뀌면 data/scroll hook 경계도 함께 정리

---

## 결론

이번 리팩토링의 핵심은 “페이지는 section만 조합하고, 실제 연결 책임은 section 내부에 둔다”는 것이다.

정리 기준은 아래와 같다.

- `WorkflowsPage`는 얇게 유지한다.
- `WorkflowListSection`이 실제 리스트 컨테이너 역할을 맡는다.
- `model`은 상태와 로직을 맡되, 하나의 facade hook에 모든 책임을 몰지 않는다.
- `ui`는 표현을 맡는다.
- 화면 전용 구조는 우선 `pages/workflows` 안에 유지하고, 재사용 근거가 생기면 그때 승격한다.

이 문서는 `#79 워크플로우 리스트 페이지 구조 리팩토링`의 기준 문서로 사용한다.
