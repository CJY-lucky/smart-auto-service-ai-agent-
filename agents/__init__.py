"""多 Agent 层。

四个 Agent 各自职责单一，由任务分类 Agent 负责路由：
- TaskClassificationAgent：意图识别与分派
- ServiceBookingAgent：预约工单
- ConsultantAgent：RAG 知识咨询
- VehicleBehaviorAgent：车主行为分析与主动提醒
"""

from config.constants import SharedState, StateEnum

from .consultant_agent import ConsultantAgent
from .service_booking_agent import ServiceBookingAgent
from .task_classification_agent import TaskClassificationAgent
from .vehicle_behavior_agent import VehicleBehaviorAgent

__all__ = [
    "ConsultantAgent",
    "ServiceBookingAgent",
    "TaskClassificationAgent",
    "VehicleBehaviorAgent",
    "SharedState",
    "StateEnum",
]