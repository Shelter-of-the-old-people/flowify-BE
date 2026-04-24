"""LoopNodeStrategy v2 테스트.

v2 시그니처: execute(node: dict, input_data: dict | None, service_tokens: dict) -> dict
canonical payload 타입별 items 추출 (FILE_LIST→items, SPREADSHEET_DATA→rows).
conftest.py의 service_tokens fixture 사용 가능.
"""


# TODO: test_file_list_iteration
# TODO: test_spreadsheet_rows_iteration
# TODO: test_max_iterations_limit
# TODO: test_empty_input_returns_zero_iterations
# TODO: test_transform_field_extracts_values
# TODO: test_validate
