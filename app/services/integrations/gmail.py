import base64
from email.message import EmailMessage

from app.services.integrations.base import BaseIntegrationService

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailService(BaseIntegrationService):
    """Gmail API integration service."""

    async def list_messages(
        self, token: str, query: str = "", max_results: int = 20
    ) -> list[dict]:
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
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        body = self._extract_body(payload)

        return {
            "id": data.get("id"),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
            "attachments": self._extract_attachments(payload, data.get("id", "")),
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
        raw = self._build_raw_message(to, subject, body, attachments)

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
        raw = self._build_raw_message(to, subject, body, attachments)

        return await self._request(
            "POST",
            f"{GMAIL_API}/drafts",
            token,
            json={"message": {"raw": raw}},
        )

    @staticmethod
    def _build_raw_message(
        to: str,
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
    ) -> str:
        """Build a Gmail API raw MIME payload."""
        message = EmailMessage()
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
                attachments.append(
                    {
                        "filename": filename,
                        "mime_type": part.get("mimeType", ""),
                        "size": body.get("size"),
                        "url": (
                            f"{GMAIL_API}/messages/{message_id}/attachments/{attachment_id}"
                            if attachment_id
                            else ""
                        ),
                    }
                )
            attachments.extend(GmailService._extract_attachments(part, message_id))

        return attachments
