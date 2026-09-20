"""
Application configuration.

All configuration is sourced from environment variables (via .env in local
development). See .env.example for the full list of supported variables.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core ---
    APP_NAME: str = "Leadyfy OS API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./leadyfy.db"

    # --- Auth / JWT ---
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours, convenient for demos

    # --- CORS ---
    # Comma-separated list of allowed origins for local React dev servers.
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"

    # --- Pagination ---
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # NOTE: The spec explicitly defines the Scripting workflow as "Manual
    # Script Workflow (No AI)" (section 5.1) and does not require any AI or
    # third-party integration elsewhere in the document. No AI provider
    # configuration is therefore included here (see README "Assumptions").

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
