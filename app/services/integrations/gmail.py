import base64
from email.mime.text import MIMEText

from app.services.integrations.base import BaseIntegrationService

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailService(BaseIntegrationService):
    """Gmail API 연동 서비스 (DC-F0406)."""

    async def list_messages(
        self, token: str, query: str = "", max_results: int = 20
    ) -> list[dict]:
        """메일 목록 조회 후 각 메일의 상세 정보를 반환합니다."""
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
        """단일 메일 상세 조회."""
        data = await self._request(
            "GET", f"{GMAIL_API}/messages/{message_id}", token,
            params={"format": "full"},
        )

        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        body = self._extract_body(data.get("payload", {}))

        return {
            "id": data.get("id"),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
            "snippet": data.get("snippet", ""),
        }

    async def send_message(
        self, token: str, to: str, subject: str, body: str
    ) -> dict:
        """메일 전송."""
        mime = MIMEText(body, "plain", "utf-8")
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

        return await self._request(
            "POST", f"{GMAIL_API}/messages/send", token,
            json={"raw": raw},
        )

    @staticmethod
    def _extract_body(payload: dict) -> str:
        """메일 payload에서 본문 텍스트를 추출합니다."""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

        return ""
