# 위자드 구현 리팩토링 설계

> **작성일:** 2026-04-06
> **최종 수정:** 2026-04-08 (v4.3 설계 반영 — 반응형 듀얼 패널 + 화살표형 custom edge)
> **이슈:** #62
> **선행:** #60 (feat#60-wizard-ui-flow), [NODE_SETUP_WIZARD_DESIGN.md](./NODE_SETUP_WIZARD_DESIGN.md)
> **목적:** #60 구현(v1) 이후 발견된 문제를 수정하고, v4.3 설계 구조로 전환한다.

---

## 목차

1. [완료된 리팩토링 (v1 → v1.1)](#1-완료된-리팩토링-v1--v11)
2. [v2 구조 전환 (완료)](#2-v2-구조-전환-완료)
3. [v3 구조 전환 (완료)](#3-v3-구조-전환-완료)
4. [v4.3 구조 전환 (예정)](#4-v43-구조-전환-예정)

---

## 1. 완료된 리팩토링 (v1 → v1.1)

> 이 섹션의 변경은 이미 `refector#62wizard-sync-docs` 브랜치에서 구현·머지 완료되었다.

### 1.1 `requiresAuth` 중복 제거

`serviceRequirements.ts`의 `ServiceRequirementGroup.requiresAuth`를 제거하고, `serviceMap.ts`의 `CategoryServiceGroup.requiresAuth`를 단일 출처로 확정했다.

### 1.2 `import type` 컨벤션 수정

`OutputPanel.tsx`에서 value import와 type import를 분리했다.

---

## 2. v2 구조 전환 (완료)

| 영역 | v1 → v2 변경 | 상태 |
|------|-------------|------|
| 시작/도착 위자드 | SSP 내부에서 전체 완료 (4단계 로컬 위자드) | ✅ 완료 |
| 위자드 상태 소유권 | store에서 SSP 로컬 상태로 이동 | ✅ 완료 |
| updateNodeConfig | replace → merge 방식 | ✅ 완료 |
| 패널 닫기 | X + 캔버스 빈 영역 + ESC | ✅ 완료 |
| 삭제 버튼 | selected → hover 표시 | ✅ 완료 |
| Handle | 전체 숨김 (opacity: 0) | ✅ 완료 |
| Edge | smoothstep 렌더링 | ✅ 완료 |
| 노드 선택 시 | 화면 중앙 고정 + 드래그 비활성화 | ✅ 완료 |

---

## 3. v3 구조 전환 (완료)

| 영역 | v2 → v3 변경 | 상태 |
|------|-------------|------|
| 중간 노드 entry | SSP 카테고리 → ChoicePanel (별도 오버레이) | ✅ 완료 |
| SSP 역할 | `isMiddleNodeMode` 제거, 시작/도착 전용 | ✅ 완료 |
| OutputPanel | RequirementSelector 제거, PanelRenderer 전용 | ✅ 완료 |
| 매핑 규칙 데이터 | `mapping_rules.json` 정적 mock 내장 | ✅ 완료 |
| placeholder 분기 | 시작/도착 → SSP, 중간 → ChoicePanel | ✅ 완료 |

---

## 4. v4.3 구조 전환 (예정)

> 피그마 디자인 기반 레이아웃을 유지하되, 고정 px 배치 대신 **canvas rect 기준 반응형 컨테이너**로 재구성한다. 중간 노드 위자드는 ChoicePanel(별도 오버레이)에서 **OutputPanel 내장**으로 전환하고, edge는 화살표형 custom edge로 교체한다. [NODE_SETUP_WIZARD_DESIGN.md](./NODE_SETUP_WIZARD_DESIGN.md) v4.3 참조.

### 4.1 변경 개요

| 영역 | v3 (현재 구현) | v4.3 (목표) |
|------|---------------|-----------|
| 시작/도착 위자드 레이아웃 | "캔버스 중앙 오버레이" (구체적 규격 없음) | `[실제 캔버스 placeholder/node] ─48px─ [카드 shadow+rounded-20px]`, SSP 내부 preview 없음 |
| 중간 노드 위자드 | **ChoicePanel** (별도 중앙 오버레이) | **OutputPanel 내장** — 왼쪽(InputPanel) + 오른쪽(OutputPanel 위자드) |
| 듀얼 패널 레이아웃 | 화면 양 끝에 타이트하게 붙음 | `wide/compact/stacked` 반응형 모드, canvas rect 중심 기준 정렬 |
| 패널 사이 노드 표시 | 모든 노드 보임 | **설정 중인 노드 체인만** (이전→현재→다음), 나머지 hidden |
| Edge 렌더링 | `smoothstep` 선 중심 | **`flow-arrow` custom edge** + midpoint 화살표 + branch label |
| 설정 중 서비스 아이콘 | 노드 위에 표시됨 | **isConfigured: true 이후에만** 표시 |
| CreationMethodNode | 도착 노드 아이콘 배치 즉시 표시 | **도착 노드 isConfigured: true 이후에만** 표시 |
| 설정 완료 후 상세 모드 | OutputPanel = PanelRenderer | OutputPanel = "나가는 데이터" + "테스트 해보기" 버튼 |
| InputPanel 상세 모드 | 들어오는 데이터만 | 들어오는 데이터 + **처리 방식** + **직접 입력** |

### 4.2 파일별 변경 상세

[NODE_SETUP_WIZARD_DESIGN.md 13장](./NODE_SETUP_WIZARD_DESIGN.md#13-파일별-변경-요약) 참조.

| 파일 | 주요 변경 |
|------|-----------|
| `ServiceSelectionPanel.tsx` | 실제 캔버스 placeholder/node 기준 anchor 레이아웃 적용, 단계별 가이드라인 제목 유지, 내부 preview 제거 |
| `OutputPanel.tsx` | 위자드 모드(isConfigured: false + 중간 노드) + 상세 모드("나가는 데이터") 이중 역할 |
| `InputPanel.tsx` | 설정 완료 시 "처리 방식" + 옵션 목록 + 직접 입력 필드 추가 |
| `Canvas.tsx` | canvas rect 기반 듀얼 패널 컨테이너, 노드 체인 필터링, chain bounds 중심 정렬, CreationMethodNode 조건부 표시 |
| `src/entities/connection/ui/FlowArrowEdge.tsx` | `BaseEdge + EdgeLabelRenderer` 기반 방향 화살표 edge 구현 |
| `src/entities/connection/model/types.ts` | `FlowEdgeData.label`, `variant` 등 edge data 계약 확장 |
| `BaseNode.tsx` | 서비스 아이콘 isConfigured 조건부 표시 |
| `src/shared/libs/` | `getDualPanelLayout`, `useDualPanelLayout` 추가. store가 아닌 파생 UI 계산 전담 |
| `choice-panel/ui/` | ChoicePanel.tsx **제거**, 서브 컴포넌트 OutputPanel로 이동 |
| `WorkflowEditorPage.tsx` | ChoicePanel 렌더링 제거 |

### 4.3 구현 순서 (권장)

``` 
1. shared layout 유틸/훅 — `getDualPanelLayout`, `useDualPanelLayout` 추가
2. SSP 레이아웃 — 실제 캔버스 placeholder/node 기준 anchor 적용 (카드 외곽 고정, 내부 preview 제거)
3. BaseNode — 서비스 아이콘 isConfigured 조건부 표시
4. Canvas — canvas rect 기반 듀얼 패널 컨테이너 + `wide/compact/stacked` 모드 적용
5. Canvas — 패널 열림 시 노드 체인 필터링 + chain bounds 중심 정렬
6. entities/connection — `FlowArrowEdge` custom edge + `FlowEdgeData` 계약 추가
7. Canvas — `edgeTypes` 연결, 기본 edge 타입 `flow-arrow`로 전환
8. Canvas — CreationMethodNode 표시 조건 (endNode isConfigured 체크)
9. Canvas — 중간 placeholder 클릭 → activePanelNodeId 직접 설정 (activePlaceholder 미사용)
10. OutputPanel — 위자드 모드 (isConfigured === false + 중간 노드) 구현
11. OutputPanel — 상세 모드 ("나가는 데이터" + 테스트 버튼) 구현
12. InputPanel — 설정 완료 시 "처리 방식" + 직접 입력 필드
13. ChoicePanel UI 제거 — 컴포넌트 삭제, WorkflowEditorPage에서 렌더링 제거
14. 통합 검증 — 회귀 및 UX 점검
```

> 순서 근거: 레이아웃 계산은 `workflowStore`가 아니라 `shared/lib`의 파생 UI 계산으로 먼저 분리해야 한다. 그 다음 Canvas/패널들이 같은 계산 결과를 공유해야 반응형 모드 전환과 중앙 정렬 기준이 한 곳에서 유지된다. edge 시각 언어는 Canvas 표시 규칙과 함께 움직여야 하므로 custom edge 전환을 Canvas 연결 단계 직전에 둔다. OutputPanel 위자드 모드가 완성된 후 ChoicePanel을 제거해야 중간 전환 기간에 빌드가 깨지지 않는다.
