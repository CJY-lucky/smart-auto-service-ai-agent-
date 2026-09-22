"""数据库连接配置。

注意：SQLite 的路径是相对"进程工作目录"的，因此项目必须从仓库根目录启动
（uvicorn 也要在根目录执行），否则会出现两个不同的数据库文件。
"""

from __future__ import annotations

import os

from .settings import settings


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class DatabaseConfig:
    """数据库连接参数。"""

    def __init__(self, url: str | None = None, echo: bool | None = None):
        self.url = url or settings.database_url
        # SQL 回显默认关闭：开发时日志会被 SQL 淹没，需要时用 DB_ECHO=true 打开
        self.echo = _env_bool("DB_ECHO", False) if echo is None else echo
        self.pool_size = 10
        self.max_overflow = 20

    @property
    def connection_string(self) -> str:
        return self.url

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def sqlite_file_path(self) -> str | None:
        """从 sqlite:/// 连接串里取出文件路径。"""

        if not self.is_sqlite:
            return None
        raw = self.url.split("sqlite:///")[-1]
        return raw or None

    def get_engine_kwargs(self) -> dict:
        kwargs = {"echo": self.echo, "future": True}
        if self.is_sqlite:
            # FastAPI 的线程池会跨线程复用连接
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kwargs.update({"pool_size": self.pool_size, "max_overflow": self.max_overflow})
        return kwargs


db_config = DatabaseConfig()