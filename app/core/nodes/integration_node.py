"""Integration node strategy for service-backed middle nodes."""

from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.nodes.base import NodeStrategy
from app.core.nodes.google_sheets_common import (
    build_sheet_range,
    coerce_bool,
    coerce_int,
    extract_headers_and_rows,
    matches_text,
    resolve_bound_value,
    row_to_record,
)
from app.services.integrations.google_sheets import GoogleSheetsService

SUPPORTED_ACTIONS: dict[str, set[str]] = {
    "google_sheets": {"read_range", "search_text", "lookup_row_by_key"},
}


class IntegrationNodeStrategy(NodeStrategy):
    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_action = node.get("runtime_action") or {}
        service = str(runtime_action.get("service") or "").strip()
        action = str(runtime_action.get("action") or "").strip()
        config = runtime_action.get("config") or {}

        token = service_tokens.get(service, "")
        if not token:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' service token is missing.",
            )

        if service == "google_sheets":
            return await self._execute_google_sheets_action(token, action, config, input_data)

        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail=f"Unsupported integration service: {service}",
        )

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_action = node.get("runtime_action") or {}
        service = str(runtime_action.get("service") or "").strip()
        action = str(runtime_action.get("action") or "").strip()
        return action in SUPPORTED_ACTIONS.get(service, set())

    async def _execute_google_sheets_action(
        self,
        token: str,
        action: str,
        config: dict[str, Any],
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        if not spreadsheet_id:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets action requires spreadsheet_id.",
            )

        sheet_name = str(config.get("sheet_name") or "Sheet1").strip() or "Sheet1"
        range_a1 = build_sheet_range(config)
        header_row = coerce_int(config.get("header_row"), 1)
        data_start_row = coerce_int(config.get("data_start_row"), max(header_row + 1, 2))

        svc = GoogleSheetsService()
        values = await svc.read_range(token, spreadsheet_id, range_a1)
        headers, rows = extract_headers_and_rows(values, header_row, data_start_row)

        if action == "read_range":
            return self._spreadsheet_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                action=action,
                headers=headers,
                rows=rows,
            )

        if action == "search_text":
            query = resolve_bound_value(
                config,
                input_data,
                value_key="search_value",
                source_key="search_source",
                field_key="search_field",
            )
            if not query:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Google Sheets search_text requires search_value or input binding.",
                )

            match_mode = str(config.get("match_mode") or "contains").strip()
            case_sensitive = coerce_bool(config.get("case_sensitive"))
            result_limit = coerce_int(config.get("result_limit"), 20)
            search_columns = config.get("search_columns") or []
            if isinstance(search_columns, str):
                search_columns = [search_columns]

            matched_rows = []
            for row in rows:
                record = row_to_record(headers, row)
                candidate_headers = search_columns or headers
                if any(
                    matches_text(
                        record.get(header, ""),
                        query,
                        match_mode=match_mode,
                        case_sensitive=case_sensitive,
                    )
                    for header in candidate_headers
                    if header
                ):
                    matched_rows.append(row)
                if len(matched_rows) >= result_limit:
                    break

            payload = self._spreadsheet_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                action=action,
                headers=headers,
                rows=matched_rows,
            )
            payload["metadata"] = {
                **payload.get("metadata", {}),
                "query": query,
                "match_mode": match_mode,
                "result_count": len(matched_rows),
            }
            return payload

        if action == "lookup_row_by_key":
            key_column = str(config.get("key_column") or "").strip()
            if not key_column:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Google Sheets lookup_row_by_key requires key_column.",
                )
            if key_column not in headers:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail=f"Google Sheets key_column '{key_column}' is not present in headers.",
                )

            lookup_value = resolve_bound_value(
                config,
                input_data,
                value_key="lookup_value",
                source_key="lookup_source",
                field_key="lookup_field",
            )
            if not lookup_value:
                raise FlowifyException(
                    ErrorCode.INVALID_REQUEST,
                    detail="Google Sheets lookup_row_by_key requires lookup_value or input binding.",
                )

            for row in rows:
                record = row_to_record(headers, row)
                if record.get(key_column, "") == lookup_value:
                    return {
                        "type": "API_RESPONSE",
                        "data": record,
                        "metadata": {
                            "service": "google_sheets",
                            "action": action,
                            "sheet_name": sheet_name,
                            "spreadsheet_id": spreadsheet_id,
                            "matched": True,
                        },
                    }

            return {
                "type": "API_RESPONSE",
                "data": {},
                "metadata": {
                    "service": "google_sheets",
                    "action": action,
                    "sheet_name": sheet_name,
                    "spreadsheet_id": spreadsheet_id,
                    "matched": False,
                },
            }

        raise FlowifyException(
            ErrorCode.INVALID_REQUEST,
            detail=f"Unsupported Google Sheets action: {action}",
        )

    @staticmethod
    def _spreadsheet_payload(
        *,
        spreadsheet_id: str,
        sheet_name: str,
        action: str,
        headers: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        return {
            "type": "SPREADSHEET_DATA",
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": rows,
            "metadata": {
                "service": "google_sheets",
                "action": action,
                "row_count": len(rows),
            },
        }
