from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str
    API_PREFIX: str

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    REDIS_HOST: str
    REDIS_PORT: int

    JWT_SECRET: str
    JWT_ALGORITHM: str
    JWT_EXPIRE_MINUTES: int

    NODE_ENROLLMENT_TOKEN: str

    MIKROTIK_BASE_URL: str = "https://10.10.20.1"
    MIKROTIK_USERNAME: str = ""
    MIKROTIK_PASSWORD: str = ""
    MIKROTIK_VERIFY_TLS: bool = True
    MIKROTIK_CA_FILE: str = "/etc/ssl/certs/ca-certificates.crt"
    MIKROTIK_TIMEOUT_SECONDS: float = 10.0
    MIKROTIK_LIVE_ENABLED: bool = False


settings = Settings()
