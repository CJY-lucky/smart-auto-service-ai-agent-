"""工单数据访问：本项目"双资源占用"的事实来源。

判断技师/工位是否空闲，一律以工单表为准（status=created 才算占用），
不要再用内存字典维护第二份状态，否则迟早不一致。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_

from config.constants import WorkOrderStatus
from config.time_config import time_config
from db.models import ServiceBay, Technician, Vehicle, WorkOrder, WorkOrderItem


def _parse_moment(value) -> Optional[datetime]:
    """解析 bay_plan 里存的时间字符串。"""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return time_config.parse_datetime(str(value))


class WorkOrderRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # -- 内部工具 -------------------------------------------------------
    @staticmethod
    def _to_dict(order: WorkOrder) -> Dict[str, Any]:
        return {
            "id": order.id,
            "order_no": order.order_no,
            "owner_id": order.owner_id,
            "vehicle_id": order.vehicle_id,
            "technician_id": order.technician_id,
            "bay_id": order.bay_id,
            "start_time": order.start_time,
            "end_time": order.end_time,
            "status": order.status,
            "item_codes": list(order.item_codes or []),
            "bay_plan": list(order.bay_plan or []),
            "estimated_minutes": order.estimated_minutes or 0,
            "amount": order.amount or 0.0,
            "mileage": order.mileage,
            "notes": order.notes or "",
            "session_id": order.session_id,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "completed_at": order.completed_at,
        }

    @staticmethod
    def _overlap_filter(start_time: datetime, end_time: datetime):
        """半开区间重叠条件：existing.start < new.end and new.start < existing.end。"""

        return and_(WorkOrder.start_time < end_time, start_time < WorkOrder.end_time)

    # -- 写操作 ---------------------------------------------------------
    def create_order(
        self,
        *,
        order_no: str,
        owner_id: int,
        vehicle_id: int,
        technician_id: int,
        bay_id: int,
        start_time: datetime,
        end_time: datetime,
        item_codes: List[str],
        estimated_minutes: int,
        amount: float,
        mileage: Optional[int] = None,
        notes: Optional[str] = None,
        session_id: Optional[str] = None,
        bay_plan: Optional[List[Dict[str, Any]]] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        with self._session_factory() as session:
            order = WorkOrder(
                order_no=order_no,
                owner_id=owner_id,
                vehicle_id=vehicle_id,
                technician_id=technician_id,
                bay_id=bay_id,
                start_time=start_time,
                end_time=end_time,
                status=WorkOrderStatus.CREATED.value,
                item_codes=list(item_codes),
                bay_plan=list(bay_plan or []),
                estimated_minutes=estimated_minutes,
                amount=amount,
                mileage=mileage,
                notes=notes,
                session_id=session_id,
            )
            session.add(order)
            session.flush()
            for index, item in enumerate(items or []):
                session.add(
                    WorkOrderItem(
                        work_order_id=order.id,
                        item_code=item["item_code"],
                        item_name=item["item_name"],
                        duration_minutes=item.get("duration_minutes", 0),
                        amount=item.get("amount", 0.0),
                        sequence=item.get("sequence", index),
                    )
                )
            session.commit()
            return order.id

    def update_order(self, order_id: int, **updates) -> bool:
        with self._session_factory() as session:
            order = session.get(WorkOrder, order_id)
            if not order:
                return False
            for key in (
                "technician_id",
                "bay_id",
                "start_time",
                "end_time",
                "status",
                "item_codes",
                "estimated_minutes",
                "amount",
                "mileage",
                "notes",
                "completed_at",
            ):
                if key in updates and updates[key] is not None:
                    setattr(order, key, updates[key])
            session.commit()
            return True

    def replace_items(self, order_id: int, items: List[Dict[str, Any]]) -> bool:
        with self._session_factory() as session:
            session.query(WorkOrderItem).filter(WorkOrderItem.work_order_id == order_id).delete()
            for index, item in enumerate(items):
                session.add(
                    WorkOrderItem(
                        work_order_id=order_id,
                        item_code=item["item_code"],
                        item_name=item["item_name"],
                        duration_minutes=item.get("duration_minutes", 0),
                        amount=item.get("amount", 0.0),
                        sequence=item.get("sequence", index),
                    )
                )
            session.commit()
            return True

    def cancel_order(self, order_id: int) -> bool:
        return self.update_order(order_id, status=WorkOrderStatus.CANCELLED.value)

    def complete_order(
        self, order_id: int, *, mileage: Optional[int] = None, amount: Optional[float] = None
    ) -> bool:
        updates: Dict[str, Any] = {
            "status": WorkOrderStatus.COMPLETED.value,
            "completed_at": datetime.now(),
        }
        if mileage is not None:
            updates["mileage"] = mileage
        if amount is not None:
            updates["amount"] = amount
        return self.update_order(order_id, **updates)

    def delete_order(self, order_id: int) -> bool:
        with self._session_factory() as session:
            order = session.get(WorkOrder, order_id)
            if not order:
                return False
            session.query(WorkOrderItem).filter(WorkOrderItem.work_order_id == order_id).delete()
            session.delete(order)
            session.commit()
            return True

    def delete_all(self) -> int:
        """清空工单，仅用于测试与演示数据重置。"""

        with self._session_factory() as session:
            session.query(WorkOrderItem).delete()
            count = session.query(WorkOrder).delete()
            session.commit()
            return int(count)

    # -- 读操作 ---------------------------------------------------------
    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            order = session.get(WorkOrder, order_id)
            return self._to_dict(order) if order else None

    def get_order_by_no(self, order_no: str) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            order = session.query(WorkOrder).filter(WorkOrder.order_no == order_no).one_or_none()
            return self._to_dict(order) if order else None

    def list_orders(
        self,
        *,
        owner_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        day: Optional[datetime] = None,
        start_from: Optional[datetime] = None,
        start_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(WorkOrder)
            if owner_id is not None:
                query = query.filter(WorkOrder.owner_id == owner_id)
            if vehicle_id is not None:
                query = query.filter(WorkOrder.vehicle_id == vehicle_id)
            if technician_id is not None:
                query = query.filter(WorkOrder.technician_id == technician_id)
            if bay_id is not None:
                query = query.filter(WorkOrder.bay_id == bay_id)
            if status:
                query = query.filter(WorkOrder.status == status)
            if statuses:
                query = query.filter(WorkOrder.status.in_(statuses))
            if day is not None:
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start.replace(hour=23, minute=59, second=59)
                query = query.filter(WorkOrder.start_time <= day_end).filter(WorkOrder.end_time >= day_start)
            if start_from is not None:
                query = query.filter(WorkOrder.start_time >= start_from)
            if start_to is not None:
                query = query.filter(WorkOrder.start_time <= start_to)

            query = query.order_by(WorkOrder.start_time)
            if limit:
                query = query.limit(limit)
            return [self._to_dict(item) for item in query.all()]

    def list_orders_detail(
        self,
        *,
        day: Optional[datetime] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """带技师、工位、车辆名称的工单列表，供看板与页面使用。"""

        with self._session_factory() as session:
            query = (
                session.query(WorkOrder, Technician, ServiceBay, Vehicle)
                .join(Technician, WorkOrder.technician_id == Technician.id)
                .join(ServiceBay, WorkOrder.bay_id == ServiceBay.id)
                .join(Vehicle, WorkOrder.vehicle_id == Vehicle.id)
            )
            if statuses:
                query = query.filter(WorkOrder.status.in_(statuses))
            if day is not None:
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start.replace(hour=23, minute=59, second=59)
                query = query.filter(WorkOrder.start_time <= day_end).filter(WorkOrder.end_time >= day_start)

            query = query.order_by(WorkOrder.start_time).limit(limit)
            results = []
            for order, technician, bay, vehicle in query.all():
                item = self._to_dict(order)
                item.update(
                    {
                        "technician_name": technician.name,
                        "technician_shift": technician.shift,
                        "bay_name": bay.name,
                        "bay_type": bay.bay_type,
                        "plate_no": vehicle.plate_no,
                        "vehicle_model": vehicle.model,
                    }
                )
                results.append(item)
            return results

    def list_items(self, order_id: int) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            rows = (
                session.query(WorkOrderItem)
                .filter(WorkOrderItem.work_order_id == order_id)
                .order_by(WorkOrderItem.sequence)
                .all()
            )
            return [
                {
                    "item_code": row.item_code,
                    "item_name": row.item_name,
                    "duration_minutes": row.duration_minutes,
                    "amount": row.amount,
                    "sequence": row.sequence,
                }
                for row in rows
            ]

    def is_technician_available(
        self,
        technician_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as session:
            query = (
                session.query(WorkOrder)
                .filter(WorkOrder.technician_id == technician_id)
                .filter(WorkOrder.status.in_(WorkOrderStatus.active_values()))
                .filter(self._overlap_filter(start_time, end_time))
            )
            if exclude_order_id:
                query = query.filter(WorkOrder.id != exclude_order_id)
            return query.first() is None

    def is_bay_available(
        self,
        bay_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> bool:
        """判断工位在 [start_time, end_time) 是否空闲。

        工单可能存在分段工位计划（同一工单内先举升机、后四轮定位），
        因此要按分段判断，而不是简单看 bay_id。
        """

        with self._session_factory() as session:
            query = (
                session.query(WorkOrder)
                .filter(WorkOrder.status.in_(WorkOrderStatus.active_values()))
                .filter(self._overlap_filter(start_time, end_time))
            )
            if exclude_order_id:
                query = query.filter(WorkOrder.id != exclude_order_id)

            for order in query.all():
                for window in self._segments_for_bay(order, bay_id):
                    if window[0] < end_time and start_time < window[1]:
                        return False
        return True

    @staticmethod
    def _segments_for_bay(order: WorkOrder, bay_id: int):
        """取出某个工单在指定工位上占用的时间段列表。"""

        plan = order.bay_plan or []
        windows = []
        for segment in plan:
            if segment.get("bay_id") != bay_id:
                continue
            start = _parse_moment(segment.get("start"))
            end = _parse_moment(segment.get("end"))
            if start and end:
                windows.append((start, end))
        if windows:
            return windows
        # 兼容没有分段计划的工单：整段时间都占用主工位
        if order.bay_id == bay_id:
            return [(order.start_time, order.end_time)]
        return []

    def busy_windows_for_technician(self, technician_id: int, day: datetime) -> List[Dict[str, Any]]:
        return self._busy_windows("technician_id", technician_id, day)

    def busy_windows_for_bay(self, bay_id: int, day: datetime) -> List[Dict[str, Any]]:
        return self._busy_windows("bay_id", bay_id, day)

    def _busy_windows(self, field: str, value: int, day: datetime) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start.replace(hour=23, minute=59, second=59)

            if field == "technician_id":
                rows = (
                    session.query(WorkOrder)
                    .filter(WorkOrder.technician_id == value)
                    .filter(WorkOrder.status.in_(WorkOrderStatus.active_values()))
                    .filter(WorkOrder.start_time <= day_end)
                    .filter(WorkOrder.end_time >= day_start)
                    .order_by(WorkOrder.start_time)
                    .all()
                )
                return [
                    {
                        "order_id": row.id,
                        "order_no": row.order_no,
                        "start": row.start_time,
                        "end": row.end_time,
                        "item_codes": list(row.item_codes or []),
                    }
                    for row in rows
                ]

            # 工位：按分段计划展开
            rows = (
                session.query(WorkOrder)
                .filter(WorkOrder.status.in_(WorkOrderStatus.active_values()))
                .filter(WorkOrder.start_time <= day_end)
                .filter(WorkOrder.end_time >= day_start)
                .order_by(WorkOrder.start_time)
                .all()
            )
            windows: List[Dict[str, Any]] = []
            for row in rows:
                for start, end in self._segments_for_bay(row, value):
                    windows.append(
                        {
                            "order_id": row.id,
                            "order_no": row.order_no,
                            "start": start,
                            "end": end,
                            "item_codes": list(row.item_codes or []),
                        }
                    )
            windows.sort(key=lambda item: item["start"])
            return windows

    def statistics(self) -> Dict[str, Any]:
        with self._session_factory() as session:
            total = session.query(WorkOrder).count()
            by_status = {
                status: session.query(WorkOrder).filter(WorkOrder.status == status).count()
                for status in [member.value for member in WorkOrderStatus]
            }
            return {"total": total, "by_status": by_status}

    def count_active(self) -> int:
        with self._session_factory() as session:
            return (
                session.query(WorkOrder)
                .filter(WorkOrder.status.in_(WorkOrderStatus.active_values()))
                .count()
            )