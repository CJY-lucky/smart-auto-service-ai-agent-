"""车主行为 Agent：后台智能分析 + 主动提醒。

它不依赖车主的显式请求，而是在预约、咨询、取消等交互之后被调用，
把行为沉淀下来，并在合适的时候生成提醒。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .vehicle_behavior import (
    BehaviorRecorder,
    CyclePredictor,
    PatternAnalyzer,
    PreferenceManager,
    ReminderBuilder,
)


class VehicleBehaviorAgent:
    """车主行为 Agent。"""

    def __init__(self, db_path: Optional[str] = None, behavior_service=None):
        self.db_path = db_path
        self.recorder = BehaviorRecorder(behavior_service, db_path)
        self.analyzer = PatternAnalyzer(behavior_service, db_path)
        self.preference_manager = PreferenceManager(behavior_service, db_path)
        self.cycle_predictor = CyclePredictor(db_path=db_path)
        self.reminder_builder = ReminderBuilder(behavior_service, db_path)

    # ---------------------------------------------------------------- 记录
    def record_behavior(self, action_type: str, **kwargs) -> int:
        return self.recorder.behavior_service.record_behavior(action_type, **kwargs)

    def record_booking(self, order: Dict[str, Any], owner_ref: str = "default_owner", session_id: Optional[str] = None) -> int:
        return self.recorder.record_booking(order=order, owner_ref=owner_ref, session_id=session_id)

    def record_consultation(self, question: str, categories: List[str], session_id: str, owner_ref: str = "default_owner") -> int:
        return self.recorder.record_consultation(question, categories, session_id, owner_ref)

    def record_addon_decision(self, accepted: bool, items: List[str], owner_ref: str = "default_owner") -> int:
        return self.recorder.record_addon_decision(accepted, items, owner_ref)

    # ---------------------------------------------------------------- 分析
    def get_user_analysis(self, owner_ref: str = "default_owner") -> Dict[str, Any]:
        return self.analyzer.analyze(owner_ref)

    def summarize(self, owner_ref: str = "default_owner") -> str:
        return self.analyzer.summarize(owner_ref)

    def analyze_vehicle_cycle(self, vehicle: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "due_items": self.cycle_predictor.due_items(vehicle),
            "next_service": self.cycle_predictor.next_service(vehicle),
            "next_service_text": self.cycle_predictor.describe_next_service(vehicle),
            "trigger_points": self.cycle_predictor.trigger_points(vehicle),
        }

    # ---------------------------------------------------------------- 提醒
    def get_reminder_with_schedule(self, owner_ref: str = "default_owner", *, include_weather: bool = False) -> Dict[str, Any]:
        return self.reminder_builder.with_schedule(owner_ref, include_weather=include_weather)

    def build_reminders(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        return self.reminder_builder.build(owner_ref)

    def pending_reminders(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        return self.reminder_builder.pending(owner_ref)