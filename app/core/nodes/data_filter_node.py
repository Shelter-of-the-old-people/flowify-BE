"""데이터 필터 노드 실행 전략."""

from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy

SUPPORTED_FILTER_ACTIONS = frozenset({"filter_fields", "filter_metadata"})
UNSUPPORTED_FILTER_ACTIONS = frozenset(
    {"filter_condition", "filter_type", "filter_content"}
)
LIST_PAYLOAD_TYPES = frozenset({"FILE_LIST", "EMAIL_LIST", "SCHEDULE_DATA"})

FIELD_ALIASES = {
    "sender": "from",
    "link": "url",
    "upload_time": "created_time",
    "file_size": "size",
}


class DataFilterNodeStrategy(NodeStrategy):
    """선택된 필드만 남기는 결정적 데이터 필터를 수행합니다."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        """입력 payload에서 선택 필드를 추출해 output_data_type에 맞게 반환합니다."""
        if not input_data:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="데이터 필터 노드는 입력 데이터가 필요합니다.",
                context={"node_id": node.get("id")},
            )

        runtime_config = node.get("runtime_config") or {}
        action_id = self._resolve_action_id(runtime_config)
        self._ensure_supported_action(node, action_id)

        selected_fields = self._resolve_selected_fields(runtime_config)
        if not selected_fields:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="데이터 필터에 사용할 필드 선택 정보가 없습니다.",
                context={"node_id": node.get("id"), "choice_action_id": action_id},
            )

        projected = self._project_input(input_data, selected_fields)
        output_type = self._resolve_output_type(runtime_config, input_data)
        return self._build_output(output_type, projected)

    def validate(self, node: dict[str, Any]) -> bool:
        """지원 가능한 필터 방식과 필드 선택 여부를 검증합니다."""
        runtime_config = node.get("runtime_config") or {}
        action_id = self._resolve_action_id(runtime_config)
        if action_id and action_id not in SUPPORTED_FILTER_ACTIONS:
            return False
        return bool(self._resolve_selected_fields(runtime_config))

    def _resolve_action_id(self, runtime_config: dict[str, Any]) -> str:
        """choiceActionId 설정을 조회합니다."""
        value = (
            runtime_config.get("choiceActionId")
            or runtime_config.get("choice_action_id")
            or self.config.get("choiceActionId")
            or self.config.get("choice_action_id")
            or ""
        )
        return str(value).strip()

    def _ensure_supported_action(self, node: dict[str, Any], action_id: str) -> None:
        """현재 구현 범위에서 처리 가능한 필터 방식인지 검증합니다."""
        if not action_id or action_id in SUPPORTED_FILTER_ACTIONS:
            return

        if action_id in UNSUPPORTED_FILTER_ACTIONS:
            detail = f"현재 데이터 필터 방식은 아직 지원하지 않습니다: {action_id}"
        else:
            detail = f"알 수 없는 데이터 필터 방식입니다: {action_id}"

        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail=detail,
            context={"node_id": node.get("id"), "choice_action_id": action_id},
        )

    def _resolve_selected_fields(self, runtime_config: dict[str, Any]) -> list[str]:
        """choiceSelections.follow_up 기준으로 선택 필드 목록을 조회합니다."""
        selections = (
            runtime_config.get("choiceSelections")
            or runtime_config.get("choice_selections")
            or self.config.get("choiceSelections")
            or self.config.get("choice_selections")
        )

        value = None
        if isinstance(selections, dict):
            value = (
                selections.get("follow_up")
                or selections.get("fields")
                or selections.get("selected_fields")
            )

        if value is None:
            value = runtime_config.get("selected_fields") or self.config.get("selected_fields")

        return self._to_field_list(value)

    @staticmethod
    def _to_field_list(value: Any) -> list[str]:
        """문자열 또는 목록 값을 필드 ID 목록으로 정규화합니다."""
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            fields = []
            for item in value:
                field = str(item).strip()
                if field:
                    fields.append(field)
            return fields
        return []

    def _project_input(self, input_data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """입력 payload 타입에 맞게 선택 필드 projection을 생성합니다."""
        data_type = input_data.get("type", "")

        if data_type == "SPREADSHEET_DATA":
            return self._project_spreadsheet(input_data, fields)

        if data_type in LIST_PAYLOAD_TYPES:
            return {
                "kind": "items",
                "fields": fields,
                "items": [
                    self._project_mapping(item, fields)
                    for item in input_data.get("items", [])
                    if isinstance(item, dict)
                ],
            }

        if data_type == "API_RESPONSE":
            return self._project_api_response(input_data, fields)

        return {
            "kind": "single",
            "fields": fields,
            "data": self._project_mapping(input_data, fields),
        }

    def _project_spreadsheet(
        self,
        input_data: dict[str, Any],
        fields: list[str],
    ) -> dict[str, Any]:
        """스프레드시트 payload에서 선택 컬럼만 추출합니다."""
        headers = [str(header) for header in input_data.get("headers", [])]
        missing_fields = [field for field in fields if field not in headers]
        if missing_fields:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="스프레드시트에 선택한 필드가 없습니다.",
                context={"missing_fields": missing_fields},
            )

        indices = [headers.index(field) for field in fields]
        rows = []
        for row in input_data.get("rows", []):
            rows.append([row[index] if index < len(row) else "" for index in indices])

        return {"kind": "table", "headers": fields, "rows": rows}

    def _project_api_response(
        self,
        input_data: dict[str, Any],
        fields: list[str],
    ) -> dict[str, Any]:
        """API_RESPONSE payload에서 data 또는 items 값을 기준으로 projection합니다."""
        data = input_data.get("data", {})
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return {
                "kind": "items",
                "fields": fields,
                "items": [
                    self._project_mapping(item, fields)
                    for item in data["items"]
                    if isinstance(item, dict)
                ],
            }
        if isinstance(data, list):
            return {
                "kind": "items",
                "fields": fields,
                "items": [
                    self._project_mapping(item, fields)
                    for item in data
                    if isinstance(item, dict)
                ],
            }
        if isinstance(data, dict):
            return {
                "kind": "single",
                "fields": fields,
                "data": self._project_mapping(data, fields),
            }

        return {"kind": "single", "fields": fields, "data": {}}

    def _project_mapping(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """딕셔너리 데이터에서 선택 필드만 추출합니다."""
        return {field: self._extract_field(data, field) for field in fields}

    def _extract_field(self, data: dict[str, Any], field: str) -> Any:
        """필드 ID와 alias를 기준으로 값을 추출합니다."""
        if field == "body_preview":
            return str(data.get("body", ""))[:200]

        source_key = FIELD_ALIASES.get(field, field)
        return data.get(source_key, "")

    def _resolve_output_type(
        self,
        runtime_config: dict[str, Any],
        input_data: dict[str, Any],
    ) -> str:
        """runtime_config의 출력 타입을 우선 사용합니다."""
        value = (
            runtime_config.get("output_data_type")
            or self.config.get("output_data_type")
            or input_data.get("type")
            or "API_RESPONSE"
        )
        return str(value)

    def _build_output(self, output_type: str, projected: dict[str, Any]) -> dict[str, Any]:
        """projection 결과를 요청된 canonical output type으로 변환합니다."""
        if output_type == "TEXT":
            return {"type": "TEXT", "content": self._to_text(projected)}
        if output_type == "SPREADSHEET_DATA":
            return self._to_spreadsheet(projected)
        if output_type == "API_RESPONSE":
            return self._to_api_response(projected)
        if output_type in LIST_PAYLOAD_TYPES and projected["kind"] == "items":
            return {"type": output_type, "items": projected["items"]}

        return self._to_api_response(projected)

    def _to_text(self, projected: dict[str, Any]) -> str:
        """projection 결과를 사람이 읽을 수 있는 텍스트로 변환합니다."""
        kind = projected["kind"]
        if kind == "table":
            lines = [", ".join(projected["headers"])]
            lines.extend(", ".join(str(value) for value in row) for row in projected["rows"])
            return "\n".join(lines)

        if kind == "items":
            blocks = []
            for index, item in enumerate(projected["items"], start=1):
                lines = [f"[{index}]"]
                lines.extend(f"{field}: {item.get(field, '')}" for field in projected["fields"])
                blocks.append("\n".join(lines))
            return "\n\n".join(blocks)

        return "\n".join(
            f"{field}: {projected['data'].get(field, '')}" for field in projected["fields"]
        )

    def _to_spreadsheet(self, projected: dict[str, Any]) -> dict[str, Any]:
        """projection 결과를 SPREADSHEET_DATA payload로 변환합니다."""
        kind = projected["kind"]
        if kind == "table":
            return {
                "type": "SPREADSHEET_DATA",
                "headers": projected["headers"],
                "rows": projected["rows"],
            }

        fields = projected["fields"]
        if kind == "items":
            rows = [[item.get(field, "") for field in fields] for item in projected["items"]]
        else:
            rows = [[projected["data"].get(field, "") for field in fields]]

        return {"type": "SPREADSHEET_DATA", "headers": fields, "rows": rows}

    @staticmethod
    def _to_api_response(projected: dict[str, Any]) -> dict[str, Any]:
        """projection 결과를 API_RESPONSE payload로 변환합니다."""
        kind = projected["kind"]
        if kind == "items":
            return {"type": "API_RESPONSE", "data": {"items": projected["items"]}}
        if kind == "table":
            return {
                "type": "API_RESPONSE",
                "data": {
                    "headers": projected["headers"],
                    "rows": projected["rows"],
                },
            }
        return {"type": "API_RESPONSE", "data": projected["data"]}
