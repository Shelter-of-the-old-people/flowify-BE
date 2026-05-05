import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.data_filter_node import DataFilterNodeStrategy


def _node(runtime_config: dict) -> dict:
    return {"id": "node_filter", "runtime_config": runtime_config}


async def test_data_filter_single_email_fields_to_text():
    strategy = DataFilterNodeStrategy()

    result = await strategy.execute(
        node=_node(
            {
                "choiceActionId": "filter_fields",
                "choiceSelections": {"follow_up": ["subject", "sender", "body_preview"]},
                "output_data_type": "TEXT",
            }
        ),
        input_data={
            "type": "SINGLE_EMAIL",
            "subject": "회의 안내",
            "from": "sender@example.com",
            "body": "본문 내용입니다.",
        },
        service_tokens={},
    )

    assert result == {
        "type": "TEXT",
        "content": "subject: 회의 안내\nsender: sender@example.com\nbody_preview: 본문 내용입니다.",
    }


async def test_data_filter_single_file_metadata_to_text():
    strategy = DataFilterNodeStrategy()

    result = await strategy.execute(
        node=_node(
            {
                "choiceActionId": "filter_metadata",
                "choiceSelections": {"follow_up": ["filename", "link", "upload_time"]},
                "output_data_type": "TEXT",
            }
        ),
        input_data={
            "type": "SINGLE_FILE",
            "filename": "report.pdf",
            "url": "https://drive.google.com/file/d/file_1",
            "created_time": "2026-05-04T12:00:00Z",
        },
        service_tokens={},
    )

    assert result["content"] == (
        "filename: report.pdf\n"
        "link: https://drive.google.com/file/d/file_1\n"
        "upload_time: 2026-05-04T12:00:00Z"
    )


async def test_data_filter_email_list_fields_to_spreadsheet():
    strategy = DataFilterNodeStrategy()

    result = await strategy.execute(
        node=_node(
            {
                "choiceActionId": "filter_fields",
                "choiceSelections": {"follow_up": ["subject", "sender"]},
                "output_data_type": "SPREADSHEET_DATA",
            }
        ),
        input_data={
            "type": "EMAIL_LIST",
            "items": [
                {"subject": "메일 1", "from": "a@example.com"},
                {"subject": "메일 2", "from": "b@example.com"},
            ],
        },
        service_tokens={},
    )

    assert result == {
        "type": "SPREADSHEET_DATA",
        "headers": ["subject", "sender"],
        "rows": [["메일 1", "a@example.com"], ["메일 2", "b@example.com"]],
    }


async def test_data_filter_spreadsheet_fields_to_spreadsheet():
    strategy = DataFilterNodeStrategy()

    result = await strategy.execute(
        node=_node(
            {
                "choiceActionId": "filter_fields",
                "choiceSelections": {"follow_up": ["name", "score"]},
                "output_data_type": "SPREADSHEET_DATA",
            }
        ),
        input_data={
            "type": "SPREADSHEET_DATA",
            "headers": ["name", "score", "memo"],
            "rows": [["홍길동", 95, "A"], ["김철수", 88, "B"]],
        },
        service_tokens={},
    )

    assert result == {
        "type": "SPREADSHEET_DATA",
        "headers": ["name", "score"],
        "rows": [["홍길동", 95], ["김철수", 88]],
    }


async def test_data_filter_api_response_fields_to_spreadsheet():
    strategy = DataFilterNodeStrategy()

    result = await strategy.execute(
        node=_node(
            {
                "choiceActionId": "filter_fields",
                "choiceSelections": {"follow_up": ["title", "url"]},
                "output_data_type": "SPREADSHEET_DATA",
            }
        ),
        input_data={
            "type": "API_RESPONSE",
            "data": {
                "items": [
                    {"title": "뉴스 1", "url": "https://example.com/1", "body": "본문"},
                    {"title": "뉴스 2", "url": "https://example.com/2", "body": "본문"},
                ]
            },
        },
        service_tokens={},
    )

    assert result == {
        "type": "SPREADSHEET_DATA",
        "headers": ["title", "url"],
        "rows": [
            ["뉴스 1", "https://example.com/1"],
            ["뉴스 2", "https://example.com/2"],
        ],
    }


async def test_data_filter_unsupported_action_raises_invalid_request():
    strategy = DataFilterNodeStrategy()

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            node=_node(
                {
                    "choiceActionId": "filter_condition",
                    "choiceSelections": {"follow_up": ["score"]},
                    "output_data_type": "SPREADSHEET_DATA",
                }
            ),
            input_data={"type": "SPREADSHEET_DATA", "headers": ["score"], "rows": [[90]]},
            service_tokens={},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.context["choice_action_id"] == "filter_condition"


async def test_data_filter_without_selected_fields_raises_invalid_request():
    strategy = DataFilterNodeStrategy()

    with pytest.raises(FlowifyException) as exc_info:
        await strategy.execute(
            node=_node({"choiceActionId": "filter_fields", "output_data_type": "TEXT"}),
            input_data={"type": "SINGLE_EMAIL", "subject": "제목"},
            service_tokens={},
        )

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST


def test_data_filter_validate_checks_action_and_fields():
    strategy = DataFilterNodeStrategy()

    assert (
        strategy.validate(
            _node(
                {
                    "choiceActionId": "filter_fields",
                    "choiceSelections": {"follow_up": ["subject"]},
                }
            )
        )
        is True
    )
    assert (
        strategy.validate(
            _node(
                {
                    "choiceActionId": "filter_condition",
                    "choiceSelections": {"follow_up": ["subject"]},
                }
            )
        )
        is False
    )
    assert strategy.validate(_node({"choiceActionId": "filter_fields"})) is False
