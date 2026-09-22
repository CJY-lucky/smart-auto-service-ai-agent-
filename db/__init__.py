"""数据持久化层。

- models：SQLAlchemy 模型
- repositories：数据访问封装
- base：会话管理与并发锁
- db_router：统一入口
"""

from .base import SessionManager, resource_lock
from .db_router import DatabaseRouter, get_database_router, reset_database_router
from .models import (
    Base,
    EmbeddingCache,
    KnowledgeDocument,
    Owner,
    OwnerBehavior,
    OwnerPreference,
    OwnerReminder,
    ServiceBay,
    Technician,
    Vehicle,
    WorkOrder,
    WorkOrderItem,
)

__all__ = [
    "Base",
    "DatabaseRouter",
    "get_database_router",
    "reset_database_router",
    "SessionManager",
    "resource_lock",
    "Owner",
    "Vehicle",
    "Technician",
    "ServiceBay",
    "WorkOrder",
    "WorkOrderItem",
    "KnowledgeDocument",
    "EmbeddingCache",
    "OwnerBehavior",
    "OwnerPreference",
    "OwnerReminder",
]