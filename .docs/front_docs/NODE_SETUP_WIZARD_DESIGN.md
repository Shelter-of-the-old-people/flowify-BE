# 노드 설정 위자드 상세 설계

> **작성일:** 2026-04-05
> **최종 수정:** 2026-04-08 (v4.3 — 반응형 듀얼 패널 유지 + 화살표형 custom edge 설계 추가)
> **선행 문서:** [FRONTEND_DESIGN_DOCUMENT.md](./FRONTEND_DESIGN_DOCUMENT.md), [FOUNDATION_IMPLEMENTATION_PLAN.md](./FOUNDATION_IMPLEMENTATION_PLAN.md)
> **목적:** 시작/도착 노드 및 중간 노드의 설정 위자드 흐름을 설계한다.
>
> **v4.3 변경 요약:**
> - 시작/도착 노드 위자드: **실제 캔버스 placeholder/node 기준**으로 SSP 카드가 오른쪽 `48px`에 anchor됨 (`[실제 캔버스 placeholder 또는 노드] —48px— [위자드 카드]`)
> - 중간 노드 위자드: 별도 오버레이(ChoicePanel) → **오른쪽 패널(OutputPanel) 내장**으로 전환
> - 듀얼 패널 레이아웃: **고정 px 배치가 아니라 캔버스 영역 기준 반응형 컨테이너**로 계산
> - 패널/노드 체인 정렬 기준: viewport가 아니라 **캔버스 rect 중심**
> - Edge 렌더링: `smoothstep` 선 중심 표현에서 **화살표형 custom edge**로 전환
> - 일반 직렬 연결과 분기 연결 모두 **EdgeLabelRenderer 기반 방향 표시** 사용
> - 설정 중 노드 위 불필요한 서비스 아이콘 완전 제거
> - "생성 방식을 결정하세요" → 모든 위자드 단계 완료 후에만 표시
> - 패널 사이에 설정 중인 노드 체인만 표시 (다른 노드 숨김)
> - SSP 내부에 placeholder나 선택된 서비스 preview를 **중복 렌더링하지 않음**
> - 시작/도착 위자드 step 전환 시 **패널 외곽 위치는 고정**되고, 카드 내부 내용만 변경됨

---

## 목차

1. [설계 원칙](#1-설계-원칙)
2. [위자드 흐름 정의](#2-위자드-흐름-정의)
3. [Store 설계](#3-store-설계)
4. [ServiceSelectionPanel 설계](#4-serviceselectionpanel-설계)
5. [중간 노드 위자드 설계 (OutputPanel 내장)](#5-중간-노드-위자드-설계-outputpanel-내장)
6. [OutputPanel 설계](#6-outputpanel-설계)
7. [InputPanel 설계](#7-inputpanel-설계)
8. [패널 닫기 규칙](#8-패널-닫기-규칙)
9. [노드 인터랙션 및 레이아웃 규칙](#9-노드-인터랙션-및-레이아웃-규칙)
10. [Edge 렌더링](#10-edge-렌더링)
11. [상태 전이 다이어그램](#11-상태-전이-다이어그램)
12. [비정상 종료 및 상태 정리](#12-비정상-종료-및-상태-정리)
13. [파일별 변경 요약](#13-파일별-변경-요약)

---

## 1. 설계 원칙

### 1.1 패널 사용 분리

| 노드 유형 | 설정 수단 | 레이아웃 |
|-----------|-----------|----------|
| **시작/도착 노드** | ServiceSelectionPanel — 실제 캔버스 placeholder/node에 붙는 anchor 패널 | `[실제 캔버스 placeholder 또는 노드] —48px— [위자드 카드]` |
| **중간 노드 (설정 진행 중)** | 듀얼 패널 — 왼쪽(InputPanel: 들어오는 데이터) + 오른쪽(OutputPanel: 위자드 단계) | 패널 사이에 노드 체인 표시 |
| **중간 노드 (설정 완료 후 클릭)** | 듀얼 패널 — 왼쪽(들어오는 데이터 + 처리 방식) + 오른쪽(나가는 데이터) | 동일한 듀얼 패널 레이아웃 |

> **v3 → v4 핵심 변경:**
> - v3에서 중간 노드의 위자드는 **ChoicePanel**(별도 중앙 오버레이)이었다.
> - v4에서는 **오른쪽 패널(OutputPanel) 안에 위자드 단계를 내장**한다. 패널 수를 늘리지 않고, 기존 듀얼 패널 구조를 그대로 활용한다.
> - ChoicePanel의 **매핑 규칙 데이터와 로직**은 유지하되, UI 위치만 오른쪽 패널로 이동한다.

### 1.2 시작/도착 노드 — 위자드 오버레이

시작/도착 노드는 캔버스에 있는 **실제 placeholder 또는 배치된 미완료 노드**를 기준으로 위자드 카드를 띄운다. ServiceSelectionPanel 내부에 placeholder, 서비스 아이콘, 서비스명을 다시 그리는 **별도 preview 영역은 만들지 않는다**.

**앵커 레이아웃 규격:**

```
실제 캔버스
[placeholder 또는 미완료 노드] ────48px──── [위자드 카드]
                                              ↑
                                      단계가 바뀌어도
                                      카드 외곽 위치는 고정
                                      내부 내용만 교체
```

- **앵커 대상:** 실제 캔버스의 `placeholder-start`, `placeholder-end`, 또는 service 선택 후 배치된 미완료 노드
- **앵커 ↔ 위자드 카드 간격:** 48px (시작·도착 동일)
- **위자드 카드:** 흰 배경, border `#f2f2f2`, `border-radius: 20px`, `box-shadow: 0 4px 4px rgba(0,0,0,0.25)`, padding 48px
- **가이드라인 제목:** 카드 상단 중앙, bold 24px, padding-bottom 24px
- **중복 금지:** SSP 내부에 placeholder나 `SelectedNodePreview` 같은 보조 노드 UI를 추가로 렌더링하지 않는다
- **위치 안정성:** `category → service → requirement → auth` 전환 중 **카드 외곽 위치는 유지**되고, step별 내용만 카드 내부에서 교체된다
- **Step 1~2 앵커:** 실제 캔버스 placeholder 기준
- **Step 3~4 앵커:** service 선택 후 캔버스에 배치된 미완료 노드 기준 (placeholder와 같은 위치를 이어받음)
- **시작/도착 완전 동일:** 앵커 규칙, 간격, 카드 스타일은 양쪽 100% 동일해야 함

### 1.3 중간 노드 — 듀얼 패널 내장 위자드

중간 노드는 이전 노드의 출력 데이터를 왼쪽에서 확인하면서, 오른쪽 패널에서 위자드를 진행한다. 단, 듀얼 패널의 위치와 크기는 `top: 140px`, `left: calc(50% ...)` 같은 **고정 px**로 박지 않고, **실제 캔버스 영역(rect)** 을 기준으로 계산한다.

#### 1.3.1 기본 데스크톱 스펙

```
                     기본 스펙(충분한 화면에서)
┌─────────────┐                                ┌─────────────┐
│ 왼쪽 패널    │  [노드A] → [현재 노드] → [노드B] │ 오른쪽 패널   │
│ 690px       │       296px gap                │ 690px       │
│ height:800px │     노드 체인 중앙 배치          │ height:800px │
└─────────────┘                                └─────────────┘
```

- **기본 패널 너비:** 690px
- **기본 패널 높이:** 800px
- **기본 gap:** 296px
- **기본 전체 너비:** 1676px

#### 1.3.2 반응형 모드

| 모드 | 조건 | 레이아웃 |
|------|------|----------|
| `wide` | `canvasWidth >= 1760` and `canvasHeight >= 864` | 기본 스펙 690 / 296 / 690 / 800 유지 |
| `compact` | `canvasWidth >= 1280` and `canvasHeight >= 720` | 기본 스펙을 **비율 축소**해 듀얼 패널 유지 |
| `stacked` | `canvasWidth < 1280` or `canvasHeight < 720` | 좌/우 패널을 세로 스택 또는 탭형 focus mode로 전환 |

> `stacked`는 정보 구조를 바꾸지 않기 위한 예외 모드다. 입력 정보, 위자드/출력 정보, 닫기 규칙은 동일하게 유지하되 동시 2열 배치만 해제한다.

#### 1.3.3 레이아웃 계산 규칙

```typescript
const SAFE_PADDING_X = 24;
const SAFE_PADDING_Y = 24;
const BASE_PANEL_WIDTH = 690;
const BASE_PANEL_HEIGHT = 800;
const BASE_GAP = 296;
const BASE_TOTAL_WIDTH = BASE_PANEL_WIDTH * 2 + BASE_GAP; // 1676

const availableWidth = canvasRect.width - SAFE_PADDING_X * 2;
const availableHeight = canvasRect.height - SAFE_PADDING_Y * 2;

const scale = Math.min(
  availableWidth / BASE_TOTAL_WIDTH,
  availableHeight / BASE_PANEL_HEIGHT,
  1,
);
```

- `wide`: `scale = 1`
- `compact`:
  - `panelWidth = clamp(round(690 * scale), 520, 690)`
  - `panelHeight = clamp(round(800 * scale), 640, 800)`
  - `gapWidth = clamp(round(296 * scale), 160, 296)`
- `stacked`:
  - `panelWidth = min(availableWidth, 720)`
  - `panelHeight = min(availableHeight - 16, 720)`
  - 한 번에 하나의 패널 그룹만 전면 표시하거나, 위/아래 스택으로 배치

#### 1.3.4 중앙 정렬 원칙

- 듀얼 패널 컨테이너의 **중심점 = 캔버스 rect의 중심점**
- `wide`/`compact` 모드에서는 패널이 좌우 대칭이므로, **패널 사이 gap의 중심 = 캔버스 중심**
- 노드 체인은 **active node 하나가 아니라 [이전 노드, 현재 노드, 다음 노드/placeholder] 바운딩 박스 중심**을 기준으로 `setCenter()` 한다
- 따라서 체인 전체가 패널 사이 정중앙에 보인다

#### 1.3.5 프로젝트 컨벤션 적용 원칙

- 레이아웃 수치(`panelWidth`, `panelHeight`, `gapWidth`, `mode`)는 **workflowStore에 넣지 않는다**
- 레이아웃은 `shared/lib` 또는 `widgets/editor-layout/model`의 **파생 계산 훅/유틸**에서 만든다
- `Canvas`, `InputPanel`, `OutputPanel`은 같은 계산 결과를 소비하되, 각자 store에 복사 저장하지 않는다
- 스타일은 Chakra props로 적용하고 `style={{ ... }}` 같은 inline style은 사용하지 않는다

### 1.4 패널 독점 규칙

동시에 하나의 패널 모드만 활성화된다:

| 상태 | ServiceSelectionPanel | InputPanel | OutputPanel |
|------|----------------------|------------|-------------|
| SSP 열림 (시작/도착 위자드) | O | X | X |
| 듀얼 패널 열림 (중간 노드) | X | O | O |
| 모두 닫힘 | X | X | X |

> **v3 대비 변경:** v3에서는 ChoicePanel이 열리면 InputPanel/OutputPanel이 숨겨졌다. v4에서는 ChoicePanel이 사라지고, 중간 노드 설정 시 처음부터 **InputPanel + OutputPanel(위자드 내장)** 이 함께 열린다.

### 1.5 통일된 닫기 동작

모든 패널은 동일한 3가지 방법으로 닫을 수 있어야 한다:
1. **X 버튼** 클릭
2. **캔버스 빈 영역** 클릭
3. **ESC** 키

### 1.6 isConfigured 판정

`isConfigured`는 `node.data.config.isConfigured` (BaseNodeConfig의 필드)이다. `node.data` 직접 필드가 아님에 유의.

현재 store의 `updateNodeConfig()`는 config를 **merge**하며 `isConfigured: true`를 주입한다:

```typescript
// store 구현 — 기존 config를 보존하며 merge
node.data.config = {
  ...node.data.config,
  ...전달된config,
  isConfigured: true,
};
```

**원칙:** `updateNodeConfig()`는 **위자드의 최종 완료 시점에만** 호출한다.

### 1.7 설정 중 노드 아이콘 표시 규칙

**설정이 진행 중인 노드 위에 서비스 아이콘을 표시하지 않는다.**

- 시작/도착 노드: 위자드 진행 중 캔버스에 표시되는 노드는 **placeholder 상태 또는 아이콘 없는 빈 노드**
- 중간 노드: 설정 완료 전까지 별도 아이콘 없음
- 서비스 아이콘은 **위자드가 완전히 끝나고 isConfigured: true가 된 후에만** 노드 위에 표시

### 1.8 "생성 방식을 결정하세요" 표시 규칙

도착 노드 설정 후 나타나는 "생성 방식을 결정하세요" (CreationMethodNode) UI는 **도착 노드의 모든 위자드 단계가 완료된 후에만** 표시한다.

```
위자드 진행 중 → CreationMethodNode 숨김
위자드 완료 (isConfigured: true) → CreationMethodNode 표시
```

---

## 2. 위자드 흐름 정의

### 2.1 시작/도착 노드 설정 흐름

시작/도착 노드는 **ServiceSelectionPanel 내부**에서 모든 단계를 완료한다. 단, SSP는 별도의 왼쪽 노드 영역을 만들지 않고 **실제 캔버스 placeholder/node를 기준으로 오른쪽 48px에 카드만 띄운다**.

1. Placeholder 클릭  
레이아웃: `[실제 캔버스 placeholder] ─48px─ [카테고리 카드]`

2. Step 1: 카테고리 선택
- 제목: `어디에서 어디로 갈까요?`
- 카드 내용: 검색바 + 카테고리 그리드
- 분기:
  - 서비스 있는 카테고리 → Step 2
  - 서비스 없음 + 요구사항 있음 → 노드 배치 후 Step 3
  - 서비스 없음 + 요구사항 없음 → 노드 배치 + 완료

3. Step 2: 서비스 선택  
레이아웃: `[실제 캔버스 placeholder] ─48px─ [서비스 목록 카드]`
- `뒤로` → Step 1
- 서비스 선택 시:
  1. `placeNode(meta, service)`로 노드를 캔버스에 배치
  2. 요구사항 있으면 → Step 3
  3. 요구사항 없으면 → 완료

4. Step 3: 요구사항 선택  
레이아웃: `[캔버스에 배치된 미완료 노드] ─48px─ [요구사항 목록 카드]`
- 캔버스 노드는 `isConfigured: false` 상태이며, 서비스 아이콘은 노드 위에 표시하지 않음
- `뒤로` → 노드 제거 + Step 2 (또는 Step 1)
- 요구사항 선택 시:
  - 인증 필요 → Step 4
  - 인증 불필요 → `updateNodeConfig()` + 완료

5. Step 4: 인증  
레이아웃: `[캔버스에 배치된 미완료 노드] ─48px─ [인증 카드]`
- `뒤로` → Step 3
- 인증 완료 → `updateNodeConfig()` + 완료

6. 고정 규칙
- Step 전환 중 **카드 외곽 위치는 유지**되고, 카드 내부 콘텐츠만 교체된다
- SSP 내부에 placeholder나 선택된 서비스 preview를 별도로 렌더링하지 않는다

### 2.2 중간 노드 설정 흐름

중간 노드는 placeholder 클릭 시 **듀얼 패널이 즉시 열린다.** 왼쪽(InputPanel)에 이전 노드의 데이터를 표시하고, 오른쪽(OutputPanel)에서 위자드 단계를 진행한다.

```
[중간 placeholder 클릭]
    │
    ├── activePanelNodeId 설정 (듀얼 패널 열림)
    │   → InputPanel: 이전 노드 데이터 표시
    │   → OutputPanel: 위자드 모드 진입
    │
    ├── 이전(leaf) 노드의 outputTypes[0] 확인
    │   → DataType(kebab) → MappingKey(SCREAMING_SNAKE) 변환
    │   → 매핑 규칙 데이터에서 해당 data_type 조회
    ▼
┌─────────────────────────────────────────────────────┐
│  Step 1: 처리 방식 (OutputPanel 내부)                │
│                                                     │
│  - requires_processing_method === true일 때만 표시   │
│  - 질문: "파일들을 어떻게 처리할까요?" 등              │
│  - 선택지:                                           │
│    A) node_type 있음 (예: LOOP)                      │
│       → 해당 노드 생성 + output_data_type 변경        │
│       → 새 output_data_type의 actions 조회            │
│       → actions 비어있으면 완료, 있으면 Step 2         │
│    B) node_type === null (예: "전체 사용")            │
│       → 노드 미생성, output_data_type 유지            │
│       → 현재 data_type의 actions 조회                 │
│       → actions 비어있으면 완료, 있으면 Step 2         │
│                                                     │
│  - requires_processing_method === false이면           │
│    바로 Step 2로 진행                                 │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Step 2: 액션 선택 (OutputPanel 내부)                │
│  - priority 순으로 정렬된 선택지 목록                  │
│  - applicable_when 조건으로 필터링                    │
│  - 선택 시:                                          │
│    1. 해당 action의 node_type으로 노드 생성            │
│    2. follow_up 있으면 → Step 3                      │
│    3. branch_config 있으면 → Step 3                  │
│    4. 둘 다 없으면 → updateNodeConfig → 완료          │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Step 3: 후속 설정 (OutputPanel 내부)                │
│  - follow_up: 단일/다중 선택 또는 텍스트 입력          │
│  - branch_config: 분기 기준 선택 (multi_select 가능)  │
│  - 완료 → updateNodeConfig                           │
│  - "뒤로" → Step 2로 복귀 (노드 제거)                 │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  완료 → OutputPanel이 위자드 모드에서 상세 모드로 전환   │
│  - 노드: isConfigured: true                          │
│  - OutputPanel: 위자드 UI → 나가는 데이터 표시로 전환   │
│  - InputPanel: 들어오는 데이터 + 처리 방식 표시         │
└─────────────────────────────────────────────────────┘
```

### 2.3 중간 노드 — 설정 완료 후 클릭

이미 설정이 완료된 중간 노드를 클릭하면 **듀얼 패널의 상세 모드**가 열린다.

**왼쪽 패널 (InputPanel):**
- 이전 노드에서 들어오는 데이터 (파일 목록 등)
- 데이터 처리 방식 표시 (예: "내용 요약/정리")
- 선택된 처리 옵션 목록 (예: "키워드별 요약", "정해진 형식에 맞춰서")
- 직접 입력 필드 (`{@파일 1}을 기준으로 ...`)

**오른쪽 패널 (OutputPanel):**
- 나가는 데이터 표시 (예: "요약된 데이터")
- 하단에 "테스트 해보기" 버튼

### 2.4 시작 노드의 InputPanel

시작 노드 클릭 시 InputPanel에는 "이전 노드" 대신 **사용자 데이터**(향후 연동 시 사용자 계정 정보 등)를 표시한다. 현재 단계에서는 "시작점" 안내 메시지를 표시한다.

---

## 3. Store 설계

### 3.1 위자드 관련 store 필드 — 제거

v1에서 사용하던 다음 3개 필드를 **store에서 제거**한다:

| 필드 | v1 용도 | 불필요한 이유 |
|------|---------|-------------|
| `wizardStep` | OutputPanel의 위자드 단계 분기 | 시작/도착 위자드가 SSP 로컬 상태로 이동, 중간 노드 위자드가 OutputPanel 로컬 상태로 이동 |
| `wizardConfigPreset` | 인증 대기 중 configPreset 임시 저장 | SSP 로컬 상태로 이동 |
| `wizardSourcePlaceholder` | 뒤로가기 시 placeholder 복원 | SSP 로컬 상태로 이동 |

### 3.2 유지되는 store 상태

| 필드 | 용도 |
|------|------|
| `activePlaceholder` | ServiceSelectionPanel 표시 여부 + 위치 정보 |
| `activePanelNodeId` | InputPanel/OutputPanel 표시 대상 노드 |
| `startNodeId` / `endNodeId` | 시작/도착 노드 추적 |
| `creationMethod` | 수동/AI 생성 모드 |

### 3.3 v4 추가 상태 — 중간 노드 위자드 모드

중간 노드 placeholder 클릭 시, 노드를 배치하고 듀얼 패널을 열어야 한다. OutputPanel이 위자드 모드인지 상세 모드인지를 판별하기 위해 **노드의 `isConfigured` 상태를 직접 사용**한다:

```typescript
// OutputPanel 내부에서 판별
const activeNode = nodes.find((n) => n.id === activePanelNodeId);
const isWizardMode = activeNode && !activeNode.data.config.isConfigured;
const isDetailMode = activeNode && activeNode.data.config.isConfigured;
```

별도 store 필드 없이, 노드의 `isConfigured` 값으로 모드를 결정한다.

### 3.4 removeNode 수정

```typescript
removeNode: (id) =>
  set((state) => {
    // ... 기존 노드/엣지 삭제 로직 ...

    // 삭제된 노드가 패널 대상이면 패널 닫기
    if (state.activePanelNodeId && removeTargets.has(state.activePanelNodeId)) {
      state.activePanelNodeId = null;
    }

    // ... startNodeId/endNodeId 정리 ...
  }),
```

### 3.5 updateNodeConfig — merge 방식

```typescript
updateNodeConfig: (nodeId, config) =>
  set((state) => {
    const node = state.nodes.find((n) => n.id === nodeId);
    if (node) {
      node.data.config = {
        ...node.data.config,  // 기존 config 보존
        ...config,            // 전달된 값으로 덮어쓰기
        isConfigured: true,   // 항상 true 주입
      };
    }
  }),
```

### 3.6 resetEditor

`initialState` 스프레드로 전체 상태가 초기화된다. SSP 및 OutputPanel 위자드 로컬 상태는 컴포넌트 unmount 시 자동 소멸.

### 3.7 레이아웃 상태 — store에 넣지 않음

반응형 듀얼 패널 레이아웃은 **에디터 도메인 상태가 아니라 파생 UI 상태**이므로 `workflowStore`에 저장하지 않는다.

| 항목 | 소유 위치 | 이유 |
|------|-----------|------|
| `panelWidth`, `panelHeight`, `gapWidth` | layout 계산 훅/유틸 | viewport/canvas 크기에 따라 매 렌더 파생 가능 |
| `layoutMode` (`wide` / `compact` / `stacked`) | layout 계산 훅/유틸 | 브라우저 크기 의존, persistence 불필요 |
| `canvasRect` | 측정 훅 (`ResizeObserver`) | DOM 측정값이므로 store 부적합 |

**권장 구현 위치:**
- `src/shared/libs/dual-panel-layout.ts` — `getDualPanelLayout`, `useDualPanelLayout` 제공

`workflowStore`는 계속해서 **의미 상태**만 유지한다:
- `activePlaceholder`
- `activePanelNodeId`
- `startNodeId`
- `endNodeId`
- `creationMethod`

---

## 4. ServiceSelectionPanel 설계

### 4.1 책임 범위

ServiceSelectionPanel은 **시작/도착 노드 전용**이다. 중간 노드는 OutputPanel 내장 위자드가 담당한다 (5절 참조).

| 진입 조건 | 처리 단계 |
|-----------|-----------|
| 시작/도착 placeholder 클릭 (`placeholder-start` 또는 `placeholder-end`) | category → service → requirement → auth (전체) |

**표시 원칙:**
- SSP는 실제 캔버스의 placeholder 또는 미완료 노드를 기준으로 카드만 anchor한다
- SSP 내부에 placeholder, 선택된 서비스 아이콘, 서비스명 preview를 다시 렌더링하지 않는다
- step 전환 중 패널 외곽 위치는 유지하고, 카드 내부 콘텐츠만 변경한다

### 4.2 레이아웃 규격

**공통 구조 (모든 단계에서 동일):**

```typescript
// SSP 오버레이 컨테이너
<Box
  position="absolute"
  inset={0}
>
  {/* 실제 캔버스 placeholder/node의 screen 좌표를 기준으로 카드 위치 계산 */}
  <Box
    position="absolute"
    left={anchorScreenX + 48}
    top={anchorScreenY - panelHeight / 2}
  >
    <Text fontSize="24px" fontWeight="bold" textAlign="center" pb="24px">
      {guidelineTitle}
    </Text>

    <Box
      bg="white"
      border="1px solid #f2f2f2"
      borderRadius="20px"
      boxShadow="0 4px 4px rgba(0,0,0,0.25)"
      p="48px"
      overflow="hidden"
    >
      {/* 단계별 내용 */}
    </Box>
  </Box>
</Box>
```

**핵심 규칙:**
- 앵커 기준은 항상 **실제 캔버스 placeholder/node**
- `48px`는 **캔버스 앵커 ↔ 카드 좌측 경계** 간격이다
- SSP 내부에 별도의 왼쪽 노드 영역을 만들지 않는다
- 가이드라인 제목이 바뀌어도 카드의 좌측 기준점은 바뀌지 않아야 한다
- 시작/도착 모두 같은 앵커 규칙과 카드 스타일을 사용한다

### 4.3 표시 조건

```typescript
const isStartOrEndPlaceholder =
  activePlaceholder?.id === "placeholder-start" ||
  activePlaceholder?.id === "placeholder-end";

// ServiceSelectionPanel은 isStartOrEndPlaceholder일 때만 렌더링
if (!isStartOrEndPlaceholder) return null;
```

### 4.4 로컬 상태

```typescript
type WizardStep = "category" | "service" | "requirement" | "auth";

const [step, setStep] = useState<WizardStep>("category");
const [searchQuery, setSearchQuery] = useState("");
const [selectedMeta, setSelectedMeta] = useState<NodeMeta | null>(null);
const [selectedService, setSelectedService] = useState<ServiceOption | null>(null);
const [placedNodeId, setPlacedNodeId] = useState<string | null>(null);
const [selectedRequirementPreset, setSelectedRequirementPreset] =
  useState<Record<string, unknown> | null>(null);
```

모든 위자드 상태가 **로컬**이다. store에는 `activePlaceholder` 하나만 사용하여 오버레이 표시 여부를 제어한다.

### 4.5 단계별 가이드라인 제목

| 위자드 단계 | 가이드라인 제목 |
|------------|---------------|
| Step 1 (카테고리 선택) | "어디에서 어디로 갈까요?" |
| Step 2 (서비스 선택) | "서비스를 선택해주세요." |
| Step 3 (요구사항 선택) | "어떻게 사용하시겠어요?" |
| Step 4 (인증) | "인증은 가장 처음 한 번만 진행됩니다." |

### 4.6 handleCategorySelect

```typescript
const handleCategorySelect = (meta: NodeMeta) => {
  const serviceGroup = CATEGORY_SERVICE_MAP[meta.type];

  if (serviceGroup && serviceGroup.services.length > 0) {
    // A) 서비스 있는 카테고리 → Step 2
    setSelectedMeta(meta);
    setStep("service");
    return;
  }

  // 서비스 없는 노드 → 바로 배치
  const nodeId = placeNode(meta);
  if (!nodeId) return;

  const reqGroup = SERVICE_REQUIREMENTS[meta.type];
  if (reqGroup) {
    // B) 서비스 없음 + 요구사항 있음 → Step 3
    setSelectedMeta(meta);
    setPlacedNodeId(nodeId);
    setStep("requirement");
    return;
  }

  // C) 서비스 없음 + 요구사항 없음 → 바로 완료
  updateNodeConfig(nodeId, {});
  resetWizard();
};
```

### 4.7 handleServiceSelect

```typescript
const handleServiceSelect = (service: ServiceOption) => {
  if (!selectedMeta) return;

  const nodeId = placeNode(selectedMeta, service);
  if (!nodeId) return;

  setSelectedService(service);
  setPlacedNodeId(nodeId);

  const reqGroup = SERVICE_REQUIREMENTS[selectedMeta.type];
  if (reqGroup) {
    setStep("requirement");
    return;
  }

  updateNodeConfig(nodeId, {});
  resetWizard();
};
```

### 4.8 handleRequirementSelect

```typescript
const handleRequirementSelect = (req: ServiceRequirement) => {
  if (!placedNodeId || !selectedMeta) return;

  const serviceGroup = CATEGORY_SERVICE_MAP[selectedMeta.type];

  if (serviceGroup?.requiresAuth) {
    setSelectedRequirementPreset(req.configPreset);
    setStep("auth");
    return;
  }

  updateNodeConfig(placedNodeId, req.configPreset);
  resetWizard();
};
```

### 4.9 handleAuth

```typescript
const handleAuth = () => {
  if (!placedNodeId || !selectedRequirementPreset) return;

  // TODO: 실제 OAuth 인증 흐름 연동
  updateNodeConfig(placedNodeId, selectedRequirementPreset);
  resetWizard();
};
```

### 4.10 뒤로가기 핸들러

```typescript
// Step 2 (서비스) → Step 1 (카테고리)
const handleBackToCategory = () => {
  setSelectedMeta(null);
  setSelectedService(null);
  setStep("category");
};

// Step 3 (요구사항) → 이전 단계
const handleBackFromRequirement = () => {
  if (placedNodeId) {
    removeNode(placedNodeId);
    setPlacedNodeId(null);
  }

  if (selectedService) {
    setSelectedService(null);
    setStep("service");
  } else {
    setSelectedMeta(null);
    setStep("category");
  }
};

// Step 4 (인증) → Step 3 (요구사항)
const handleBackToRequirement = () => {
  setSelectedRequirementPreset(null);
  setStep("requirement");
};
```

### 4.11 handleOverlayClose (X / 배경 클릭 / ESC)

```typescript
const handleOverlayClose = () => {
  // 배치된 노드가 있으면 캔버스에 유지 (config 미완료 상태)
  resetWizard();
};
```

### 4.12 resetWizard

```typescript
const resetWizard = () => {
  setStep("category");
  setSearchQuery("");
  setSelectedMeta(null);
  setSelectedService(null);
  setPlacedNodeId(null);
  setSelectedRequirementPreset(null);
  setActivePlaceholder(null);  // 오버레이 닫힘
};
```

### 4.13 ESC 키 처리

```typescript
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && activePlaceholder) {
      handleOverlayClose();
    }
  };
  window.addEventListener("keydown", handleKeyDown);
  return () => window.removeEventListener("keydown", handleKeyDown);
}, [activePlaceholder]);
```

### 4.14 store 구독

```typescript
// 읽기
const activePlaceholder = useWorkflowStore((s) => s.activePlaceholder);
const startNodeId = useWorkflowStore((s) => s.startNodeId);
const endNodeId = useWorkflowStore((s) => s.endNodeId);

// 쓰기
const setActivePlaceholder = useWorkflowStore((s) => s.setActivePlaceholder);
const setStartNodeId = useWorkflowStore((s) => s.setStartNodeId);
const setEndNodeId = useWorkflowStore((s) => s.setEndNodeId);
const openPanel = useWorkflowStore((s) => s.openPanel);
const removeNode = useWorkflowStore((s) => s.removeNode);
const updateNodeConfig = useWorkflowStore((s) => s.updateNodeConfig);
const onConnect = useWorkflowStore((s) => s.onConnect);
```

---

## 5. 중간 노드 위자드 설계 (OutputPanel 내장)

### 5.1 개요

중간 노드의 위자드는 **별도 오버레이가 아니라, 듀얼 패널의 오른쪽(OutputPanel) 안에서** 진행된다. 이전 노드의 `outputTypes`를 기반으로 매핑 규칙 데이터를 조회하여 사용자에게 가능한 처리 방식을 제공한다.

| 항목 | 내용 |
|------|------|
| **위치** | OutputPanel 내부 (위자드 모드) |
| **진입 조건** | 중간 placeholder 클릭 → 노드 배치 → `openPanel(nodeId)` → OutputPanel이 `isConfigured === false` 감지 |
| **데이터 소스** | 정적 매핑 규칙 (Phase 2에서 백엔드 API로 교체) |
| **UI 형태** | OutputPanel 안의 단계별 선택 UI |
| **상태** | OutputPanel 내부의 로컬 상태 |

> **v3 → v4 변경:** v3의 ChoicePanel(독립 오버레이)이 사라지고, 그 로직과 데이터가 OutputPanel 내부로 통합된다.

### 5.2 매핑 규칙 데이터 구조

#### 파일 위치

매핑 규칙 관련 모델 파일은 기존 위치를 유지한다:

```
src/features/choice-panel/
├── model/
│   ├── index.ts
│   ├── mappingRules.ts          ← 정적 매핑 규칙 데이터
│   ├── types.ts                 ← 매핑 규칙 타입 정의
│   └── dataTypeKeyMap.ts        ← DataType ↔ MappingKey 변환
└── index.ts
```

> **ui/ 디렉토리 변경:** v3의 `ui/ChoicePanel.tsx`, `ui/ProcessingMethodStep.tsx`, `ui/ActionStep.tsx`, `ui/FollowUpStep.tsx`는 **제거**한다. 이 UI 로직은 OutputPanel 내부의 위자드 모드 컴포넌트로 대체된다.

#### 타입 정의 (`types.ts`)

v3과 동일 — 변경 없음.

```typescript
/** 매핑 규칙에서 사용하는 데이터 타입 키 (백엔드 형식) */
export type MappingDataTypeKey =
  | "FILE_LIST"
  | "SINGLE_FILE"
  | "EMAIL_LIST"
  | "SINGLE_EMAIL"
  | "SPREADSHEET_DATA"
  | "API_RESPONSE"
  | "SCHEDULE_DATA"
  | "TEXT";

/** 매핑 규칙에서 사용하는 노드 타입 (백엔드 형식) */
export type MappingNodeType =
  | "LOOP"
  | "CONDITION_BRANCH"
  | "AI"
  | "DATA_FILTER"
  | "AI_FILTER"
  | "PASSTHROUGH";

/** follow_up 옵션 */
export interface FollowUpOption {
  id: string;
  label: string;
  type?: "text_input";
}

/** follow_up 설정 */
export interface FollowUp {
  question: string;
  options?: FollowUpOption[];
  options_source?: "fields_from_data" | "fields_from_service";
  multi_select?: boolean;
  description?: string;
}

/** branch_config 설정 */
export interface BranchConfig {
  question: string;
  options?: FollowUpOption[];
  options_source?: "fields_from_data";
  multi_select?: boolean;
  description?: string;
}

/** applicable_when 조건 */
export interface ApplicableWhen {
  file_subtype?: string[];
}

/** 처리 방식 옵션 (Step 1) */
export interface ProcessingMethodOption {
  id: string;
  label: string;
  node_type: MappingNodeType | null;
  output_data_type: MappingDataTypeKey;
  priority: number;
}

/** 처리 방식 질문 */
export interface ProcessingMethod {
  question: string;
  options: ProcessingMethodOption[];
}

/** 액션 선택지 (Step 2) */
export interface MappingAction {
  id: string;
  label: string;
  node_type: MappingNodeType;
  output_data_type: MappingDataTypeKey;
  priority: number;
  description?: string;
  applicable_when?: ApplicableWhen;
  follow_up?: FollowUp;
  branch_config?: BranchConfig;
}

/** 데이터 타입별 매핑 규칙 */
export interface DataTypeMapping {
  label: string;
  description: string;
  requires_processing_method: boolean;
  processing_method?: ProcessingMethod;
  actions: MappingAction[];
}

/** 전체 매핑 규칙 */
export interface MappingRules {
  data_types: Record<MappingDataTypeKey, DataTypeMapping>;
  node_types: Record<MappingNodeType, { label: string; description: string }>;
  service_fields: Record<string, string[]>;
}
```

#### DataType ↔ MappingKey 변환 (`dataTypeKeyMap.ts`)

v3과 동일 — 변경 없음.

#### 백엔드 노드 타입 → 프론트엔드 NodeType 변환

v3과 동일 — 변경 없음.

#### 매핑 규칙 데이터 (`mappingRules.ts`)

v3과 동일 — 변경 없음.

### 5.3 OutputPanel 내부 위자드 로컬 상태

OutputPanel이 `isConfigured === false`인 노드를 감지하면, 위자드 모드로 진입한다. 위자드 상태는 **OutputPanel의 로컬 상태**로 관리된다:

```typescript
type WizardStep = "processing-method" | "action" | "follow-up";

// OutputPanel 내부
const [wizardStep, setWizardStep] = useState<WizardStep | null>(null);
const [currentDataTypeKey, setCurrentDataTypeKey] = useState<MappingDataTypeKey | null>(null);
const [selectedProcessingOption, setSelectedProcessingOption] = useState<ProcessingMethodOption | null>(null);
const [selectedAction, setSelectedAction] = useState<MappingAction | null>(null);
const [followUpSelections, setFollowUpSelections] = useState<Record<string, string | string[]>>({});
```

### 5.4 초기화 — 이전 노드 outputTypes 확인

```typescript
// OutputPanel 내부
const activeNode = nodes.find((n) => n.id === activePanelNodeId);
const isWizardMode = activeNode && !activeNode.data.config.isConfigured;

// 이전 노드의 outputTypes 확인 (중간 노드일 때)
const isStartNode = activeNode?.id === startNodeId;
const isEndNode = activeNode?.id === endNodeId;
const isMiddleNode = !isStartNode && !isEndNode;

useEffect(() => {
  if (!isWizardMode || !isMiddleNode) return;

  // 이전 노드 찾기 (edges에서 target이 현재 노드인 edge의 source)
  const incomingEdge = edges.find((e) => e.target === activePanelNodeId);
  const parentNode = incomingEdge
    ? nodes.find((n) => n.id === incomingEdge.source)
    : null;
  const parentOutputType = parentNode?.data.outputTypes[0] ?? null;

  if (!parentOutputType) return;

  const mappingKey = toMappingKey(parentOutputType);
  const dataType = MAPPING_RULES.data_types[mappingKey];
  setCurrentDataTypeKey(mappingKey);

  if (dataType.requires_processing_method) {
    setWizardStep("processing-method");
  } else {
    setWizardStep("action");
  }
}, [isWizardMode, isMiddleNode, activePanelNodeId]);
```

### 5.5 Step 1 — 처리 방식 선택

```typescript
const handleProcessingMethodSelect = (option: ProcessingMethodOption) => {
  setSelectedProcessingOption(option);

  // LOOP 등 node_type이 있으면 노드 생성
  if (option.node_type) {
    const frontendNodeType = MAPPING_NODE_TYPE_MAP[option.node_type];
    const meta = NODE_REGISTRY[frontendNodeType];
    const nodeId = placeNode(meta);
    if (!nodeId) return;

    updateNodeConfig(nodeId, {}); // 처리 방식 노드는 바로 설정 완료
  }

  // 새 output_data_type으로 actions 조회
  const nextDataType = MAPPING_RULES.data_types[option.output_data_type];
  setCurrentDataTypeKey(option.output_data_type);

  if (nextDataType.actions.length === 0) {
    // 액션 없음 → 위자드 완료
    finishMiddleWizard();
    return;
  }

  // 액션 있음 → Step 2
  setWizardStep("action");
};
```

### 5.6 Step 2 — 액션 선택

```typescript
const handleActionSelect = (action: MappingAction) => {
  setSelectedAction(action);

  // 노드 생성
  const frontendNodeType = MAPPING_NODE_TYPE_MAP[action.node_type];
  const meta = NODE_REGISTRY[frontendNodeType];
  const nodeId = placeNode(meta);
  if (!nodeId) return;

  // follow_up 또는 branch_config가 있으면 Step 3
  if (action.follow_up || action.branch_config) {
    setWizardStep("follow-up");
    return;
  }

  // 후속 설정 없음 → 바로 완료
  const outputDataType = toDataType(action.output_data_type);
  updateNodeConfig(nodeId, {
    choiceActionId: action.id,
    outputDataType,
  });
  finishMiddleWizard();
};
```

### 5.7 Step 3 — 후속 설정

```typescript
const handleFollowUpComplete = (selections: Record<string, string | string[]>) => {
  if (!activePanelNodeId || !selectedAction) return;

  const outputDataType = toDataType(selectedAction.output_data_type);
  updateNodeConfig(activePanelNodeId, {
    choiceActionId: selectedAction.id,
    outputDataType,
    followUpSelections: selections,
  });
  finishMiddleWizard();
};
```

### 5.8 위자드 완료 처리

```typescript
const finishMiddleWizard = () => {
  // 위자드 로컬 상태 초기화
  setWizardStep(null);
  setCurrentDataTypeKey(null);
  setSelectedProcessingOption(null);
  setSelectedAction(null);
  setFollowUpSelections({});

  // OutputPanel은 자동으로 상세 모드로 전환됨
  // (isConfigured가 true로 바뀌면서 위자드 모드 조건 해제)
};
```

> **듀얼 패널은 닫히지 않는다.** 위자드 완료 후 OutputPanel은 **나가는 데이터** 표시 모드로 전환되고, InputPanel은 **들어오는 데이터 + 처리 방식** 표시로 업데이트된다.

### 5.9 뒤로가기

```typescript
// Step 2 → Step 1 (처리 방식이 있었던 경우만)
const handleBackToProcessingMethod = () => {
  if (selectedAction) {
    // 액션 단계에서 배치한 노드 제거
    // (실제 배치된 노드가 있으면 제거 로직)
    setSelectedAction(null);
  }
  setSelectedProcessingOption(null);
  setWizardStep("processing-method");
};

// Step 3 → Step 2
const handleBackToAction = () => {
  setSelectedAction(null);
  setFollowUpSelections({});
  setWizardStep("action");
};
```

### 5.10 렌더링 분기 (OutputPanel 내부)

```typescript
// OutputPanel 내부 — 위자드 모드와 상세 모드 분기
if (isWizardMode && isMiddleNode && wizardStep) {
  const dataType = currentDataTypeKey
    ? MAPPING_RULES.data_types[currentDataTypeKey]
    : null;

  return (
    <Box /* OutputPanel 컨테이너 */>
      {/* 헤더: "설정" + X 버튼 */}
      <Flex justifyContent="space-between" alignItems="center" px="12px">
        <Text fontSize="20px" fontWeight="medium">설정</Text>
        <Icon as={MdCancel} onClick={handleClose} cursor="pointer" />
      </Flex>

      {/* Step 1: 처리 방식 */}
      {wizardStep === "processing-method" && dataType?.processing_method && (
        <ProcessingMethodStep
          processingMethod={dataType.processing_method}
          onSelect={handleProcessingMethodSelect}
        />
      )}

      {/* Step 2: 액션 선택 */}
      {wizardStep === "action" && dataType && (
        <ActionStep
          actions={dataType.actions}
          onSelect={handleActionSelect}
          onBack={selectedProcessingOption ? handleBackToProcessingMethod : undefined}
        />
      )}

      {/* Step 3: 후속 설정 */}
      {wizardStep === "follow-up" && selectedAction && (
        <FollowUpStep
          followUp={selectedAction.follow_up ?? null}
          branchConfig={selectedAction.branch_config ?? null}
          onComplete={handleFollowUpComplete}
          onBack={handleBackToAction}
        />
      )}
    </Box>
  );
}

// 상세 모드 (isConfigured === true)
return (
  <Box /* OutputPanel 컨테이너 */>
    {/* 헤더: 아이콘 + "나가는 데이터" + X 버튼 */}
    <Flex justifyContent="space-between" alignItems="center">
      <Flex gap="10px" alignItems="center">
        <Image src={nodeIcon} boxSize="38px" />
        <Text fontSize="20px" fontWeight="medium">나가는 데이터</Text>
      </Flex>
      <Icon as={MdCancel} onClick={handleClose} cursor="pointer" />
    </Flex>

    {/* 나가는 데이터 내용 */}
    <Box flex="1">
      <Text fontSize="16px" fontWeight="bold">{outputDataLabel}</Text>
      {/* 처리된 데이터 미리보기 영역 */}
    </Box>

    {/* 하단: 테스트 버튼 */}
    <Button
      bg="black"
      color="white"
      borderRadius="10px"
      px="24px"
      py="12px"
      fontSize="14px"
      fontWeight="semibold"
    >
      테스트 해보기
    </Button>
  </Box>
);
```

### 5.11 하위 컴포넌트 (OutputPanel 내부 서브 컴포넌트)

v3의 하위 컴포넌트 인터페이스를 그대로 유지하되, 위치가 OutputPanel 내부로 이동:

#### ProcessingMethodStep

```typescript
interface ProcessingMethodStepProps {
  processingMethod: ProcessingMethod;
  onSelect: (option: ProcessingMethodOption) => void;
}
// UI: 질문 텍스트 + 선택지 목록 (priority 순 정렬)
```

#### ActionStep

```typescript
interface ActionStepProps {
  actions: MappingAction[];
  onSelect: (action: MappingAction) => void;
  onBack?: () => void;
}
// UI: 선택지 목록 (priority 순 정렬)
// "그대로 전달" (PASSTHROUGH)은 항상 맨 아래 (priority: 99)
```

#### FollowUpStep

```typescript
interface FollowUpStepProps {
  followUp: FollowUp | null;
  branchConfig: BranchConfig | null;
  onComplete: (selections: Record<string, string | string[]>) => void;
  onBack: () => void;
}
// UI: follow_up 또는 branch_config 기반 선택/입력
```

### 5.12 중간 placeholder 클릭 시 진입 흐름

v3에서는 중간 placeholder 클릭 시 ChoicePanel이 열렸다. v4에서는:

```typescript
// Canvas.tsx — handlePlaceholderClick (중간 placeholder)
const handleMiddlePlaceholderClick = (placeholderId: string) => {
  const leafId = placeholderId.replace("placeholder-", "");

  // 1. 노드 배치 (isConfigured: false)
  const meta = getDefaultMiddleNodeMeta(); // 또는 적절한 기본 meta
  const nodeId = placeNode(meta);
  if (!nodeId) return;

  // 2. 듀얼 패널 열기
  openPanel(nodeId);

  // 3. OutputPanel은 isConfigured === false를 감지하여 위자드 모드 진입
};
```

> **activePlaceholder는 사용하지 않는다.** 중간 노드는 `activePanelNodeId`를 통해 듀얼 패널을 열고, OutputPanel의 위자드 모드를 활성화한다.

### 5.13 applicable_when 필터링

v3과 동일 — 현재 단계에서는 무시 (모든 선택지 표시). Phase 2에서 구현.

### 5.14 options_source 처리

v3과 동일 — 현재 단계에서는 description만 표시. Phase 2에서 구현.

---

## 6. OutputPanel 설계

### 6.1 책임 범위 (v4 확장)

OutputPanel은 **두 가지 모드**를 가진다:

| 모드 | 조건 | 내용 |
|------|------|------|
| **위자드 모드** | `isConfigured === false` AND 중간 노드 | 매핑 규칙 기반 단계별 선택 UI (5절 참조) |
| **상세 모드** | `isConfigured === true` | 나가는 데이터 표시 + 테스트 버튼 |
| **시작/도착 미설정** | `isConfigured === false` AND 시작/도착 노드 | PanelRenderer (기본 상태) |

> **v3 대비 변경:**
> - v3에서 OutputPanel은 PanelRenderer만 표시했다.
> - v4에서는 **중간 노드 위자드 UI**도 포함한다 (ChoicePanel의 역할 흡수).
> - 설정 완료 후에는 "나가는 데이터" 표시 + "테스트 해보기" 버튼을 제공한다.

### 6.2 모드 분기 로직

```typescript
const activeNode = nodes.find((n) => n.id === activePanelNodeId);
const isMiddleNode = activeNode?.id !== startNodeId && activeNode?.id !== endNodeId;
const isWizardMode = isMiddleNode && !activeNode?.data.config.isConfigured;
const isDetailMode = activeNode?.data.config.isConfigured;

if (isWizardMode) {
  // 위자드 모드 (5절 참조)
  return <WizardModeContent ... />;
}

if (isDetailMode) {
  // 상세 모드 — 나가는 데이터 표시
  return <DetailModeContent ... />;
}

// 시작/도착 미설정 — PanelRenderer
return <PanelRenderer />;
```

### 6.3 상세 모드 콘텐츠 (설정 완료 후)

```typescript
// 상세 모드 — 나가는 데이터
<Box>
  {/* 헤더: 노드 아이콘 + "나가는 데이터" + X 버튼 */}
  <Flex justifyContent="space-between">
    <Flex gap="10px" alignItems="center">
      <Image src={processingIcon} boxSize="36px" />
      <Text fontSize="20px" fontWeight="medium" letterSpacing="-0.4px">
        나가는 데이터
      </Text>
    </Flex>
    <Icon as={MdCancel} onClick={handleClose} cursor="pointer" boxSize="24px" />
  </Flex>

  {/* 처리 결과 데이터 영역 */}
  <Box flex="1">
    <Text fontSize="16px" fontWeight="bold">{outputDataLabel}</Text>
    {/* 데이터 미리보기 (Phase 2에서 구현) */}
  </Box>

  {/* 하단: 테스트 버튼 */}
  <Button
    bg="black" color="white"
    borderRadius="10px" px="24px" py="12px"
    fontSize="14px" fontWeight="semibold"
  >
    테스트 해보기
  </Button>
</Box>
```

### 6.4 닫기

```typescript
const handleClose = () => {
  closePanel();
};
```

### 6.5 표시 조건

```typescript
const isOpen = Boolean(activePanelNodeId) && activePlaceholder === null;
```

ServiceSelectionPanel이 열려 있으면(`activePlaceholder !== null`) OutputPanel은 숨긴다.

---

## 7. InputPanel 설계

### 7.1 표시 조건

```typescript
const isOpen = Boolean(activePanelNodeId) && activePlaceholder === null;
```

### 7.2 콘텐츠 분기

InputPanel은 **중간 노드 설정 완료 여부에 따라** 다른 콘텐츠를 표시한다:

**미설정 중간 노드 (위자드 진행 중):**
- 이전 노드에서 들어오는 데이터만 표시

**설정 완료 중간 노드:**
- 이전 노드에서 들어오는 데이터
- 데이터 처리 방식 (예: "내용 요약/정리")
- 선택된 처리 옵션 목록 (예: "키워드별 요약", "정해진 형식에 맞춰서")
- 직접 입력 필드

**시작 노드:**
- "시작점" 안내 메시지

```typescript
// 설정 완료된 중간 노드 InputPanel
<Box>
  {/* 헤더: 서비스 아이콘 + "들어오는 데이터" */}
  <Flex gap="10px" alignItems="center" px="12px">
    <Image src={sourceServiceIcon} boxSize="38px" />
    <Text fontSize="20px" fontWeight="medium" letterSpacing="-0.4px">
      들어오는 데이터
    </Text>
  </Flex>

  {/* 데이터 목록 (파일 그리드 등) */}
  <Box>
    <Text fontSize="16px" fontWeight="medium">{`내 드라이브 > 폴더 1`}</Text>
    <Grid templateColumns="repeat(6, 1fr)" gap="24px" p="24px">
      {files.map((file) => (
        <FileItem key={file.id} file={file} />
      ))}
    </Grid>
  </Box>

  {/* 데이터 처리 방식 (isConfigured일 때만) */}
  {isConfigured && (
    <Box>
      <Text fontSize="16px" fontWeight="bold">데이터 처리 방식</Text>
      <Text fontSize="16px" fontWeight="semibold">{processingMethodLabel}</Text>
      {selectedOptions.map((opt) => (
        <Flex key={opt.id} gap="10px" alignItems="center" px="24px" py="12px">
          <Image src={opt.icon} boxSize="36px" />
          <Text fontSize="14px" fontWeight="bold">{opt.label}</Text>
        </Flex>
      ))}
    </Box>
  )}

  {/* 직접 입력 (isConfigured일 때만) */}
  {isConfigured && (
    <Box>
      <Text fontSize="16px" fontWeight="bold">직접 입력</Text>
      <Flex
        bg="#f6f6f6" borderRadius="24px"
        px="24px" py="12px" opacity="0.8"
        justifyContent="space-between"
      >
        <Text fontSize="16px" fontWeight="bold">{promptText}</Text>
        <Icon as={MdSend} boxSize="24px" />
      </Flex>
    </Box>
  )}
</Box>
```

### 7.3 닫기 동작

InputPanel은 OutputPanel과 수명을 공유한다. OutputPanel이 닫히면 `activePanelNodeId`가 `null`이 되어 InputPanel도 자동으로 닫힌다.

---

## 8. 패널 닫기 규칙

### 8.1 공통 규칙

| 패널 | X 버튼 | 캔버스 빈 영역 클릭 | ESC 키 |
|------|--------|---------------------|--------|
| ServiceSelectionPanel | `handleOverlayClose()` | `setActivePlaceholder(null)` | `handleOverlayClose()` |
| OutputPanel (위자드/상세) | `closePanel()` | `closePanel()` | `closePanel()` |
| InputPanel | `closePanel()` | `closePanel()` (OutputPanel과 함께) | `closePanel()` |

### 8.2 Canvas.tsx onPaneClick

```typescript
const handlePaneClick = () => {
  // ServiceSelectionPanel 닫기
  if (activePlaceholder) {
    setActivePlaceholder(null);
  }

  // 듀얼 패널 닫기
  if (activePanelNodeId) {
    closePanel();
  }
};
```

### 8.3 ESC 키 전역 리스너

```typescript
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;

    // ServiceSelectionPanel이 열려 있으면 먼저 닫기
    if (activePlaceholder) {
      setActivePlaceholder(null);
      return;
    }

    // 듀얼 패널이 열려 있으면 닫기
    if (activePanelNodeId) {
      closePanel();
    }
  };

  window.addEventListener("keydown", handleKeyDown);
  return () => window.removeEventListener("keydown", handleKeyDown);
}, [activePlaceholder, activePanelNodeId]);
```

---

## 9. 노드 인터랙션 및 레이아웃 규칙

### 9.1 듀얼 패널 레이아웃 규격

듀얼 패널(InputPanel + OutputPanel)이 열릴 때, 캔버스 전체 레이아웃:

```
캔버스 rect 중심
┌─────────────────────────────────────────────────────────────────────┐
│                   [dual panel container centered]                   │
│                                                                     │
│  ┌──────────┐                                      ┌──────────┐     │
│  │ 왼쪽 패널  │  [이전노드] → [현재노드] → [다음노드]  │ 오른쪽 패널 │     │
│  │ 690→520  │         296→160 gap                 │ 690→520  │     │
│  │ 800→640  │        체인 bounds 중앙 정렬          │ 800→640  │     │
│  └──────────┘                                      └──────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**구현 방식:**

```typescript
const layout = useDualPanelLayout(canvasRect);

<Box
  position="absolute"
  left={`${layout.containerLeft}px`}
  top={`${layout.containerTop}px`}
  width={`${layout.containerWidth}px`}
  height={`${layout.containerHeight}px`}
>
  <Box
    position="absolute"
    left="0"
    top="0"
    width={`${layout.panelWidth}px`}
    height={`${layout.panelHeight}px`}
  >
    <InputPanel />
  </Box>

  <Box
    position="absolute"
    left={`${layout.panelWidth + layout.gapWidth}px`}
    top="0"
    width={`${layout.panelWidth}px`}
    height={`${layout.panelHeight}px`}
  >
    <OutputPanel />
  </Box>
</Box>
```

**추가 규칙:**
- `top: 140px` 같은 고정 세로 위치를 사용하지 않는다
- `left="calc(50% ...)"` 같은 고정 가로 위치를 사용하지 않는다
- 듀얼 패널 컨테이너는 항상 **캔버스 rect 중심** 기준으로 계산된다
- `stacked` 모드에서는 두 패널을 세로 스택 또는 탭형 focus mode로 전환한다

### 9.2 패널 사이 노드 체인 표시 규칙

패널이 열려 있을 때 **설정 중인 노드와 직접 연결된 노드만** 표시한다:

```
[이전 노드 아이콘] → [현재 노드 아이콘/placeholder] → [다음 노드 아이콘]
```

- **이전 노드:** 현재 노드의 소스 (incoming edge의 source)
- **현재 노드:** 설정 중인 노드 (activePanelNodeId)
- **다음 노드:** 현재 노드의 타겟 (outgoing edge의 target) — 없으면 placeholder

**다른 모든 노드는 숨긴다.** 사용자가 지금 어떤 노드를 설정하는지 명확히 알 수 있어야 한다.

```typescript
// Canvas.tsx — 패널 열림 시 노드 필터링
const visibleNodes = useMemo(() => {
  if (!activePanelNodeId) return allNodes;

  // 관련 노드만 추출
  const relatedIds = new Set<string>();
  relatedIds.add(activePanelNodeId);

  // 이전 노드
  const incomingEdge = edges.find((e) => e.target === activePanelNodeId);
  if (incomingEdge) relatedIds.add(incomingEdge.source);

  // 다음 노드
  const outgoingEdge = edges.find((e) => e.source === activePanelNodeId);
  if (outgoingEdge) relatedIds.add(outgoingEdge.target);

  return allNodes.map((node) => ({
    ...node,
    hidden: !relatedIds.has(node.id),
  }));
}, [activePanelNodeId, allNodes, edges]);
```

### 9.3 삭제 버튼 — Hover 표시

```typescript
// BaseNode.tsx
const [isHovered, setIsHovered] = useState(false);

<Box
  onMouseEnter={() => setIsHovered(true)}
  onMouseLeave={() => setIsHovered(false)}
>
  {isHovered && (
    <Box position="absolute" top={-2} right={-2} onClick={handleDelete}>
      <Icon as={MdCancel} boxSize={5} />
    </Box>
  )}
</Box>
```

### 9.4 노드 선택 시 화면 중앙 고정

```typescript
const handleNodeClick = (_: React.MouseEvent, node: Node) => {
  openPanel(node.id);

  const chainBounds = getChainBounds({
    previousNode,
    activeNode: node,
    nextNodeOrPlaceholder,
  });

  reactFlowInstance.setCenter(chainBounds.centerX, chainBounds.centerY, {
    duration: 300,
    zoom: reactFlowInstance.getZoom(),
  });
};
```

전제:
- 듀얼 패널 컨테이너 자체가 캔버스 rect 중심에 놓여 있어야 한다
- 따라서 `setCenter(chainBounds.centerX, chainBounds.centerY)`만으로 패널 사이 gap 중심 정렬이 성립한다

### 9.5 선택 노드 드래그 비활성화

```typescript
const nodesWithDragControl = nodes.map((node) => ({
  ...node,
  draggable: node.id !== activePanelNodeId,
}));
```

### 9.6 Handle(연결점) 숨김

```typescript
<Handle
  type="source"
  position={Position.Right}
  style={{ opacity: 0, width: 0, height: 0, pointerEvents: "none" }}
/>
<Handle
  type="target"
  position={Position.Left}
  style={{ opacity: 0, width: 0, height: 0, pointerEvents: "none" }}
/>
```

### 9.7 설정 중 서비스 아이콘 제거

BaseNode에서 설정이 완료되지 않은 노드(`isConfigured === false`)에는 **서비스 아이콘을 표시하지 않는다:**

```typescript
// BaseNode.tsx
const showServiceIcon = node.data.config.isConfigured;

{showServiceIcon && node.data.config.service && (
  <Image src={getServiceIcon(node.data.config.service)} />
)}
```

### 9.8 CreationMethodNode 표시 조건

"생성 방식을 결정하세요" (CreationMethodNode)는 **도착 노드의 설정이 완전히 완료된 후에만** 표시한다:

```typescript
// Canvas.tsx — nodesWithPlaceholders
const showCreationMethod = useMemo(() => {
  if (!endNodeId) return false;

  const endNode = nodes.find((n) => n.id === endNodeId);
  return endNode?.data.config.isConfigured === true;
}, [endNodeId, nodes]);

// CreationMethodNode는 showCreationMethod가 true일 때만 추가
if (showCreationMethod) {
  placeholderNodes.push(creationMethodNode);
}
```

---

## 10. Edge 렌더링

### 10.1 연결선 표시

노드 간 연결은 더 이상 단순 `smoothstep` 선만으로 표현하지 않고, **방향 화살표 중심의 custom edge**로 렌더링한다.

구현 방식은 React Flow의 공식 확장 패턴을 따른다:

```typescript
const edgeTypes = {
  "flow-arrow": FlowArrowEdge,
};
```

- 기본 path: `BaseEdge`
- path 계산: `getSmoothStepPath()` 또는 `getBezierPath()`
- 화살표/라벨 UI: `EdgeLabelRenderer`

> 핵심 원칙: **연결 관계는 edge로 유지하고, 시각 표현만 custom edge로 교체**한다.

### 10.2 Edge 스타일

```typescript
const defaultEdgeOptions: DefaultEdgeOptions = {
  type: "flow-arrow",
  animated: false,
  data: {
    variant: "flow-arrow",
  },
};
```

#### 10.2.1 일반 직렬 연결

- 기준 시안: Figma `1917:1680`
- 시각 중심은 **중간 화살표 아이콘 1개**
- 실제 path는 hit area/정렬 계산용으로 유지하되, 시각적으로는 매우 옅게 처리하거나 거의 보이지 않게 처리
- 화살표는 **source → target 방향**으로 회전한다

```text
[노드 A]   →   [노드 B]
```

#### 10.2.2 분기 연결

- 기준 시안: Figma `1744:3715`
- 상향/하향 분기에서도 같은 화살표 자산을 **회전**해서 사용한다
- `edge.data.label`이 있으면 화살표 근처에 branch label을 함께 표시한다

```text
          ↗ PDF
[분기 노드]
          ↘ 이미지
```

#### 10.2.3 시각 규칙

- 화살표 색상: 현재 gray 계열과 맞춘 중간 회색 톤 사용
- 라벨 텍스트: `16px`, semibold, gray 계열
- custom edge는 **방향 표시가 목적**이므로 굵은 실선보다 화살표 자체의 가독성을 우선한다
- path hit area는 남기되, 사용자에게는 선보다 화살표가 먼저 읽혀야 한다

### 10.3 자동 연결

노드 배치 시 `placeNode()` 내부에서 `onConnect()`를 호출하여 Edge를 자동 생성한다.

`onConnect()` 계약은 유지하되, 렌더링 타입은 전역 기본값으로 `flow-arrow`를 사용한다.

추가 데이터가 필요한 경우는 `edge.data`로 확장한다:

```typescript
interface FlowEdgeData {
  label?: string;
  variant?: "flow-arrow";
}
```

- 일반 edge: `label` 없음
- 분기 edge: `label`에 `"PDF"`, `"이미지"`, `"true"`, `"false"` 등 표시 텍스트 저장 가능

> 현재 프로젝트 컨벤션 기준으로 edge 확장 타입은 `src/entities/connection/model/types.ts`에서 관리한다.

### 10.4 노드 체인 화살표 (패널 사이)

듀얼 패널 사이의 노드 체인에는 **화살표 아이콘**으로 방향을 표시한다:

```
[이전 노드] ─→─ [현재 노드] ─→─ [다음 노드]
```

화살표는 일반 edge에서 사용하는 것과 **같은 시각 언어**를 사용한다.

- 패널 사이 체인 화살표와 실제 edge 화살표는 동일한 자산/스타일 계열을 사용
- 사용자는 캔버스 전체와 패널 사이 보조 체인에서 **같은 방향 언어**를 경험해야 한다

### 10.5 파일 구조

| 파일 | 역할 |
|------|------|
| `src/entities/connection/model/types.ts` | `FlowEdgeData` 확장 타입 관리 |
| `src/entities/connection/ui/FlowArrowEdge.tsx` | custom edge 본체 (`BaseEdge + EdgeLabelRenderer`) |
| `src/entities/connection/index.ts` | edge export |
| `src/widgets/canvas/ui/Canvas.tsx` | `edgeTypes`, `defaultEdgeOptions`, edge 표시 규칙 연결 |
| `src/shared/libs/workflow-adapter.ts` | 필요 시 edge label hydrate/serialize 확장 |

---

## 11. 상태 전이 다이어그램

### 11.1 시작/도착 노드 위자드 (ServiceSelectionPanel 로컬 상태)

```
┌──────────────────────────────────────────────────────────────────┐
│ 초기 상태                                                        │
│ activePlaceholder: null                                          │
│ activePanelNodeId: null                                          │
│ SSP: 닫힘                                                        │
└──────────────────────────────────────────────────────────────────┘
        │
        │ Placeholder 클릭
        │ → setActivePlaceholder({ id, position })
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 카테고리 선택 (SSP — step: "category")                            │
│ 레이아웃: [실제 캔버스 placeholder] ─48px─ [카테고리 그리드 카드]    │
│ activePlaceholder: { id, position }                              │
│ activePanelNodeId: null                                          │
└──────────────────────────────────────────────────────────────────┘
        │
        │ 카테고리 선택 (서비스 있음)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 서비스 선택 (SSP — step: "service")                               │
│ 레이아웃: [실제 캔버스 placeholder] ─48px─ [서비스 목록 카드]       │
└──────────────────────────────────────────────────────────────────┘
        │
        │ 서비스 선택 → placeNode(meta, service)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 요구사항 선택 (SSP — step: "requirement")                         │
│ 레이아웃: [캔버스의 미완료 노드] ─48px─ [요구사항 목록 카드]        │
│ 캔버스: 노드 배치됨 (isConfigured: false, 서비스 아이콘 미표시)     │
│ SSP: 추가 preview 없음, 카드 내부 내용만 변경                      │
└──────────────────────────────────────────────────────────────────┘
        │
        ├── 인증 필요 → Step 4
        │   레이아웃: [캔버스의 미완료 노드] ─48px─ [인증 카드]
        │       │
        │       │ 인증 완료 → updateNodeConfig → resetWizard
        │       ▼
        │   완료 (activePlaceholder: null, isConfigured: true)
        │
        └── 인증 불필요 → updateNodeConfig → resetWizard
            ▼
          완료 (activePlaceholder: null, isConfigured: true)
```

### 11.2 중간 노드 설정 (OutputPanel 내장 위자드)

```
┌──────────────────────────────────────────────────────────────────┐
│ 중간 placeholder 클릭                                             │
│ → 노드 배치 (isConfigured: false)                                 │
│ → openPanel(nodeId)                                              │
│ → 듀얼 패널 열림 (InputPanel + OutputPanel)                        │
│ → OutputPanel이 isConfigured === false 감지 → 위자드 모드           │
│ → 이전 노드의 outputTypes[0] → MappingKey 변환                    │
└──────────────────────────────────────────────────────────────────┘
        │
        ├── requires_processing_method === true
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 처리 방식 선택 (OutputPanel 위자드 — wizardStep: "processing-method")│
│ 왼쪽 패널: 이전 노드 데이터                                        │
│ 오른쪽 패널: 처리 방식 선택 UI                                      │
│ 중앙: 노드 체인                                                   │
└──────────────────────────────────────────────────────────────────┘
        │
        │ 처리 방식 선택 → 새 dataType의 actions 조회
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 액션 선택 (OutputPanel 위자드 — wizardStep: "action")              │
│ 오른쪽 패널: 액션 선택 UI                                          │
└──────────────────────────────────────────────────────────────────┘
        │
        │ 액션 선택 → follow_up 또는 branch_config 있으면 Step 3
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 후속 설정 (OutputPanel 위자드 — wizardStep: "follow-up")           │
│ 오른쪽 패널: 후속 설정 UI                                          │
└──────────────────────────────────────────────────────────────────┘
        │
        │ 후속 설정 완료 → updateNodeConfig → finishMiddleWizard
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ 완료 → OutputPanel 자동 전환                                       │
│ activePanelNodeId: nodeId (유지 — 패널 닫히지 않음)                 │
│ isConfigured: true                                                │
│ 왼쪽 패널: 들어오는 데이터 + 처리 방식 + 직접 입력                   │
│ 오른쪽 패널: 나가는 데이터 + 테스트 버튼                             │
└──────────────────────────────────────────────────────────────────┘
```

### 11.3 Store 상태 스냅샷

**시작/도착 노드 (SSP):**

| 단계 | `activePlaceholder` | `activePanelNodeId` | SSP 열림 | 듀얼 패널 |
|------|-------|-------|--------|--------|
| 초기 | `null` | `null` | X | X |
| 카테고리~인증 | `{ id, pos }` | `null` | O | X |
| 완료 | `null` | `null` | X | X |

**중간 노드 (OutputPanel 위자드):**

| 단계 | `activePlaceholder` | `activePanelNodeId` | SSP 열림 | 듀얼 패널 |
|------|-------|-------|--------|--------|
| placeholder 클릭 | `null` | `nodeId` | X | O (위자드 모드) |
| 처리 방식~후속 설정 | `null` | `nodeId` | X | O (위자드 모드) |
| 완료 | `null` | `nodeId` | X | O (상세 모드) |

> **핵심 차이:** v3에서 중간 노드 설정 시 `activePlaceholder`를 사용했지만, v4에서는 `activePanelNodeId`만 사용한다. OutputPanel의 `isConfigured` 상태로 위자드/상세 모드를 결정한다.

---

## 12. 비정상 종료 및 상태 정리

### 12.1 ServiceSelectionPanel 위자드 중

| 트리거 | 처리 | 배치된 노드 |
|--------|------|-------------|
| X 버튼 | `resetWizard()` | 유지 (isConfigured: false) |
| 캔버스 빈 영역 클릭 | `setActivePlaceholder(null)` → SSP unmount | 유지 |
| ESC 키 | `resetWizard()` | 유지 |

### 12.2 OutputPanel 위자드 중 (중간 노드)

| 트리거 | 처리 | 배치된 노드 |
|--------|------|-------------|
| X 버튼 | `closePanel()` → 위자드 로컬 상태 소멸 | 유지 (isConfigured: false) |
| 캔버스 빈 영역 클릭 | `closePanel()` | 유지 |
| ESC 키 | `closePanel()` | 유지 |

> **재진입:** 미완료 노드를 다시 클릭하면 OutputPanel이 다시 위자드 모드로 열린다 (`isConfigured === false` 감지).

### 12.3 듀얼 패널 상세 모드 중

| 트리거 | 처리 |
|--------|------|
| X 버튼 | `closePanel()` → 양쪽 패널 닫힘 |
| 캔버스 빈 영역 클릭 | `closePanel()` |
| ESC 키 | `closePanel()` |
| 다른 노드 클릭 | `openPanel(새 nodeId)` → 패널 전환 |

### 12.4 노드 삭제 시

```typescript
removeNode: (id) =>
  set((state) => {
    // 삭제된 노드가 패널 대상이면 패널 닫기
    if (state.activePanelNodeId && removeTargets.has(state.activePanelNodeId)) {
      state.activePanelNodeId = null;
    }
  }),
```

### 12.5 에디터 이탈

`resetEditor`로 전체 store 상태가 초기화된다. SSP 및 OutputPanel 위자드 로컬 상태는 컴포넌트 unmount 시 자동 소멸.

---

## 13. 파일별 변경 요약

### 13.1 `src/features/add-node/ui/ServiceSelectionPanel.tsx`

| 변경 | 내용 |
|------|------|
| **추가** | 실제 캔버스 placeholder/node 기준 anchor 레이아웃 적용 — `[실제 캔버스 anchor] ─48px─ [카드 shadow+rounded-20px]` |
| **추가** | 단계별 가이드라인 제목 유지, 카드 외곽 위치 고정 |
| **변경** | SSP 내부 placeholder / selected service preview 제거 |
| **변경** | 시작/도착 노드에서 동일한 레이아웃 보장 |
| 유지 | 4단계 위자드 흐름 (category → service → requirement → auth) |
| 유지 | 로컬 상태, X 버튼, ESC 키, 뒤로가기 |

### 13.2 `src/features/choice-panel/` (변경)

| 파일 | 변경 |
|------|------|
| `model/types.ts` | **유지** — 타입 정의 변경 없음 |
| `model/mappingRules.ts` | **유지** — 매핑 규칙 데이터 변경 없음 |
| `model/dataTypeKeyMap.ts` | **유지** — 변환 유틸 변경 없음 |
| `ui/ChoicePanel.tsx` | **제거** — OutputPanel 내장으로 대체 |
| `ui/ProcessingMethodStep.tsx` | **이동** → OutputPanel 내부 서브 컴포넌트 |
| `ui/ActionStep.tsx` | **이동** → OutputPanel 내부 서브 컴포넌트 |
| `ui/FollowUpStep.tsx` | **이동** → OutputPanel 내부 서브 컴포넌트 |
| `index.ts` | **변경** — UI 컴포넌트 export 제거, model만 export |

### 13.3 `src/widgets/output-panel/ui/OutputPanel.tsx`

| 변경 | 내용 |
|------|------|
| **추가** | 위자드 모드 (isConfigured === false + 중간 노드) — 매핑 규칙 기반 단계별 선택 UI |
| **추가** | 상세 모드 (isConfigured === true) — "나가는 데이터" 표시 + "테스트 해보기" 버튼 |
| **추가** | 위자드 로컬 상태 (wizardStep, currentDataTypeKey, selectedAction 등) |
| **추가** | ProcessingMethodStep, ActionStep, FollowUpStep 서브 컴포넌트 (또는 import) |
| **변경** | 레이아웃 → `wide/compact/stacked` 반응형 모드, canvas rect 기준 중앙 정렬 |
| **변경** | 헤더 → 위자드 모드: "설정", 상세 모드: 아이콘 + "나가는 데이터" |

### 13.4 `src/widgets/input-panel/ui/InputPanel.tsx`

| 변경 | 내용 |
|------|------|
| **추가** | 설정 완료 시 "데이터 처리 방식" + 선택 옵션 목록 + 직접 입력 필드 |
| **변경** | 레이아웃 → `wide/compact/stacked` 반응형 모드, canvas rect 기준 중앙 정렬 |
| 유지 | 시작 노드 "시작점" 안내 |

### 13.5 `src/widgets/canvas/ui/Canvas.tsx`

| 변경 | 내용 |
|------|------|
| **추가** | 듀얼 패널 레이아웃 컨테이너 (`useDualPanelLayout(canvasRect)` 기반, `wide/compact/stacked`) |
| **추가** | 패널 열림 시 관련 노드만 표시 (나머지 hidden) |
| **추가** | 노드 체인 표시 (이전→현재→다음, 화살표) |
| **변경** | edge 렌더링 → `smoothstep` 대신 `flow-arrow` custom edge 적용 |
| **변경** | 중간 placeholder 클릭 → `activePlaceholder` 대신 `openPanel()` 사용 |
| **변경** | CreationMethodNode 표시 조건 → 도착 노드 `isConfigured: true` 이후에만 |
| **변경** | 설정 중 서비스 아이콘 미표시 |
| 유지 | `onPaneClick`, ESC 키 리스너, 노드 중앙 고정, 드래그 비활성화 |

### 13.6 `src/entities/connection/ui/FlowArrowEdge.tsx`

| 변경 | 내용 |
|------|------|
| **추가** | `BaseEdge + EdgeLabelRenderer` 기반 custom edge 컴포넌트 |
| **추가** | source → target 방향에 따라 화살표 회전 |
| **추가** | `edge.data.label` 기반 분기 라벨 표시 |
| **유지** | 실제 연결 관계는 React Flow edge 데이터로 유지 |

### 13.7 `src/entities/node/ui/BaseNode.tsx`

| 변경 | 내용 |
|------|------|
| **변경** | 서비스 아이콘 → `isConfigured === true`일 때만 표시 |
| 유지 | 삭제 버튼 hover 표시, Handle 숨김 |

### 13.8 `src/shared/model/workflowStore.ts`

| 변경 | 내용 |
|------|------|
| 유지 | wizard 상태 제거 (v2에서 완료) |
| 유지 | `updateNodeConfig` merge 방식 |
| 유지 | `removeNode` 패널 정리 |

### 13.8 `src/pages/workflow-editor/WorkflowEditorPage.tsx`

| 변경 | 내용 |
|------|------|
| **제거** | `ChoicePanel` 컴포넌트 렌더링 (OutputPanel 내장으로 대체) |
| 유지 | `ServiceSelectionPanel` 렌더링 |

### 13.9 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `serviceMap.ts` | 데이터 변경 없음 |
| `serviceRequirements.ts` | 데이터 변경 없음 |
| `PanelRenderer.tsx` | 기존 동작 유지 (시작/도착 미설정 노드용) |
| `choice-panel/model/*` | 타입, 데이터, 유틸 변경 없음 |
