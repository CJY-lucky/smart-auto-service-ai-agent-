"""周期推算：回答"这辆车下次该什么时候做什么项目"。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.vehicle_service import VehicleService


class CyclePredictor:
    """保养周期推算。"""

    def __init__(self, vehicle_service: Optional[VehicleService] = None, db_path: Optional[str] = None):
        self.vehicle_service = vehicle_service or VehicleService(db_path)

    def due_items(self, vehicle: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.vehicle_service.due_items(vehicle)

    def next_service(self, vehicle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.vehicle_service.next_service_estimate(vehicle)

    def trigger_points(self, vehicle: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.vehicle_service.cycle_trigger_points(vehicle)

    def describe_next_service(self, vehicle: Dict[str, Any]) -> str:
        estimate = self.next_service(vehicle)
        if not estimate:
            return "档案信息不足，暂时无法推算下次保养节点。"
        parts = []
        if estimate.get("next_mileage"):
            parts.append(f"下次保养里程约 {estimate['next_mileage']} 公里")
        if estimate.get("remaining_km") is not None:
            parts.append(f"还差约 {estimate['remaining_km']} 公里")
        if estimate.get("next_date"):
            parts.append(f"时间上建议 {estimate['next_date'].strftime('%Y-%m-%d')} 前后")
        if estimate.get("days_left") is not None:
            parts.append(f"还有 {estimate['days_left']} 天")
        return "，".join(parts) + "。"