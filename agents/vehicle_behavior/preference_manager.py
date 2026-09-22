"""偏好管理：读写在排班与推荐中真正会用到的偏好。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.vehicle_behavior_service import VehicleBehaviorService


class PreferenceManager:
    """车主偏好。"""

    def __init__(self, behavior_service: Optional[VehicleBehaviorService] = None, db_path: Optional[str] = None):
        self.behavior_service = behavior_service or VehicleBehaviorService(db_path)

    @property
    def _repository(self):
        return self.behavior_service.db.behaviors

    def list_preferences(self, owner_ref: str = "default_owner", preference_type: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._repository.get_preferences(owner_ref, preference_type)

    def update_preference(self, owner_ref: str, preference_type: str, preference_value: str) -> bool:
        self._repository.upsert_preference(owner_ref, preference_type, preference_value)
        return True

    def preferred_technician_id(self, owner_ref: str = "default_owner") -> Optional[int]:
        for preference in self.list_preferences(owner_ref, "technician"):
            if str(preference["preference_value"]).isdigit():
                return int(preference["preference_value"])
        return None

    def preference_summary(self, owner_ref: str = "default_owner") -> Dict[str, Any]:
        preferences = self.list_preferences(owner_ref)
        summary: Dict[str, Any] = {}
        for preference in preferences:
            summary.setdefault(preference["preference_type"], preference["preference_value"])
        return summary