"""数据库会话管理。"""

from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from config.database import db_config
from db.models import Base


class SessionManager:
    """负责建表、提供会话与事务边界。"""

    def __init__(self, db_path: str | None = None, echo: bool | None = None):
        self.db_path = db_path or db_config.connection_string
        self._prepare_sqlite_directory()
        self.engine = create_engine(self.db_path, **self._engine_kwargs(echo))
        Base.metadata.create_all(self.engine)
        self.Session = scoped_session(sessionmaker(bind=self.engine, expire_on_commit=False))

    def _engine_kwargs(self, echo: bool | None) -> dict:
        kwargs = {"echo": db_config.echo if echo is None else echo, "future": True}
        if self.db_path.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        return kwargs

    def _prepare_sqlite_directory(self) -> None:
        if not self.db_path.startswith("sqlite"):
            return
        raw = self.db_path.split("sqlite:///")[-1]
        if not raw or raw == ":memory:":
            return
        directory = os.path.dirname(os.path.abspath(raw))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)

    @contextmanager
    def session_scope(self):
        """自动提交/回滚的会话上下文。"""

        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        self.Session.remove()
        self.engine.dispose()