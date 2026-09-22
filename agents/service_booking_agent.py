"""预约工单 Agent 主控制器。

职责：初始化各组件、维护会话级预约状态、把用户输入交给流程处理器。
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator, Dict, Optional

from config.model_provider import create_chat_model

from .service_booking import (
    BookingDatabase,
    BookingProcessor,
    InputParser,
    MessageBuilder,
    VehicleRecognizer,
)


class ServiceBookingAgent:
    """预约工单 Agent。"""

    def __init__(
        self,
        session_id: Optional[str] = None,
        *,
        llm=None,
        db_path: Optional[str] = None,
        unrelated_callback=None,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.shared_state = None
        self.unrelated_callback = unrelated_callback
        self.db_path = db_path

        self.llm = llm if llm is not None else create_chat_model(temperature=0)

        self.input_parser = InputParser(self.llm)
        self.vehicle_recognizer = VehicleRecognizer()
        self.message_builder = MessageBuilder()
        self.booking_database = BookingDatabase(db_path)
        self.booking_processor = BookingProcessor(
            self.input_parser,
            self.vehicle_recognizer,
            self.message_builder,
            self.booking_database,
            self.llm,
        )

        self.booking_state: Dict[str, Any] = {}
        self.history: list = []

    # ---------------------------------------------------------------- 状态
    def set_shared_state(self, shared_state) -> None:
        self.shared_state = shared_state

    def reset(self) -> None:
        self.booking_state = {}
        self.history = []

    def _reset_after_booking(self) -> None:
        preserved = {
            key: self.booking_state[key]
            for key in ("plate_no", "vehicle_id", "vehicle_model", "mileage")
            if key in self.booking_state
        }
        self.booking_state = preserved
        if self.shared_state is not None:
            from config.constants import StateEnum

            self.shared_state.value = StateEnum.CLASSIFY

    # ---------------------------------------------------------------- 主流程
    async def run_stream(
        self, user_input: Optional[str] = None, owner_ref: str = "default_owner"
    ) -> AsyncGenerator[str, None]:
        """流式处理一次预约交互。"""

        if user_input is None:
            return

        self.history.append({"role": "user", "content": user_input})
        had_items = bool(self.booking_state.get("item_codes"))

        try:
            async for token in self.booking_processor.handle(
                user_input, self.booking_state, self.session_id, owner_ref
            ):
                if token.startswith("[REPLY]"):
                    self.history.append({"role": "assistant", "content": token.split("]", 2)[-1]})
                yield token
        except Exception as exc:  # pragma: no cover - 兜底，避免整条链路崩掉
            yield self.message_builder.reply(
                f"\n抱歉，处理预约时出了点问题（{type(exc).__name__}），请再说一次或者直接致电门店。\n"
            )
            return

        # 工单已成功创建：预约状态被清空，但保留了车辆信息
        if had_items and not self.booking_state.get("item_codes") and not self.booking_state.get("awaiting"):
            self._reset_after_booking()