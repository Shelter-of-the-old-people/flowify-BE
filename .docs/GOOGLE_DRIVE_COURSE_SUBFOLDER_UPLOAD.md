# Google Drive Course Subfolder Upload

## 배경

- `Canvas LMS(term_all_files) -> Google Drive` 실행 시 Canvas 쪽 파일명은 `과목명/파일명` 형태로 만들어지고 있었다.
- 하지만 Google Drive 업로드는 이 값을 단순 파일명으로만 사용해서, 선택 폴더 아래에 과목별 하위 폴더를 만들지 못했다.

## 목표

- 사용자가 선택한 Google Drive 폴더 아래에 `과목명` 폴더를 자동으로 만들고,
- 해당 과목 파일을 그 폴더 안에 업로드한다.

## 변경 사항

- [app/services/integrations/google_drive.py](/C:/Users/김민호/CD2/flowify-BE/app/services/integrations/google_drive.py:1)
  - `ensure_folder_path()`를 추가했다.
  - 폴더가 이미 있으면 재사용하고, 없으면 Google Drive 폴더를 생성한다.
  - 내부 helper `_find_folder()`, `_create_folder()`를 추가했다.
- [app/core/nodes/output_node.py](/C:/Users/김민호/CD2/flowify-BE/app/core/nodes/output_node.py:156)
  - Google Drive 업로드 전 `filename`을 `/` 기준으로 path segment로 해석한다.
  - 예: `데이터베이스/Week01_Introduction.pdf`
    - `데이터베이스` 폴더를 선택 폴더 아래에서 찾거나 생성
    - 실제 업로드 파일명은 `Week01_Introduction.pdf`
  - `SINGLE_FILE`, `FILE_LIST` 모두 같은 path 해석을 사용한다.

## 기대 효과

- 학기 전체 다운로드 실행 시 Google Drive 결과가 `선택 폴더 / 과목명 폴더 / 파일` 구조로 정리된다.
- 같은 과목 폴더가 이미 있으면 재생성하지 않고 재사용한다.

## 검증

- `ruff check app/services/integrations/google_drive.py app/core/nodes/output_node.py tests/test_output_node.py`
- `pytest tests/test_output_node.py -q`

## 비고

- 이번 변경은 shared drive 전용 대응을 추가한 것은 아니다.
- 현재 범위는 사용자가 선택한 폴더 하위의 하위 폴더 생성/재사용까지다.
