import base64
from email.header import Header, decode_header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parsedate_to_datetime
import logging

from app.core.document_content import default_file_content_fields
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

    async def send_message(
        self,
        token: str,
        to: str,
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
    ) -> dict:
        """Send a Gmail message."""
        sender_email, sender_display_name = await self._get_sender_identity(token)
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
    ) -> dict:
        """Create a Gmail draft."""
        sender_email, sender_display_name = await self._get_sender_identity(token)
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

    async def _get_sender_identity(self, token: str) -> tuple[str, str]:
        """Return the authenticated sender email and preferred display name."""
        try:
            send_as_data = await self._request("GET", f"{GMAIL_API}/settings/sendAs", token)
        except Exception as exc:
            logger.warning("Falling back to bare Gmail sender email because sendAs lookup failed: %s", exc)
            return await self._get_sender_email(token), ""

        send_as_list = send_as_data.get("sendAs", [])
        if not isinstance(send_as_list, list) or not send_as_list:
            logger.info("Falling back to bare Gmail sender email because sendAs list is empty")
            return await self._get_sender_email(token), ""

        chosen = next((item for item in send_as_list if item.get("isPrimary")), None)
        if chosen is None:
            chosen = next((item for item in send_as_list if item.get("isDefault")), None)
        if chosen is None:
            chosen = send_as_list[0]

        email_address = str(chosen.get("sendAsEmail") or "").strip()
        if not email_address:
            logger.info("Falling back to profile email because chosen sendAs entry has no email")
            email_address = await self._get_sender_email(token)
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
                    "messageId": message_id,
                    "attachmentId": attachment_id or "",
                    "content": None,
                    "downloadUrl": None,
                    "url": url,
                }
                attachment_payload.update(default_file_content_fields())
                attachments.append(attachment_payload)
            attachments.extend(GmailService._extract_attachments(part, message_id))

        return attachments

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
