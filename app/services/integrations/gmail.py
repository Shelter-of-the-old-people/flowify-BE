import base64
from email.header import Header, decode_header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parsedate_to_datetime
import logging

from app.common.errors import FlowifyException
from app.config import settings
from app.core.document_content import (
    CONTENT_STATUS_FAILED,
    CONTENT_STATUS_TOO_LARGE,
    CONTENT_STATUS_UNSUPPORTED,
    MAX_DOWNLOAD_BYTES,
    build_extraction_result,
    default_file_content_fields,
)
from app.services.integrations.base import BaseIntegrationService

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
logger = logging.getLogger(__name__)


class GmailService(BaseIntegrationService):
    """Gmail API integration service."""

    async def list_messages(self, token: str, query: str = "", max_results: int = 20) -> list[dict]:
        """Return message details for a Gmail search/list query."""
        params = {"maxResults": max_results}
        if query:
            params["q"] = query

        data = await self._request("GET", f"{GMAIL_API}/messages", token, params=params)
        messages = data.get("messages", [])

        results = []
        for msg in messages:
            detail = await self.get_message(token, msg["id"])
            results.append(detail)
        return results

    async def get_message(self, token: str, message_id: str) -> dict:
        """Return one Gmail message with canonical-friendly fields."""
        data = await self._request(
            "GET",
            f"{GMAIL_API}/messages/{message_id}",
            token,
            params={"format": "full"},
        )

        payload = data.get("payload", {})
        headers = {
            str(h.get("name", "")).lower(): h.get("value", "") for h in payload.get("headers", [])
        }
        body = self._extract_body(payload)
        message_id = data.get("id", "")
        subject = self._decode_header_value(headers.get("subject", ""))
        from_header = self._decode_header_value(headers.get("from", ""))
        to_header = self._decode_header_value(headers.get("to", ""))

        return {
            "id": message_id,
            "threadId": data.get("threadId", ""),
            "subject": subject,
            "from": from_header,
            "sender": from_header,
            "to": self._parse_address_list(to_header),
            "date": self._normalize_date(headers.get("date", "")),
            "body": body,
            "bodyPreview": data.get("snippet") or body[:200],
            "labels": data.get("labelIds", []),
            "attachments": self._extract_attachments(payload, message_id),
            "snippet": data.get("snippet", ""),
        }

    async def download_attachment_bytes(
        self,
        token: str,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """Download and decode Gmail attachment bytes."""
        data = await self._request(
            "GET",
            f"{GMAIL_API}/messages/{message_id}/attachments/{attachment_id}",
            token,
        )
        encoded = str(data.get("data") or "")
        if not encoded:
            return b""
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))

    async def extract_attachment_text(
        self,
        token: str,
        *,
        message_id: str,
        attachment_id: str,
        mime_type: str,
        filename: str = "",
        file_size: int | str | None = None,
        inline: bool = False,
        extraction_action: str | None = None,
    ) -> dict:
        """Download a Gmail attachment and run it through the common file extractor."""
        metadata = {
            "source_service": "gmail",
            "message_id": message_id,
            "attachment_id": attachment_id,
            "inline": inline,
        }
        if inline:
            return build_extraction_result(
                content_status=CONTENT_STATUS_UNSUPPORTED,
                content_error="Gmail inline image는 첨부 본문 추출 대상이 아닙니다.",
                metadata=metadata,
            )
        if not settings.ENABLE_GMAIL_ATTACHMENT_EXTRACTION:
            return build_extraction_result(
                content_status=CONTENT_STATUS_UNSUPPORTED,
                content_error="Gmail 첨부파일 본문 추출이 비활성화되어 있습니다.",
                metadata=metadata,
            )
        if not attachment_id:
            return build_extraction_result(
                content_status=CONTENT_STATUS_UNSUPPORTED,
                content_error="Gmail attachment id가 없어 본문을 다운로드할 수 없습니다.",
                metadata=metadata,
            )
        if self._is_size_over_download_limit(file_size):
            return build_extraction_result(
                content_status=CONTENT_STATUS_TOO_LARGE,
                content_error="파일이 현재 처리 가능한 크기를 초과했습니다.",
                limits={"observed_size_bytes": self._coerce_size(file_size)},
                metadata=metadata,
            )

        try:
            raw = await self.download_attachment_bytes(token, message_id, attachment_id)
        except FlowifyException:
            raise
        except Exception as e:
            return build_extraction_result(
                content_status=CONTENT_STATUS_FAILED,
                content_error=str(e),
                metadata=metadata,
            )
        from app.services.integrations.google_drive import GoogleDriveService

        return await GoogleDriveService.extract_file_text_from_bytes(
            raw,
            mime_type,
            filename=filename,
            file_size=file_size,
            extraction_action=extraction_action,
            metadata=metadata,
        )

    async def send_message(
        self,
        token: str,
        to: str,
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
        preferred_display_name: str = "",
    ) -> dict:
        """Send a Gmail message."""
        sender_email, sender_display_name = await self._get_sender_identity(
            token, preferred_display_name
        )
        raw = self._build_raw_message(
            to,
            subject,
            body,
            attachments,
            from_address=sender_email,
            from_display_name=sender_display_name,
        )

        return await self._request(
            "POST",
            f"{GMAIL_API}/messages/send",
            token,
            json={"raw": raw},
        )

    async def create_draft(
        self,
        token: str,
        to: str,
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
        preferred_display_name: str = "",
    ) -> dict:
        """Create a Gmail draft."""
        sender_email, sender_display_name = await self._get_sender_identity(
            token, preferred_display_name
        )
        raw = self._build_raw_message(
            to,
            subject,
            body,
            attachments,
            from_address=sender_email,
            from_display_name=sender_display_name,
        )

        return await self._request(
            "POST",
            f"{GMAIL_API}/drafts",
            token,
            json={"message": {"raw": raw}},
        )

    async def _get_sender_email(self, token: str) -> str:
        """Return the authenticated Gmail address for stable From headers."""
        profile = await self._request("GET", f"{GMAIL_API}/profile", token)
        return str(profile.get("emailAddress", "")).strip()

    async def _get_sender_identity(
        self, token: str, preferred_display_name: str = ""
    ) -> tuple[str, str]:
        """Return the authenticated sender email and preferred display name."""
        try:
            send_as_data = await self._request("GET", f"{GMAIL_API}/settings/sendAs", token)
        except Exception as exc:
            logger.warning("Falling back to bare Gmail sender email because sendAs lookup failed: %s", exc)
            return await self._get_sender_email(token), self._normalize_display_name(
                preferred_display_name
            )

        send_as_list = send_as_data.get("sendAs", [])
        if not isinstance(send_as_list, list) or not send_as_list:
            logger.info("Falling back to bare Gmail sender email because sendAs list is empty")
            return await self._get_sender_email(token), self._normalize_display_name(
                preferred_display_name
            )

        chosen = next((item for item in send_as_list if item.get("isPrimary")), None)
        if chosen is None:
            chosen = next((item for item in send_as_list if item.get("isDefault")), None)
        if chosen is None:
            chosen = send_as_list[0]

        email_address = str(chosen.get("sendAsEmail") or "").strip()
        if not email_address:
            logger.info("Falling back to profile email because chosen sendAs entry has no email")
            email_address = await self._get_sender_email(token)
        display_name = self._normalize_display_name(preferred_display_name)
        if not display_name:
            display_name = self._decode_header_value(str(chosen.get("displayName") or "").strip())
        if not display_name:
            logger.info("Using bare Gmail sender email because chosen sendAs entry has no displayName")
        return email_address, display_name

    @staticmethod
    def _build_raw_message(
        to: str,
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
        *,
        from_address: str = "",
        from_display_name: str = "",
    ) -> str:
        """Build a Gmail API raw MIME payload."""
        message = EmailMessage()
        if from_address:
            message["from"] = GmailService._format_from_header(from_address, from_display_name)
        message["to"] = to
        message["subject"] = subject
        message.set_content(body or "", subtype="plain", charset="utf-8")

        for attachment in attachments or []:
            filename = attachment.get("filename") or "attachment"
            mime_type = attachment.get("mime_type") or "application/octet-stream"
            maintype, _, subtype = mime_type.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            message.add_attachment(
                GmailService._coerce_attachment_content(attachment.get("content", b"")),
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        return base64.urlsafe_b64encode(message.as_bytes()).decode()

    @staticmethod
    def _format_from_header(email_address: str, display_name: str) -> str:
        """Build a MIME-safe From header from display name and email."""
        if not display_name:
            return email_address
        return formataddr((str(Header(display_name, "utf-8")), email_address))

    @staticmethod
    def _normalize_display_name(display_name: str) -> str:
        return str(display_name or "").strip()

    @staticmethod
    def _decode_header_value(raw_value: str) -> str:
        """Decode MIME-encoded header values to UTF-8 text."""
        if not raw_value:
            return ""

        decoded_parts: list[str] = []
        for value, encoding in decode_header(raw_value):
            if isinstance(value, bytes):
                candidate_encodings = [encoding, "utf-8", "cp949", "latin-1"]
                for candidate in candidate_encodings:
                    if not candidate:
                        continue
                    try:
                        decoded_parts.append(value.decode(candidate))
                        break
                    except Exception:
                        continue
                else:
                    decoded_parts.append(value.decode("utf-8", errors="replace"))
                continue
            decoded_parts.append(value)

        return "".join(decoded_parts)

    @staticmethod
    def _coerce_attachment_content(content: bytes | str | None) -> bytes:
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        try:
            return base64.b64decode(content, validate=True)
        except Exception:
            return content.encode("utf-8")

    @staticmethod
    def _extract_body(payload: dict) -> str:
        """Extract a text body from a Gmail message payload."""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="replace"
            )

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="replace"
                )

            nested_body = GmailService._extract_body(part)
            if nested_body:
                return nested_body

        return ""

    @staticmethod
    def _extract_attachments(payload: dict, message_id: str) -> list[dict]:
        """Extract Gmail attachment metadata recursively."""
        attachments: list[dict] = []

        for part in payload.get("parts", []):
            body = part.get("body", {}) or {}
            attachment_id = body.get("attachmentId")
            filename = part.get("filename", "")
            inline = GmailService._is_inline_part(part)
            if filename or attachment_id:
                attachment_key = attachment_id or filename or "attachment"
                url = (
                    f"{GMAIL_API}/messages/{message_id}/attachments/{attachment_id}"
                    if attachment_id
                    else ""
                )
                attachment_payload = {
                    "id": f"gmail-{message_id}:{attachment_key}",
                    "name": filename,
                    "filename": filename,
                    "mimeType": part.get("mimeType", ""),
                    "mime_type": part.get("mimeType", ""),
                    "size": body.get("size"),
                    "source": "gmail",
                    "source_service": "gmail",
                    "messageId": message_id,
                    "message_id": message_id,
                    "attachmentId": attachment_id or "",
                    "attachment_id": attachment_id or "",
                    "inline": inline,
                    "content": None,
                    "downloadUrl": None,
                    "url": url,
                }
                attachment_payload.update(default_file_content_fields())
                attachments.append(attachment_payload)
            attachments.extend(GmailService._extract_attachments(part, message_id))

        return attachments

    @staticmethod
    def _is_inline_part(part: dict) -> bool:
        disposition = GmailService._part_header_value(part, "content-disposition").lower()
        if "inline" in disposition:
            return True
        if "attachment" in disposition:
            return False
        return str(part.get("mimeType", "")).startswith("image/") and bool(part.get("filename"))

    @staticmethod
    def _part_header_value(part: dict, header_name: str) -> str:
        for header in part.get("headers", []) or []:
            if str(header.get("name", "")).lower() == header_name:
                return str(header.get("value", ""))
        return ""

    @staticmethod
    def _coerce_size(value: int | str | None) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_size_over_download_limit(value: int | str | None) -> bool:
        size = GmailService._coerce_size(value)
        return size is not None and size > MAX_DOWNLOAD_BYTES

    @staticmethod
    def _parse_address_list(raw_value: str) -> list[str]:
        """Return normalized email addresses from an RFC 5322 address header."""
        if not raw_value:
            return []
        parsed = [email for _, email in getaddresses([raw_value]) if email]
        return parsed or [raw_value]

    @staticmethod
    def _normalize_date(raw_value: str) -> str:
        """Normalize an email Date header to ISO-8601 when possible."""
        if not raw_value:
            return ""
        try:
            return parsedate_to_datetime(raw_value).isoformat()
        except Exception:
            return raw_value
