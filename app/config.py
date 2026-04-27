from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "flowify"

    LLM_MODEL_NAME: str = "gpt-4o"
    LLM_API_KEY: str = ""
    LLM_API_BASE_URL: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    SLACK_BOT_TOKEN: str = ""
    NOTION_INTEGRATION_TOKEN: str = ""
    GITHUB_TOKEN: str = ""

    INTERNAL_API_SECRET: str = ""
    SPRING_BASE_URL: str = ""
    SPRING_CALLBACK_TIMEOUT_SECONDS: float = 5.0

    CANVAS_API_URL: str = "https://canvas.kumoh.ac.kr"
    CANVAS_TOKEN: str = ""

    @property
    def CANVAS_LMS_API_URL(self) -> str:
        return f"{self.CANVAS_API_URL.rstrip('/')}/api/v1"

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "env_file_ignore_missing": True,
    }


settings = Settings()
