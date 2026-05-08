import pytest

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.logic_node import IfElseNodeStrategy


def _file_type_runtime_config(
    branch_rules: list[dict] | None = None,
    fallback_key: str = "other",
) -> dict:
    return {
        "branch_type": "file_type",
        "branch_rules": branch_rules if branch_rules is not None else _file_type_branch_rules(),
        "fallback_branch": {"key": fallback_key, "label": "Other"},
    }


def _file_type_branch_rules() -> list[dict]:
    return [
        {
            "key": "pdf",
            "label": "PDF",
            "matcher": {
                "type": "file_type",
                "extensions": ["pdf"],
                "mime_types": ["application/pdf"],
                "mime_prefixes": [],
            },
        },
        {
            "key": "image",
            "label": "Image",
            "matcher": {
                "type": "file_type",
                "extensions": ["jpg", "jpeg", "png"],
                "mime_types": [],
                "mime_prefixes": ["image/"],
            },
        },
    ]


class TestIfElseNodeStrategy:
    @pytest.mark.asyncio
    async def test_boolean_branch_true(self):
        strategy = IfElseNodeStrategy()

        result = await strategy.execute(
            node={
                "runtime_config": {
                    "condition_field": "status",
                    "expected_value": "ready",
                }
            },
            input_data={"type": "TEXT", "status": "ready"},
            service_tokens={},
        )

        assert result["branch"] == "true"

    @pytest.mark.asyncio
    async def test_boolean_branch_false(self):
        strategy = IfElseNodeStrategy()

        result = await strategy.execute(
            node={
                "runtime_config": {
                    "condition_field": "status",
                    "expected_value": "ready",
                }
            },
            input_data={"type": "TEXT", "status": "pending"},
            service_tokens={},
        )

        assert result["branch"] == "false"

    @pytest.mark.asyncio
    async def test_file_type_branch_splits_items_by_rule(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "FILE_LIST",
            "items": [
                {"filename": "lecture.pdf", "mime_type": "application/pdf"},
                {"filename": "photo.png", "mime_type": "image/png"},
                {"filename": "memo.bin", "mime_type": "application/octet-stream"},
            ],
        }

        result = await strategy.execute(
            node={"id": "branch_1", "runtime_config": _file_type_runtime_config()},
            input_data=input_data,
            service_tokens={},
        )

        assert result["branch"] == "multi"
        assert result["branch_outputs"]["pdf"]["items"] == [input_data["items"][0]]
        assert result["branch_outputs"]["image"]["items"] == [input_data["items"][1]]
        assert result["branch_outputs"]["other"]["items"] == [input_data["items"][2]]
        assert result["branch_counts"] == {"pdf": 1, "image": 1, "other": 1}

    @pytest.mark.asyncio
    async def test_file_type_branch_accepts_other_only_selection(self):
        strategy = IfElseNodeStrategy()
        input_data = {
            "type": "FILE_LIST",
            "items": [
                {"filename": "lecture.pdf", "mime_type": "application/pdf"},
                {"filename": "photo.png", "mime_type": "image/png"},
            ],
        }

        result = await strategy.execute(
            node={
                "id": "branch_1",
                "runtime_config": _file_type_runtime_config(branch_rules=[]),
            },
            input_data=input_data,
            service_tokens={},
        )

        assert list(result["branch_outputs"].keys()) == ["other"]
        assert result["branch_outputs"]["other"]["items"] == input_data["items"]
        assert result["branch_counts"] == {"other": 2}

    @pytest.mark.asyncio
    async def test_file_type_branch_requires_file_list_input(self):
        strategy = IfElseNodeStrategy()

        with pytest.raises(FlowifyException) as exc_info:
            await strategy.execute(
                node={"id": "branch_1", "runtime_config": _file_type_runtime_config()},
                input_data={"type": "TEXT", "content": "hello"},
                service_tokens={},
            )

        assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST

    def test_file_type_branch_validate_accepts_fallback_only(self):
        strategy = IfElseNodeStrategy()

        assert strategy.validate(
            {
                "runtime_config": _file_type_runtime_config(
                    branch_rules=[],
                    fallback_key="other",
                )
            }
        )
