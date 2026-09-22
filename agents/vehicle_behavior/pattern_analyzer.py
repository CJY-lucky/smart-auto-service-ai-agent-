"""行为模式分析：把原始行为记录变成可用的结论。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.vehicle_behavior_service import VehicleBehaviorService


class PatternAnalyzer:
    """行为模式分析。"""

    def __init__(self, behavior_service: Optional[VehicleBehaviorService] = None, db_path: Optional[str] = None):
        self.behavior_service = behavior_service or VehicleBehaviorService(db_path)

    def analyze(self, owner_ref: str = "default_owner") -> Dict[str, Any]:
        return self.behavior_service.analyze(owner_ref)

    def summarize(self, owner_ref: str = "default_owner") -> str:
        """给一句人话总结，便于在对话里直接说出来。"""

        analysis = self.analyze(owner_ref)
        parts = []
        if analysis.get("favorite_technician_name"):
            parts.append(f"您比较常找{analysis['favorite_technician_name']}技师")
        if analysis.get("favorite_service_name"):
            parts.append(f"最常做的项目是{analysis['favorite_service_name']}")
        if analysis.get("preferred_time_period"):
            parts.append(f"习惯{analysis['preferred_time_period']}到店")
        if analysis.get("total_appointments"):
            parts.append(f"累计到店 {analysis['total_appointments']} 次")
        if analysis.get("price_sensitivity") == "high":
            parts.append("对价格比较敏感，建议优先推荐高性价比方案")
        return "，".join(parts) + "。" if parts else "目前还没有足够的到店记录，多来几次我就能摸清您的用车习惯了。"