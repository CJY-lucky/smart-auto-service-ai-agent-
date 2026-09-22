"""车主行为服务：行为记录、模式分析与个性化提醒。

行为数据不做"展示型统计"，而是要能反过来影响业务：偏好技师用于排班排序，
价格敏感度用于调整加项建议的力度，周期推理用于决定什么时候该主动提醒。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.constants import BehaviorAction, WorkOrderStatus
from config.service_catalog import get_service_item
from config.time_config import time_config
from db.db_router import get_database_router
from services.scheduling_service import SchedulingService
from services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)

REMINDER_DAYS_THRESHOLD = 90


class VehicleBehaviorService:
    """车主行为分析与提醒生成。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)
        self.vehicle_service = VehicleService(db_path)
        self.scheduling_service = SchedulingService(db_path)

    # ---------------------------------------------------------------- 记录
    def record_behavior(
        self,
        action_type: str,
        *,
        owner_ref: str = "default_owner",
        action_data: Optional[Dict[str, Any]] = None,
        technician_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        return self.db.behaviors.record_behavior(
            owner_id=owner_ref,
            action_type=action_type,
            action_data=action_data or {},
            technician_id=technician_id,
            vehicle_id=vehicle_id,
            session_id=session_id,
        )

    def get_behaviors(
        self, owner_ref: str = "default_owner", action_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.db.behaviors.get_behaviors(owner_ref, action_type=action_type, limit=limit)

    # ---------------------------------------------------------------- 分析
    def analyze(self, owner_ref: str = "default_owner") -> Dict[str, Any]:
        """行为模式分析结果，供行为分析页面与推荐逻辑使用。"""

        owner = self.db.owners.get_by_ref(owner_ref)
        if not owner:
            return self._empty_analysis(owner_ref)

        behaviors = self.db.behaviors.get_behaviors(owner_ref, limit=500)
        orders = self.db.work_orders.list_orders(owner_id=owner["id"], limit=200)
        preferences = self.db.behaviors.get_preferences(owner_ref)

        booking_behaviors = [item for item in behaviors if item["action_type"] == BehaviorAction.BOOKING.value]
        consultation_behaviors = [
            item for item in behaviors if item["action_type"] == BehaviorAction.CONSULTATION.value
        ]
        cancel_count = len([item for item in behaviors if item["action_type"] == BehaviorAction.CANCEL.value])
        accepted = len([item for item in behaviors if item["action_type"] == BehaviorAction.ADDON_ACCEPTED.value])
        declined = len([item for item in behaviors if item["action_type"] == BehaviorAction.ADDON_DECLINED.value])

        favorite_technician_id = self._favorite_technician(preferences, booking_behaviors, orders)
        favorite_technician_name = None
        if favorite_technician_id:
            technician = self.db.technicians.get_by_id(favorite_technician_id)
            favorite_technician_name = technician["name"] if technician else None

        favorite_service = self._favorite_service(preferences, orders)
        favorite_service_name = None
        if favorite_service and get_service_item(favorite_service):
            favorite_service_name = get_service_item(favorite_service).name

        durations = [order["estimated_minutes"] for order in orders if order.get("estimated_minutes")]
        average_duration = int(sum(durations) / len(durations)) if durations else None

        last_order = orders[0] if orders else None
        days_since_last = None
        if last_order:
            days_since_last = (time_config.now() - last_order["start_time"]).days

        vehicles = self.db.vehicles.list_by_owner(owner["id"])
        due_summary = []
        for vehicle in vehicles:
            due_items = self.vehicle_service.due_items(vehicle)
            if due_items:
                due_summary.append(
                    {
                        "vehicle_id": vehicle["id"],
                        "plate_no": vehicle["plate_no"],
                        "due_items": due_items,
                    }
                )

        topics = self._consultation_topics(consultation_behaviors)
        price_sensitivity = self._price_sensitivity(accepted, declined)
        total_spending = round(sum(order["amount"] or 0 for order in orders if order["status"] == WorkOrderStatus.COMPLETED.value), 2)

        should_send_reminder = bool(due_summary) or (
            days_since_last is not None and days_since_last >= REMINDER_DAYS_THRESHOLD
        )

        return {
            "owner_id": owner_ref,
            "owner_name": owner.get("name"),
            "favorite_technician_id": favorite_technician_id,
            "favorite_technician_name": favorite_technician_name,
            "favorite_service": favorite_service,
            "favorite_service_name": favorite_service_name,
            "favorite_duration": average_duration,
            "preferred_time_period": self._preference_value(preferences, "time_period"),
            "total_appointments": len(orders),
            "active_appointments": len(
                [order for order in orders if order["status"] == WorkOrderStatus.CREATED.value]
            ),
            "cancel_count": cancel_count,
            "consultation_count": len(consultation_behaviors),
            "consultation_topics": topics,
            "addon_accept_rate": round(accepted / (accepted + declined), 2) if (accepted + declined) else None,
            "price_sensitivity": price_sensitivity,
            "days_since_last_appointment": days_since_last,
            "total_spending": total_spending,
            "vehicles": vehicles,
            "due_reminders": due_summary,
            "should_send_reminder": should_send_reminder,
            "behaviors": behaviors[:50],
            "orders": orders[:20],
        }

    def _empty_analysis(self, owner_ref: str) -> Dict[str, Any]:
        return {
            "owner_id": owner_ref,
            "owner_name": None,
            "favorite_technician_id": None,
            "favorite_technician_name": None,
            "favorite_service": None,
            "favorite_service_name": None,
            "favorite_duration": None,
            "preferred_time_period": None,
            "total_appointments": 0,
            "active_appointments": 0,
            "cancel_count": 0,
            "consultation_count": 0,
            "consultation_topics": [],
            "addon_accept_rate": None,
            "price_sensitivity": "unknown",
            "days_since_last_appointment": None,
            "total_spending": 0,
            "vehicles": [],
            "due_reminders": [],
            "should_send_reminder": False,
            "behaviors": [],
            "orders": [],
        }

    @staticmethod
    def _preference_value(preferences: List[Dict[str, Any]], preference_type: str) -> Optional[str]:
        for preference in preferences:
            if preference["preference_type"] == preference_type:
                return preference["preference_value"]
        return None

    def _favorite_technician(
        self, preferences: List[Dict[str, Any]], behaviors: List[Dict[str, Any]], orders: List[Dict[str, Any]]
    ) -> Optional[int]:
        preference = self._preference_value(preferences, "technician")
        if preference and preference.isdigit():
            return int(preference)

        counter: Dict[int, int] = {}
        for behavior in behaviors:
            technician_id = behavior.get("technician_id")
            if technician_id:
                counter[technician_id] = counter.get(technician_id, 0) + 1
        for order in orders:
            technician_id = order.get("technician_id")
            if technician_id:
                counter[technician_id] = counter.get(technician_id, 0) + 1
        if not counter:
            return None
        return max(counter.items(), key=lambda item: item[1])[0]

    def _favorite_service(self, preferences: List[Dict[str, Any]], orders: List[Dict[str, Any]]) -> Optional[str]:
        preference = self._preference_value(preferences, "service")
        if preference:
            return preference
        counter: Dict[str, int] = {}
        for order in orders:
            for code in order.get("item_codes") or []:
                counter[code] = counter.get(code, 0) + 1
        if not counter:
            return None
        return max(counter.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _consultation_topics(behaviors: List[Dict[str, Any]], limit: int = 5) -> List[str]:
        counter: Dict[str, int] = {}
        for behavior in behaviors:
            data = behavior.get("action_data") or {}
            for category in data.get("categories") or []:
                counter[category] = counter.get(category, 0) + 1
        ranked = sorted(counter.items(), key=lambda item: item[1], reverse=True)
        return [name for name, _ in ranked[:limit]]

    @staticmethod
    def _price_sensitivity(accepted: int, declined: int) -> str:
        total = accepted + declined
        if total == 0:
            return "unknown"
        accept_rate = accepted / total
        if accept_rate >= 0.7:
            return "low"
        if accept_rate >= 0.4:
            return "medium"
        return "high"

    # ---------------------------------------------------------------- 提醒
    def build_reminders(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        """按车辆周期生成提醒条目（不落库）。"""

        owner = self.db.owners.get_by_ref(owner_ref)
        if not owner:
            return []

        reminders: List[Dict[str, Any]] = []
        for vehicle in self.db.vehicles.list_by_owner(owner["id"]):
            due_items = self.vehicle_service.due_items(vehicle)
            if due_items:
                top = due_items[0]
                content = (
                    f"{vehicle['plate_no']} 该做保养了：{'；'.join(top['reasons'])}，"
                    f"建议项目为{top['item_name']}。"
                )
                reminders.append(
                    {
                        "owner_id": owner_ref,
                        "vehicle_id": vehicle["id"],
                        "reminder_type": "maintenance",
                        "content": content,
                        "due_date": time_config.now(),
                        "due_items": due_items,
                    }
                )

            for trigger in self.vehicle_service.cycle_trigger_points(vehicle):
                reminders.append(
                    {
                        "owner_id": owner_ref,
                        "vehicle_id": vehicle["id"],
                        "reminder_type": trigger["type"],
                        "content": f"{vehicle['plate_no']}：{trigger['title']}——{trigger['detail']}",
                        "due_date": time_config.now(),
                    }
                )
        return reminders

    def get_reminder_with_schedule(
        self, owner_ref: str = "default_owner", *, include_weather: bool = False
    ) -> Dict[str, Any]:
        """生成一条带"可预约时段"的提醒（用于回访触达）。"""

        owner = self.db.owners.get_by_ref(owner_ref)
        owner_name = owner["name"] if owner else "您好"

        vehicles = self.db.vehicles.list_by_owner(owner["id"]) if owner else []
        if not vehicles:
            return {
                "message": f"{owner_name}，目前还没有您的车辆档案。方便的话把车牌和车型发给我，我帮您建立档案并推算保养时间。",
                "available_slots": [],
                "due_items": [],
            }

        vehicle = vehicles[0]
        due_items = self.vehicle_service.due_items(vehicle)
        if due_items:
            item_names = "、".join(item["item_name"] for item in due_items[:2])
            item_codes = [item["item_code"] for item in due_items[:2]]
            lead = f"{owner_name}，您的 {vehicle['plate_no']} 已经到保养节点，建议做{item_names}。"
        else:
            item_codes = ["oil_change"]
            lead = f"{owner_name}，您的 {vehicle['plate_no']} 距上次保养已有一段时间，建议回店做一次常规保养。"

        suggestions = self.scheduling_service.suggest_slots(item_codes, time_config.now(), limit=3)
        slots = [
            {
                "start_time": time_config.format_datetime(solution.start_time),
                "friendly": time_config.friendly_datetime(solution.start_time),
                "technician_name": solution.technician["name"],
                "bay_name": solution.bay["name"],
                "duration_minutes": solution.duration_minutes,
            }
            for solution in suggestions
        ]

        if slots:
            slot_text = "、".join(slot["friendly"] for slot in slots)
            message = f"{lead} 目前最近的空闲时段是 {slot_text}，需要我帮您预约吗？"
        else:
            message = f"{lead} 目前工位比较紧张，建议致电门店确认最近的档期。"

        weather_note = None
        if include_weather:
            weather_note = fetch_weather_note()
            if weather_note:
                message = f"{message}\n{weather_note}"

        return {
            "message": message,
            "available_slots": slots,
            "due_items": due_items,
            "vehicle": vehicle,
            "weather": weather_note,
        }

    def record_addon_decision(self, owner_ref: str, accepted: bool, items: List[str]) -> None:
        """记录车主对加项建议的态度（用于价格敏感度分析）。"""

        self.record_behavior(
            BehaviorAction.ADDON_ACCEPTED.value if accepted else BehaviorAction.ADDON_DECLINED.value,
            owner_ref=owner_ref,
            action_data={"items": items},
        )


def fetch_weather_note(city: Optional[str] = None) -> Optional[str]:
    """调用天气接口生成一句用车提示；未配置密钥时返回 None。"""

    from config.settings import settings

    api_key = settings.openweather_api_key
    if not api_key:
        return None

    try:
        import requests

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city or settings.weather_city, "appid": api_key, "units": "metric", "lang": "zh_cn"},
            timeout=8,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        description = data.get("weather", [{}])[0].get("description", "")
        temperature = data.get("main", {}).get("temp")
        if temperature is None:
            return None

        note = f"当前天气{description}，气温 {temperature:.0f}℃。"
        if temperature is not None and temperature <= 5:
            note += "气温偏低，提醒您留意电瓶与胎压状态。"
        elif "雨" in description or "雪" in description:
            note += "路面湿滑，建议检查轮胎与雨刮。"
        return note
    except Exception:  # pragma: no cover - 外部服务失败不影响主流程
        logger.debug("获取天气信息失败，已忽略")
        return None