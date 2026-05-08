# Gmail 노드 선택지 C 구현 계획

> 작성일: 2026-05-08
> 브랜치: `9-gmail-node-error-fix`
> 기준 문서: `.docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`, `.docs/GMAIL_NODE_ERROR_FIX_DESIGN.md`
> 목적: Gmail source와 sink를 모두 유지하는 선택지 C 전환에 필요한 문서, FE 작업, 백엔드 의존성, 검증 순서를 정리한다.

---

## 1. 최종 결정

이번 이슈의 최종 선택지는 **선택지 C: Gmail source/sink 모두 유지**다.

선택지 C의 의미:

- Gmail OAuth 연결을 지원 대상으로 유지한다.
- Gmail source mode를 신규 노드 추가 UI에 노출한다.
- Gmail sink를 신규 노드 추가 UI에 노출한다.
- Gmail required template을 “준비 중”으로 막지 않는다.
- `label_emails`는 `label_picker` 기반 remote picker로 target을 선택한다.
- 실행 payload와 preview schema는 FastAPI 계약 완료 상태로 보고, error mapping은 Spring `FastApiClient` 변환까지 이번 PR 범위에 포함해 최종 검증한다.

Spring Boot 최신 상태:

- Gmail OAuth/source/sink catalog는 선택지 C 기준으로 유지한다.
- `label_emails` target-options와 OAuth scope 검증을 먼저 정렬하는 단계다.
- Gmail source 실행 payload와 source preview schema는 FastAPI 계약 반영이 완료되었으므로, Spring은 FastAPI error code 변환과 preflight/status 표현을 맞춰야 한다.

FastAPI 최신 상태:

- Gmail source runtime은 Spring catalog 기준 6개 mode에 맞춰 canonical payload를 정렬했다.
- Gmail source preview는 runtime source와 같은 canonical schema를 사용한다.
- Gmail sink send/draft 결과는 `SEND_RESULT` detail로 정렬했다.
- keyword Gmail search mode는 이번 범위에서 추가하지 않는다.

---

## 2. 문서 작업

### 2.1 요구사항 문서

대상:

- `.docs/GMAIL_NODE_ERROR_REQUIREMENTS.md`

반영 내용:

- 선택지 C를 최종 선택지로 명시한다.
- Gmail 비활성화 완료 기준을 제거하고 source/sink/OAuth 유지 완료 기준으로 바꾼다.
- Spring Boot 완료 기준과 FastAPI 완료 기준을 분리한다.
- keyword filtering은 1차에서 FE 임의 source mode를 만들지 않는다고 명시한다.

### 2.2 FE 설계 문서

대상:

- `.docs/GMAIL_NODE_ERROR_FIX_DESIGN.md`

반영 내용:

- 기존 선택지 A 방어 설계를 선택지 C 구현 설계로 전환한다.
- Gmail source/sink/OAuth allowlist 복구를 필수 변경으로 둔다.
- `label_picker` 최초 생성 위자드 보정을 필수 변경으로 둔다.
- Gmail required template 차단 제거를 필수 변경으로 둔다.
- runtime/preview 미완료 영역은 백엔드 의존성으로 분리한다.

### 2.3 Spring Boot 요청 문서

대상:

- `.docs/GMAIL_NODE_ERROR_SPRING_BOOT_REQUEST.md`

반영 내용:

- Spring Boot 작업은 Gmail 전체 runtime 완료가 아니라 OAuth/scope/target-options 정렬 단계임을 명확히 한다.
- `label_emails` target-options provider 구현과 scope 검증을 우선순위로 둔다.
- FastAPI error code를 Spring API error shape로 변환하는 작업을 명시한다.
- FE가 선택지 C로 열리는 만큼 preflight/status 검증이 필요함을 명시한다.

### 2.4 FastAPI 요청 문서

대상:

- `.docs/GMAIL_NODE_ERROR_FASTAPI_REQUEST.md`

반영 내용:

- Spring catalog 기준 6개 Gmail source mode만 runtime 대상으로 둔다.
- `SINGLE_EMAIL`, `EMAIL_LIST`, `FILE_LIST`, `SEND_RESULT` canonical payload를 확정한다.
- Gmail source preview schema를 runtime source schema와 맞춘다.
- OAuth/scope/external/runtime 오류를 구분 가능한 error code로 내려야 한다.

---

## 3. FE 구현 작업

### 3.1 Gmail 노출 복구

대상:

- `src/features/add-node/model/source-rollout.ts`
- `src/features/add-node/model/sink-rollout.ts`
- `src/entities/oauth-token/model/oauth-connect-support.ts`

작업:

- source rollout에 Gmail 6개 mode를 복구한다.
- sink rollout에 `gmail`을 복구한다.
- OAuth connect supported services에 `gmail`을 복구한다.

기대 결과:

- Gmail source가 신규 노드 추가 UI에 보인다.
- Gmail sink가 도착 노드 선택 UI에 보인다.
- Gmail OAuth 연결 버튼이 준비 중이 아니라 연결 가능 상태로 보인다.

### 3.2 Gmail label picker 보정

대상:

- `src/features/add-node/model/source-target-picker.ts`
- `src/features/add-node/ui/SourceTargetPicker.tsx`
- `src/features/configure-node/model/source-target-schema.ts`

작업:

- add-node remote schema type에 `label_picker`를 추가한다.
- Gmail label option에 적절한 icon과 문구를 적용한다.
- Drive 전용 root/empty 문구가 Gmail label picker에 노출되지 않게 한다.
- 기존 노드 설정 패널과 최초 생성 위자드의 저장 계약을 맞춘다.

저장 계약:

```json
{
  "target": "gmail-label-id",
  "target_label": "라벨명",
  "target_meta": {}
}
```

### 3.3 Gmail template 차단 제거

대상:

- `src/entities/template/model/template-service-support.ts`
- `src/pages/template-detail/ui/TemplateInfoPanel.tsx`
- `src/pages/template-detail/ui/TemplateRequiredServices.tsx`

작업:

- Gmail required template을 unsupported로 막는 로직을 제거하거나 비활성화한다.
- Gmail required service는 일반 required service로 표시한다.
- template instantiate는 OAuth/status 흐름으로 진입하게 둔다.

주의:

- 선택지 C에서는 template 목록을 숨기지 않는다.
- template preview graph는 유지한다.

### 3.4 Gmail sink 저장/status 확인

대상:

- `src/features/configure-node/ui/panels/SinkNodePanel.tsx`
- `src/entities/workflow/lib/node-status.ts`

작업:

- Gmail sink schema field key가 FE 저장 config와 맞는지 확인한다.
- `to`, `subject`, `body`, `body_format`, `action`의 required 여부를 확인한다.
- scope 부족 raw key가 사용자 문구 `권한 부족`으로 표시되는지 확인한다.

### 3.5 Gmail source data preview 확인

대상:

- `src/widgets/node-data-panel/ui/DataPreviewBlock.tsx`
- email payload mapping 관련 shared/model 코드

작업:

- `SINGLE_EMAIL` payload 표시를 확인한다.
- `EMAIL_LIST` payload 표시를 확인한다.
- `FILE_LIST` attachment metadata 표시를 확인한다.
- FastAPI preview/runtime error가 raw key로 노출되지 않게 한다.

---

## 4. 백엔드 의존성

### 4.1 Spring Boot

필수:

- Gmail OAuth connector 유지
- Gmail 기능별 required scope 검증
- `label_emails` target-options provider
- Gmail source/sink node lifecycle status 정렬
- FastAPI error code를 Spring API error shape로 변환

이번 단계에서 명확히 해야 할 것:

- Gmail source runtime payload와 source preview schema는 FastAPI 계약 반영이 완료되었으므로, Spring은 error code 변환과 lifecycle/preflight 상태 표현을 맞춘다.
- Spring은 실행 전 preflight/status에서 token 없음, scope 부족, target-options 실패를 구분해야 한다.

### 4.2 FastAPI

필수:

- Spring catalog와 동일한 Gmail source mode key 처리
- canonical payload 반환
- Gmail sink send 결과 반환
- source preview payload와 runtime source payload 정렬
- OAuth/scope/external/runtime unsupported error code 구분

이번 단계에서 제외:

- keyword search 전용 Gmail source mode
- Gmail draft action 제품 노출
- attachment content download/전달
- Gmail sink no-write preview

---

## 5. 수동 검증 시나리오

### 5.1 신규 Gmail source

1. 새 노드 추가를 연다.
2. source 목록에서 Gmail을 선택한다.
3. `label_emails` mode를 선택한다.
4. label picker가 열리는지 확인한다.
5. label 선택 후 `target`, `target_label`, `target_meta`가 저장되는지 확인한다.

### 5.2 Gmail OAuth

1. Gmail source 또는 sink를 선택한다.
2. OAuth 연결 상태를 확인한다.
3. 미연결이면 연결 시작 버튼이 보이는지 확인한다.
4. scope 부족이면 `권한 부족` 상태가 보이는지 확인한다.

### 5.3 Gmail sink

1. Gmail sink를 추가한다.
2. `to`, `subject`, `body`를 입력한다.
3. 저장 후 node config가 유지되는지 확인한다.
4. 다른 사용자 이메일 주소 입력이 가능한지 확인한다.

### 5.4 Gmail template

1. Gmail required template 상세로 이동한다.
2. Gmail이 “현재 준비 중”으로 표시되지 않는지 확인한다.
3. 가져오기 버튼이 활성화되어 있는지 확인한다.
4. instantiate 이후 OAuth/status 흐름으로 진입하는지 확인한다.

### 5.5 Gmail runtime/preview

1. Gmail source workflow를 실행하거나 preview한다.
2. `SINGLE_EMAIL`, `EMAIL_LIST`, `FILE_LIST` 결과가 깨지지 않는지 확인한다.
3. FastAPI/Spring 오류가 발생하면 raw key 대신 사용자 문구로 보이는지 확인한다.

---

## 6. PR에 적을 잔여 리스크

- Spring Boot 수정은 `label_emails` target-options, OAuth scope 검증, Gmail sink send schema/status 정렬 단계다.
- Gmail source 실행 payload와 source preview schema는 FastAPI 계약 반영이 완료되었다.
- **FastAPI error code 변환은 이번 PR에 포함한다.**
  - 이번 PR은 “선택지 C 서버 계약 완성” 범위로 설명한다.
  - `FastApiClient`가 FastAPI error body의 `error_code`를 파싱해 Spring error shape로 변환하고, 관련 테스트를 추가한다.
- keyword search source mode는 이번 범위에서 추가하지 않는다.
- Gmail draft action과 attachment content 전달은 후속 범위다.
- FE는 선택지 C 기준으로 Gmail 진입을 열지만, 서버 runtime 미완료 영역은 status/error mapping으로 사용자에게 명확히 보여야 한다.

### 6.1 FastAPI Error Mapping 포함 시 추가 작업

구현 후보:

- `FastApiClient`에서 `WebClientResponseException` body를 파싱한다.
- FastAPI error body의 `error_code`를 Spring `ErrorCode` 또는 preflight/lifecycle 상태로 매핑한다.
- mapping 실패 시에만 기존 `FASTAPI_UNAVAILABLE` fallback을 사용한다.

권장 mapping:

| FastAPI `error_code` | Spring/FE 처리 |
| --- | --- |
| `OAUTH_SCOPE_INSUFFICIENT` | `oauth_scope_insufficient` |
| `OAUTH_TOKEN_INVALID`, `OAUTH_TOKEN_MISSING` | `oauth_token` 또는 OAuth 재연결 안내 |
| `EXTERNAL_API_ERROR` | 외부 서비스 오류 |
| `EXTERNAL_RATE_LIMITED` | rate limit 또는 잠시 후 재시도 안내 |
| `UNSUPPORTED_RUNTIME_SOURCE`, `UNSUPPORTED_RUNTIME_SINK` | runtime/preflight unsupported |

권장 테스트:

- Gmail start node에서 readonly scope 부족 시 `oauth_scope_insufficient`
- Gmail end node에서 send scope 부족 시 `oauth_scope_insufficient`
- Gmail draft config가 `WorkflowValidator.validateForExecution()`에서 실패
- FastAPI `OAUTH_SCOPE_INSUFFICIENT` 응답이 Spring `OAUTH_SCOPE_INSUFFICIENT`로 변환
