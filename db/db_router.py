"""数据库路由器：对上层提供统一的数据访问入口。

上层（Services）只需要 DatabaseRouter().work_orders，不关心底层是 SQLite
还是别的数据库，也不关心表结构。
"""

from __future__ import annotations

from typing import Dict, Optional

from config.database import db_config
from db.base import SessionManager
from db.repositories import (
    BayRepository,
    BehaviorRepository,
    KnowledgeRepository,
    OwnerRepository,
    TechnicianRepository,
    VehicleRepository,
    WorkOrderRepository,
)


class DatabaseRouter:
    """聚合各 Repository，并持有唯一的会话管理器。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or db_config.connection_string
        self.session_manager = SessionManager(self.db_path)
        session_factory = self.session_manager.Session

        self.owners = OwnerRepository(session_factory)
        self.vehicles = VehicleRepository(session_factory)
        self.technicians = TechnicianRepository(session_factory)
        self.bays = BayRepository(session_factory)
        self.work_orders = WorkOrderRepository(session_factory)
        self.knowledge = KnowledgeRepository(session_factory)
        self.behaviors = BehaviorRepository(session_factory)

    def close(self) -> None:
        self.session_manager.close()


_ROUTERS: Dict[str, DatabaseRouter] = {}


def get_database_router(db_path: Optional[str] = None) -> DatabaseRouter:
    """按连接串缓存路由器实例，避免每个请求都新建 engine。"""

    key = db_path or db_config.connection_string
    router = _ROUTERS.get(key)
    if router is None:
        router = DatabaseRouter(key)
        _ROUTERS[key] = router
    return router


def reset_database_router(db_path: Optional[str] = None) -> None:
    """释放并移除缓存的路由器（测试用）。"""

    if db_path is None:
        keys = list(_ROUTERS)
    else:
        keys = [db_path]
    for key in keys:
        router = _ROUTERS.pop(key, None)
        if router is not None:
            router.close()