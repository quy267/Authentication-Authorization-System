from pydantic import field_validator
from pydantic_settings import BaseSettings

_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
_JWT_KEY_MIN_LENGTH = 32


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Auth System"
    DEBUG: bool = False

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "auth_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT — default is intentionally insecure; override in production via env var
    JWT_SECRET_KEY: str = "change-me-in-production-set-a-secure-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # SMTP / Email
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@example.com"

    # Account lockout
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_key_length(cls, v: str) -> str:
        if len(v) < _JWT_KEY_MIN_LENGTH:
            raise ValueError(f"JWT_SECRET_KEY must be at least {_JWT_KEY_MIN_LENGTH} characters")
        return v

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        if v not in _ALLOWED_ALGORITHMS:
            raise ValueError(f"JWT_ALGORITHM must be one of {_ALLOWED_ALGORITHMS}")
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
