from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "flowify"

    LLM_MODEL_NAME: str = "EXAONE-3.0-7.8B-Instruct"
    LLM_API_KEY: str = ""
    LLM_API_BASE_URL: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    SLACK_BOT_TOKEN: str = ""
    NOTION_INTEGRATION_TOKEN: str = ""
    GITHUB_TOKEN: str = ""

    INTERNAL_API_SECRET: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
