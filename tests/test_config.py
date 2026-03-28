import os

import pytest


def test_settings_load_defaults():
    """Settings load with default values."""
    from app.core.config import Settings

    s = Settings()
    assert s.MONGODB_DB_NAME == "auth_db"
    assert s.JWT_ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert s.LOCKOUT_THRESHOLD == 5


def test_settings_load_from_env():
    """Settings can be overridden via environment variables."""
    os.environ["MONGODB_DB_NAME"] = "custom_db"
    os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

    from app.core.config import Settings

    s = Settings()
    assert s.MONGODB_DB_NAME == "custom_db"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 60

    # Cleanup
    del os.environ["MONGODB_DB_NAME"]
    del os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]
