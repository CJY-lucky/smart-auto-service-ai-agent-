"""车辆档案服务。

负责车辆档案的增删改查，以及"这辆车下次该做什么"的周期推理：
按里程与时间双维度比对每个保养项目的周期，产出到期项目清单。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.constants import ReminderType
from config.service_catalog import SERVICE_ITEMS, get_service_item
from config.time_config import time_config
from db.db_router import get_database_router

logger = logging.getLogger(__name__)

# 到达周期的 90% 就提前提醒，留出预约缓冲
DUE_RATIO = 0.9

PLATE_PATTERN = re.compile(r"[\u4e00-\u9fa5][A-Z][A-Z0-9]{5,6}")


class VehicleService:
    """车辆档案与保养周期推理。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)

    # -- 车主 -----------------------------------------------------------
    def ensure_owner(self, owner_ref: str, name: Optional[str] = None) -> int:
        return self.db.owners.ensure_owner(owner_ref, name)

    def get_owner(self, owner_id: int) -> Optional[Dict[str, Any]]:
        return self.db.owners.get_by_id(owner_id)

    # -- 车辆档案 ---------------------------------------------------------
    def create_vehicle(self, owner_id: int, plate_no: str, **fields) -> int:
        return self.db.vehicles.add_vehicle(owner_id, plate_no, **fields)

    def ensure_vehicle(self, owner_id: int, plate_no: str, **fields) -> int:
        """按车牌查档案，没有就建一条新档案。"""

        existing = self.db.vehicles.get_by_plate(plate_no)
        if existing:
            self.db.vehicles.update_vehicle(existing["id"], **fields)
            return existing["id"]
        return self.db.vehicles.add_vehicle(owner_id, plate_no, **fields)

    def get_by_plate(self, plate_no: str) -> Optional[Dict[str, Any]]:
        return self.db.vehicles.get_by_plate(plate_no)

    def get_vehicle(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        return self.db.vehicles.get_by_id(vehicle_id)

    def list_by_owner(self, owner_id: int) -> List[Dict[str, Any]]:
        return self.db.vehicles.list_by_owner(owner_id)

    def list_vehicles(self) -> List[Dict[str, Any]]:
        return self.db.vehicles.list_vehicles()

    def update_vehicle(self, vehicle_id: int, **updates) -> bool:
        return self.db.vehicles.update_vehicle(vehicle_id, **updates)

    @staticmethod
    def extract_plate_no(text: str) -> Optional[str]:
        """从口语化输入里提取车牌号。"""

        if not text:
            return None
        normalized = str(text).upper().replace(" ", "")
        match = PLATE_PATTERN.search(normalized)
        return match.group(0) if match else None

    def update_mileage(self, vehicle_id: int, mileage: int) -> bool:
        return self.db.vehicles.update_vehicle(vehicle_id, mileage=int(mileage))

    def record_service(
        self,
        vehicle_id: int,
        item_codes: List[str],
        *,
        mileage: Optional[int] = None,
        service_date: Optional[datetime] = None,
    ) -> bool:
        """工单完成后回写档案：更新里程与上次保养时间。"""

        vehicle = self.db.vehicles.get_by_id(vehicle_id)
        if not vehicle:
            return False

        updates: Dict[str, Any] = {}
        service_date = service_date or time_config.now()
        if any(get_service_item(code) and get_service_item(code).category == "保养" for code in item_codes):
            updates["last_service_date"] = service_date
            updates["last_service_mileage"] = mileage if mileage is not None else vehicle.get("mileage")
        if mileage is not None:
            updates["mileage"] = int(mileage)
        if not updates:
            return False
        return self.db.vehicles.update_vehicle(vehicle_id, **updates)

    # -- 周期推理 ---------------------------------------------------------
    def due_items(self, vehicle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按里程与时间推算到期（或即将到期）的保养项目。"""

        if not vehicle:
            return []

        mileage = vehicle.get("mileage")
        last_service_date = vehicle.get("last_service_date")
        last_service_mileage = vehicle.get("last_service_mileage")

        baseline_date = last_service_date or vehicle.get("purchase_date")
        baseline_mileage = last_service_mileage if last_service_mileage is not None else 0
        months_since = self._months_since(baseline_date)
        km_since = (mileage - baseline_mileage) if (mileage is not None) else None

        results: List[Dict[str, Any]] = []
        for item in SERVICE_ITEMS.values():
            if item.category != "保养" or item.interval_km is None and item.interval_months is None:
                continue

            reasons: List[str] = []
            progress_values: List[float] = []

            if item.interval_km and km_since is not None:
                progress = km_since / item.interval_km
                progress_values.append(progress)
                if progress >= DUE_RATIO:
                    reasons.append(f"距上次保养已行驶约 {km_since} 公里（建议 {item.interval_km} 公里）")

            if item.interval_months and months_since is not None:
                progress = months_since / item.interval_months
                progress_values.append(progress)
                if progress >= 1.0:
                    reasons.append(f"距上次保养已 {months_since:.1f} 个月（建议 {item.interval_months} 个月）")

            if not reasons:
                continue

            progress = max(progress_values) if progress_values else 0.0
            results.append(
                {
                    "item_code": item.code,
                    "item_name": item.name,
                    "reasons": reasons,
                    "progress": round(progress, 2),
                    "severity": "high" if progress >= 1.0 else "medium",
                    "estimated_amount": item.amount,
                    "duration_minutes": item.duration_minutes,
                }
            )

        results.sort(key=lambda record: record["progress"], reverse=True)
        return results

    def next_service_estimate(self, vehicle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """推算下次常规保养（机油机滤）的里程与时间节点。"""

        if not vehicle:
            return None
        item = get_service_item("oil_change")
        if item is None:
            return None

        baseline_mileage = vehicle.get("last_service_mileage")
        if baseline_mileage is None:
            baseline_mileage = vehicle.get("mileage") or 0
        next_mileage = baseline_mileage + (item.interval_km or 10000)

        baseline_date = vehicle.get("last_service_date") or vehicle.get("purchase_date")
        next_date = None
        if baseline_date:
            months = item.interval_months or 12
            next_date = self._add_months(baseline_date, months)

        remaining_km = None
        if vehicle.get("mileage") is not None:
            remaining_km = max(next_mileage - int(vehicle["mileage"]), 0)

        days_left = None
        if next_date:
            days_left = (next_date.date() - time_config.now().date()).days

        return {
            "next_mileage": next_mileage,
            "next_date": next_date,
            "remaining_km": remaining_km,
            "days_left": days_left,
        }

    def cycle_trigger_points(self, vehicle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """年检、电瓶、刹车片等易损件的触发点（用于主动提醒）。"""

        if not vehicle:
            return []

        triggers: List[Dict[str, Any]] = []
        purchase_date = vehicle.get("purchase_date")
        mileage = vehicle.get("mileage")

        if purchase_date:
            months = self._months_since(purchase_date)
            triggers.append(
                {
                    "type": ReminderType.INSPECTION.value,
                    "title": "年检到期提醒",
                    "detail": f"车辆上牌至今约 {months:.0f} 个月，请确认年检有效期。",
                }
            )
            if months >= 20:
                triggers.append(
                    {
                        "type": ReminderType.BATTERY.value,
                        "title": "电瓶健康检查",
                        "detail": f"电瓶使用已约 {months:.0f} 个月，建议做一次电瓶健康检测。",
                    }
                )

        if mileage is not None:
            progress = (mileage % 40000) / 40000
            triggers.append(
                {
                    "type": ReminderType.BRAKE_PAD.value,
                    "title": "刹车片检查点",
                    "detail": f"当前里程 {mileage} 公里，正处于刹车片检查区间内。",
                    "progress": round(progress, 2),
                }
            )

        return triggers

    # -- 内部工具 ---------------------------------------------------------
    @staticmethod
    def _months_since(moment: Optional[datetime]) -> Optional[float]:
        if not moment:
            return None
        now = time_config.now()
        return max((now - moment).days / 30.4, 0.0)

    @staticmethod
    def _add_months(moment: datetime, months: int) -> datetime:
        month_index = moment.month - 1 + months
        year = moment.year + month_index // 12
        month = month_index % 12 + 1
        day = min(moment.day, 28)
        return moment.replace(year=year, month=month, day=day)