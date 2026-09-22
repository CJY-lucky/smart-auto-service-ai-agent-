"""行为记录器：把交互过程沉淀成可分析的数据。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config.constants import BehaviorAction
from services.vehicle_behavior_service import VehicleBehaviorService


class BehaviorRecorder:
    """行为记录。"""

    def __init__(self, behavior_service: Optional[VehicleBehaviorService] = None, db_path: Optional[str] = None):
        self.behavior_service = behavior_service or VehicleBehaviorService(db_path)

    def record_consultation(
        self, question: str, categories: List[str], session_id: str, owner_ref: str = "default_owner"
    ) -> int:
        return self.behavior_service.record_behavior(
            BehaviorAction.CONSULTATION.value,
            owner_ref=owner_ref,
            action_data={"question": question, "categories": categories},
            session_id=session_id,
        )

    def record_booking(
        self,
        *,
        order: Dict[str, Any],
        owner_ref: str = "default_owner",
        session_id: Optional[str] = None,
    ) -> int:
        return self.behavior_service.record_behavior(
            BehaviorAction.BOOKING.value,
            owner_ref=owner_ref,
            action_data={
                "order_no": order.get("order_no"),
                "item_codes": order.get("item_codes"),
                "start_time": str(order.get("start_time")),
                "amount": order.get("amount"),
            },
            technician_id=order.get("technician_id"),
            vehicle_id=order.get("vehicle_id"),
            session_id=session_id,
        )

    def record_cancel(self, order: Dict[str, Any], owner_ref: str = "default_owner") -> int:
        return self.behavior_service.record_behavior(
            BehaviorAction.CANCEL.value,
            owner_ref=owner_ref,
            action_data={"order_no": order.get("order_no"), "item_codes": order.get("item_codes")},
            vehicle_id=order.get("vehicle_id"),
        )

    def record_addon_decision(self, accepted: bool, items: List[str], owner_ref: str = "default_owner") -> int:
        action = BehaviorAction.ADDON_ACCEPTED.value if accepted else BehaviorAction.ADDON_DECLINED.value
        return self.behavior_service.record_behavior(action, owner_ref=owner_ref, action_data={"items": items})

    def list_behaviors(self, owner_ref: str = "default_owner", limit: int = 100) -> List[Dict[str, Any]]:
        return self.behavior_service.get_behaviors(owner_ref, limit=limit)