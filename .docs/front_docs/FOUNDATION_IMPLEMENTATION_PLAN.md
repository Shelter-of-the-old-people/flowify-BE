# Flowify 프론트엔드 기반 구현 계획서

> **작성일:** 2026-04-03
> **작성자:** 리드 (팀원 합류 전 기반 작업)
> **선행 문서:** [FRONTEND_DESIGN_DOCUMENT.md](./FRONTEND_DESIGN_DOCUMENT.md)
> **현재 브랜치:** `feat#46-middle-flow-ui` (main 대비 10커밋 ahead)

---

## 목차

1. [목적과 범위](#1-목적과-범위)
2. [코드 컨벤션](#2-코드-컨벤션)
3. [Phase 0 — 현재 브랜치 정리](#3-phase-0--현재-브랜치-정리)
4. [Phase 1 — 타입 정합](#4-phase-1--타입-정합)
5. [Phase 2 — 팀원 작업 패턴 확립](#5-phase-2--팀원-작업-패턴-확립)
6. [Phase 3 — API·어댑터 계층](#6-phase-3--api어댑터-계층)
7. [Phase 4 — 검증·보호 장치](#7-phase-4--검증보호-장치)
8. [팀원 작업 가이드](#8-팀원-작업-가이드)

---

## 1. 목적과 범위

### 1.1 목적

팀원 2명이 각자 담당 노드의 추가·관리를 독립적으로 진행할 수 있도록 **타입 안전성, 패턴 일관성, API 계층**을 선제적으로 확보한다.

### 1.2 범위

이 문서는 **리드가 단독으로 완료해야 하는 기반 작업**만 다룬다. 개별 노드의 UI/패널 구현은 팀원에게 위임한다.

### 1.3 현행 요약

| 영역 | 현재 상태 | 문제 |
|------|----------|------|
| `NodeConfig` 유니온 | discriminant 없음 | `as` 캐스팅 필수, 타입 안전성 없음 |
| `DataType` | 6개, kebab-case | 백엔드 8개와 불일치 |
| `ApiResponse` | 프론트 전용 구조 | 백엔드 `{ success, data, message, errorCode }`와 다름 |
| `Workflow` 엔티티 | 6개 필드 | 백엔드 대비 7개 필드 누락 |
| 노드 Presentation | 2개만 처리 | 13개 노드가 제네릭 label |
| 패널 Registry | 빈 객체 | 팀원용 레퍼런스 없음 |
| API 계층 | workflow CRUD만 | 노드 CRUD, 선택지, 실행, 인증 없음 |
| 어댑터 | 없음 | 프론트↔백엔드 모델 직접 전달 |

---

## 2. 코드 컨벤션

### 2.1 파일·디렉토리

| 규칙 | 예시 |
|------|------|
| 파일명 | kebab-case: `node-registry.ts`, `BaseNode.tsx` (컴포넌트만 PascalCase) |
| 디렉토리 | kebab-case: `custom-nodes/`, `add-node/` |
| 배럴 인덱스 (상위) | `export * from "./하위"` |
| 배럴 인덱스 (하위) | named export: `export { Foo } from "./Foo"` |

### 2.2 Import

```typescript
// 1) 외부 라이브러리 — value import
import { useState } from "react";

// 2) 외부 라이브러리 — type import (반드시 분리)
import type { Node, NodeProps } from "@xyflow/react";

// 3) 다른 FSD 계층 — @/ 절대 경로
import { NODE_REGISTRY } from "@/entities/node";
import type { NodeType } from "@/entities/node";

// 4) 같은 FSD 계층 — 상대 경로
import { BaseNode } from "../BaseNode";
import type { FlowNodeData } from "../../model/types";
```

**금지:**
- `import type`과 value import를 한 문장에 쓰지 않는다.
- 같은 계층에서 `@/` 절대 경로를 쓰지 않는다.
- 다른 계층에서 상대 경로를 쓰지 않는다.

### 2.3 타입 정의

```typescript
// ✅ type alias — Record<string, unknown> 확장이 필요하거나 유니온이 필요할 때
type FlowNodeData = { ... };

// ✅ interface — 확장 가능한 객체 형태, extends 사용 시
interface BaseNodeConfig { ... }
interface CommunicationNodeConfig extends BaseNodeConfig { ... }

// ❌ 금지 — interface에 index signature가 필요하면 type으로 변경
// React Flow의 Node<T>는 T extends Record<string, unknown>을 요구하므로
// FlowNodeData는 반드시 type으로 선언
```

### 2.4 컴포넌트

```typescript
// ✅ 커스텀 노드 컴포넌트 — named export, const + 화살표 함수
export const CommunicationNode = ({ id, data, selected }: NodeProps<Node<FlowNodeData>>) => {
  // ...
};

// ✅ 페이지 컴포넌트 — default export, function 선언문
export default function WorkflowEditorPage() {
  // ...
}

// ✅ 스타일 — Chakra UI props만 사용
<Box px={4} py={3} borderRadius="xl" bg="bg.surface" />

// ❌ 금지
<div style={{ padding: "16px" }} />
```

### 2.5 상태 관리

```typescript
// ✅ Zustand selector — 개별 필드 구독 (리렌더 최소화)
const nodes = useWorkflowStore((s) => s.nodes);
const addNode = useWorkflowStore((s) => s.addNode);

// ❌ 금지 — 전체 스토어 구독
const store = useWorkflowStore();
```

### 2.6 주석

```typescript
// ─── 섹션 구분자 (파일 내 큰 단위 분리) ──────────────────────
/** JSDoc — export 함수/인터페이스에 작성 */
// 인라인 주석 — 왜(why) 중심, 무엇(what)은 코드로 표현
// TODO: 구체적 태스크 — 반드시 이슈 번호 포함 (예: TODO(#52): ...)
```

---

## 3. Phase 0 — 현재 브랜치 정리

### 3.1 목적

`feat#46-middle-flow-ui`의 작업물을 main에 머지하여 깨끗한 시작점을 만든다.

### 3.2 작업

1. `feat#46` 남은 버그 확인 및 수정
2. PR 생성 → 코드 리뷰 → main 머지
3. 이후 Phase 1~4는 새 브랜치 `refactor/foundation`에서 진행

### 3.3 완료 기준

- main에 에디터 가이드 흐름 (시작→도착→생성방식→수동확장) 골격이 머지됨
- 빌드 에러 없음 (`pnpm run build` 통과)

---

## 4. Phase 1 — 타입 정합

### 4.1 목적

백엔드 실제 구현(flowify-BE-spring f16b095)과 프론트엔드 타입을 일치시킨다. 이 Phase가 완료되어야 API 연동, 어댑터 구현, 팀원 작업이 가능하다.

### 4.2 [P1-1] ApiResponse 타입 교체

**파일:** `src/shared/types/api.type.ts`

**현행:**
```typescript
export type ApiResponse<T> = {
  data: T;
  status: string;
  serverDateTime: string;
  errorCode: string | null;
  errorMessage: string | null;
};
```

**목표:**
```typescript
// ─── 백엔드 공통 응답 래퍼 ───────────────────────────────────
export type ApiResponse<T> = {
  success: boolean;
  data: T;
  message: string | null;
  errorCode: string | null;
};

// ─── 페이지네이션 응답 ──────────────────────────────────────
export type PageResponse<T> = {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
};
```

**근거:** 백엔드 `common/dto/ApiResponse.java`, `common/dto/PageResponse.java` 기반.

**영향 범위:** `workflow.api.ts`의 제네릭 타입 파라미터. 현재 API 함수들이 `ApiResponse<T>`를 사용 중이나, 응답 구조만 바뀌므로 함수 시그니처 변경 없음.

### 4.3 [P1-2] DataType 확장 및 통일

**파일:** `src/entities/node/model/dataType.ts`

**현행:**
```typescript
export type DataType =
  | "file-list"
  | "single-file"
  | "text"
  | "spreadsheet"
  | "email-list"
  | "api-response";
```

**목표:**
```typescript
export type DataType =
  | "file-list"
  | "single-file"
  | "text"
  | "spreadsheet"
  | "email-list"
  | "single-email"     // 🆕
  | "api-response"
  | "schedule-data";   // 🆕
```

**판단:** 케이스 변환(kebab → UPPER_SNAKE)은 어댑터 레이어(Phase 3)에서 처리한다. 프론트 내부는 kebab-case를 유지한다. 이유:
- NODE_REGISTRY, 커스텀 노드 UI 등 이미 kebab-case로 광범위하게 사용 중
- 전면 리팩토링 비용 대비 어댑터 변환 비용이 낮음

**함께 수정:**
- `nodeRegistry.ts`의 `defaultInputTypes`/`defaultOutputTypes`에서 새 타입을 사용하는 노드가 있으면 추가
- `DataTypeTransformRule` 타입 제거 (미사용, dead code)
- `NodeDataIO` 인터페이스 제거 (미사용, `FlowNodeData`가 직접 배열을 가지고 있음)

### 4.4 [P1-3] NodeConfig discriminant 도입

**파일:** `src/entities/node/model/types.ts`

이것이 Phase 1의 **핵심 변경**이다. 현재 `NodeConfig` 유니온은 discriminant가 없어서 `as` 캐스팅 없이는 타입을 좁힐 수 없다.

**현행 (unsafe):**
```typescript
// nodePresentation.ts — as 캐스팅 필수
const service = (data.config as StorageNodeConfig).service;

// CommunicationNode.tsx — as 캐스팅 필수
const config = data.config as CommunicationNodeConfig;
```

**변경 전략:**

`BaseNodeConfig`에 `type` 필드를 discriminant로 추가하지 **않는다**. 이유:
- `FlowNodeData`에 이미 `type: NodeType`이 있다
- `config.type`과 `data.type`이 동일 값을 중복 저장하게 됨
- NODE_REGISTRY의 `defaultConfig`에도 전부 `type`을 추가해야 함

대신, **`NodeConfigMap` 매핑 타입**을 도입하여 캐스팅을 한 곳에 집중시킨다:

```typescript
// ─── NodeType → NodeConfig 매핑 ──────────────────────────────
export type NodeConfigMap = {
  communication: CommunicationNodeConfig;
  storage: StorageNodeConfig;
  spreadsheet: SpreadsheetNodeConfig;
  "web-scraping": WebScrapingNodeConfig;
  calendar: CalendarNodeConfig;
  trigger: TriggerNodeConfig;
  filter: FilterNodeConfig;
  loop: LoopNodeConfig;
  condition: ConditionNodeConfig;
  "multi-output": MultiOutputNodeConfig;
  "data-process": DataProcessNodeConfig;
  "output-format": OutputFormatNodeConfig;
  "early-exit": EarlyExitNodeConfig;
  notification: NotificationNodeConfig;
  llm: LLMNodeConfig;
};

// 중앙집중형 캐스팅 헬퍼 — as 캐스팅을 이 함수 안에 격리한다
export const getTypedConfig = <T extends NodeType>(
  type: T,
  config: NodeConfig,
): NodeConfigMap[T] => {
  return config as NodeConfigMap[T];
};
```

> **주의: `getTypedConfig`는 진짜 타입 가드(runtime narrowing)가 아니다.**
> 내부적으로 `as` 캐스팅이며, 런타임에 타입을 검증하지 않는다. 목적은 `as XxxNodeConfig` 캐스팅이 코드 전역에 흩어지는 것을 방지하고, **switch 문의 리터럴 case 안에서 호출**하여 컴파일러가 타입을 좁힐 수 있게 하는 것이다.

**올바른 사용법:**

```typescript
// ✅ switch case 안에서 리터럴로 호출 — 컴파일러가 타입을 좁힘
switch (data.type) {
  case "storage": {
    const config = getTypedConfig("storage", data.config);
    // config: StorageNodeConfig — 리터럴 "storage"로 NodeConfigMap["storage"] 확정
    return config.service ? STORAGE_SERVICE_TITLE[config.service] : null;
  }
}

// ✅ 컴포넌트에서 타입이 이미 확정된 경우
// CommunicationNode는 React Flow nodeTypes에서 "communication" 타입에만 연결되므로
// data.type이 항상 "communication"임이 보장된다
export const CommunicationNode = ({ id, data, selected }: NodeProps<Node<FlowNodeData>>) => {
  const config = getTypedConfig("communication", data.config);
  // config: CommunicationNodeConfig
};
```

**잘못된 사용법:**

```typescript
// ❌ data.type을 유니온 그대로 넘기면 타입이 좁혀지지 않음
const config = getTypedConfig(data.type, data.config);
// config: CommunicationNodeConfig | StorageNodeConfig | ... (유니온 전체)

// ❌ switch 밖에서 리터럴 없이 사용
function processAnyNode(data: FlowNodeData) {
  const config = getTypedConfig(data.type, data.config); // 의미 없음
}
```

**변경 파일:**
- `types.ts` — `NodeConfigMap` 타입 + `getTypedConfig` 함수 추가
- `nodePresentation.ts` — `as` 캐스팅을 `getTypedConfig`로 교체 (switch case 내에서 리터럴 호출)
- `custom-nodes/*.tsx` — `as` 캐스팅을 `getTypedConfig`로 교체 (컴포넌트 타입이 확정된 맥락)
- `model/index.ts` — `getTypedConfig` export 추가

### 4.5 [P1-4] Workflow 엔티티 확장

**파일:** `src/entities/workflow/model/types.ts`

**현행:**
```typescript
export interface Workflow {
  id: string;
  name: string;
  status: WorkflowStatus;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  createdAt: string;
  updatedAt: string;
}
```

**목표:**
```typescript
// ─── 트리거 설정 ─────────────────────────────────────────────
export interface TriggerConfig {
  type: "manual" | "schedule" | "event";
  schedule?: string;       // cron 표현식
  eventService?: string;
  eventType?: string;
}

// ─── 워크플로우 엔티티 ───────────────────────────────────────
export interface Workflow {
  id: string;
  name: string;
  description: string;
  status: WorkflowStatus;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  userId: string;
  sharedWith: string[];
  isTemplate: boolean;
  templateId: string | null;
  trigger: TriggerConfig | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** 목록 화면용 요약 타입 */
export type WorkflowSummary = Pick<
  Workflow,
  "id" | "name" | "description" | "status" | "isActive" | "createdAt" | "updatedAt"
>;
```

**근거:** 백엔드 `workflow/entity/Workflow.java` 기반.

### 4.6 [P1-5] FlowNodeData 확장

**파일:** `src/entities/node/model/types.ts`

**현행:**
```typescript
export type FlowNodeData = {
  type: NodeType;
  label: string;
  config: NodeConfig;
  inputTypes: DataType[];
  outputTypes: DataType[];
};
```

**목표:**
```typescript
export type FlowNodeData = {
  type: NodeType;
  label: string;
  config: NodeConfig;
  inputTypes: DataType[];
  outputTypes: DataType[];
  authWarning?: boolean;  // 🆕 OAuth 미연결 경고 (서버에서 수신, 읽기 전용)
};
```

**제외 항목과 이유:**
- `role` — `nodePresentation.ts`의 `getNodeRole()`이 source of truth. 저장하지 않음.
- `dataType`/`outputDataType` (단일) — 배열 유지. 어댑터에서 변환.

---

## 5. Phase 2 — 팀원 작업 패턴 확립

### 5.1 목적

팀원이 새 노드를 추가할 때 **어디를 수정하면 되는지** 패턴을 확립한다. 레퍼런스 구현 1개를 만들어서 복사 가능하게 한다.

### 5.2 [P2-1] nodePresentation 아이콘 연결

**파일:** `src/entities/node/model/nodePresentation.ts`

**현행 문제:** 모든 노드가 `TEMPORARY_ICON` (MdApps)을 사용한다.

```typescript
// 현행 — 하드코딩
const TEMPORARY_ICON = MdApps;

return {
  // ...
  iconComponent: TEMPORARY_ICON,  // 모든 노드가 같은 아이콘
};
```

**목표:** `NODE_REGISTRY`에 이미 정의된 `iconComponent`를 사용한다.

```typescript
// 변경 후
return {
  // ...
  iconComponent: meta.iconComponent,  // NODE_REGISTRY에서 가져옴
};
```

**변경 범위:** `getNodePresentation()` 함수 내 1줄. `TEMPORARY_ICON` 상수 제거.

### 5.3 [P2-2] getConfiguredTitle 확장 구조

**파일:** `src/entities/node/model/nodePresentation.ts`

**현행 문제:** `getConfiguredTitle()`이 2개 노드만 처리한다.

```typescript
const getConfiguredTitle = (data: FlowNodeData): string | null => {
  switch (data.type) {
    case "storage": { ... }
    case "communication": { ... }
    default:
      return null;  // 13개 노드가 여기로 빠짐
  }
};
```

**목표:** 모든 노드에 대해 "설정된 경우 표시할 제목"을 정의한다. 단, 리드가 모든 케이스를 구현하는 것이 아니라 **구조를 잡고 팀원이 채울 수 있게** 한다.

```typescript
const getConfiguredTitle = (data: FlowNodeData): string | null => {
  switch (data.type) {
    // ── 도메인 서비스 ─────────────────────────────────────
    case "communication": {
      const config = getTypedConfig("communication", data.config);
      return config.service ? COMMUNICATION_SERVICE_TITLE[config.service] : null;
    }
    case "storage": {
      const config = getTypedConfig("storage", data.config);
      return config.service ? STORAGE_SERVICE_TITLE[config.service] : null;
    }
    case "spreadsheet": {
      const config = getTypedConfig("spreadsheet", data.config);
      return config.service ? "Google Sheets" : null;
    }
    case "calendar": {
      const config = getTypedConfig("calendar", data.config);
      return config.service ? "Google Calendar" : null;
    }
    case "web-scraping": {
      const config = getTypedConfig("web-scraping", data.config);
      return config.targetUrl ?? null;
    }

    // ── 프로세싱 ─────────────────────────────────────────
    // TODO(#XX): 팀원 A — filter, loop, condition, multi-output
    case "filter":
    case "loop":
    case "condition":
    case "multi-output":
      return null;

    // TODO(#XX): 팀원 B — data-process, output-format, early-exit, notification, trigger
    case "data-process":
    case "output-format":
    case "early-exit":
    case "notification":
    case "trigger":
      return null;

    // ── AI ────────────────────────────────────────────────
    case "llm": {
      const config = getTypedConfig("llm", data.config);
      return config.model ?? null;
    }

    default:
      return null;
  }
};
```

**핵심:**
- `getTypedConfig` 사용으로 `as` 캐스팅 제거
- 팀원 담당 노드는 `return null`로 비워두되 case를 명시하여 TODO 위치를 확인 가능하게 함
- 새 NodeType이 추가되면 switch에서 컴파일 에러가 발생하도록 exhaustive check 추가:

```typescript
default: {
  const _exhaustive: never = data.type;
  return null;
}
```

### 5.4 [P2-3] 레퍼런스 패널 구현 (CommunicationPanel)

**신규 파일:** `src/features/configure-node/ui/panels/CommunicationPanel.tsx`

팀원이 복사할 수 있는 **완전한 레퍼런스 구현체**를 1개 만든다.

```typescript
import { Box, Text } from "@chakra-ui/react";

import { getNodePresentation, getTypedConfig } from "@/entities/node";
import { useWorkflowStore } from "@/shared";

import type { NodePanelProps } from "../../model";

import { NodePanelShell } from "./NodePanelShell";

export const CommunicationPanel = ({ nodeId, data }: NodePanelProps) => {
  const startNodeId = useWorkflowStore((s) => s.startNodeId);
  const endNodeId = useWorkflowStore((s) => s.endNodeId);
  const updateNodeConfig = useWorkflowStore((s) => s.updateNodeConfig);

  const presentation = getNodePresentation(data, {
    nodeId,
    startNodeId,
    endNodeId,
  });
  const config = getTypedConfig("communication", data.config);

  const handleServiceChange = (service: "gmail" | "slack") => {
    updateNodeConfig(nodeId, { ...config, service });
  };

  return (
    <NodePanelShell
      eyebrow={presentation.roleLabel}
      title={presentation.title}
      description="이메일 또는 메시지 서비스를 선택하세요."
    >
      <Box display="flex" flexDirection="column" gap={3}>
        <Text fontSize="sm" fontWeight="medium" color="text.primary">
          서비스
        </Text>
        <Box display="flex" gap={2}>
          {(["gmail", "slack"] as const).map((svc) => (
            <Box
              key={svc}
              px={4}
              py={2}
              borderRadius="lg"
              border="1px solid"
              borderColor={config.service === svc ? "blue.500" : "border.default"}
              bg={config.service === svc ? "blue.50" : "bg.surface"}
              cursor="pointer"
              onClick={() => handleServiceChange(svc)}
            >
              <Text fontSize="sm">{svc === "gmail" ? "Gmail" : "Slack"}</Text>
            </Box>
          ))}
        </Box>
      </Box>

      {/* 이후 필드들은 config.service에 따라 조건부 렌더링 */}
      {config.service && (
        <Text fontSize="xs" color="text.secondary">
          {config.service} 설정 상세 필드가 여기에 추가됩니다.
        </Text>
      )}
    </NodePanelShell>
  );
};
```

**패널 등록:**

```typescript
// src/features/configure-node/model/panelRegistry.ts
import { CommunicationPanel } from "../ui/panels/CommunicationPanel";

export const NODE_PANEL_REGISTRY: NodePanelRegistry = {
  communication: CommunicationPanel,
  // 팀원이 여기에 자기 노드 패널을 추가한다
};
```

### 5.5 [P2-4] 커스텀 노드 UI 패턴 정리

**현행 문제:** 커스텀 노드들이 `as` 캐스팅을 사용하고, props 타입이 `NodeProps & { data: FlowNodeData }`로 비표준적이다.

**현행:**
```typescript
export const CommunicationNode = ({
  id,
  data,
  selected,
}: NodeProps & { data: FlowNodeData }) => {
  const config = data.config as CommunicationNodeConfig;  // unsafe
  return (
    <BaseNode id={id} data={data} selected={selected}>
      <Text>{config.service ?? "서비스 미설정"}</Text>
      <Text>{config.action ?? "동작 미설정"}</Text>
    </BaseNode>
  );
};
```

**목표 패턴:**
```typescript
import type { Node, NodeProps } from "@xyflow/react";

import { getTypedConfig } from "../../model";
import type { FlowNodeData } from "../../model/types";
import { BaseNode } from "../BaseNode";

export const CommunicationNode = ({
  id,
  data,
  selected,
}: NodeProps<Node<FlowNodeData>>) => {
  const config = getTypedConfig("communication", data.config);

  return (
    <BaseNode id={id} data={data} selected={selected ?? false}>
      {config.service ? (
        <Text fontSize="xs" color="text.secondary">
          {config.service === "gmail" ? "Gmail" : "Slack"}
          {config.action ? ` · ${config.action}` : ""}
        </Text>
      ) : null}
    </BaseNode>
  );
};
```

**변경 포인트:**
1. Props 타입: `NodeProps & { data: FlowNodeData }` → `NodeProps<Node<FlowNodeData>>`
2. Config 접근: `as XxxNodeConfig` → `getTypedConfig("xxx", data.config)`
3. children 내용: 미설정 시 `null` 반환 (BaseNode의 helperText가 대신 표시)

**리드 작업 범위:** 패턴을 정립하고 `CommunicationNode`, `StorageNode` 2개만 리팩토링. 나머지는 팀원이 담당 노드 작업 시 같은 패턴으로 수정.

---

## 6. Phase 3 — API·어댑터 계층

### 6.1 목적

백엔드 실제 엔드포인트에 맞는 API 함수와, 프론트↔백엔드 모델 변환 어댑터를 구현한다.

### 6.2 [P3-1] workflow.api.ts 확장

**파일:** `src/shared/api/workflow.api.ts`

**현행:** 5개 함수 (getList, getById, create, update, delete)

**추가:**

```typescript
// ─── 노드 관리 ──────────────────────────────────────────────
/** 중간 노드 추가 */
addNode: (workflowId: string, body: NodeAddRequest) =>
  apiClient.post<ApiResponse<NodeDefinitionResponse>>(
    `/workflows/${workflowId}/nodes`,
    body,
  ),

/** 노드 설정 수정 */
updateNode: (workflowId: string, nodeId: string, body: NodeUpdateRequest) =>
  apiClient.put<ApiResponse<NodeDefinitionResponse>>(
    `/workflows/${workflowId}/nodes/${nodeId}`,
    body,
  ),

/** 노드 삭제 (하위 cascade) */
deleteNode: (workflowId: string, nodeId: string) =>
  apiClient.delete<ApiResponse<void>>(
    `/workflows/${workflowId}/nodes/${nodeId}`,
  ),

// ─── 선택지 매핑 ────────────────────────────────────────────
/** 이전 노드 기반 선택지 조회 */
getChoices: (workflowId: string, prevNodeId: string) =>
  apiClient.get<ApiResponse<ChoiceResponse>>(
    `/workflows/${workflowId}/choices/${prevNodeId}`,
  ),

/** 선택지 선택 → 노드 결정 */
selectChoice: (
  workflowId: string,
  prevNodeId: string,
  body: NodeChoiceSelectRequest,
) =>
  apiClient.post<ApiResponse<NodeSelectionResult>>(
    `/workflows/${workflowId}/choices/${prevNodeId}/select`,
    body,
  ),

// ─── 공유·생성 ──────────────────────────────────────────────
/** 워크플로우 공유 */
share: (workflowId: string, body: ShareRequest) =>
  apiClient.post<ApiResponse<void>>(
    `/workflows/${workflowId}/share`,
    body,
  ),

/** LLM 기반 워크플로우 자동 생성 */
generate: (body: WorkflowGenerateRequest) =>
  apiClient.post<ApiResponse<Workflow>>(
    `/workflows/generate`,
    body,
  ),
```

**Request/Response 타입 정의:**

```typescript
// src/shared/api/workflow.api.ts 상단에 추가

// ─── 노드 관련 DTO ──────────────────────────────────────────
export interface NodeAddRequest {
  type: string;
  label: string;
  position: { x: number; y: number };
  config: Record<string, unknown>;
  prevNodeId: string;
}

export interface NodeUpdateRequest {
  config: Record<string, unknown>;
}

export interface NodeChoiceSelectRequest {
  actionId: string;
  processingMethod?: string;
  options?: Record<string, unknown>;
}

export interface ShareRequest {
  userIds: string[];
}

export interface WorkflowGenerateRequest {
  prompt: string;
}

// ─── 선택지 응답 ────────────────────────────────────────────
export interface ChoiceAction {
  id: string;
  label: string;
  nodeType: string;
  outputDataType: string;
  priority: number;
  followUp?: ChoiceFollowUp;
  branchConfig?: ChoiceBranchConfig;
}

export interface ChoiceFollowUp {
  question: string;
  options: Array<{ id: string; label: string }>;
}

export interface ChoiceBranchConfig {
  type: string;
  options: Array<{ id: string; label: string }>;
}

export interface ChoiceResponse {
  dataType: string;
  requiresProcessingMethod: boolean;
  processingMethods?: Array<{ id: string; label: string }>;
  actions: ChoiceAction[];
}

export interface NodeSelectionResult {
  nodeType: string;
  label: string;
  outputDataType: string;
  config: Record<string, unknown>;
}
```

### 6.3 [P3-2] 신규 API 파일

**`src/shared/api/auth.api.ts`**

```typescript
import type { ApiResponse } from "../types";

import { apiClient } from "./client";

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  user: {
    id: string;
    email: string;
    name: string;
    picture: string | null;
  };
}

export const authApi = {
  /** Google OAuth 로그인 URL 요청 */
  getGoogleLoginUrl: () =>
    apiClient.get<ApiResponse<string>>("/auth/google"),

  /** Google OAuth 콜백 처리 */
  googleCallback: (code: string) =>
    apiClient.get<ApiResponse<LoginResponse>>(`/auth/google/callback?code=${code}`),

  /** 토큰 갱신 */
  refresh: (refreshToken: string) =>
    apiClient.post<ApiResponse<{ accessToken: string; refreshToken: string }>>(
      "/auth/refresh",
      { refreshToken },
    ),

  /** 로그아웃 */
  logout: () =>
    apiClient.post<ApiResponse<void>>("/auth/logout"),
};
```

**`src/shared/api/execution.api.ts`**

```typescript
import type { ApiResponse } from "../types";

import { apiClient } from "./client";

export const executionApi = {
  execute: (workflowId: string) =>
    apiClient.post<ApiResponse<{ executionId: string }>>(
      `/workflows/${workflowId}/execute`,
    ),

  getList: (workflowId: string) =>
    apiClient.get<ApiResponse<ExecutionSummary[]>>(
      `/workflows/${workflowId}/executions`,
    ),

  getById: (workflowId: string, execId: string) =>
    apiClient.get<ApiResponse<ExecutionDetail>>(
      `/workflows/${workflowId}/executions/${execId}`,
    ),

  rollback: (workflowId: string, execId: string) =>
    apiClient.post<ApiResponse<void>>(
      `/workflows/${workflowId}/executions/${execId}/rollback`,
    ),
};
```

**`src/shared/api/template.api.ts`**, **`src/shared/api/oauth-token.api.ts`**도 동일 패턴으로 생성. 상세 시그니처는 FRONTEND_DESIGN_DOCUMENT.md 5.2절 참조.

### 6.4 [P3-3] 어댑터 레이어

**신규 파일:** `src/shared/libs/workflow-adapter.ts`

상세 설계는 FRONTEND_DESIGN_DOCUMENT.md 6.8절에 정의됨. 핵심 함수:

| 함수 | 방향 | 용도 |
|------|------|------|
| `toNodeDefinition()` | 프론트→백엔드 | Node\<FlowNodeData\> → NodeDefinition |
| `toFlowNode()` | 백엔드→프론트 | NodeDefinition → Node\<FlowNodeData\> |
| `toWorkflowUpdateRequest()` | 프론트→백엔드 | 스토어 → API 요청 body |
| `hydrateStore()` | 백엔드→프론트 | API 응답 → 스토어 초기값 |
| `toBackendDataType()` | 변환 | kebab-case → UPPER_SNAKE_CASE |
| `toFrontendDataType()` | 변환 | UPPER_SNAKE_CASE → kebab-case |

### 6.5 [P3-4] 클라이언트 인터셉터 개선

**파일:** `src/shared/api/client.ts`

**추가:** 리프레시 토큰 자동 갱신 인터셉터

```typescript
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach((prom) => {
    if (token) prom.resolve(token);
    else prom.reject(error);
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // 갱신 중이면 큐에 추가
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshToken = localStorage.getItem("refreshToken");
        if (!refreshToken) throw new Error("No refresh token");

        const { data } = await authApi.refresh(refreshToken);
        const newAccessToken = data.data.accessToken;

        localStorage.setItem("accessToken", newAccessToken);
        localStorage.setItem("refreshToken", data.data.refreshToken);

        processQueue(null, newAccessToken);
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.removeItem("accessToken");
        localStorage.removeItem("refreshToken");
        window.location.href = "/login";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);
```

---

## 7. Phase 4 — 검증·보호 장치

### 7.1 목적

팀원이 잘못된 구현을 해도 빌드나 런타임에서 잡히도록 안전장치를 추가한다.

### 7.2 [P4-1] exhaustive switch 패턴

모든 `NodeType` switch문에 exhaustive check를 적용한다:

```typescript
// 새 NodeType이 추가되면 여기서 컴파일 에러 발생
default: {
  const _exhaustive: never = data.type;
  return null;
}
```

**적용 위치:**
- `nodePresentation.ts` — `getConfiguredTitle()`
- `Canvas.tsx` — `nodeTypes` 객체 (새 타입 추가 시 빠트리면 런타임에 렌더링 안 됨)

### 7.3 [P4-2] 엣지 연결 검증

**파일:** `src/entities/node/model/dataType.ts`

`isDataTypeCompatible()`의 TODO를 해소한다:

```typescript
export const isDataTypeCompatible = (
  sourceOutput: DataType[],
  targetInput: DataType[],
): boolean => {
  // 시작/종단 노드는 제약 없음
  if (sourceOutput.length === 0 || targetInput.length === 0) {
    return true;
  }
  return sourceOutput.some((type) => targetInput.includes(type));
};
```

현행 로직 자체는 **유지**한다. 이유:
- 백엔드의 선택지 매핑 API가 이미 호환 가능한 노드만 반환한다
- 프론트엔드에서 이중 검증을 할 필요는 있지만, NODE_REGISTRY의 `defaultInputTypes`/`defaultOutputTypes`가 현재 정의된 대로면 기존 로직으로 충분하다
- 실제 변환 테이블은 백엔드 `mapping_rules.json`이 authority

대신, **Canvas의 `onConnect`에서 검증을 호출**하도록 연결한다:

```typescript
// Canvas.tsx — onConnect 핸들러에 검증 추가
const handleConnect = useCallback(
  (connection: Connection) => {
    const sourceNode = nodes.find((n) => n.id === connection.source);
    const targetNode = nodes.find((n) => n.id === connection.target);

    if (sourceNode && targetNode) {
      const compatible = isDataTypeCompatible(
        sourceNode.data.outputTypes,
        targetNode.data.inputTypes,
      );
      if (!compatible) {
        // TODO: toast 알림 표시
        return;
      }
    }

    onConnect(connection);
  },
  [nodes, onConnect],
);
```

### 7.4 [P4-3] PanelRenderer 안전장치

**파일:** `src/features/configure-node/ui/PanelRenderer.tsx`

```typescript
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

// ─── Error Boundary ──────────────────────────────────────────
interface PanelErrorBoundaryState {
  hasError: boolean;
}

class PanelErrorBoundary extends Component<
  { children: ReactNode },
  PanelErrorBoundaryState
> {
  state: PanelErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): PanelErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[PanelRenderer] 패널 렌더링 에러:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box p={4}>
          <Text color="status.error" fontSize="sm">
            패널을 표시할 수 없습니다.
          </Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

// ─── PanelRenderer ───────────────────────────────────────────
export const PanelRenderer = () => {
  const activeNode = useWorkflowStore(
    (s) => s.nodes.find((node) => node.id === s.activePanelNodeId) ?? null,
  );

  if (!activeNode) return null;

  const PanelComponent =
    NODE_PANEL_REGISTRY[activeNode.data.type] ?? GenericNodePanel;

  return (
    <PanelErrorBoundary>
      <PanelComponent nodeId={activeNode.id} data={activeNode.data} />
    </PanelErrorBoundary>
  );
};
```

---

## 8. 팀원 작업 가이드

### 8.1 노드 추가 체크리스트

팀원이 새 노드 `xxx`를 추가하거나 기존 노드를 완성할 때 수정하는 파일:

```
수정 필수 (6개 파일):
┌─────────────────────────────────────────────────────────────┐
│ 1. entities/node/model/types.ts                             │
│    → XxxNodeConfig 인터페이스 정의 (이미 있으면 확인만)       │
│    → NodeConfigMap에 매핑 추가 (이미 있으면 확인만)           │
│                                                             │
│ 2. entities/node/model/nodeRegistry.ts                      │
│    → NODE_REGISTRY에 해당 타입 등록 (이미 있으면 확인만)      │
│                                                             │
│ 3. entities/node/model/nodePresentation.ts                  │
│    → getConfiguredTitle()에 case 추가                       │
│                                                             │
│ 4. entities/node/ui/custom-nodes/XxxNode.tsx                │
│    → BaseNode 래핑, getTypedConfig 사용                     │
│    → export를 custom-nodes/index.ts에 추가                  │
│                                                             │
│ 5. features/configure-node/ui/panels/XxxPanel.tsx           │
│    → NodePanelShell 사용, getTypedConfig 사용               │
│    → export를 panels/index.ts에 추가                        │
│                                                             │
│ 6. features/configure-node/model/panelRegistry.ts           │
│    → NODE_PANEL_REGISTRY에 등록                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 파일별 컨벤션

#### 커스텀 노드 (XxxNode.tsx)

```typescript
// 템플릿 — 이 구조를 따른다
import { Text } from "@chakra-ui/react";
import type { Node, NodeProps } from "@xyflow/react";

import { getTypedConfig } from "../../model";
import type { FlowNodeData } from "../../model/types";
import { BaseNode } from "../BaseNode";

export const XxxNode = ({
  id,
  data,
  selected,
}: NodeProps<Node<FlowNodeData>>) => {
  const config = getTypedConfig("xxx", data.config);

  return (
    <BaseNode id={id} data={data} selected={selected ?? false}>
      {/* 미설정 시 null 반환 — BaseNode.helperText가 대신 표시 */}
      {config.someField ? (
        <Text fontSize="xs" color="text.secondary">
          {config.someField}
        </Text>
      ) : null}
    </BaseNode>
  );
};
```

#### 설정 패널 (XxxPanel.tsx)

```typescript
// 템플릿 — CommunicationPanel.tsx를 복사하여 시작
import { getNodePresentation, getTypedConfig } from "@/entities/node";
import { useWorkflowStore } from "@/shared";

import type { NodePanelProps } from "../../model";
import { NodePanelShell } from "./NodePanelShell";

export const XxxPanel = ({ nodeId, data }: NodePanelProps) => {
  const startNodeId = useWorkflowStore((s) => s.startNodeId);
  const endNodeId = useWorkflowStore((s) => s.endNodeId);
  const updateNodeConfig = useWorkflowStore((s) => s.updateNodeConfig);

  const presentation = getNodePresentation(data, {
    nodeId, startNodeId, endNodeId,
  });
  const config = getTypedConfig("xxx", data.config);

  return (
    <NodePanelShell
      eyebrow={presentation.roleLabel}
      title={presentation.title}
      description="설명 텍스트"
    >
      {/* 설정 필드 UI */}
    </NodePanelShell>
  );
};
```

### 8.3 Phase별 의존 관계

```
Phase 0 (브랜치 정리)
    │
    ▼
Phase 1 (타입 정합) ←── 팀원 작업 전 반드시 완료
    │
    ▼
Phase 2 (패턴 확립) ←── 팀원 작업 시작 가능 시점
    │
    ├──→ 팀원 A: 담당 노드 UI + 패널
    ├──→ 팀원 B: 담당 노드 UI + 패널
    │
    ▼
Phase 3 (API·어댑터) ←── 리드가 병행 진행
    │
    ▼
Phase 4 (검증) ←── 팀원 작업 완료 후 통합 시 적용
```

**팀원 작업 시작 가능 시점: Phase 2 완료 후**

Phase 3·4는 팀원 작업과 병행 가능하다. 팀원은 로컬에서 노드 UI + 패널만 만들면 되고, API 연동은 리드가 Phase 3에서 연결한다.
