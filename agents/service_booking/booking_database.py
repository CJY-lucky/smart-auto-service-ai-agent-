"""预约数据操作器。

Agent 层不允许直接访问 DB，一律经过这里 -> Services -> DB 的链路。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.vehicle_behavior_service import VehicleBehaviorService
from services.work_order_service import WorkOrderService


class BookingDatabase:
    """工单落库与行为记录的薄封装。"""

    def __init__(self, db_path: Optional[str] = None):
        self._work_order_service: Optional[WorkOrderService] = None
        self._behavior_service: Optional[VehicleBehaviorService] = None
        self.db_path = db_path

    @property
    def work_order_service(self) -> WorkOrderService:
        if self._work_order_service is None:
            self._work_order_service = WorkOrderService(self.db_path)
        return self._work_order_service

    @property
    def behavior_service(self) -> VehicleBehaviorService:
        if self._behavior_service is None:
            self._behavior_service = VehicleBehaviorService(self.db_path)
        return self._behavior_service

    def save_appointment(
        self,
        *,
        item_codes: List[str],
        start_time,
        owner_ref: str,
        plate_no: Optional[str] = None,
        vehicle_model: Optional[str] = None,
        mileage: Optional[int] = None,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
        preference: Optional[str] = None,
        notes: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.work_order_service.create_work_order(
            item_codes,
            start_time,
            owner_ref=owner_ref,
            plate_no=plate_no,
            vehicle_model=vehicle_model,
            mileage=mileage,
            technician_id=technician_id,
            bay_id=bay_id,
            preference=preference,
            notes=notes,
            session_id=session_id,
        )

    def find_solution(self, item_codes, start_time, **kwargs):
        return self.work_order_service.scheduling_service.find_solution(item_codes, start_time, **kwargs)

    def reschedule(self, order_id: int, start_time, **kwargs) -> Dict[str, Any]:
        return self.work_order_service.reschedule(order_id, start_time, **kwargs)

    def cancel(self, order_id: int) -> Dict[str, Any]:
        return self.work_order_service.cancel(order_id)

    def upcoming_orders(self, owner_ref: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.work_order_service.upcoming_orders(owner_ref, limit=limit)

    def record_behavior(self, action_type: str, **kwargs) -> int:
        return self.behavior_service.record_behavior(action_type, **kwargs)