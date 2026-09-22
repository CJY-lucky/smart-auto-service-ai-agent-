"""预约流程处理器：把解析结果 + 排班结果串成一条完整的对话流程。

关键分工（对应 README 的核心设计思想）：
- 大模型/规则解析只负责"听懂"（车型、里程、项目、时间）；
- 能不能排上、排在哪，全部由 Services 层的排班算法决定；
- 排不上时，这里负责把算法给出的结构化冲突原因翻译成车主能听懂的话，
  并引导车主换时间或调整项目。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from config.time_config import time_config
from services.scheduling_service import ConflictReason, SchedulingService
from services.technician_service import TechnicianService
from services.vehicle_behavior_service import fetch_weather_note
from services.vehicle_service import VehicleService

from .booking_database import BookingDatabase
from .input_parser import InputParser
from .message_builder import MessageBuilder
from .vehicle_recognizer import VehicleRecognizer

CANCEL_WORDS = ["取消预约", "取消工单", "不去了", "取消掉", "帮我取消"]
RESCHEDULE_WORDS = ["改约", "改到", "改成", "换个时间", "推迟", "提前"]
RECOMMEND_WORDS = ["推荐", "按里程", "该做什么", "你看着办", "看着办", "该保养", "有什么要做"]

ORDINAL_MAP = {
    "1": 0, "一": 0, "第一": 0, "第一个": 0,
    "2": 1, "二": 1, "第二": 1, "第二个": 1,
    "3": 2, "三": 2, "第三": 2, "第三个": 2,
    "4": 3, "四": 3, "第四": 3, "第四个": 3,
}


class BookingProcessor:
    """预约流程控制。"""

    def __init__(
        self,
        input_parser: InputParser,
        vehicle_recognizer: VehicleRecognizer,
        message_builder: MessageBuilder,
        booking_database: BookingDatabase,
        llm=None,
    ):
        self.input_parser = input_parser
        self.vehicle_recognizer = vehicle_recognizer
        self.message_builder = message_builder
        self.booking_database = booking_database
        self.llm = llm
        self.vehicle_service = VehicleService()
        self.technician_service = TechnicianService()

    # ================================================================ 入口
    async def handle(
        self,
        user_input: str,
        state: Dict[str, Any],
        session_id: str,
        owner_ref: str = "default_owner",
    ) -> AsyncGenerator[str, None]:
        # 上下文恢复：每轮都重新注入外部依赖，避免状态里存对象
        parsed = await self.input_parser.parse(user_input, known=state)

        # ---- 取消 / 改约 ----
        if self._is_cancel(user_input):
            async for token in self._handle_cancel(user_input, state, owner_ref):
                yield token
            return
        if self._is_reschedule(user_input):
            async for token in self._handle_reschedule(user_input, state, owner_ref):
                yield token
            return

        awaiting = state.get("awaiting")
        if awaiting == "items_confirm":
            async for token in self._handle_items_confirmation(parsed, state, session_id, owner_ref):
                yield token
            return
        if awaiting == "slot_choice":
            async for token in self._handle_slot_choice(parsed, state, session_id, owner_ref):
                yield token
            return
        if awaiting == "technician_confirm":
            async for token in self._handle_technician_confirmation(parsed, state, session_id, owner_ref):
                yield token
            return
        if awaiting == "reschedule_time":
            async for token in self._handle_reschedule_time(parsed, state, owner_ref):
                yield token
            return

        self._merge(parsed, state)
        async for token in self._continue_booking(state, session_id, owner_ref, parsed):
            yield token

    # ================================================================ 主流程
    async def _continue_booking(
        self,
        state: Dict[str, Any],
        session_id: str,
        owner_ref: str,
        parsed: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        yield self.message_builder.thought("正在整理您的预约需求……")

        # 1) 车辆档案
        recognition = self.vehicle_recognizer.recognize(state)
        vehicle = recognition.get("vehicle")
        if vehicle is None and recognition.get("need_new_profile") and recognition.get("plate_no"):
            owner_id = self.vehicle_service.ensure_owner(owner_ref)
            vehicle_id = self.vehicle_service.ensure_vehicle(
                owner_id,
                recognition["plate_no"],
                model=state.get("vehicle_model"),
                mileage=state.get("mileage"),
            )
            vehicle = self.vehicle_service.get_vehicle(vehicle_id)
            yield self.message_builder.thought(f"已为车辆 {vehicle['plate_no']} 建立档案")

        if vehicle is None:
            if recognition.get("message"):
                yield self.message_builder.reply("\n" + recognition["message"] + "\n")
            missing = self._missing_fields(state, need_vehicle=True)
            if "plate_no" in missing:
                yield self.message_builder.reply(self.message_builder.ask_missing(["plate_no"]))
            return

        state["vehicle_id"] = vehicle["id"]
        state["plate_no"] = vehicle["plate_no"]

        # 2) 时间
        if not state.get("start_time"):
            yield self.message_builder.reply(self.message_builder.ask_missing(["start_time"]))
            return

        start_time = time_config.parse_datetime(state["start_time"])
        if start_time is None:
            state.pop("start_time", None)
            yield self.message_builder.reply("\n我没听懂这个时间，可以说得具体一点吗？比如“明天上午10点”。\n")
            return

        # 3) 项目：没说做什么时，按里程与历史推荐
        if not state.get("item_codes"):
            due_items = self.vehicle_service.due_items(vehicle)
            wants_recommendation = any(word in (parsed.get("raw") or "") for word in RECOMMEND_WORDS)
            if due_items:
                state["awaiting"] = "items_confirm"
                state["pending_items"] = [item["item_code"] for item in due_items[:4]]
                yield self.message_builder.reply(
                    self.message_builder.suggest_addons(vehicle, due_items)
                )
                return
            if wants_recommendation:
                state["item_codes"] = ["oil_change"]
                yield self.message_builder.thought("车辆周期信息不足，先按常规保养处理")
            else:
                yield self.message_builder.reply(self.message_builder.ask_missing(["item_codes"]))
                return

        # 4) 求解排期
        async for token in self._solve_and_book(state, session_id, owner_ref, start_time):
            yield token

    # ================================================================ 排期与下单
    async def _solve_and_book(
        self,
        state: Dict[str, Any],
        session_id: str,
        owner_ref: str,
        start_time: datetime,
        *,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        item_codes = state.get("item_codes") or []
        if not item_codes:
            yield self.message_builder.reply(self.message_builder.ask_missing(["item_codes"]))
            return

        if technician_id is None and state.get("technician_name"):
            technician = self.technician_service.get_by_name(state["technician_name"])
            if technician is None:
                yield self.message_builder.reply(f"\n抱歉，店里没有找到叫{state['technician_name']}的技师，我按资质为您安排其他技师可以吗？\n")
                state.pop("technician_name", None)
            else:
                technician_id = technician["id"]

        plan = self.booking_database.work_order_service.scheduling_service.estimate_workload(item_codes)
        if not plan.items:
            yield self.message_builder.reply(self.message_builder.ask_missing(["item_codes"]))
            return

        result = self.booking_database.find_solution(
            item_codes,
            start_time,
            technician_id=technician_id,
            bay_id=bay_id,
            preference=state.get("preference"),
        )
        yield self.message_builder.thought(
            f"正在按双资源约束校验：需要资质 { '、'.join(plan.required_certifications) or '不限' }，"
            f"需要工位 { '、'.join(plan.bay_type_options) }，"
            f"共 {len(plan.segments)} 道工序（含工位转移 {plan.transfer_minutes} 分钟），"
            f"预计 {plan.total_minutes} 分钟"
        )

        if result.feasible and result.solution:
            async for token in self._book(state, result, session_id, owner_ref):
                yield token
            return

        state["last_conflict"] = {
            "reasons": result.reasons,
            "requested_start": time_config.format_datetime(start_time),
        }
        async for token in self._respond_infeasible(state, result, start_time, state.get("technician_name")):
            yield token


    async def _respond_infeasible(
        self, state: Dict[str, Any], result, requested_start: datetime, technician_name: Optional[str]
    ) -> AsyncGenerator[str, None]:
        yield self.message_builder.reply(self.message_builder.describe_conflict(result))

        suggestions = [solution.to_dict() for solution in result.suggestions]
        if not suggestions:
            yield self.message_builder.reply(self.message_builder.appointment_failed(result))
            return

        specified_name = technician_name or state.get("technician_name")
        if specified_name:
            same_technician = [
                slot for slot in suggestions if (slot.get("technician") or {}).get("name") == specified_name
            ]
            if same_technician:
                state["awaiting"] = "slot_choice"
                state["pending_slots"] = same_technician
                yield self.message_builder.reply(
                    self.message_builder.suggest_slots(
                        same_technician, note=f"\n{specified_name}技师在您说的时间没空，但他这几天还有这些空档："
                    )
                )
                return
            state["awaiting"] = "technician_confirm"
            state["pending_solution"] = suggestions[0]
            state["original_technician_name"] = specified_name
            yield self.message_builder.thought("指定技师档期冲突，准备推荐同资质技师")
            yield self.message_builder.reply(
                self.message_builder.suggest_alternative_technician(specified_name, result.suggestions[0])
            )
            return

        state["awaiting"] = "slot_choice"
        state["pending_slots"] = suggestions
        yield self.message_builder.reply(self.message_builder.suggest_slots(suggestions))

    async def _book(self, state, result, session_id: str, owner_ref: str) -> AsyncGenerator[str, None]:
        solution = result.solution
        outcome = self.booking_database.save_appointment(
            item_codes=result.plan.item_codes,
            start_time=solution.start_time,
            owner_ref=owner_ref,
            plate_no=state.get("plate_no"),
            vehicle_model=state.get("vehicle_model"),
            mileage=state.get("mileage"),
            technician_id=solution.technician["id"],
            bay_id=solution.bay["id"],
            preference=state.get("preference"),
            session_id=session_id,
        )
        if not outcome.get("success"):
            yield self.message_builder.reply(self.message_builder.save_failed())
            return

        weather_note = fetch_weather_note()
        yield self.message_builder.reply(
            self.message_builder.appointment_success(outcome["order"], solution, weather_note=weather_note)
        )
        self._reset_state(state, keep_vehicle=True)

    # ================================================================ 分支处理
    async def _handle_items_confirmation(self, parsed, state, session_id, owner_ref) -> AsyncGenerator[str, None]:
        self._merge(parsed, state)
        pending = state.get("pending_items") or []

        if parsed.get("is_denial"):
            self.booking_database.record_behavior(
                "addon_declined", owner_ref=owner_ref, action_data={"items": pending}
            )
            state["awaiting"] = None
            state.pop("pending_items", None)
            yield self.message_builder.reply(self.message_builder.ask_missing(["item_codes"]))
            return

        state["item_codes"] = list(dict.fromkeys(pending))
        state["awaiting"] = None
        state.pop("pending_items", None)
        self.booking_database.record_behavior(
            "addon_accepted", owner_ref=owner_ref, action_data={"items": state["item_codes"]}
        )
        yield self.message_builder.thought("车主确认了推荐项目")

        start_time = time_config.parse_datetime(state.get("start_time"))
        if start_time:
            async for token in self._solve_and_book(state, session_id, owner_ref, start_time):
                yield token
        else:
            yield self.message_builder.reply(self.message_builder.ask_missing(["start_time"]))

    async def _handle_slot_choice(self, parsed, state, session_id, owner_ref) -> AsyncGenerator[str, None]:
        slots: List[Dict[str, Any]] = state.get("pending_slots") or []
        choice = self._parse_choice(parsed.get("raw") or "")

        # 车主直接给了新时间：按新时间重排
        if parsed.get("start_time") and choice is None:
            state["awaiting"] = None
            state.pop("pending_slots", None)
            self._merge(parsed, state)
            start_time = time_config.parse_datetime(state["start_time"])
            async for token in self._solve_and_book(state, session_id, owner_ref, start_time):
                yield token
            return

        if choice is None or choice >= len(slots):
            yield self.message_builder.reply("\n请回复序号（比如 1），或者直接告诉我您方便的时间。\n")
            return

        slot = slots[choice]
        technician = slot.get("technician") or {}
        bay = slot.get("bay") or {}
        start_time = slot.get("start_time")
        if isinstance(start_time, str):
            start_time = time_config.parse_datetime(start_time)

        state["awaiting"] = None
        state.pop("pending_slots", None)

        pending_order_id = state.get("pending_order_id")
        if pending_order_id:
            state.pop("pending_order_id", None)
            outcome = self.booking_database.reschedule(
                pending_order_id, start_time, technician_id=technician.get("id"), bay_id=bay.get("id")
            )
            if outcome.get("success"):
                yield self.message_builder.reply(
                    self.message_builder.reschedule_success(outcome["order"], outcome["result"].solution)
                )
            else:
                yield self.message_builder.reply("\n" + outcome.get("message", "改约失败，请换个时间试试") + "\n")
            return

        async for token in self._solve_and_book(
            state, session_id, owner_ref, start_time, technician_id=technician.get("id"), bay_id=bay.get("id")
        ):
            yield token

    async def _handle_technician_confirmation(self, parsed, state, session_id, owner_ref) -> AsyncGenerator[str, None]:
        solution = state.get("pending_solution") or {}
        original_name = state.get("original_technician_name")
        state["awaiting"] = None
        state.pop("pending_solution", None)

        if parsed.get("is_denial"):
            state.pop("technician_name", None)
            yield self.message_builder.reply("\n好的，那我按资质给您安排其他技师，您方便说个时间吗？\n")
            return

        technician = solution.get("technician") or {}
        bay = solution.get("bay") or {}
        start_time = solution.get("start_time")
        if isinstance(start_time, str):
            start_time = time_config.parse_datetime(start_time)

        state.pop("technician_name", None)
        yield self.message_builder.thought(
            f"车主接受了替代技师{(technician.get('name') or '')}，原指定技师{original_name or ''}"
        )
        async for token in self._solve_and_book(
            state, session_id, owner_ref, start_time, technician_id=technician.get("id"), bay_id=bay.get("id")
        ):
            yield token

    async def _handle_reschedule_time(self, parsed, state, owner_ref: str) -> AsyncGenerator[str, None]:
        start_time = time_config.parse_datetime(parsed.get("start_time"))
        order_id = state.get("pending_order_id")
        if start_time is None or not order_id:
            yield self.message_builder.reply("\n请告诉我您想改到哪个具体时间，比如“明天下午3点”。\n")
            return

        state["awaiting"] = None
        state.pop("pending_order_id", None)
        outcome = self.booking_database.reschedule(order_id, start_time)
        if outcome.get("success"):
            yield self.message_builder.reply(
                self.message_builder.reschedule_success(outcome["order"], outcome["result"].solution)
            )
            return
        result = outcome.get("result")
        if result is None:
            yield self.message_builder.reply("\n" + outcome.get("message", "改约失败") + "\n")
            return
        yield self.message_builder.reply(self.message_builder.describe_conflict(result))
        suggestions = [solution.to_dict() for solution in result.suggestions]
        if suggestions:
            state["awaiting"] = "slot_choice"
            state["pending_slots"] = suggestions
            state["pending_order_id"] = order_id
            yield self.message_builder.reply(self.message_builder.suggest_slots(suggestions))

    async def _handle_cancel(self, user_input: str, state, owner_ref: str) -> AsyncGenerator[str, None]:
        orders = self.booking_database.upcoming_orders(owner_ref, limit=5)
        if not orders:
            yield self.message_builder.reply("\n目前没有查到您待进行的预约，需要我帮您安排一次保养吗？\n")
            return
        order = orders[0]
        outcome = self.booking_database.cancel(order["id"])
        self._reset_state(state)
        yield self.message_builder.reply(self.message_builder.cancel_success(outcome.get("order") or order))

    async def _handle_reschedule(self, user_input: str, state, owner_ref: str) -> AsyncGenerator[str, None]:
        orders = self.booking_database.upcoming_orders(owner_ref, limit=5)
        if not orders:
            yield self.message_builder.reply("\n没有查到您待进行的预约，需要我帮您安排一次新的保养吗？\n")
            return

        parsed = await self.input_parser.parse(user_input, known=state)
        start_time = time_config.parse_datetime(parsed.get("start_time"))
        order = orders[0]
        if start_time is None:
            state["awaiting"] = "reschedule_time"
            state["pending_order_id"] = order["id"]
            yield self.message_builder.reply("\n好的，您想改到什么时候？\n")
            return

        outcome = self.booking_database.reschedule(order["id"], start_time)
        if outcome.get("success"):
            self._reset_state(state)
            yield self.message_builder.reply(self.message_builder.reschedule_success(outcome["order"], outcome["result"].solution))
        else:
            result = outcome.get("result")
            if result is None:
                yield self.message_builder.reply("\n" + outcome.get("message", "改约失败") + "\n")
                return
            yield self.message_builder.reply(self.message_builder.describe_conflict(result))
            suggestions = [solution.to_dict() for solution in result.suggestions]
            if suggestions:
                state["awaiting"] = "slot_choice"
                state["pending_slots"] = suggestions
                state["pending_order_id"] = order["id"]
                yield self.message_builder.reply(self.message_builder.suggest_slots(suggestions))

    # ================================================================ 工具
    @staticmethod
    def _merge(parsed: Dict[str, Any], state: Dict[str, Any]) -> None:
        for key in ("plate_no", "vehicle_model", "mileage", "preference", "technician_name"):
            value = parsed.get(key)
            if value:
                state[key] = value
        if parsed.get("start_time"):
            state["start_time"] = parsed["start_time"]
        if parsed.get("item_codes"):
            state["item_codes"] = list(dict.fromkeys(parsed["item_codes"]))

    @staticmethod
    def _missing_fields(state: Dict[str, Any], *, need_vehicle: bool = False) -> List[str]:
        missing = []
        if need_vehicle and not state.get("plate_no"):
            missing.append("plate_no")
        if not state.get("start_time"):
            missing.append("start_time")
        if not state.get("item_codes"):
            missing.append("item_codes")
        return missing

    @staticmethod
    def _is_cancel(user_input: str) -> bool:
        return any(word in (user_input or "") for word in CANCEL_WORDS)

    @staticmethod
    def _is_reschedule(user_input: str) -> bool:
        return any(word in (user_input or "") for word in RESCHEDULE_WORDS)

    @staticmethod
    def _parse_choice(text: str) -> Optional[int]:
        stripped = (text or "").strip()
        for token, index in ORDINAL_MAP.items():
            if stripped == token or stripped.startswith(token):
                return index
        return None

    @staticmethod
    def _reset_state(state: Dict[str, Any], *, keep_vehicle: bool = False) -> None:
        preserved = {key: state[key] for key in ("plate_no", "vehicle_id", "vehicle_model", "mileage") if key in state} if keep_vehicle else {}
        state.clear()
        state.update(preserved)