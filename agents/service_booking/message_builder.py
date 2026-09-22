"""预约流程的消息构建。

统一负责"把结构化的排期结果翻译成人话"，让 Processor 专注流程控制。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from config.service_catalog import get_service_item
from config.time_config import time_config

ROLE = "预约机器人"

MISSING_PROMPTS = {
    "plate_no": "方便告诉我您的车牌号吗？我帮您调出车辆档案。",
    "start_time": "您希望什么时候到店？比如“明天上午10点”。",
    "item_codes": "这次想做什么项目呢？比如换机油、四轮定位，或者您也可以说“按里程该做什么就做什么”。",
    "vehicle_model": "您的车是什么车型？",
}


class MessageBuilder:
    """预约相关文案。"""

    role = ROLE

    # ---------------------------------------------------------------- 思考过程
    @staticmethod
    def thought(text: str) -> str:
        return f"[THOUGHT][{ROLE}] {text}\n"

    @staticmethod
    def reply(text: str) -> str:
        return f"[REPLY][{ROLE}]{text}"

    # ---------------------------------------------------------------- 追问
    def ask_missing(self, missing: List[str]) -> str:
        questions = [MISSING_PROMPTS.get(field, f"请补充{field}信息") for field in missing]
        return "\n" + " ".join(questions) + "\n"

    # ---------------------------------------------------------------- 加项建议
    def suggest_addons(self, vehicle: Dict[str, Any], due_items: List[Dict[str, Any]]) -> str:
        lines = [f"\n您的 {vehicle.get('plate_no')}（{vehicle.get('model') or '车型未登记'}，当前里程 {vehicle.get('mileage') or '未登记'} 公里）按里程和时间推算，建议同时做："]
        for index, item in enumerate(due_items[:4], 1):
            reason = "；".join(item["reasons"])
            lines.append(f"{index}. {item['item_name']}（约 {item['duration_minutes']} 分钟，参考价 {item['estimated_amount']:.0f} 元）—— {reason}")
        lines.append("需要我一并安排进这次的预约吗？回复“要”或“不用”都可以。")
        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------------- 冲突与备选
    def describe_conflict(self, result) -> str:
        reasons = result.reason_texts or ["暂时无法安排这个时间"]
        return "\n" + "，".join(reasons) + "。\n"

    def suggest_slots(self, slots: List[Dict[str, Any]], *, note: Optional[str] = None) -> str:
        lines = ["\n" + (note or "这个时间段排不开，这几个时间段可以安排：")]
        for index, slot in enumerate(slots, 1):
            start_time = slot.get("start_time")
            if isinstance(start_time, datetime):
                friendly = time_config.friendly_datetime(start_time)
            else:
                friendly = str(start_time)
            technician_name = (slot.get("technician") or {}).get("name", "技师")
            bay_name = (slot.get("bay") or {}).get("name", "工位")
            lines.append(f"{index}. {friendly} 由 {technician_name} 在 {bay_name} 施工（约 {slot.get('duration_minutes', 0)} 分钟）")
        lines.append("回复序号或者直接说您方便的时间都可以。")
        return "\n".join(lines) + "\n"

    def suggest_alternative_technician(self, original_name: str, solution) -> str:
        technician_name = solution.technician["name"]
        return (
            f"\n{original_name}技师在您选的时间已经排满了。"
            f"{technician_name}技师具备同样的资质，"
            f"{time_config.friendly_datetime(solution.start_time)}有空，要帮您约{technician_name}技师吗？\n"
        )

    # ---------------------------------------------------------------- 成功
    def appointment_success(
        self,
        order: Dict[str, Any],
        solution,
        *,
        weather_note: Optional[str] = None,
        extra_items: Optional[List[str]] = None,
    ) -> str:
        item_names = "、".join(
            get_service_item(code).name for code in (order.get("item_codes") or []) if get_service_item(code)
        )
        lines = [
            "\n预约成功！",
            f"工单号：{order.get('order_no')}",
            f"时间：{time_config.friendly_datetime(order['start_time'])}-{order['end_time']:%H:%M}",
            f"项目：{item_names or '待定'}",
            f"技师：{solution.technician['name']}（{solution.technician.get('level') or '技师'}）",
            f"工位：{' → '.join(solution.bay_names)}",
            f"预计工时：{order.get('estimated_minutes')} 分钟，参考金额：{order.get('amount'):.0f} 元",
        ]
        if weather_note:
            lines.append(weather_note)
        lines.append("到店前 10 分钟可以电话联系前台，我们会提前把车开进工位。")
        return "\n".join(lines) + "\n"

    def reschedule_success(self, order: Dict[str, Any], solution) -> str:
        return (
            f"\n已为您改约：工单号 {order.get('order_no')}，"
            f"新时间 {time_config.friendly_datetime(order['start_time'])}-{order['end_time']:%H:%M}，"
            f"技师 {solution.technician['name']}，工位 {solution.bay['name']}。\n"
        )

    def cancel_success(self, order: Dict[str, Any]) -> str:
        return f"\n已为您取消工单 {order.get('order_no')}（{time_config.friendly_datetime(order['start_time'])}）。需要重新安排随时告诉我。\n"

    # ---------------------------------------------------------------- 兜底
    def appointment_failed(self, result) -> str:
        return "\n抱歉，这个时间暂时安排不了：" + "，".join(result.reason_texts) + "。您可以换个时间，或者减少部分项目。\n"

    def save_failed(self) -> str:
        return "\n抱歉，工单保存失败了，请稍后再试或直接致电门店。\n"

    def parse_error(self) -> str:
        return f"[REPLY][{ROLE}]\n抱歉，我没太理解，可以说得更具体一点吗？比如“明天上午10点给我的卡罗拉换机油”。\n"

    def unrelated(self) -> str:
        return f"[REPLY][{ROLE}]抱歉，这个问题我处理不了。我可以帮您安排保养预约，或者解答保养相关的问题。\n"