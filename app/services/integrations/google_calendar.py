from app.services.integrations.base import BaseIntegrationService

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarService(BaseIntegrationService):
    """Google Calendar API 연동 서비스 (DC-F0408)."""

    async def list_events(
        self,
        token: str,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """캘린더 이벤트 목록을 조회합니다."""
        params: dict = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        data = await self._request(
            "GET",
            f"{CALENDAR_API}/calendars/{calendar_id}/events",
            token,
            params=params,
        )
        return [
            {
                "id": ev.get("id"),
                "summary": ev.get("summary", ""),
                "start": ev.get("start", {}),
                "end": ev.get("end", {}),
                "description": ev.get("description", ""),
                "location": ev.get("location", ""),
            }
            for ev in data.get("items", [])
        ]

    async def create_event(
        self, token: str, calendar_id: str = "primary", event: dict | None = None
    ) -> dict:
        """캘린더에 이벤트를 생성합니다.

        event 예시: {"summary": "회의", "start": {"dateTime": "..."}, "end": {"dateTime": "..."}}
        """
        return await self._request(
            "POST",
            f"{CALENDAR_API}/calendars/{calendar_id}/events",
            token,
            json=event or {},
        )

    async def update_event(
        self,
        token: str,
        calendar_id: str = "primary",
        event_id: str = "",
        event: dict | None = None,
    ) -> dict:
        """캘린더 이벤트를 수정합니다."""
        return await self._request(
            "PUT",
            f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
            token,
            json=event or {},
        )

    async def list_calendars(self, token: str) -> list[dict]:
        """사용자 캘린더 목록을 조회합니다."""
        data = await self._request(
            "GET",
            f"{CALENDAR_API}/users/me/calendarList",
            token,
        )
        return [
            {
                "id": cal.get("id"),
                "summary": cal.get("summary", ""),
                "primary": cal.get("primary", False),
            }
            for cal in data.get("items", [])
        ]
