import httpx

from app.common.errors import ErrorCode, FlowifyException
from app.services.integrations.base import BaseIntegrationService

SLACK_API = "https://slack.com/api"


class SlackService(BaseIntegrationService):
    """Slack API 연동 서비스 (DC-F0402).

    Slack API는 Bearer token이 아닌 자체 헤더 형식을 사용하지만,
    OAuth access token은 Bearer 방식으로도 동작합니다.
    """

    async def send_message(self, token: str, channel: str, text: str) -> dict:
        """Slack 채널에 메시지를 전송합니다."""
        data = await self._request(
            "POST", f"{SLACK_API}/chat.postMessage", token,
            json={"channel": channel, "text": text},
        )
        if not data.get("ok"):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"Slack 메시지 전송 실패: {data.get('error', 'unknown')}",
                context={"channel": channel, "error": data.get("error")},
            )
        return data

    async def list_channels(self, token: str) -> list[dict]:
        """사용자가 접근 가능한 채널 목록을 조회합니다."""
        data = await self._request(
            "GET", f"{SLACK_API}/conversations.list", token,
            params={"types": "public_channel,private_channel", "limit": 200},
        )
        if not data.get("ok"):
            raise FlowifyException(
                ErrorCode.EXTERNAL_API_ERROR,
                detail=f"Slack 채널 목록 조회 실패: {data.get('error', 'unknown')}",
            )
        return [
            {"id": ch["id"], "name": ch["name"], "is_private": ch.get("is_private", False)}
            for ch in data.get("channels", [])
        ]
