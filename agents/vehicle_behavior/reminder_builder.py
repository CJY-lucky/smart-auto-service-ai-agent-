"""提醒构建：把周期结论变成可以直接发给车主的提醒。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.vehicle_behavior_service import VehicleBehaviorService


class ReminderBuilder:
    """提醒生成。"""

    def __init__(self, behavior_service: Optional[VehicleBehaviorService] = None, db_path: Optional[str] = None):
        self.behavior_service = behavior_service or VehicleBehaviorService(db_path)

    def build(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        return self.behavior_service.build_reminders(owner_ref)

    def with_schedule(self, owner_ref: str = "default_owner", *, include_weather: bool = False) -> Dict[str, Any]:
        return self.behavior_service.get_reminder_with_schedule(owner_ref, include_weather=include_weather)

    def pending(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        return self.behavior_service.pending_reminders(owner_ref)

    def mark_sent(self, reminder_id: int) -> bool:
        return self.behavior_service.db.behaviors.mark_reminder_sent(reminder_id)