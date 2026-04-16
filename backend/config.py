from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Groq
    GROQ_API_KEYS: str = ""

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Optional integrations
    NEWSDATA_API_KEY: Optional[str] = None
    FRESHRSS_URL: Optional[str] = None
    FRESHRSS_USERNAME: str = "admin"
    FRESHRSS_PASSWORD: Optional[str] = None

    # NLP
    NLP_BATCH_SIZE: int = 25
    BRIEF_ARTICLE_LIMIT: int = 30

    # Environment
    ENVIRONMENT: str = "development"

    @property
    def groq_keys_list(self) -> list[str]:
        return [k.strip() for k in self.GROQ_API_KEYS.split(",") if k.strip()]

    model_config = {"env_file": "infrastructure/.env", "extra": "ignore"}


settings = Settings()
