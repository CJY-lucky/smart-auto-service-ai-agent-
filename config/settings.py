"""应用运行设置：把环境变量收敛成一份只读配置对象。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    """应用级设置。"""

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite:///data/smart_auto_service.db")
    )
    default_owner_id: str = field(default_factory=lambda: _env("DEFAULT_OWNER_ID", "default_owner"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", True))
    log_level: str = field(default_factory=lambda: (_env("LOG_LEVEL", "INFO") or "INFO").upper())
    enable_scheduler: bool = field(default_factory=lambda: _env_bool("ENABLE_SCHEDULER", False))
    openweather_api_key: str | None = field(default_factory=lambda: _env("OPENWEATHER_API_KEY"))
    weather_city: str = field(default_factory=lambda: _env("WEATHER_CITY", "Beijing") or "Beijing")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = AppSettings()