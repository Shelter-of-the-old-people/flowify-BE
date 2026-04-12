# Flowify 프론트엔드 컨벤션

> **작성일:** 2026-04-12
> **대상:** flowify-fe 프론트엔드 프로젝트
> **참조:** [seed-fe](https://github.com/team-seedLab/seed-fe) 컨벤션 + flowify-fe 기존 코드베이스

---

## 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [네이밍 컨벤션](#2-네이밍-컨벤션)
3. [Import / Export 규칙](#3-import--export-규칙)
4. [컴포넌트 작성 규칙](#4-컴포넌트-작성-규칙)
5. [타입 컨벤션](#5-타입-컨벤션)
6. [Chakra UI 사용 규칙](#6-chakra-ui-사용-규칙)
7. [상태 관리 (Zustand)](#7-상태-관리-zustand)
8. [API 레이어](#8-api-레이어)
9. [React Query 패턴](#9-react-query-패턴)
10. [에러 처리](#10-에러-처리)
11. [코드 스타일 & 포매팅](#11-코드-스타일--포매팅)
12. [주석 규칙](#12-주석-규칙)
13. [Git 컨벤션](#13-git-컨벤션)
14. [새 노드 추가 체크리스트](#14-새-노드-추가-체크리스트)

---

## 1. 프로젝트 구조

### 1.1 FSD (Feature-Sliced Design) 레이어

```
src/
├── app/           # 진입점, 프로바이더, 라우터
├── pages/         # 라우트 기반 페이지
├── widgets/       # 복합 UI 블록 (canvas, layout, panel 등)
├── features/      # 사용자 기능 단위 (add-node, configure-node, auth 등)
├── entities/      # 비즈니스 엔티티 (node, connection, workflow)
└── shared/        # 공통 인프라 (api, model, libs, theme, styles, types, constants)
```

**의존성 방향**: `app → pages → widgets → features → entities → shared` (상위 → 하위만 허용)

### 1.2 엔티티 / 피처 내부 구조

```
[entity|feature]/
├── model/
│   ├── apis/          # API 호출 함수 (액션별 1파일)
│   ├── hooks/         # 커스텀 훅
│   ├── store/         # Zustand 스토어
│   ├── constants/     # 상수, 쿼리 키
│   └── types/         # 타입 정의
├── ui/                # 프레젠테이션 컴포넌트
├── utils/             # 유틸리티 함수
└── index.ts           # 배럴 export
```

---

## 2. 네이밍 컨벤션

### 2.1 파일 & 디렉토리

| 대상 | 규칙 | 예시 |
|------|------|------|
| 디렉토리 | kebab-case | `add-node/`, `custom-nodes/` |
| 컴포넌트 파일 | PascalCase.tsx | `BaseNode.tsx`, `CalendarNode.tsx` |
| 훅 파일 | camelCase.ts | `useAddNode.ts`, `useLogout.ts` |
| API 파일 | kebab-case.api.ts | `project-list.api.ts`, `auth.api.ts` |
| 타입 파일 | kebab-case.type.ts 또는 types.ts | `project.type.ts`, `types.ts` |
| 스토어 파일 | kebab-case.store.ts | `workflow-editor.store.ts` |
| 상수 파일 | kebab-case.ts | `query-keys.ts`, `route-path.ts` |
| 비공개 에셋 | `_assets/` 접두사 | `_assets/icons/` |

### 2.2 코드 네이밍

| 대상 | 규칙 | 예시 |
|------|------|------|
| 컴포넌트 | PascalCase | `ServiceSelectionPanel` |
| Props 타입 | `Props` (단수, 고정) | `type Props = { ... }` |
| 커스텀 훅 | `use` + PascalCase | `useAddNode`, `useCreateProject` |
| 상수 | UPPER_SNAKE_CASE | `ACCESS_TOKEN_KEY`, `ROADMAP_TYPE_MAP` |
| 변수/함수 | camelCase | `addNode`, `getProjectList` |
| 불리언 변수 | `is/has/can/should` 접두사 | `isAuthenticated`, `canSubmit`, `hasNext` |
| 이벤트 핸들러 | `handle` + EventName | `handleDragOver`, `handleFileInput` |
| NodeType 값 | 소문자 kebab-case (단수형) | `"communication"`, `"web-scraping"` |
| DataType 값 | kebab-case | `"file-list"`, `"email-list"` |
| Union 타입 값 | UPPER_SNAKE_CASE 또는 소문자 | `"IN_PROGRESS"`, `"idle"` |

---

## 3. Import / Export 규칙

### 3.1 Import 순서 (Prettier 자동 정렬)

그룹 사이에 **빈 줄**을 삽입한다. 스페시파이어는 알파벳순 정렬된다.

```typescript
// 1. React 관련
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

// 2. 서드파티
import { useQuery } from "@tanstack/react-query";
import { Box, Flex, Text } from "@chakra-ui/react";

// 3. @/ 절대경로 (다른 FSD 레이어)
import { type AssignmentType, useCreateProject } from "@/entities";
import { ROUTE_PATHS } from "@/shared";

// 4. ../ 상대경로 (같은 레이어 상위)
import { projectKeys } from "../constants";

// 5. ./ 상대경로 (같은 레이어 현재)
import { useUploadFiles } from "./useUploadFiles";
```

### 3.2 FSD Import 규칙

| 상황 | 경로 방식 | 예시 |
|------|----------|------|
| **다른** FSD 레이어 참조 | `@/` 절대경로 | `import { BaseNode } from "@/entities"` |
| **같은** FSD 레이어 참조 | `./` `../` 상대경로 | `import { useUploadFiles } from "./useUploadFiles"` |

> **절대 혼용 금지**: 같은 레이어에서 `@/` 사용 금지, 다른 레이어에서 상대경로 사용 금지

### 3.3 Type Import

**인라인 `type` 키워드**를 사용한다:

```typescript
// O 올바름: 인라인 type
import { type AssignmentType, useCreateProject } from "@/entities";

// X 금지: 별도 import type 문
import type { AssignmentType } from "@/entities";
import { useCreateProject } from "@/entities";
```

### 3.4 배럴 파일 (index.ts)

모든 슬라이스는 `index.ts`로 공개 API를 노출한다. `export *` 체이닝 방식.

```typescript
// entities/index.ts
export * from "./connection";
export * from "./node";
export * from "./workflow";

// entities/node/index.ts
export * from "./model";
export * from "./ui";

// entities/node/model/index.ts
export * from "./types";
export * from "./nodeRegistry";
export * from "./nodePresentation";
```

### 3.5 컴포넌트 Export 규칙

| 대상 | 방식 | 예시 |
|------|------|------|
| 일반 컴포넌트 | `export const` (named) | `export const BaseNode = () => { ... }` |
| 페이지 컴포넌트 | `export default function` | `export default function LoginPage() { ... }` |
| 배럴 파일 리-export | `export { default as ... }` | `export { default as UploadPage } from "./UploadPage"` |

---

## 4. 컴포넌트 작성 규칙

### 4.1 선언 패턴

```typescript
// --- 일반 컴포넌트: const + 화살표 함수 + named export ---

type Props = {
  label: string;
  content: string;
  onCopy: () => void;
  copied?: boolean;
};

export const PromptCard = ({ label, content, onCopy, copied }: Props) => {
  return (
    <Flex direction="column" gap={3} p={4}>
      <Text fontSize="sm" fontWeight="medium">{label}</Text>
      {/* ... */}
    </Flex>
  );
};
```

```typescript
// --- 페이지 컴포넌트: function 선언 + default export ---

export default function WorkflowEditorPage() {
  return (
    <Box w="100vw" h="100dvh">
      {/* ... */}
    </Box>
  );
}
```

### 4.2 커스텀 노드 컴포넌트

모든 커스텀 노드는 `BaseNode`로 래핑한다:

```typescript
export const CalendarNode = ({
  id,
  data,
  selected,
}: NodeProps<Node<FlowNodeData>>) => {
  const config = getTypedConfig("calendar", data.config);

  return (
    <BaseNode id={id} data={data} selected={selected ?? false}>
      {/* 노드별 고유 콘텐츠 */}
    </BaseNode>
  );
};
```

### 4.3 Provider 컴포지션

```typescript
export const ApplicationProviders = ({ children }: Props) => {
  return (
    <QueryProvider>
      <AuthProvider>
        <ThemeProvider>
          {children}
          <Toaster />
        </ThemeProvider>
      </AuthProvider>
    </QueryProvider>
  );
};
```

### 4.4 관심사 분리 기준

페이지와 UI를 분리할 때는 "페이지가 모든 것을 알고 하위 컴포넌트에 props를 내려주는 구조"보다, 화면 단위 `section`이 필요한 상태와 UI를 내부에서 조합하는 구조를 기본값으로 삼는다.

이 프로젝트에서 새 화면을 만들 때의 기본 구조는 아래와 같다.

```text
Page
→ Section
  → model hooks
  → ui components
    → entity ui
```

즉, **기본값은 page slice 내부 분리**이며, 재사용 근거가 생길 때만 `entities` 또는 `widgets`로 승격한다.

#### 기본 원칙

- `page`는 라우트 진입점과 최상위 레이아웃 조합만 담당한다.
- `section`은 실제 화면 단위 컨테이너 역할을 담당한다.
- `model hook`은 section 내부에서 호출하되, **하나의 거대한 facade hook보다 책임별로 나뉜 작은 hook 조합을 우선한다.**
- `ui` 컴포넌트는 props 기반 표현 컴포넌트로 유지한다.
- `entity ui`는 item, card, row, badge처럼 재사용 가능한 도메인 표현에 집중한다.
- `feature`는 생성, 삭제, 실행, 로그아웃처럼 사용자 액션 단위를 담당한다.
- `widget`은 여러 페이지나 레이아웃에서 의미를 갖는 공용 복합 블록에 한해 사용한다.
- **재사용 근거가 없는 화면 전용 섹션을 처음부터 `widgets`로 올리지 않는다.**

#### 권장 디렉토리 구조

```text
src/pages/<route>/
├─ XxxPage.tsx
├─ index.ts
├─ model/
│  ├─ useXxxData.ts
│  ├─ useXxxActions.ts
│  ├─ useXxxScroll.ts
│  ├─ constants.ts
│  ├─ types.ts
│  └─ *.ts
└─ ui/
   ├─ section/
   │  └─ XxxSection.tsx
   ├─ XxxToolbar.tsx
   ├─ XxxRow.tsx
   └─ index.ts
```

#### 레이어별 책임

- `page`
  - route 진입
  - 최상위 레이아웃
  - section 조합
  - page 자체는 가능한 한 얇게 유지

- `section`
  - 화면 단위 조합
  - 필요한 model hook들을 직접 호출해 조합
  - loading / error / empty / list 상태 처리
  - toolbar, list, dialog, action UI 연결

- `model`
  - query/mutation 조합
  - 파생 상태
  - 로컬 상태
  - 핸들러
  - 순수 계산 로직

- `ui`
  - props 기반 표현 컴포넌트
  - fetch/query 직접 호출 지양
  - toolbar, badge, row, empty state 같은 시각 요소

- `entity ui`
  - 도메인 단위 재사용 표현
  - item, row, card, badge, status chip
  - route 맥락 없이도 의미가 유지되는 표현

- `feature`
  - 사용자 기능 단위
  - 여러 화면에서 호출될 수 있는 액션 흐름
  - 예: create, delete, execute, connect, logout

- `widget`
  - 공용 복합 UI 블록
  - 여러 페이지/레이아웃에서 의미를 갖는 구조적 단위
  - 예: layout, shell, canvas, toolbar, panel

#### model hook 분리 기준

- section 안에서 사용하는 model hook은 **기능이 아니라 책임 기준으로 분리**한다.
- 조회/정렬/필터링은 `data` 계열 hook으로 분리한다.
- 생성/삭제/이동/토글 같은 사용자 액션은 `actions` 계열 hook으로 분리한다.
- observer, infinite scroll, resize, keyboard binding 같은 효과성 로직은 별도 hook으로 분리한다.
- 하나의 `useXxxSection` hook이 단순히 section에서 쓰는 모든 값과 핸들러를 모아 반환하기 시작하면, facade가 아니라 **God hook**이 되기 쉽다.
- section facade hook은 여러 작은 hook을 얇게 조합할 때만 선택적으로 둔다. 단일 section만 위해 모든 책임을 감춘다면 우선 제거를 검토한다.

#### 승격 기준

- **기본값은 page slice 내부 유지**다.
- 한 화면 전용 조합이면 `pages/<route>` 안에 둔다.
- 같은 도메인 표현이 여러 화면에 반복되기 시작하면 `entities/.../ui`로 승격한다.
- 같은 사용자 액션 흐름이 여러 화면에서 재사용되면 `features/...`로 승격한다.
- 여러 페이지/레이아웃에서 같은 복합 블록을 공유하면 `widgets/...`로 승격한다.
- 승격 근거가 불명확하면 **더 낮은 레이어에 둔 채 시작**하고, 반복이 확인된 뒤 올린다.

#### 예시

```tsx
// O 권장: 페이지는 섹션만 조합
export default function MyPage() {
  return (
    <Layout>
      <UserNameSection />
      <ProjectListSection />
    </Layout>
  );
}
```

```tsx
// O 권장: 섹션이 책임별 hook을 직접 조합
export const ProjectListSection = () => {
  const { projects, isLoading, activeFilter, setActiveFilter } =
    useProjectListData();
  const { handleOpenProject, handleDeleteProject } = useProjectListActions();

  return (
    <>
      <ProjectListToolbar
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
      />
      {projects.map((project) => (
        <ProjectListItem
          key={project.id}
          {...project}
          onClick={() => handleOpenProject(project.id)}
          onDelete={() => handleDeleteProject(project.id)}
        />
      ))}
    </>
  );
};
```

```tsx
// X 지양: section 전용 책임을 하나의 facade hook에 모두 몰아넣기
const sectionState = useWorkflowListSection();
```

#### 적용 기준

- 페이지가 너무 많은 props를 하위로 전달하기 시작하면 section 분리를 우선 검토한다.
- loading, error, empty, list rendering이 페이지에 함께 있으면 section 컨테이너로 이동을 검토한다.
- item row, toolbar, badge처럼 표현 중심인 요소는 section 밖으로 분리하되, **우선은 같은 page slice 안에 둔다.**
- section model hook 하나가 조회, 액션, observer, navigation을 함께 들고 있으면 책임 기준 재분리를 검토한다.
- section이 사용하는 값이 모두 하나의 hook에서 나오더라도, 그 hook이 실제로 여러 성격의 책임을 숨기고 있지 않은지 먼저 본다.
- row/card/badge가 다른 화면에서도 반복되기 전에는 `entities`로 올리지 않는다.
- 공용 레이아웃/캔버스/패널처럼 구조적 의미가 있는 블록이 아니라면 `widgets`를 기본 저장소처럼 사용하지 않는다.

---

## 5. 타입 컨벤션

### 5.1 type vs interface

| 용도 | 키워드 | 예시 |
|------|--------|------|
| 객체 형태, extends 필요 시 | `interface` | `interface Project { ... }` |
| Union, Record, 별칭 | `type` | `type NodeType = "communication" \| "storage"` |
| Props | `type` | `type Props = { ... }` |

### 5.2 Enum 금지 — Union 타입 사용

```typescript
// O 올바름
type ProjectStatus = "IN_PROGRESS" | "COMPLETED";
type ExecutionStatus = "idle" | "running" | "success" | "failed";

// X 금지
enum ProjectStatus { IN_PROGRESS, COMPLETED }
```

### 5.3 NodeConfig 판별 패턴

`getTypedConfig()` 헬퍼로 타입 좁히기:

```typescript
export type NodeConfigMap = {
  communication: CommunicationNodeConfig;
  storage: StorageNodeConfig;
  // ...
};

export const getTypedConfig = <T extends NodeType>(
  _type: T,
  config: NodeConfig,
): NodeConfigMap[T] => {
  return config as NodeConfigMap[T];
};
```

### 5.4 Exhaustive Switch

모든 `NodeType` switch 문에 `never` 기본값 필수:

```typescript
switch (data.type) {
  case "communication": return <CommunicationPanel />;
  case "storage": return <StoragePanel />;
  // ... 모든 케이스
  default: {
    const _exhaustive: never = data.type;
    return null;
  }
}
```

---

## 6. Chakra UI 사용 규칙

### 6.1 테마 시스템

```typescript
const config = defineConfig({
  cssVarsRoot: ":where(:root, :host)",
  cssVarsPrefix: "sd",
  globalCss: globalStyles,
  theme: {
    tokens: {
      fonts: { heading: { value: "Pretendard" }, body: { value: "Pretendard" } },
      colors: colorToken,
      sizes: layoutToken,
    },
    semanticTokens: { colors: colorSemanticToken },
  },
});

export const system = createSystem(defaultConfig, config);
```

### 6.2 스타일링 방식 — Props 전용

Chakra UI 컴포넌트 props로만 스타일링한다. Recipe, SlotRecipe, CSS modules, styled-components, inline `style={{}}` 모두 **사용 금지**.

```typescript
// O 올바름: Chakra props
<Box px={4} py={3} borderRadius="xl" bg="container.bg" cursor="pointer" />

// X 금지: inline style
<Box style={{ padding: "12px 16px" }} />
```

### 6.3 fontSize

시맨틱 토큰을 우선 사용한다. 픽셀 값은 디자인 시안에서 토큰에 해당하지 않는 특수한 경우에만 허용.

| 토큰 | 크기 | 용도 |
|------|------|------|
| `xs` | 12px | 보조 텍스트, 노드 라벨 |
| `sm` | 14px | 일반 본문, 버튼 텍스트 |
| `md` | 16px | 기본 본문 |
| `lg` | 18px | 소제목 |
| `xl` | 20px | 제목 |
| `2xl` | 24px | 대제목 |
| `3xl` | 30px | 히어로 텍스트 |

**반응형** 사용 시 객체 문법:

```typescript
<Heading fontSize={{ base: "2xl", lg: "3xl" }} />
<Text fontSize={{ base: "sm", md: "md" }} />
```

### 6.4 fontWeight

| 토큰 | 두께 | 용도 |
|------|------|------|
| `medium` | 500 | 일반 텍스트 |
| `semibold` | 600 | 강조 텍스트, 소제목 |
| `bold` | 700 | 제목, 헤딩 |

```typescript
<Text fontWeight="medium">일반 텍스트</Text>
<Text fontWeight="semibold">강조 텍스트</Text>
<Heading fontWeight="bold">제목</Heading>
```

### 6.5 borderRadius

| 토큰 | 크기 | 용도 |
|------|------|------|
| `md` | 6px | 작은 요소 (인풋, 뱃지) |
| `lg` | 8px | 버튼, 페이지네이션 |
| `xl` | 12px | 카드, 노드 |
| `2xl` | 16px | 큰 카드, 모달 |
| `3xl` | 24px | 위자드 카드 |
| `full` | 9999px | 원형 요소, 태그, 아바타 |

```typescript
<Button borderRadius="lg">확인</Button>
<Box borderRadius="xl" bg="container.bg">카드 콘텐츠</Box>
<Flex borderRadius="full" boxSize={10} bg="seed">아이콘</Flex>
```

### 6.6 boxSize

`boxSize`는 `width`와 `height`를 동시에 설정한다. 아이콘, 아바타, 원형 요소에 주로 사용.

| 값 | 실제 크기 | 용도 |
|----|----------|------|
| `5` | 20px | 소형 아이콘 |
| `6` | 24px | 기본 아이콘 |
| `7` | 28px | 사이드바 아이콘 |
| `8` | 32px | 페이지네이션 셀, 작은 버튼 |
| `10` | 40px | 아바타, 중형 아이콘 |
| `14` | 56px | 노드 아이콘 |
| `16` | 64px | 대형 아이콘 |

```typescript
<Icon boxSize={5} />                              // 20px 소형 아이콘
<Flex boxSize={8} borderRadius="lg">페이지</Flex>  // 32px 페이지네이션
<Image boxSize={14} borderRadius="xl" />           // 56px 노드 아이콘
<Flex boxSize={{ base: 20, lg: 28 }}>로드맵</Flex>  // 반응형
```

### 6.7 간격 (gap, p, px, py, m 등)

Chakra 숫자 토큰을 사용한다. `1 = 4px`, `2 = 8px`, `4 = 16px` 기준.

| 값 | 크기 | 일반적 용도 |
|----|------|------------|
| `1` | 4px | 인라인 간격 |
| `2` | 8px | 아이콘-텍스트 간격 |
| `3` | 12px | 작은 요소 간 간격 |
| `4` | 16px | 기본 패딩, 카드 내부 |
| `5` | 20px | 카드 간 간격 |
| `6` | 24px | 섹션 패딩 |
| `8` | 32px | 큰 섹션 간격 |
| `12` | 48px | 위자드 카드 패딩 |

```typescript
<Flex gap={2} px={4} py={3}>...</Flex>
<Box p={6}>섹션 콘텐츠</Box>
<Stack gap={5}>카드 리스트</Stack>
```

**반응형 패딩**:

```typescript
<Box px={{ base: 6, md: 10 }} py={{ base: 8, md: 10 }}>
  반응형 레이아웃
</Box>
```

### 6.8 너비 / 높이 (w, h, minW, maxW)

```typescript
// 시맨틱 값
<Box w="full" h="fit-content" />

// 뷰포트 단위
<Box w="100vw" h="100dvh" />

// 고정 픽셀 (레이아웃 제약)
<Box maxW="1200px" minW="172px" />

// 레이아웃 토큰 활용
<Box h="calc(100vh - {sizes.headerHeight} - {sizes.footerHeight})" />

// 반응형
<Box maxW={{ base: "100vw", lg: "1280px" }} />
```

### 6.9 컬러 토큰

**시맨틱 토큰을 우선 사용**한다. 베이스 토큰(`neutral.500`)은 시맨틱 토큰으로 커버되지 않는 경우에만 사용.

```typescript
// O 시맨틱 토큰 (권장)
<Box bg="container.bg" borderColor="container.border" />
<Text color="text.secondary" />
<Button bg="seed" _hover={{ bg: "seed.hover" }} _active={{ bg: "seed.active" }} />

// O 베이스 토큰 (시맨틱이 없는 경우)
<Box _hover={{ bg: "neutral.50" }} />
<Text color="neutral.600" />
```

### 6.10 의사 상태 (Pseudo States)

```typescript
<Button
  bg="seed"
  color="white"
  _hover={{ bg: "seed.hover" }}
  _active={{ bg: "seed.active" }}
  _focusVisible={{ outline: "2px solid", outlineColor: "seed", outlineOffset: "2px" }}
  _disabled={{ cursor: "not-allowed", opacity: 0.5 }}
  transition="background 0.15s"
/>
```

### 6.11 반응형 디자인

모든 반응형은 **객체 문법**을 사용한다:

```typescript
<Text fontSize={{ base: "sm", md: "md", lg: "lg" }} />
<Flex direction={{ base: "column", md: "row" }} />
<Box display={{ base: "none", md: "block" }} />
```

### 6.12 트랜지션 & 애니메이션

```typescript
// 기본 트랜지션
transition="background 0.15s"
transition="border-color 220ms ease, box-shadow 220ms ease"

// 호버 트랜스폼
_hover={{ transform: "translateY(-2px)" }}
transition="transform 200ms ease"
```

---

## 7. 상태 관리 (Zustand)

### 7.1 스토어 구조

**미들웨어 스택**: `devtools` → `persist` → `immer` → `combine`

```typescript
type WorkflowEditorState = {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  activePanelNodeId: string | null;
};

type WorkflowEditorActions = {
  onNodesChange: (changes: NodeChange[]) => void;
  addNode: (node: Node<FlowNodeData>) => void;
  removeNode: (nodeId: string) => void;
};

export const useWorkflowStore = create<WorkflowEditorState & WorkflowEditorActions>()(
  devtools(
    persist(
      immer(
        combine(initialState, (set) => ({
          addNode: (node) =>
            set((state) => {
              state.nodes.push(node);
            }),
          removeNode: (nodeId) =>
            set((state) => {
              state.nodes = state.nodes.filter((n) => n.id !== nodeId);
            }),
        })),
      ),
      {
        name: "workflow-store",
        storage: createJSONStorage(() => sessionStorage),
        partialize: (state) => ({ /* 영속화할 필드만 선택 */ }),
      },
    ),
    { name: "workflow-store-devtools" },
  ),
);
```

### 7.2 사용 규칙

**개별 셀렉터 구독** (전체 스토어 구독 금지):

```typescript
// O 올바름
const nodes = useWorkflowStore((state) => state.nodes);
const addNode = useWorkflowStore((state) => state.addNode);

// X 금지
const store = useWorkflowStore();
```

**레이아웃 상태는 스토어에 넣지 않음** — 별도 훅/유틸로 관리:

```typescript
// O 레이아웃 → 훅
const { width, height } = useDualPanelLayout();

// X 레이아웃 → 스토어
useWorkflowStore((s) => s.panelWidth); // 금지
```

---

## 8. API 레이어

### 8.1 파일 구조

액션별 1파일 원칙:

```
shared/api/
├── client.ts                  # Axios 인스턴스 + 인터셉터
entities/project/model/apis/
├── project-list.api.ts        # GET /api/projects
├── create-project.api.ts      # POST /api/projects
├── delete-project.api.ts      # DELETE /api/projects/:id
└── index.ts                   # 배럴 export
```

### 8.2 API 함수 패턴

```typescript
import { type ApiResponse, fetchInstance, processApiResponse } from "@/shared";

import type { Project } from "../types";

export interface ProjectListParameters {
  page?: number;
  size?: number;
  sort?: string;
}

export const getProjectListAPI = async (
  params: ProjectListParameters,
): Promise<ProjectListResponse> => {
  const response = await fetchInstance.get<ApiResponse<ProjectListResponse>>(
    "/api/projects",
    { params },
  );
  return processApiResponse(response.data);
};
```

### 8.3 응답 타입 체계

```typescript
interface BaseResponse {
  status: "SUCCESS" | "ERROR";
  serverDateTime: string;
}

interface SuccessResponse<T> extends BaseResponse {
  status: "SUCCESS";
  data: T;
}

interface ErrorResponse extends BaseResponse {
  status: "ERROR";
  errorCode: string;
  errorMessage: string;
}

type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;
```

### 8.4 HTTP 인터셉터

```typescript
// Request: Bearer 토큰 자동 부착
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response: 401 시 토큰 갱신 → 실패 시 로그아웃 + /login 리다이렉트
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    // 토큰 갱신 로직 + 요청 큐잉
  },
);
```

### 8.5 어댑터 패턴 (프론트 ↔ 백엔드 변환)

```typescript
// shared/libs/workflow-adapter.ts
toNodeDefinition()       // Front Node<FlowNodeData> → Backend NodeDefinition
toFlowNode()             // Backend → Front
toBackendDataType()      // "file-list" → "FILE_LIST"
toFrontendDataType()     // "FILE_LIST" → "file-list"
```

---

## 9. React Query 패턴

### 9.1 쿼리 키 팩토리

```typescript
const PROJECT_QUERY_KEY = "project";

export const projectKeys = {
  all: () => [PROJECT_QUERY_KEY] as const,
  lists: () => [...projectKeys.all(), "list"] as const,
  details: () => [...projectKeys.all(), "detail"] as const,
  list: (params) => [...projectKeys.lists(), params.page, params.size] as const,
  detail: (id: string) => [...projectKeys.details(), id] as const,
};
```

### 9.2 Query 훅

```typescript
export const useGetProjectList = (params: ProjectListParameters = {}) => {
  return useQuery({
    queryKey: projectKeys.list(params),
    queryFn: () => getProjectListAPI(params),
    throwOnError: false,
    meta: {
      showErrorToast: true,
      errorMessage: "프로젝트 목록을 불러오지 못했습니다.",
    },
  });
};
```

### 9.3 Mutation 훅

```typescript
export const useCreateProject = () => {
  const setProjectId = useUploadFlowStore((state) => state.setProjectId);

  return useMutation({
    mutationFn: createProjectAPI,
    onSuccess: (data) => {
      setProjectId(data.projectId);
    },
    onError: (error) => {
      toaster.create({
        type: "error",
        description: getApiErrorMessage(error),
      });
    },
  });
};
```

### 9.4 QueryClient 기본 설정

```typescript
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.showErrorToast !== true) return;
      const message = typeof query.meta?.errorMessage === "string"
        ? query.meta.errorMessage
        : getApiErrorMessage(error);
      toaster.create({ type: "error", description: message });
    },
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 60 * 3,      // 3분
      refetchOnMount: false,
      refetchOnWindowFocus: false,
      throwOnError: true,
    },
  },
});
```

---

## 10. 에러 처리

### 10.1 커스텀 ApiError 클래스

```typescript
export class ApiError extends Error {
  public readonly errorCode: string;
  public readonly serverDateTime: string;

  constructor(errorResponse: ErrorResponse) {
    super(errorResponse.errorMessage);
    this.name = "ApiError";
    this.errorCode = errorResponse.errorCode;
    this.serverDateTime = errorResponse.serverDateTime;
  }
}
```

### 10.2 에러 메시지 매핑

```typescript
export const HTTP_ERROR_MESSAGES = {
  400: "잘못된 요청입니다. 입력 정보를 확인해주세요.",
  401: "인증이 필요합니다. 다시 로그인해주세요.",
  403: "권한이 없습니다.",
  404: "요청한 리소스를 찾을 수 없습니다.",
  500: "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
  default: "요청을 처리할 수 없습니다.",
} as const;

export const API_ERROR_MESSAGES = {
  DUPLICATE_USER_ID: "이미 사용 중인 아이디입니다.",
  // 프로젝트별 에러 코드 매핑 추가
} as const;
```

### 10.3 에러 처리 흐름

```
API 호출 실패
  → processApiResponse()에서 ApiError throw
  → React Query onError / QueryCache.onError에서 catch
  → getApiErrorMessage()로 사용자 메시지 변환
  → toaster.create()로 토스트 표시
```

---

## 11. 코드 스타일 & 포매팅

### 11.1 Prettier 설정

```json
{
  "printWidth": 80,
  "tabWidth": 2,
  "useTabs": false,
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "arrowParens": "always",
  "plugins": ["@trivago/prettier-plugin-sort-imports"],
  "importOrder": [
    "^react(.*)$",
    "<THIRD_PARTY_MODULES>",
    "^@/(.*)$",
    "^\\.\\.(?:/|$)",
    "^\\.(?:/|$)"
  ],
  "importOrderSeparation": true,
  "importOrderSortSpecifiers": true
}
```

### 11.2 TypeScript 설정

```json
{
  "strict": true,
  "noUnusedLocals": true,
  "noUnusedParameters": true,
  "target": "ES2022",
  "module": "ESNext",
  "moduleResolution": "bundler"
}
```

### 11.3 Husky + lint-staged

커밋 전 자동 실행:

```json
{
  "lint-staged": {
    "*.{js,jsx,ts,tsx}": [
      "prettier --write",
      "eslint --fix"
    ]
  }
}
```

---

## 12. 주석 규칙

### 12.1 일반 규칙

- **WHY** 중심으로 작성 (코드가 WHAT을 보여줌)
- **한국어** 주로 사용
- 불필요한 주석 금지 (코드로 명확한 경우)

### 12.2 패턴

```typescript
// 섹션 구분자
// ─── Node Registration ─────────────

// TODO: 이슈 번호 포함
// TODO(#52): 백엔드 API 연동 후 실제 데이터로 교체

// 타입/API 설명 (한국어)
// 모든 응답에 공통으로 들어가는 필드를 BaseResponse로 정의
interface BaseResponse { ... }
```

---

## 13. Git 컨벤션

### 13.1 커밋 메시지

- **"왜"**에 초점, "무엇"이 아닌 이유를 설명
- 이슈 번호 참조
- 커밋 당 하나의 관심사

```
feat: 백엔드 주도 OAuth 로그인 흐름으로 전환
fix: 빌드 에러 잡음
refactor: 컴포넌트 구조 개선
```

### 13.2 브랜치 네이밍

```
feat#68-api-setting
refactor#70-backend-oauth-resetting
fix#72-build-error
```

---

## 14. 새 노드 추가 체크리스트

새 노드 타입을 추가할 때 수정해야 할 6개 파일:

| 순서 | 파일 | 작업 |
|------|------|------|
| 1 | `entities/node/model/types.ts` | NodeConfig 인터페이스 + NodeConfigMap 매핑 추가 |
| 2 | `entities/node/model/nodeRegistry.ts` | NODE_REGISTRY 엔트리 추가 |
| 3 | `entities/node/model/nodePresentation.ts` | getConfiguredTitle case 추가 |
| 4 | `entities/node/ui/custom-nodes/XxxNode.tsx` | 커스텀 노드 컴포넌트 생성 |
| 5 | `features/configure-node/ui/panels/XxxPanel.tsx` | 설정 패널 컴포넌트 생성 |
| 6 | `features/configure-node/model/panelRegistry.ts` | NODE_PANEL_REGISTRY 엔트리 추가 |
