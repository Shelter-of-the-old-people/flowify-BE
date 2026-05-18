"""Input node strategy for runtime source collection.

Reads ``runtime_source`` metadata from a workflow node, fetches data from the
matching external service, and returns a canonical payload that matches the
declared input type.
"""

from datetime import UTC, datetime
import logging
from typing import Any

from app.common.errors import ErrorCode, FlowifyException
from app.core.document_content import ensure_file_content_fields
from app.core.nodes.base import NodeStrategy
from app.core.nodes.google_sheets_common import (
    build_sheet_range,
    coerce_int,
    extract_headers_and_rows,
    hash_record,
    row_to_record,
)
from app.services.integrations.canvas_lms import CanvasLmsService
from app.services.integrations.github import GitHubService
from app.services.integrations.gmail import GmailService
from app.services.integrations.google_drive import GoogleDriveService
from app.services.integrations.google_sheets import GoogleSheetsService
from app.services.integrations.naver_news import NaverNewsService
from app.services.integrations.web_news import WebNewsService

logger = logging.getLogger(__name__)

# Phase 1 supported source modes only.
SUPPORTED_SOURCES: dict[str, set[str]] = {
    "google_drive": {
        "single_file",
        "file_changed",
        "new_file",
        "folder_new_file",
        "folder_all_files",
    },
    "gmail": {
        "single_email",
        "new_email",
        "sender_email",
        "starred_email",
        "label_emails",
        "attachment_email",
    },
    "google_sheets": {"sheet_all", "new_row", "row_updated"},
    "canvas_lms": {"course_files", "course_new_file", "term_all_files"},
    "github": {"new_pr"},
    "naver_news": {"article_search", "new_articles"},
    "web_news": {"seboard_posts", "seboard_new_posts", "website_feed"},
}

TOKENLESS_SOURCES = frozenset({"web_crawl", "web_news", "naver_news"})


class InputNodeStrategy(NodeStrategy):
    """Fetch external source data and normalize it into canonical payloads."""

    async def execute(
        self,
        node: dict[str, Any],
        input_data: dict[str, Any] | None,
        service_tokens: dict[str, str],
    ) -> dict[str, Any]:
        runtime_source = node.get("runtime_source")
        if not runtime_source:
            # Transitional fallback for older config-based nodes.
            return {"type": "TEXT", "content": self.config.get("data", "")}

        service = runtime_source["service"]
        mode = runtime_source["mode"]
        target = runtime_source.get("target", "")
        canonical_type = runtime_source.get("canonical_input_type", "TEXT")
        runtime_source_config = runtime_source.get("config") or {}
        runtime_source_state = runtime_source.get("state") or {}
        config = node.get("config") or {}

        supported_modes = SUPPORTED_SOURCES.get(service)
        if supported_modes is None or mode not in supported_modes:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service={service}, mode={mode} is not supported in current runtime phase",
            )

        token = service_tokens.get(service, "")
        if not token and service not in TOKENLESS_SOURCES:
            raise FlowifyException(
                ErrorCode.OAUTH_TOKEN_INVALID,
                detail=f"'{service}' ?쒕퉬?ㅼ쓽 ?좏겙???놁뒿?덈떎.",
            )

        if service == "google_drive":
            return await self._fetch_google_drive(token, mode, target, canonical_type)
        if service == "gmail":
            return await self._fetch_gmail(
                token,
                mode,
                target,
                canonical_type,
                self._resolve_max_results(config),
            )
        if service == "google_sheets":
            return await self._fetch_google_sheets(
                token,
                mode,
                target,
                canonical_type,
                runtime_source_config or config,
                runtime_source_state,
            )
        if service == "canvas_lms":
            return await self._fetch_canvas_lms(token, mode, target)
        if service == "github":
            return await self._fetch_github(
                token,
                mode,
                target,
                runtime_source_state,
            )
        if service == "naver_news":
            return await self._fetch_naver_news(mode, target, config)
        if service == "web_news":
            return await self._fetch_web_news(
                mode,
                target,
                {**runtime_source_config, **config},
            )

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service={service}, mode={mode} is not supported in current runtime phase",
        )

    def validate(self, node: dict[str, Any]) -> bool:
        runtime_source = node.get("runtime_source")
        if not runtime_source:
            return False

        service = runtime_source.get("service", "")
        mode = runtime_source.get("mode", "")
        supported_modes = SUPPORTED_SOURCES.get(service)
        if supported_modes is None:
            return False
        return mode in supported_modes

    # Google Drive

    async def _fetch_google_drive(
        self, token: str, mode: str, target: str, canonical_type: str
    ) -> dict[str, Any]:
        svc = GoogleDriveService()

        if mode == "single_file":
            metadata = await svc.get_file_metadata(token, target)
            return self._to_drive_single_file(metadata, target)

        if mode in ("file_changed", "new_file", "folder_new_file"):
            files = await svc.list_files(
                token,
                folder_id=target,
                max_results=1,
                order_by="createdTime desc",
                include_folders=False,
            )
            if not files:
                return ensure_file_content_fields({
                    "type": "SINGLE_FILE",
                    "source_service": "google_drive",
                    "file_id": "",
                    "filename": "",
                    "mime_type": "",
                    "size": None,
                    "url": "",
                    "created_time": "",
                    "modified_time": "",
                })

            latest_file = files[0]
            return self._to_drive_single_file(latest_file)

        if mode == "folder_all_files":
            files = await svc.list_files(token, folder_id=target, include_folders=False)
            return {
                "type": "FILE_LIST",
                "items": [self._to_drive_file_item(drive_file) for drive_file in files],
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_drive, mode={mode} is not supported",
        )

    @staticmethod
    def _to_drive_single_file(
        file_data: dict[str, Any], fallback_file_id: str = ""
    ) -> dict[str, Any]:
        file_id = file_data.get("id") or fallback_file_id
        return ensure_file_content_fields({
            "type": "SINGLE_FILE",
            "source_service": "google_drive",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        })

    @staticmethod
    def _to_drive_file_item(file_data: dict[str, Any]) -> dict[str, Any]:
        file_id = file_data.get("id", "")
        return ensure_file_content_fields({
            "source_service": "google_drive",
            "file_id": file_id,
            "filename": file_data.get("name", ""),
            "mime_type": file_data.get("mimeType", ""),
            "size": file_data.get("size"),
            "created_time": file_data.get("createdTime", ""),
            "modified_time": file_data.get("modifiedTime", ""),
            "url": file_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}",
        })

    # Gmail

    async def _fetch_gmail(
        self,
        token: str,
        mode: str,
        target: str,
        canonical_type: str,
        max_results: int,
    ) -> dict[str, Any]:
        svc = GmailService()

        if mode == "single_email":
            msg = await svc.get_message(token, target)
            return self._to_single_email(msg)

        if mode == "new_email":
            msgs = await svc.list_messages(token, query="", max_results=1)
            if not msgs:
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "sender_email":
            msgs = await svc.list_messages(token, query=f"from:{target}", max_results=1)
            if not msgs:
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "starred_email":
            msgs = await svc.list_messages(token, query="is:starred", max_results=1)
            if not msgs:
                return self._empty_single_email()
            return self._to_single_email(msgs[0])

        if mode == "label_emails":
            msgs = await svc.list_messages(
                token,
                query=f"label:{target}",
                max_results=max_results,
            )
            emails = [self._to_email_item(msg) for msg in msgs]
            return {
                "type": "EMAIL_LIST",
                "emails": emails,
                "items": emails,
                "metadata": {
                    "count": len(emails),
                    "truncated": len(emails) >= max_results,
                    "sourceMode": mode,
                },
            }

        if mode == "attachment_email":
            msgs = await svc.list_messages(token, query="has:attachment", max_results=1)
            files = []
            for msg in msgs:
                files.extend(self._to_file_items(msg.get("attachments", [])))
            return {
                "type": "FILE_LIST",
                "files": files,
                "items": files,
                "metadata": {
                    "count": len(files),
                    "truncated": False,
                },
            }

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=gmail, mode={mode} is not supported",
        )

    @staticmethod
    def _resolve_max_results(config: dict[str, Any]) -> int:
        raw_value = config.get("maxResults")
        if raw_value in (None, ""):
            return 20

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid maxResults value for Gmail source: %s", raw_value)
            return 20

        return max(1, value)

    @staticmethod
    def _to_single_email(msg: dict) -> dict[str, Any]:
        email = InputNodeStrategy._to_email_detail(msg, include_body=True)
        return {
            "type": "SINGLE_EMAIL",
            "email": email,
            "id": email["id"],
            "threadId": email["threadId"],
            "subject": email["subject"],
            "from": email["from"],
            "sender": email["sender"],
            "to": email["to"],
            "date": email["date"],
            "body": email["body"],
            "bodyPreview": email["bodyPreview"],
            "labels": email["labels"],
            "attachments": email["attachments"],
        }

    @staticmethod
    def _empty_single_email() -> dict[str, Any]:
        return InputNodeStrategy._to_single_email({})

    @staticmethod
    def _to_email_item(msg: dict[str, Any]) -> dict[str, Any]:
        return InputNodeStrategy._to_email_detail(msg, include_body=False)

    @staticmethod
    def _to_email_detail(msg: dict[str, Any], include_body: bool) -> dict[str, Any]:
        from_value = msg.get("from", "")
        body = msg.get("body", "") if include_body else ""
        return {
            "id": msg.get("id", ""),
            "threadId": msg.get("threadId", ""),
            "subject": msg.get("subject", ""),
            "from": from_value,
            "sender": msg.get("sender", from_value),
            "to": InputNodeStrategy._normalize_email_recipients(msg.get("to", [])),
            "date": msg.get("date", ""),
            "body": body,
            "bodyPreview": msg.get("bodyPreview")
            or msg.get("snippet")
            or msg.get("body", "")[:200],
            "labels": msg.get("labels", msg.get("labelIds", [])),
            "attachments": InputNodeStrategy._to_file_items(msg.get("attachments", [])),
        }

    @staticmethod
    def _normalize_email_recipients(raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return [str(value) for value in raw_value if value]
        if raw_value:
            return [str(raw_value)]
        return []

    @staticmethod
    def _to_file_items(attachments: list[dict]) -> list[dict[str, Any]]:
        items = []
        for attachment in attachments:
            item = {
                "id": attachment.get("id", ""),
                "name": attachment.get("name", attachment.get("filename", "")),
                "filename": attachment.get("filename", ""),
                "mimeType": attachment.get("mimeType", attachment.get("mime_type", "")),
                "mime_type": attachment.get("mime_type", attachment.get("mimeType", "")),
                "size": attachment.get("size"),
                "source": attachment.get("source", "gmail"),
                "source_service": attachment.get("source_service", attachment.get("source", "gmail")),
                "messageId": attachment.get("messageId", ""),
                "message_id": attachment.get("message_id", attachment.get("messageId", "")),
                "attachmentId": attachment.get("attachmentId", ""),
                "attachment_id": attachment.get("attachment_id", attachment.get("attachmentId", "")),
                "inline": attachment.get("inline", False),
                "content": attachment.get("content"),
                "downloadUrl": attachment.get("downloadUrl"),
                "url": attachment.get("url", ""),
            }
            items.append(ensure_file_content_fields(item))
        return items

    # Google Sheets

    async def _fetch_google_sheets(
        self,
        token: str,
        mode: str,
        target: str,
        canonical_type: str,
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        svc = GoogleSheetsService()
        spreadsheet_id = str(config.get("spreadsheet_id") or target or "").strip()
        if not spreadsheet_id:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets source requires spreadsheet_id.",
            )

        sheet_name = str(config.get("sheet_name") or "Sheet1").strip() or "Sheet1"
        range_a1 = build_sheet_range(config)
        header_row = coerce_int(config.get("header_row"), 1)
        data_start_row = coerce_int(config.get("data_start_row"), max(header_row + 1, 2))

        values = await svc.read_range(token, spreadsheet_id, range_a1)
        headers, rows = extract_headers_and_rows(values, header_row, data_start_row)

        if mode == "sheet_all":
            return self._build_google_sheets_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                mode=mode,
                headers=headers,
                rows=rows,
                metadata={"row_count": len(rows)},
            )

        if mode == "new_row":
            return self._build_google_sheets_new_row_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                rows=rows,
                config=config,
                state=state,
            )

        if mode == "row_updated":
            return self._build_google_sheets_row_updated_payload(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                rows=rows,
                config=config,
                state=state,
            )

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=google_sheets, mode={mode} is not supported",
        )

    def _build_google_sheets_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        mode: str,
        headers: list[str],
        rows: list[list[Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "SPREADSHEET_DATA",
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": rows,
            "metadata": {"mode": mode, **(metadata or {})},
        }

    def _build_google_sheets_new_row_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
        rows: list[list[Any]],
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        initial_sync_mode = str(config.get("initial_sync_mode") or "skip_existing").strip()
        prior_last_seen = state.get("last_seen_row_index")
        current_last_seen = len(rows)

        if prior_last_seen in (None, ""):
            emitted_rows = rows if initial_sync_mode == "emit_existing" else []
        else:
            try:
                emitted_rows = rows[int(prior_last_seen) :]
            except (TypeError, ValueError):
                emitted_rows = rows

        payload = self._build_google_sheets_payload(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            mode="new_row",
            headers=headers,
            rows=emitted_rows,
            metadata={
                "row_count": len(emitted_rows),
                "total_rows": len(rows),
                "initial_sync_mode": initial_sync_mode,
            },
        )
        payload["node_state_update"] = {
            "service": "google_sheets",
            "state": {"last_seen_row_index": current_last_seen},
        }
        return payload

    def _build_google_sheets_row_updated_payload(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
        rows: list[list[Any]],
        config: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        key_column = str(config.get("key_column") or "").strip()
        if not key_column:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail="Google Sheets row_updated requires key_column.",
            )
        if key_column not in headers:
            raise FlowifyException(
                ErrorCode.INVALID_REQUEST,
                detail=f"Google Sheets key_column '{key_column}' is not present in headers.",
            )

        initial_sync_mode = str(config.get("initial_sync_mode") or "skip_existing").strip()
        previous_snapshot = state.get("row_snapshot") if isinstance(state, dict) else {}
        previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}

        current_snapshot: dict[str, str] = {}
        changed_rows: list[list[Any]] = []
        changed_keys: list[str] = []

        for row in rows:
            record = row_to_record(headers, row)
            row_key = record.get(key_column, "")
            if not row_key:
                continue

            row_hash = hash_record(record)
            current_snapshot[row_key] = row_hash

            if not previous_snapshot:
                if initial_sync_mode == "emit_existing":
                    changed_rows.append(row)
                    changed_keys.append(row_key)
                continue

            if previous_snapshot.get(row_key) != row_hash:
                changed_rows.append(row)
                changed_keys.append(row_key)

        payload = self._build_google_sheets_payload(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            mode="row_updated",
            headers=headers,
            rows=changed_rows,
            metadata={
                "row_count": len(changed_rows),
                "changed_keys": changed_keys,
                "initial_sync_mode": initial_sync_mode,
            },
        )
        payload["node_state_update"] = {
            "service": "google_sheets",
            "state": {
                "last_seen_row_index": len(rows),
                "row_snapshot": current_snapshot,
            },
        }
        return payload

    # GitHub

    async def _fetch_github(
        self,
        token: str,
        mode: str,
        target: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if mode != "new_pr":
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service=github, mode={mode} is not supported",
            )

        owner, repo = GitHubService.parse_repository_target(target)
        repository = f"{owner}/{repo}"
        svc = GitHubService()
        pull_requests = await svc.list_open_pull_requests(token, owner, repo)

        if not state:
            return self._build_github_skip_payload(
                repository=repository,
                owner=owner,
                repo=repo,
                pull_requests=pull_requests,
                status="initialized",
                next_state=self._build_github_bootstrap_state(pull_requests),
            )

        last_seen_created_at = self._to_github_cursor_datetime(
            state.get("last_seen_pr_created_at")
        )
        last_seen_pr_number = self._coerce_github_pr_number(
            state.get("last_seen_pr_number")
        )
        selected_pr = self._select_next_unseen_pr(
            pull_requests,
            last_seen_created_at=last_seen_created_at,
            last_seen_pr_number=last_seen_pr_number,
        )

        if selected_pr is None:
            return self._build_github_skip_payload(
                repository=repository,
                owner=owner,
                repo=repo,
                pull_requests=pull_requests,
                status="no_new_items",
                next_state={
                    "last_seen_pr_created_at": state.get("last_seen_pr_created_at"),
                    "last_seen_pr_number": last_seen_pr_number,
                },
            )

        pr_number = int(selected_pr.get("number") or 0)
        pr_detail = await svc.get_pull_request(token, owner, repo, pr_number)
        changed_files, changed_files_truncated = await svc.list_pull_request_files(
            token,
            owner,
            repo,
            pr_number,
            limit=50,
        )
        pr_payload = self._build_github_pr_payload(
            repository=repository,
            owner=owner,
            repo=repo,
            pr_detail=pr_detail,
            changed_files=changed_files,
            changed_files_truncated=changed_files_truncated,
            checked_count=len(pull_requests),
        )
        pr_payload["node_state_update"] = {
            "service": "github",
            "state": {
                "last_seen_pr_created_at": pr_payload["created_at"],
                "last_seen_pr_number": pr_payload["pr_number"],
            },
        }
        return pr_payload

    def _build_github_skip_payload(
        self,
        *,
        repository: str,
        owner: str,
        repo: str,
        pull_requests: list[dict[str, Any]],
        status: str,
        next_state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "API_RESPONSE",
            "source_service": "github",
            "event": "new_pr",
            "repository": repository,
            "repository_owner": owner,
            "repository_name": repo,
            "items": [],
            "pr": None,
            "metadata": {
                "mode": "new_pr",
                "freshness": {
                    "status": status,
                    "checked_count": len(pull_requests),
                    "new_count": 0,
                },
            },
            "node_state_update": {
                "service": "github",
                "state": next_state,
            },
            "execution_control": {
                "skip_descendants": True,
            },
        }

    def _build_github_pr_payload(
        self,
        *,
        repository: str,
        owner: str,
        repo: str,
        pr_detail: dict[str, Any],
        changed_files: list[dict[str, Any]],
        changed_files_truncated: bool,
        checked_count: int,
    ) -> dict[str, Any]:
        pr_payload = {
            "repository": repository,
            "repository_owner": owner,
            "repository_name": repo,
            "pr_number": int(pr_detail.get("number") or 0),
            "title": pr_detail.get("title") or "",
            "body": pr_detail.get("body") or "",
            "author": (pr_detail.get("user") or {}).get("login") or "",
            "url": pr_detail.get("html_url") or "",
            "state": pr_detail.get("state") or "",
            "draft": bool(pr_detail.get("draft")),
            "created_at": pr_detail.get("created_at") or "",
            "updated_at": pr_detail.get("updated_at") or "",
            "base_branch": ((pr_detail.get("base") or {}).get("ref")) or "",
            "head_branch": ((pr_detail.get("head") or {}).get("ref")) or "",
            "requested_reviewers": [
                reviewer.get("login")
                for reviewer in (pr_detail.get("requested_reviewers") or [])
                if isinstance(reviewer, dict) and reviewer.get("login")
            ],
            "labels": [
                label.get("name")
                for label in (pr_detail.get("labels") or [])
                if isinstance(label, dict) and label.get("name")
            ],
            "changed_files_count": int(
                pr_detail.get("changed_files") or len(changed_files)
            ),
            "changed_files_truncated": changed_files_truncated,
            "changed_files": changed_files,
        }
        return {
            "type": "API_RESPONSE",
            "source_service": "github",
            "event": "new_pr",
            **pr_payload,
            "pr": pr_payload,
            "items": [pr_payload],
            "metadata": {
                "mode": "new_pr",
                "freshness": {
                    "status": "new_items",
                    "checked_count": checked_count,
                    "new_count": 1,
                },
            },
        }

    def _build_github_bootstrap_state(
        self,
        pull_requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not pull_requests:
            return {
                "last_seen_pr_created_at": self._format_github_cursor_datetime(
                    datetime.now(UTC)
                ),
                "last_seen_pr_number": 0,
            }

        latest_pr = max(
            pull_requests,
            key=lambda pr: (
                self._to_github_cursor_datetime(pr.get("created_at")),
                self._coerce_github_pr_number(pr.get("number")),
            ),
        )
        return {
            "last_seen_pr_created_at": latest_pr.get("created_at") or "",
            "last_seen_pr_number": self._coerce_github_pr_number(
                latest_pr.get("number")
            ),
        }

    def _select_next_unseen_pr(
        self,
        pull_requests: list[dict[str, Any]],
        *,
        last_seen_created_at: datetime,
        last_seen_pr_number: int,
    ) -> dict[str, Any] | None:
        sorted_pull_requests = sorted(
            pull_requests,
            key=lambda pr: (
                self._to_github_cursor_datetime(pr.get("created_at")),
                self._coerce_github_pr_number(pr.get("number")),
            ),
        )

        for pull_request in sorted_pull_requests:
            created_at = self._to_github_cursor_datetime(
                pull_request.get("created_at")
            )
            pr_number = self._coerce_github_pr_number(pull_request.get("number"))
            if (created_at, pr_number) > (last_seen_created_at, last_seen_pr_number):
                return pull_request

        return None

    @staticmethod
    def _to_github_cursor_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, str) and value.strip():
            normalized = value.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).astimezone(UTC)
            except ValueError:
                logger.warning("Invalid GitHub cursor datetime value: %s", value)
        return datetime.min.replace(tzinfo=UTC)

    @staticmethod
    def _format_github_cursor_datetime(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _coerce_github_pr_number(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0    # Canvas LMS

    async def _fetch_canvas_lms(self, token: str, mode: str, target: str) -> dict[str, Any]:
        svc = CanvasLmsService()

        if mode == "course_files":
            files = await svc.get_course_files(token, target)
            return {
                "type": "FILE_LIST",
                "items": [svc.to_file_item(file_item) for file_item in files],
            }

        if mode == "course_new_file":
            latest_file = await svc.get_course_latest_file(token, target)
            if not latest_file:
                return {
                    "type": "SINGLE_FILE",
                    "filename": "",
                    "content": None,
                    "mime_type": "",
                    "url": "",
                }
            return {
                "type": "SINGLE_FILE",
                "filename": latest_file.get("display_name", latest_file.get("filename", "")),
                "content": None,
                "mime_type": latest_file.get("content-type", "application/octet-stream"),
                "url": latest_file.get("url", ""),
            }

        if mode == "term_all_files":
            courses = await svc.get_courses(token, include_completed=True)
            matching = [
                course
                for course in courses
                if course.get("term", {}).get("name") == target and course.get("name")
            ]
            if not matching:
                raise FlowifyException(
                    ErrorCode.NODE_EXECUTION_FAILED,
                    detail=f"?숆린 '{target}'???대떦?섎뒗 怨쇰ぉ???놁뒿?덈떎.",
                )

            all_items: list[dict] = []
            for course in matching:
                try:
                    files = await svc.get_course_files(token, str(course["id"]))
                    all_items.extend(
                        svc.to_file_item(file_item, course_name=course["name"])
                        for file_item in files
                    )
                except Exception as e:
                    logger.warning(
                        "Canvas LMS 怨쇰ぉ '%s' ?뚯씪 議고쉶 ?ㅽ뙣: %s",
                        course.get("name"),
                        e,
                    )
                    continue
            return {"type": "FILE_LIST", "items": all_items}

        raise FlowifyException(
            ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
            detail=f"service=canvas_lms, mode={mode} is not supported",
        )

    # Web news

    async def _fetch_naver_news(
        self,
        mode: str,
        target: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if mode not in {"article_search", "new_articles"}:
            raise FlowifyException(
                ErrorCode.UNSUPPORTED_RUNTIME_SOURCE,
                detail=f"service=naver_news, mode={mode} is not supported",
            )

        svc = NaverNewsService()
        return await svc.search_articles(
            target,
            limit=self._resolve_article_limit(config),
        )

    async def _fetch_web_news(
        self,
        mode: str,
        target: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        svc = WebNewsService()
        fetch_mode = "seboard_posts" if mode == "seboard_new_posts" else mode
        include_content = bool(config.get("includeContent") or config.get("include_content"))
        keyword = self._source_keyword(config)
        if fetch_mode == "website_feed":
            targets = self._resolve_web_news_targets(target, config)
            if len(targets) > 1:
                return await svc.fetch_articles_from_sources(
                    fetch_mode,
                    targets,
                    limit=self._resolve_article_limit(config),
                    include_content=include_content,
                    keyword=keyword,
                )

        return await svc.fetch_articles(
            fetch_mode,
            target,
            limit=self._resolve_article_limit(config),
            include_content=include_content,
            keyword=keyword,
        )

    @staticmethod
    def _resolve_web_news_targets(target: str, config: dict[str, Any]) -> list[str]:
        raw_targets = config.get("targets")
        targets = []
        if isinstance(raw_targets, list):
            targets = [
                str(value).strip()
                for value in raw_targets
                if str(value).strip()
            ]

        if not targets and target:
            targets = [target.strip()]

        return list(dict.fromkeys(targets))

    @staticmethod
    def _source_keyword(config: dict[str, Any]) -> str | None:
        value = config.get("keyword")
        if not isinstance(value, str):
            return None

        keyword = value.strip()
        return keyword or None

    @staticmethod
    def _resolve_article_limit(config: dict[str, Any]) -> int:
        raw_value = config.get("maxResults", config.get("limit"))
        if raw_value in (None, ""):
            return 10

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid article limit value for web_news source: %s", raw_value)
            return 10

