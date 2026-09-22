"""API 编排层：对外接口、请求校验与响应封装。

允许调用 Agents 层或 Services 层，不允许绕过它们直接操作数据库。
"""

from .bay import router as bay_router
from .consultation import router as consultation_router
from .knowledge import router as knowledge_router
from .service_booking import router as service_booking_router
from .task import router as task_router
from .technician import router as technician_router
from .vehicle import router as vehicle_router
from .vehicle_behavior_analysis import router as vehicle_behavior_router
from .vehicle_behavior_analysis import router_underscore as vehicle_behavior_underscore_router

api_routers = [
    task_router,
    consultation_router,
    service_booking_router,
    technician_router,
    bay_router,
    vehicle_router,
    knowledge_router,
    vehicle_behavior_router,
    vehicle_behavior_underscore_router,
]

__all__ = ["api_routers"]