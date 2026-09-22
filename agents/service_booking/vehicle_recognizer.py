"""车辆识别：把车主说的车牌/车型对应到车辆档案。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.vehicle_service import VehicleService


class VehicleRecognizer:
    """车辆识别器。"""

    def __init__(self, vehicle_service: Optional[VehicleService] = None):
        self.vehicle_service = vehicle_service or VehicleService()

    def recognize(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """返回 {vehicle, plate_no, matched_by, need_new_profile, message}。"""

        plate_no = parsed.get("plate_no")
        model = parsed.get("vehicle_model")

        if plate_no:
            vehicle = self.vehicle_service.get_by_plate(plate_no)
            if vehicle:
                return {
                    "vehicle": vehicle,
                    "plate_no": vehicle["plate_no"],
                    "matched_by": "plate",
                    "need_new_profile": False,
                    "message": None,
                }
            return {
                "vehicle": None,
                "plate_no": plate_no,
                "matched_by": "plate_new",
                "need_new_profile": True,
                "message": None,
            }

        if model:
            candidates = [
                vehicle for vehicle in self.vehicle_service.list_vehicles() if model and model in (vehicle.get("model") or "")
            ]
            if len(candidates) == 1:
                vehicle = candidates[0]
                return {
                    "vehicle": vehicle,
                    "plate_no": vehicle["plate_no"],
                    "matched_by": "model",
                    "need_new_profile": False,
                    "message": None,
                }
            if len(candidates) > 1:
                return {
                    "vehicle": None,
                    "plate_no": None,
                    "matched_by": "model_ambiguous",
                    "need_new_profile": False,
                    "message": f"我们店里有 {len(candidates)} 台{model}在保养，方便发一下车牌号吗？",
                }

        return {
            "vehicle": None,
            "plate_no": None,
            "matched_by": "none",
            "need_new_profile": False,
            "message": "方便告诉我您的车牌号吗？我帮您调出车辆档案，这样能按里程推荐该做的项目。",
        }