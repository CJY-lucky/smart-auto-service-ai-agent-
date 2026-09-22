"""工单业务逻辑：创建、改约、取消、完成。

并发要点：SQLite 没有行级锁，"检查空闲 -> 写入工单"之间天然存在竞态。
所以这里在写入临界区里再校验一次技师与工位，确保不会排出两张互相冲突的工单。
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.constants import BehaviorAction, WorkOrderStatus
from config.time_config import TimeWindow, time_config
from db.base.locks import booking_critical_section
from db.db_router import get_database_router
from services.scheduling_service import ConflictReason, ScheduleResult, SchedulingService
from services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)


class WorkOrderService:
    """工单全生命周期管理。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)
        self.scheduling_service = SchedulingService(db_path)
        self.vehicle_service = VehicleService(db_path)

    # ---------------------------------------------------------------- 创建
    def create_work_order(
        self,
        item_codes: List[str],
        start_time: datetime,
        *,
        owner_ref: Optional[str] = None,
        plate_no: Optional[str] = None,
        vehicle_model: Optional[str] = None,
        mileage: Optional[int] = None,
        oil_spec: Optional[str] = None,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
        preference: Optional[str] = None,
        notes: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """尝试创建工单。返回 {success, result, order, message}。"""

        owner_id = self.vehicle_service.ensure_owner(owner_ref or "default_owner")
        vehicle_id = None
        if plate_no:
            vehicle_id = self.vehicle_service.ensure_vehicle(
                owner_id,
                plate_no,
                model=vehicle_model,
                mileage=mileage,
                oil_spec=oil_spec,
            )

        result = self.scheduling_service.find_solution(
            item_codes,
            start_time,
            technician_id=technician_id,
            bay_id=bay_id,
            preference=preference,
        )
        if not result.feasible or result.solution is None:
            return {
                "success": False,
                "result": result,
                "order": None,
                "message": SchedulingService.describe(result),
            }

        solution = result.solution

        with booking_critical_section():
            # 临界区内二次校验：避免两个请求同时通过可性性检查
            if not self.db.work_orders.is_technician_available(
                solution.technician["id"], solution.start_time, solution.end_time
            ):
                result = self.scheduling_service.find_solution(
                    item_codes, start_time, technician_id=technician_id, bay_id=bay_id, preference=preference
                )
                if not result.feasible or result.solution is None:
                    return {
                        "success": False,
                        "result": result,
                        "order": None,
                        "message": SchedulingService.describe(result),
                    }
                solution = result.solution

            if not self.db.work_orders.is_bay_available(
                solution.bay["id"], solution.start_time, solution.end_time
            ):
                result = self.scheduling_service.find_solution(
                    item_codes, start_time, technician_id=technician_id, preference=preference
                )
                if not result.feasible or result.solution is None:
                    return {
                        "success": False,
                        "result": result,
                        "order": None,
                        "message": SchedulingService.describe(result),
                    }
                solution = result.solution

            order_id = self.db.work_orders.create_order(
                order_no=self.generate_order_no(),
                owner_id=owner_id,
                vehicle_id=vehicle_id,
                technician_id=solution.technician["id"],
                bay_id=solution.bay["id"],
                start_time=solution.start_time,
                end_time=solution.end_time,
                item_codes=result.plan.item_codes,
                bay_plan=[
                    {
                        "item_code": segment["item_code"],
                        "bay_id": segment["bay"]["id"],
                        "bay_name": segment["bay"]["name"],
                        "bay_type": segment["bay"]["bay_type"],
                        "start": time_config.format_datetime(segment["start"]),
                        "end": time_config.format_datetime(segment["end"]),
                    }
                    for segment in (solution.segments or [])
                ],
                estimated_minutes=result.plan.total_minutes,
                amount=result.plan.amount,
                mileage=mileage,
                notes=notes,
                session_id=session_id,
                items=[
                    {
                        "item_code": item["item_code"],
                        "item_name": item["name"],
                        "duration_minutes": item["duration_minutes"],
                        "amount": item["amount"],
                        "sequence": item["sequence"],
                    }
                    for item in result.plan.items
                ],
            )

        order = self.db.work_orders.get_order(order_id)
        self._record_behavior(
            owner_ref or "default_owner",
            BehaviorAction.BOOKING.value,
            order=order,
            vehicle_id=vehicle_id,
        )
        self._record_preferences(owner_ref or "default_owner", solution, result.plan.item_codes)

        return {
            "success": True,
            "result": result,
            "order": order,
            "message": SchedulingService.describe(result),
        }

    # ---------------------------------------------------------------- 改约
    def reschedule(
        self,
        order_id: int,
        start_time: datetime,
        *,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """改约：重新求解排期并更新工单。"""

        order = self.db.work_orders.get_order(order_id)
        if not order:
            return {"success": False, "order": None, "message": "工单不存在"}
        if order["status"] != WorkOrderStatus.CREATED.value:
            return {"success": False, "order": order, "message": "该工单已结束，无法改约"}

        result = self.scheduling_service.find_solution(
            order["item_codes"],
            start_time,
            technician_id=technician_id,
            bay_id=bay_id,
            exclude_order_id=order_id,
        )
        if not result.feasible or result.solution is None:
            return {"success": False, "result": result, "order": order, "message": SchedulingService.describe(result)}

        solution = result.solution
        with booking_critical_section():
            self.db.work_orders.update_order(
                order_id,
                technician_id=solution.technician["id"],
                bay_id=solution.bay["id"],
                start_time=solution.start_time,
                end_time=solution.end_time,
            )

        updated = self.db.work_orders.get_order(order_id)
        self._record_behavior(
            order.get("session_id") or "default_owner",
            BehaviorAction.RESCHEDULE.value,
            technician_id=solution.technician["id"],
            action_data={
                "order_no": order["order_no"],
                "start_time": time_config.format_datetime(solution.start_time),
            },
        )
        return {"success": True, "result": result, "order": updated, "message": SchedulingService.describe(result)}

    # ---------------------------------------------------------------- 取消/完成
    def cancel(self, order_id: int) -> Dict[str, Any]:
        order = self.db.work_orders.get_order(order_id)
        if not order:
            return {"success": False, "order": None, "message": "工单不存在"}
        self.db.work_orders.cancel_order(order_id)
        self._record_behavior(
            "default_owner",
            BehaviorAction.CANCEL.value,
            action_data={"order_no": order["order_no"]},
        )
        return {"success": True, "order": self.db.work_orders.get_order(order_id), "message": "工单已取消"}

    def complete(self, order_id: int, *, mileage: Optional[int] = None, amount: Optional[float] = None) -> Dict[str, Any]:
        order = self.db.work_orders.get_order(order_id)
        if not order:
            return {"success": False, "order": None, "message": "工单不存在"}

        self.db.work_orders.complete_order(order_id, mileage=mileage, amount=amount)
        if order.get("vehicle_id"):
            self.vehicle_service.record_service(
                order["vehicle_id"],
                order.get("item_codes") or [],
                mileage=mileage,
                service_date=time_config.now(),
            )
        return {"success": True, "order": self.db.work_orders.get_order(order_id), "message": "工单已完成"}

    # ---------------------------------------------------------------- 查询
    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        return self.db.work_orders.get_order(order_id)

    def get_order_by_no(self, order_no: str) -> Optional[Dict[str, Any]]:
        return self.db.work_orders.get_order_by_no(order_no)

    def list_orders(
        self,
        *,
        owner_ref: Optional[str] = None,
        status: Optional[str] = None,
        day: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        owner_id = None
        if owner_ref:
            owner = self.db.owners.get_by_ref(owner_ref)
            owner_id = owner["id"] if owner else -1
        return self.db.work_orders.list_orders(owner_id=owner_id, status=status, day=day, limit=limit)

    def list_orders_detail(self, day: Optional[datetime] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.db.work_orders.list_orders_detail(day=day, limit=limit)

    def upcoming_orders(self, owner_ref: str, limit: int = 5) -> List[Dict[str, Any]]:
        owner = self.db.owners.get_by_ref(owner_ref)
        if not owner:
            return []
        orders = self.db.work_orders.list_orders(
            owner_id=owner["id"], statuses=[WorkOrderStatus.CREATED.value], limit=limit
        )
        return [order for order in orders if order["end_time"] >= time_config.now()]

    def history(self, owner_ref: str, limit: int = 20) -> List[Dict[str, Any]]:
        owner = self.db.owners.get_by_ref(owner_ref)
        if not owner:
            return []
        return self.db.work_orders.list_orders(owner_id=owner["id"], limit=limit)

    def statistics(self) -> Dict[str, Any]:
        stats = self.db.work_orders.statistics()
        stats["technicians"] = self.db.technicians.count()
        stats["bays"] = self.db.bays.count()
        return stats

    def available_alternatives(
        self, item_codes: List[str], start_time: datetime, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """给车主的备选时段（结构化）。"""

        suggestions = self.scheduling_service.suggest_slots(item_codes, start_time, limit=limit)
        return [solution.to_dict() for solution in suggestions]

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def generate_order_no() -> str:
        return "WO{0}{1:04d}".format(time_config.now().strftime("%Y%m%d%H%M%S"), random.randint(0, 9999))

    def _record_behavior(
        self,
        owner_ref: str,
        action_type: str,
        *,
        order: Optional[Dict[str, Any]] = None,
        technician_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        action_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            payload = dict(action_data or {})
            if order:
                payload.setdefault("order_no", order["order_no"])
                payload.setdefault("start_time", time_config.format_datetime(order["start_time"]))
                payload.setdefault("end_time", time_config.format_datetime(order["end_time"]))
                payload.setdefault("item_codes", order["item_codes"])
                payload.setdefault("amount", order["amount"])
                technician_id = technician_id or order.get("technician_id")
                vehicle_id = vehicle_id or order.get("vehicle_id")
            self.db.behaviors.record_behavior(
                owner_id=owner_ref,
                action_type=action_type,
                action_data=payload,
                technician_id=technician_id,
                vehicle_id=vehicle_id,
            )
        except Exception as exc:  # pragma: no cover - 行为记录失败不能影响下单
            logger.warning("记录车主行为失败：%s", exc)

    def _record_preferences(self, owner_ref: str, solution, item_codes: List[str]) -> None:
        try:
            self.db.behaviors.upsert_preference(owner_ref, "technician", str(solution.technician["id"]))
            for code in item_codes:
                self.db.behaviors.upsert_preference(owner_ref, "service", code)
            hour = solution.start_time.hour
            period = "上午" if hour < 12 else ("下午" if hour < 18 else "晚间")
            self.db.behaviors.upsert_preference(owner_ref, "time_period", period)
        except Exception as exc:  # pragma: no cover
            logger.warning("写入车主偏好失败：%s", exc)