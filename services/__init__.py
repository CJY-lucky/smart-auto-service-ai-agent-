"""业务逻辑层。

Services 只依赖 DB 层，不允许反向调用 Agents / API / Web。
所有"能不能排上、该不该提醒"的判断都发生在这里。
"""

from .bay_service import BayService
from .knowledge_service import KnowledgeService
from .recommendation_service import RecommendationService
from .scheduling_service import (
    ConflictReason,
    ScheduleResult,
    ScheduleSolution,
    SchedulingService,
    WorkloadPlan,
)
from .technician_service import TechnicianService
from .text_embedding import (
    embed_input,
    embed_inputs,
    find_best_match_indices,
    rank_by_similarity,
    reset_embedder,
)
from .vehicle_behavior_service import VehicleBehaviorService
from .vehicle_service import VehicleService
from .work_order_service import WorkOrderService

__all__ = [
    "BayService",
    "ConflictReason",
    "KnowledgeService",
    "RecommendationService",
    "ScheduleResult",
    "ScheduleSolution",
    "SchedulingService",
    "TechnicianService",
    "VehicleBehaviorService",
    "VehicleService",
    "WorkOrderService",
    "WorkloadPlan",
    "embed_input",
    "embed_inputs",
    "find_best_match_indices",
    "rank_by_similarity",
    "reset_embedder",
]