from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://acg_user:acg_pass@localhost:5432/ai_commerce_gateway"
    GEMINI_API_KEY: str = ""
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    JWT_SECRET: str = "insecure-dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    MCP_TRANSPORT: str = "streamable-http"
    MCP_PORT: int = 8100
    ENVIRONMENT: str = "development"
    N8N_GROWTH_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_API_KEY: str = "dev-n8n-webhook-key"
    N8N_CALLBACK_API_KEY: str = "dev-n8n-callback-key"
    GROWTH_CALLBACK_BASE_URL: str = "http://localhost:8000"
    CORS_ALLOWED_ORIGINS: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
