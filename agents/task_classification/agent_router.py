"""Agent 路由器：根据分类结果把请求交给对应 Agent。"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional

from config.time_config import time_config
from services.vehicle_behavior_service import VehicleBehaviorService
from services.vehicle_service import VehicleService

from .state_manager import StateManager

logger = logging.getLogger(__name__)


class AgentRouter:
    """路由与协调。"""

    def __init__(
        self,
        booking_agent: Any,
        consultant_agent: Any,
        behavior_agent: Any,
        state_manager: StateManager,
        db_path: Optional[str] = None,
    ):
        self.booking_agent = booking_agent
        self.consultant_agent = consultant_agent
        self.behavior_agent = behavior_agent
        self.state_manager = state_manager
        self.vehicle_service = VehicleService(db_path)
        self.behavior_service = VehicleBehaviorService(db_path)
        self._sync_states()

    def _sync_states(self) -> None:
        for agent in (self.booking_agent, self.consultant_agent):
            if agent is not None and hasattr(agent, "set_shared_state"):
                agent.set_shared_state(self.state_manager.state)

    # ---------------------------------------------------------------- 路由
    async def route_to_booking(self, task: str, owner_ref: str = "default_owner") -> AsyncGenerator[str, None]:
        if self.booking_agent is None:
            yield "[ERROR]预约服务暂时不可用"
            return
        self.state_manager.transition_to_booking()
        yield "[THOUGHT][归类机器人]这是预约相关需求，我转给预约机器人处理。"
        try:
            async for token in self.booking_agent.run_stream(user_input=task, owner_ref=owner_ref):
                yield token
        except Exception as exc:  # pragma: no cover
            yield f"[ERROR]预约处理失败：{exc}"
            self.state_manager.force_reset()

    async def route_to_consultation(self, task: str, owner_ref: str = "default_owner") -> AsyncGenerator[str, None]:
        if self.consultant_agent is None:
            yield "[ERROR]咨询服务暂时不可用"
            return
        self.state_manager.transition_to_consultation()
        yield "[THOUGHT][归类机器人]这是咨询类问题，我转给咨询机器人解答。"
        try:
            async for token in self.consultant_agent.consult_stream(task, owner_ref=owner_ref):
                yield token
        except Exception as exc:  # pragma: no cover
            yield f"[ERROR]咨询处理失败：{exc}"
            self.state_manager.force_reset()

    async def route_to_vehicle_profile(self, task: str, owner_ref: str = "default_owner") -> AsyncGenerator[str, None]:
        self.state_manager.transition_to_booking()
        yield "[THOUGHT][归类机器人]车主在查询车辆档案，我直接查一下。"
        reply = self._describe_vehicle_profile(task, owner_ref)
        yield "[REPLY][归类机器人]"
        for char in reply:
            yield char
        self.state_manager.force_reset()

    async def route_to_behavior(self, task: str, owner_ref: str = "default_owner") -> AsyncGenerator[str, None]:
        self.state_manager.transition_to_behavior()
        yield "[THOUGHT][归类机器人]这是查看用车习惯的请求，我调一下行为分析。"
        analysis = self.behavior_service.analyze(owner_ref)
        summary = self.behavior_agent.summarize(owner_ref) if self.behavior_agent else ""
        lines = ["[REPLY][归类机器人]"]
        lines.append(summary)
        if analysis.get("due_reminders"):
            first = analysis["due_reminders"][0]
            due_names = "、".join(item["item_name"] for item in first["due_items"][:2])
            lines.append(f"\n另外提醒您，{first['plate_no']} 建议做：{due_names}。")
        if analysis.get("total_spending"):
            lines.append(f"\n您在门店累计消费约 {analysis['total_spending']} 元。")
        for char in "".join(lines):
            yield char
        self.state_manager.force_reset()

    async def handle_unsupported_task(self, category: str) -> AsyncGenerator[str, None]:
        reply = "这个问题我暂时帮不上忙。我可以帮您安排保养预约，或者解答保养周期、价格、故障灯这类问题。"
        yield "[REPLY][归类机器人]"
        for char in reply:
            yield char

    # ---------------------------------------------------------------- 档案查询
    def _describe_vehicle_profile(self, task: str, owner_ref: str) -> str:
        owner = self.vehicle_service.db.owners.get_by_ref(owner_ref)
        if not owner:
            return "暂时没有查到您的车辆档案。把车牌号发给我，我帮您建一份，之后就能按里程提醒您保养了。"

        vehicles = self.vehicle_service.list_by_owner(owner["id"])
        if not vehicles:
            return "还没有您的车辆档案。告诉我车牌号和车型，我马上帮您建立。"

        plate = self.vehicle_service.extract_plate_no(task)
        target = None
        if plate:
            target = next((item for item in vehicles if item["plate_no"] == plate), None)
        target = target or vehicles[0]

        orders = self.vehicle_service.db.work_orders.list_orders(vehicle_id=target["id"], limit=3)
        lines = [
            f"车辆档案：{target['plate_no']}（{target.get('model') or '车型未登记'}，{target.get('year') or '年款未登记'}）",
            f"当前里程：{target.get('mileage') or '未登记'} 公里",
            f"上次保养：{target['last_service_date'].strftime('%Y-%m-%d') if target.get('last_service_date') else '暂无记录'}",
        ]
        estimate = self.vehicle_service.next_service_estimate(target)
        if estimate:
            lines.append(
                f"下次保养：约 {estimate['next_mileage']} 公里"
                + (f"（还有 {estimate['remaining_km']} 公里）" if estimate.get("remaining_km") is not None else "")
            )
        if orders:
            latest = orders[0]
            lines.append(f"最近一次工单：{latest['order_no']}（{time_config.format_datetime(latest['start_time'])}）")
        due_items = self.vehicle_service.due_items(target)
        if due_items:
            lines.append("按周期建议项目：" + "、".join(item["item_name"] for item in due_items[:3]))
        return "\n".join(lines)

    def get_available_services(self) -> list:
        services = []
        if self.booking_agent:
            services.append("预约工单")
        if self.consultant_agent:
            services.append("知识咨询")
        if self.behavior_agent:
            services.append("车主行为分析")
        services.append("车辆档案查询")
        return services