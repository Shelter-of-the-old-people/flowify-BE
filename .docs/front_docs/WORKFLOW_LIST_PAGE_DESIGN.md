# 워크플로우 목록 페이지 설계 문서

> **작성일:** 2026-04-12
> **이슈:** #72
> **브랜치:** `feat#72-workflow-list-page`
> **대상 화면:** `/workflows`
> **목적:** Figma 시안을 기준으로 워크플로우 목록 페이지를 구현하고, 백엔드 목록 응답 스펙(`active`, `warnings`, 페이지네이션)에 맞는 프론트 동작을 정리한다.

---

## 목차

1. [개요](#1-개요)
2. [구현 범위](#2-구현-범위)
3. [UI 설계](#3-ui-설계)
4. [데이터 및 API 정합성](#4-데이터-및-api-정합성)
5. [동작 설계](#5-동작-설계)
6. [주요 구현 파일](#6-주요-구현-파일)
7. [검증 결과](#7-검증-결과)
8. [후속 작업](#8-후속-작업)

---

## 1. 개요

워크플로우 목록 페이지는 사용자가 생성했거나 공유받은 자동화 워크플로우를 한 곳에서 확인하는 진입 화면이다.

이번 작업에서는 다음 목표를 가진다.

- Figma 시안 기준의 목록형 UI 구현
- 최근 업데이트순 정렬
- 상태 필터(`전체`, `실행`, `중지됨`) 제공
- 페이지네이션 UI 대신 무한 스크롤 적용
- 목록 행에서 워크플로우 활성/비활성 토글 제공
- `warnings`가 존재하는 경우 hover 시 경고 메시지 노출
- 백엔드 Swagger 응답 스펙의 `active` 필드에 맞춘 정합성 수정

참고 시안:

- `https://www.figma.com/design/liTdK7QHV5tufaQW8DwV6U/Untitled?node-id=1872-1518&m=dev`

---

## 2. 구현 범위

### 2.1 포함 범위

- 워크플로우 목록 페이지 헤더 및 생성 버튼
- 행형 카드 레이아웃
- 시작/종료 서비스 배지 표시
- 최근 수정 시간 표시
- 구축 진행 상태 표시
- 활성 상태 필터링
- 무한 스크롤 로딩
- 활성/비활성 토글
- 구성 연결 경고(`warnings`) hover 표시

### 2.2 제외 범위

- 실행 로그 기반 에러 내역 조회
- 경고 상세 모달 또는 별도 상세 페이지
- 서버 정렬 파라미터 연동
- 공유 워크플로우 전용 구분 UI

---

## 3. UI 설계

### 3.1 상단 영역

- 제목: `내 자동화 목록`
- 설명: `내가 구축한 자동화 시스템 목록`
- 우측 액션: `자동화 시스템 만들기`

### 3.2 필터 탭

- `전체`
- `실행`
- `중지됨`

탭 선택 시 목록 데이터를 프론트에서 필터링한다.

### 3.3 목록 행 구성

각 목록 행은 아래 정보를 보여준다.

- 시작 서비스 아이콘
- 연결 방향 표시(`→`)
- 종료 서비스 아이콘
- 워크플로우 이름
- 최근 수정 시간
- 구축 진행 상태
- 활성/비활성 토글 버튼
- 상세 진입 버튼

### 3.4 경고 메시지 노출 방식

- `workflow.warnings`가 비어 있으면 추가 메시지를 노출하지 않는다.
- `workflow.warnings`가 존재하면 row hover 시 하단에 경고 메시지 박스를 노출한다.
- 경고가 여러 개인 경우 요약하지 않고 메시지 전체를 세로 목록으로 보여준다.

경고 영역은 현재 "실행 에러"가 아니라 "구성 연결 경고" 성격으로 사용한다.

---

## 4. 데이터 및 API 정합성

### 4.1 목록 응답 스펙

Swagger 기준 워크플로우 목록 응답의 핵심 구조는 아래와 같다.

```json
{
  "content": [
    {
      "id": "string",
      "name": "string",
      "description": "string",
      "updatedAt": "2026-04-12T10:04:49.774Z",
      "warnings": [
        {
          "nodeId": "string",
          "message": "string",
          "sourceType": "string",
          "targetType": "string"
        }
      ],
      "active": true
    }
  ],
  "page": 0,
  "size": 20,
  "totalPages": 1
}
```

### 4.2 `active` 필드 정합성

초기 프론트 구현에서는 활성 상태를 `isActive`로 가정하고 있었으나, Swagger 기준 목록 응답은 `active`를 사용한다.

따라서 아래 항목을 `active` 기준으로 정리했다.

- 워크플로우 엔티티 타입
- 목록 상태 필터
- 실행/중지 버튼 라벨과 아이콘
- 활성 토글 mutation payload
- 워크플로우 summary 변환

### 4.3 `warnings` 활용 방식

`warnings`는 현재 목록 화면에서 "구성 연결 경고" 표시 용도로 사용한다.

- 경고 존재 여부 판단: `workflow.warnings?.length > 0`
- 표시 내용: `warnings[].message`
- 표시 조건: row hover

이 필드는 나중에 별도의 실행 로그 에러와는 분리해서 다뤄야 한다.

---

## 5. 동작 설계

### 5.1 정렬

목록은 `updatedAt` 기준 내림차순으로 정렬한다.

- 최신 수정 워크플로우가 상단에 위치
- 서버 응답 순서에 의존하지 않고 프론트에서 명시적으로 정렬

### 5.2 무한 스크롤

백엔드 API는 `page`, `size`, `totalPages` 기반 페이지네이션 응답을 사용한다.

프론트는 이를 그대로 사용하되 UX는 무한 스크롤로 제공한다.

- React Query `useInfiniteQuery` 사용
- `IntersectionObserver`로 하단 sentinel 감지
- sentinel 진입 시 다음 페이지 요청
- 수신한 각 페이지의 `content`를 평탄화 후 렌더링

### 5.3 워크플로우 생성

상단의 `자동화 시스템 만들기` 버튼 클릭 시 `POST /api/workflows`를 호출한다.

생성 요청은 "초기 이름만 있는 빈 워크플로우"가 아니라, 아래와 같은 기본 구조의 빈 워크플로우 body를 보낸다.

```json
{
  "name": "새 워크플로우",
  "description": "",
  "nodes": [],
  "edges": [],
  "trigger": null
}
```

동작 순서는 아래와 같다.

- `POST /api/workflows` 호출
- 생성 성공 시 목록 query 무효화
- 응답으로 받은 `id` 기준으로 `/workflows/:id` 편집 화면으로 이동

이 생성 요청은 Swagger의 워크플로우 생성 스펙과 맞추기 위해 `description`, `nodes`, `edges`, `trigger`까지 함께 전송한다.

### 5.4 활성 상태 토글

목록 행 우측 액션 버튼으로 워크플로우 활성 상태를 토글한다.

- `active === true` 이면 중지 아이콘 표시
- `active === false` 이면 실행 아이콘 표시
- 토글 시 `PUT /api/workflows/:id` 호출
- 성공 시 관련 query cache 무효화

### 5.5 경고 hover 표시

- hover 전: 목록 행만 보임
- hover 후: row 하단에 경고 박스 확장
- 경고 박스에는 `구성 연결 경고` 제목과 각 메시지 전체를 표시

---

## 6. 주요 구현 파일

| 파일 | 역할 |
|------|------|
| `src/pages/workflows/WorkflowsPage.tsx` | 목록 페이지 UI, 정렬, 필터, hover 경고, 무한 스크롤 |
| `src/features/create-workflow/model/useCreateWorkflowShortcut.ts` | 빈 워크플로우 생성 요청 및 편집 화면 이동 |
| `src/shared/model/useWorkflowQueries.ts` | 목록 무한 조회, 활성 상태 토글 mutation |
| `src/shared/api/workflow.api.ts` | 생성/목록/수정 API 타입 및 요청 스펙 |
| `src/entities/workflow/model/types.ts` | 워크플로우 엔티티 타입 정의 |

### 6.1 WorkflowsPage 주요 책임

- 목록 화면 레이아웃
- 서비스 배지 렌더링
- `updatedAt` 기준 정렬
- 상태 필터링
- sentinel 기반 추가 로드
- `warnings` hover 메시지 표시

### 6.2 Query 계층 주요 책임

- `useInfiniteWorkflowListQuery(size)`
- `useToggleWorkflowActiveMutation()`

### 6.3 Chakra UI 컨벤션 정렬

목록 페이지는 후속 정리 과정에서 `docs/CONVENTION.md` 기준에 맞춰 Chakra UI 표현을 정리했다.

- 정사각형 배지/래퍼는 `w`, `h` 대신 `boxSize`를 사용
- `fontSize`는 가능한 범위에서 Chakra 토큰(`2xs`, `xs`, `sm`, `xl`)을 사용
- `borderRadius`는 `lg`, `xl`, `2xl` 같은 토큰 값을 사용
- 필터 탭은 `chakra.button` 대신 Chakra `Button` 컴포넌트를 사용
- 일반 UI 레벨 색상은 semantic token 및 color token(`text.secondary`, `border.default`, `bg.surface` 등) 기준으로 정리
- 서비스 브랜드 SVG 색상은 아이콘 원형 보존을 위해 예외적으로 inline 값 유지

---

## 7. 검증 결과

이번 작업은 아래 기준으로 검증했다.

- `pnpm run tsc`
- `pnpm run lint`
- `pnpm test`
- pre-commit 훅(`lint-staged`, `lint:fix`, `tsc`) 통과

테스트 파일은 현재 저장소에 존재하지 않아 `vitest --passWithNoTests` 기준으로 종료 코드 0을 확인했다.

---

## 8. 후속 작업

### 8.1 에러/경고 모델 분리

현재 목록 hover 메시지는 `warnings`를 사용한다. 이 값은 구성 연결 경고에 가깝기 때문에, 실제 실행 실패 로그와는 분리해서 다루는 것이 좋다.

후속 과제:

- 실행 이력 기반 에러 상태 필드 정의
- 경고(`warnings`)와 실행 에러(`execution errors`) UI 분리
- 경고 아이콘/상태 뱃지 추가 검토

### 8.2 서버 정렬 연동

현재는 프론트에서 `updatedAt` 기준 정렬을 수행한다.

후속 과제:

- 서버 정렬 파라미터 제공 여부 확인
- 백엔드 정렬과 프론트 정렬 중복 여부 정리

### 8.3 목록 정보 확장

후속으로 추가 검토 가능한 항목:

- 공유된 워크플로우 여부 표시
- 마지막 실행 시간 표시
- 실행 상태 배지
- 검색 및 정렬 옵션

---

## 결론

이번 작업으로 워크플로우 목록 페이지는 Figma 시안 기준의 기본 UX를 갖추었고, 백엔드 Swagger 응답의 `active`, `warnings`, 페이지네이션 구조와도 정합성을 맞추게 되었다.

특히 목록 화면에서 중요한 세 가지 축을 정리했다.

- 최근 업데이트순 목록 노출
- 무한 스크롤 기반 탐색
- 구성 연결 경고의 hover 메시지 표시

이 문서는 이후 목록 화면 고도화와 에러/경고 모델 분리 작업의 기준 문서로 사용한다.
