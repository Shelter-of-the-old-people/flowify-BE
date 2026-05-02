# Canvas Term-All-Files Runtime Fix

## 배경

- Canvas LMS 시작 노드의 `term_all_files` picker에서는 지난 학기도 선택할 수 있었다.
- 하지만 FastAPI 런타임은 Canvas 과목 조회 시 `active`만 요청하고 있어서, 지난 학기를 실행하면 `학기 '<term>'에 해당하는 과목이 없습니다.`로 실패했다.

## 원인

- 실행 실패 로그 기준 최신 실패 실행은 `state=failed`, `error="학기 '2025-2학기'에 해당하는 과목이 없습니다."`였다.
- 실제 워크플로우 설정은 `source_mode=term_all_files`, `target=2025-2학기`였고, 런타임 코드가 `get_active_courses()`만 사용하고 있었다.

## 변경 사항

- [app/services/integrations/canvas_lms.py](/C:/Users/김민호/CD2/flowify-BE/app/services/integrations/canvas_lms.py:1)
  - `get_courses(include_completed: bool)`를 추가했다.
  - `include_completed=True`일 때 Canvas에 `enrollment_state[]=active&enrollment_state[]=completed`로 요청한다.
  - `to_file_item()`에서 `course_name`도 `_safe_filename()`으로 정리하도록 보강했다.
- [app/core/nodes/input_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/input_node.py:329)
  - `term_all_files` 실행 경로가 `get_courses(token, include_completed=True)`를 사용하도록 변경했다.

## 기대 효과

- `term_all_files` 실행 시 현재 학기뿐 아니라 완료된 학기도 런타임에서 정상 조회할 수 있다.
- picker에서 보이는 학기와 실제 실행 가능한 학기의 범위가 일치한다.

## 검증

- `ruff check app/services/integrations/canvas_lms.py app/core/nodes/input_node.py tests/test_canvas_lms.py`
- `pytest tests/test_canvas_lms.py -q`

## 비고

- 기존 `get_active_courses()`는 호환용 helper로 유지했다.
