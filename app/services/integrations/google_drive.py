class GoogleDriveService:
    """Google Drive 연동 서비스"""

    def __init__(self, credentials: dict | None = None):
        self._credentials = credentials
        # TODO: google-api-python-client 초기화

    async def list_files(self, folder_id: str | None = None) -> list[dict]:
        """폴더 내 파일 목록 조회"""
        # TODO: Drive API files().list() 호출
        return []

    async def download_file(self, file_id: str) -> bytes:
        """파일 다운로드"""
        # TODO: Drive API files().get_media() 호출
        return b""

    async def upload_file(self, name: str, content: bytes, folder_id: str | None = None) -> str:
        """파일 업로드"""
        # TODO: Drive API files().create() 호출
        return ""

    async def watch_folder(self, folder_id: str, webhook_url: str) -> dict:
        """폴더 변경 감시 (웹훅)"""
        # TODO: Drive API files().watch() 호출
        return {}
