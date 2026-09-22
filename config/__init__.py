"""配置模块。

集中提供常量、运行设置、时间基准、模型工厂与门店服务目录。
"""

from .constants import (
    StateEnum,
    SharedState,
    IntentCategory,
    WorkOrderStatus,
    BayType,
    Certification,
    Shift,
    BehaviorAction,
    ReminderType,
    busy_periods_dict,
)
from .settings import settings
from .time_config import TimeConfig, TimeWindow, time_config

__all__ = [
    "StateEnum",
    "SharedState",
    "IntentCategory",
    "WorkOrderStatus",
    "BayType",
    "Certification",
    "Shift",
    "BehaviorAction",
    "ReminderType",
    "busy_periods_dict",
    "settings",
    "TimeConfig",
    "TimeWindow",
    "time_config",
]