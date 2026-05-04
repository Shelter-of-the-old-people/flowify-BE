# Choice Wizard 백엔드 수정 보고서

> 작성일: 2026-04-30
> 근거 문서: `WORKFLOW_CHOICE_WIZARD_BACKEND_ALIGNED_DESIGN.md`
> 범위: `GET /api/workflows/{id}/choices/{prevNodeId}` / `POST /api/workflows/{id}/choices/{prevNodeId}/select`

---

## FE/BE 합의 결과

| 항목 | 합의 내용 |
|------|-----------|
| Q1. JSON 필드명 | **단기: `actionId` 유지** / 장기: 별도 합의 시 `selectedOptionId`로 rename |
| Q2. 동적 옵션 resolve | **백엔드가 `onUserSelect` 응답에서 resolve하여 완성된 `options[]` 반환** |
| Q3. GET context | **`service`, `file_subtype` scalar query param만 단기 도입** / `fields` 등 배열은 POST context에서 처리 |

---

## 수정 요약

| # | 이슈 | 원인 | 수정 내용 | 파일 |
|---|------|------|-----------|------|
| 1 | GET /choices에서 context를 받지 않아 `applicable_when` 필터링 불가 | 컨트롤러가 항상 `null` 전달 | `service`, `file_subtype` query parameter 지원 추가 | `WorkflowController.java` |
| 2 | `selectNodeChoice`에서 context가 `onUserSelect`에 전달되지 않음 | `WorkflowService`가 context를 받지만 `ChoiceMappingService`에 미전달 | `onUserSelect(selectedOptionId, dataType, context)` 시그니처로 변경 및 context 전달 | `WorkflowService.java`, `ChoiceMappingService.java` |
| 3 | `onUserSelect`가 동적 옵션(`options_source`)을 resolve하지 않음 | `followUp`/`branchConfig`의 raw 설정만 반환 | `fields_from_service`, `fields_from_data` 기반 동적 옵션을 resolve하여 완성된 `options[]` 반환 | `ChoiceMappingService.java` |

**참고**: Q1(`actionId` 필드명)은 현재 `actionId` 유지로 합의되어 변경 없음.

---

## 1. GET /choices context query parameter 지원

### 변경 전

```java
public ApiResponse<ChoiceResponse> getNodeChoices(Authentication authentication,
                                                   @PathVariable String id,
                                                   @PathVariable String prevNodeId) {
    return ApiResponse.ok(workflowService.getNodeChoices(user.getId(), id, prevNodeId, null));
}
```

- context 항상 `null` → `applicable_when` 필터링 불가

### 변경 후

```java
public ApiResponse<ChoiceResponse> getNodeChoices(Authentication authentication,
                                                   @PathVariable String id,
                                                   @PathVariable String prevNodeId,
                                                   @RequestParam(required = false) String service,
                                                   @RequestParam(name = "file_subtype", required = false) String fileSubtype) {
    Map<String, Object> context = new HashMap<>();
    if (service != null) context.put("service", service);
    if (fileSubtype != null) context.put("file_subtype", fileSubtype);

    return ApiResponse.ok(workflowService.getNodeChoices(user.getId(), id, prevNodeId,
            context.isEmpty() ? null : context));
}
```

### 지원 query parameter (단기 범위)

| Parameter | 타입 | 설명 | 예시 |
|-----------|------|------|------|
| `service` | String | 서비스명 (fields_from_service용) | `?service=쿠팡` |
| `file_subtype` | String | 파일 하위 타입 (applicable_when 필터) | `?file_subtype=image` |

> **왜 이 두 개만 단기 GET에 포함하는가?**
> 현재 mapping_rules.json 기준으로 GET 단계의 `applicable_when` 필터링에는 `file_subtype` 중심의 scalar context가 주로 사용된다.
> `fields`는 GET 필터 용도가 아니라 POST /select 이후 follow-up option resolve 용도(`fields_from_data`, `fields_from_service`)이므로 단기 GET 범위에서 제외한다.
> 배열/복합 context의 query param 인코딩 규칙(예: `fields=a&fields=b` vs `fields=a,b`)은 별도 합의가 필요하며, 불명확한 상태로 도입하는 것보다 POST context에서 먼저 안정적으로 처리하는 것이 안전하다.

---

## 2. context → onUserSelect 전달 (버그 수정)

### 변경 전

```java
// WorkflowService.selectNodeChoice()
return choiceMappingService.onUserSelect(selectedOptionId, dataType);
// context를 받지만 전달하지 않음 — 동적 옵션 resolve 불가
```

### 변경 후

```java
// WorkflowService.selectNodeChoice()
return choiceMappingService.onUserSelect(selectedOptionId, dataType, context);
```

```java
// ChoiceMappingService 시그니처 변경
public NodeSelectionResult onUserSelect(String selectedOptionId, String dataType,
                                        Map<String, Object> context)
```

---

## 3. 동적 옵션 resolve

### 변경 전

`onUserSelect`가 `action.getFollowUp()`을 그대로 반환 → `options_source`가 있어도 options가 비어있거나 null

### 변경 후

`onUserSelect` 내부에서 동적 옵션을 context 기반으로 resolve:

1. `followUp.options_source == "fields_from_service"` → `context.service`로 서비스 필드 조회 → `options[]` 채움
2. `followUp.options_source == "fields_from_data"` → `context.fields`로 필드 목록 변환 → `options[]` 채움
3. `branchConfig`도 동일 로직 적용
4. `options_source`가 없으면 기존 정적 options 그대로 유지

### 추가된 private 메서드

```java
resolveFollowUp(Action action, Map<String, Object> context)
resolveBranchConfig(Action action, Map<String, Object> context)
resolveOptionsBySource(String optionsSource, Map<String, Object> context)
```

### 응답 예시 (resolve 성공)

아래는 `context: { "service": "쿠팡" }`으로 `fields_from_service`를 resolve한 경우.
실제 옵션 값은 `mapping_rules.json`의 `service_fields.쿠팡`에서 가져온다.

```json
{
  "nodeType": "AI",
  "outputDataType": "SINGLE_FILE",
  "followUp": {
    "question": "어떤 항목을 사용할까요?",
    "options": [
      { "id": "상품명", "label": "상품명" },
      { "id": "가격", "label": "가격" },
      { "id": "평점", "label": "평점" },
      { "id": "리뷰 수", "label": "리뷰 수" },
      { "id": "URL", "label": "URL" },
      { "id": "배송 정보", "label": "배송 정보" }
    ],
    "options_source": "fields_from_service",
    "multi_select": true
  }
}
```

---

## 4. `options` 비어있을 때의 의미 정책

### 배경

`followUp` 또는 `branchConfig`의 `options`가 비어있거나 null일 때,
FE 입장에서는 아래 세 가지 의미가 혼동될 수 있다.

1. 원래 선택지가 없는 정상 케이스
2. context 부족으로 resolve 실패한 케이스
3. 데이터가 준비되지 않은 케이스

### 확정 정책

**FE는 `options_source` 필드 유무로 의미를 구분한다.**

| 상태 | `options_source` | `options` | 의미 | FE 처리 |
|------|-----------------|-----------|------|---------|
| resolve 성공 | 있음 | 채워짐 | 동적 옵션이 정상 resolve됨 | 옵션 목록 렌더 |
| resolve 실패 | 있음 | null/빈 배열 | **context 부족으로 옵션을 resolve하지 못함** | 사용자에게 context 입력 안내 또는 해당 단계 진행 차단 |
| 정적 옵션 존재 | 없음 | 채워짐 | 고정 선택지 | 옵션 목록 렌더 |
| 선택 불필요 | 없음 | null/빈 배열 | **추가 선택 없이 바로 진행 가능** | 완료 버튼 활성화, 바로 다음 단계로 |

### 판단 규칙 요약

```
if (options_source != null && (options == null || options.isEmpty())) {
    // context 부족 → resolve 실패 → 진행 차단 또는 context 입력 유도
}

if (options_source == null && (options == null || options.isEmpty())) {
    // 선택 없이 진행 가능 → 완료 허용
}
```

### 백엔드 동작

- `options_source`가 있고 context로 resolve 성공 → 채워진 `options[]` 반환
- `options_source`가 있고 context 부족으로 resolve 실패 → 원본 `followUp` 그대로 반환 (mapping_rules.json의 원본 구조. `options`는 null)
- `options_source`가 없음 → 정적 `options` 그대로 반환

즉 백엔드는 resolve 실패 시 별도 에러 코드를 내지 않고, `options_source` 존재 + `options` 부재의 조합으로 FE가 상태를 판단할 수 있다.

**FE 후속 구현 필요**: 이 `options_source` 기반 판별 규칙은 현재 FE에 아직 반영되어 있지 않다. 현재 FE follow-up UI는 `options`가 비어있으면 일괄적으로 "선택지 없음" 안내를 보여주는 구조이므로, 위 정책을 실제로 활용하려면 FE 쪽에서 `options_source` 유무에 따른 분기 로직 후속 구현이 필요하다.

---

## GET/POST context schema

| Key | 타입 | GET 지원 | POST 지원 | 용도 |
|-----|------|----------|-----------|------|
| `service` | String | query param | context object | fields_from_service 해석 |
| `file_subtype` | String | query param | context object | applicable_when 필터링 |
| `fields` | List\<String\> | 미지원 (단기) | context object | fields_from_data 해석 |

> GET과 POST가 동일한 canonical context key set을 공유하되,
> GET은 단순 scalar 값만 단기 지원.

---

## API 계약 정리

### POST /choices/{prevNodeId}/select

**Request Body**

```json
{
  "actionId": "one_by_one",
  "context": {
    "service": "쿠팡",
    "file_subtype": "image",
    "fields": ["title", "price"]
  }
}
```

- `actionId`: 필수, 선택된 옵션 ID (현재 canonical wire contract)
- `context`: 선택적, 동적 옵션 resolve 및 필터링용

**Response Body**

```json
{
  "nodeType": "LOOP",
  "outputDataType": "SINGLE_FILE",
  "followUp": null,
  "branchConfig": null
}
```

- `followUp`/`branchConfig`가 있으면 `options[]`가 이미 resolve된 상태로 반환
- resolve 실패 시 `options_source`는 남아있고 `options`는 null/빈 배열 (Section 4 정책 참조)

### GET /choices/{prevNodeId}

```
GET /api/workflows/{id}/choices/{prevNodeId}?service=쿠팡&file_subtype=image
```

- 모든 query param은 optional
- 없으면 전체 선택지 반환 (`applicable_when` 조건 없는 항목만 포함)

**GET context filtering의 효력 범위**

GET context는 choice filtering에 사용되지만, 단계에 따라 효력이 다르다.

- `requires_processing_method=true`인 data type(예: `FILE_LIST`)에서는 먼저 processing method 선택지가 반환된다. 이 단계에서는 context filtering의 영향이 제한적이다 (processing method 옵션은 `applicable_when` 조건 없이 고정 제공).
- processing method 선택 후 새 노드가 저장되고, 그 노드를 기준으로 다시 `GET /choices`를 호출하면 action 선택 단계가 된다. **이 action 단계에서 `file_subtype` 등 context filtering이 직접적으로 작동한다** (예: `file_subtype=image`일 때 `describe_image` action만 노출).

---

## 빌드/테스트 결과

- `./gradlew compileJava` — BUILD SUCCESSFUL
- `./gradlew test` — BUILD SUCCESSFUL (전체 테스트 통과)

---

## FE 대응 가이드

### 하위호환성 (non-breaking)

기존 FE 호출은 깨지지 않는다.

- `actionId` 필드명 유지 → 기존 POST request 그대로 동작
- GET /choices에 query param 없이 호출해도 기존처럼 동작 (모두 optional)

### 새 기능 활용에 필요한 FE 변경

GET context filtering 기능을 실제로 사용하려면 FE query layer 수정이 필요하다.

1. `getWorkflowChoicesAPI(workflowId, prevNodeId, context?)` 형태로 API 함수 확장
2. `useWorkflowChoicesQuery`에서 context를 query key에 반영 (context 변경 시 캐시 분리)
3. controller 또는 query 호출부에서 GET context를 실제로 넘기도록 연결
4. `POST /select` 시 `context`에 `service`, `fields` 전달하면 `followUp.options`/`branchConfig.options`가 resolve된 상태로 반환
5. FE는 `options_source` 유무와 `options` 상태를 기준으로 follow-up UI 분기 처리 (Section 4 정책)

### 장기 정리 이슈 (별도 합의 필요)

- `actionId` → `selectedOptionId` rename (FE/BE 동시 변경 필요)
- GET /choices에 배열 context (`fields`) 지원 여부 및 인코딩 규칙
