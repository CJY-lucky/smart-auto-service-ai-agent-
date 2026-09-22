"""全局常量与枚举。

存放跨层共享、且不依赖具体业务实现的定义。除 SharedState 这类显式的会话
状态对象外，各层只读取、不修改这里的值。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

# 兼容参考项目的历史接口：{technician_id: [{"start": "HH:MM", "end": "HH:MM"}]}
# 新代码不要依赖它做资源判断，真实的资源占用以工单表为准。
busy_periods_dict: Dict[str, List[Dict[str, Any]]] = {}


class StateEnum(Enum):
    """对话状态机的状态。"""

    CLASSIFY = "classify"
    BOOKING = "booking"
    CONSULT = "consult"
    BEHAVIOR = "behavior"
    OTHER = "other"


class SharedState:
    """在多个 Agent 之间共享的会话状态对象。"""

    def __init__(self, value: StateEnum = StateEnum.CLASSIFY):
        self.value: StateEnum = value

    def __repr__(self) -> str:
        return f"SharedState({self.value})"


class IntentCategory(str, Enum):
    """任务分类 Agent 的产出类别。"""

    BOOKING = "booking"
    CONSULT = "consult"
    VEHICLE_PROFILE = "vehicle_profile"
    BEHAVIOR = "behavior"
    OTHER = "other"


class WorkOrderStatus(str, Enum):
    """工单状态。"""

    CREATED = "created"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def active_values(cls) -> List[str]:
        """仍然占用技师与工位的状态。"""

        return [cls.CREATED.value]


class BayType(str, Enum):
    """工位类型。"""

    LIFT = "举升机工位"
    ALIGNMENT = "四轮定位工位"
    PAINT = "钣喷房"
    WASH = "洗车工位"
    QUICK = "快修工位"


class Certification(str, Enum):
    """技师资质。"""

    BASIC = "基础保养"
    BRAKE = "制动系统"
    ALIGNMENT = "四轮定位"
    ELECTRICAL = "电气系统"
    ENGINE = "发动机"
    TRANSMISSION = "变速箱"
    PAINT = "钣金喷漆"
    NONE = "通用"


class Shift(str, Enum):
    """技师班次。"""

    MORNING = "早班"
    EVENING = "晚班"
    FULL = "全天班"


class BehaviorAction(str, Enum):
    """车主行为记录类别。"""

    CONSULTATION = "consultation"
    BOOKING = "booking"
    CANCEL = "cancel"
    RESCHEDULE = "reschedule"
    ADDON_ACCEPTED = "addon_accepted"
    ADDON_DECLINED = "addon_declined"


class ReminderType(str, Enum):
    """提醒类型。"""

    MAINTENANCE = "maintenance"
    INSPECTION = "inspection"
    BATTERY = "battery"
    BRAKE_PAD = "brake_pad"
    TIRE = "tire"
    WEATHER = "weather"


SERVICE_BAY_TYPES: List[str] = [member.value for member in BayType]
CERTIFICATIONS: List[str] = [member.value for member in Certification]
WORK_ORDER_STATUSES: List[str] = [member.value for member in WorkOrderStatus]
SHIFT_NAMES: List[str] = [member.value for member in Shift]