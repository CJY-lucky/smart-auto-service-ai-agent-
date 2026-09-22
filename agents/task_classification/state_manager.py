"""对话状态管理。"""

from __future__ import annotations

import logging
from typing import Optional

from config.constants import SharedState, StateEnum

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    StateEnum.CLASSIFY: [StateEnum.BOOKING, StateEnum.CONSULT, StateEnum.BEHAVIOR, StateEnum.OTHER],
    StateEnum.BOOKING: [StateEnum.CLASSIFY],
    StateEnum.CONSULT: [StateEnum.CLASSIFY],
    StateEnum.BEHAVIOR: [StateEnum.CLASSIFY],
    StateEnum.OTHER: [StateEnum.CLASSIFY],
}


class StateManager:
    """状态机。"""

    def __init__(self, shared_state: Optional[SharedState] = None):
        self.state = shared_state or SharedState()

    def get_current_state(self) -> StateEnum:
        return self.state.value or StateEnum.CLASSIFY

    def set_state(self, new_state: StateEnum) -> None:
        previous = self.state.value
        self.state.value = new_state
        logger.debug("状态流转：%s -> %s", previous, new_state)

    def reset_to_classify(self) -> None:
        self.set_state(StateEnum.CLASSIFY)

    def should_classify(self) -> bool:
        return self.get_current_state() in (StateEnum.CLASSIFY, StateEnum.OTHER)

    def is_in_booking_flow(self) -> bool:
        return self.get_current_state() == StateEnum.BOOKING

    def is_in_consultation_flow(self) -> bool:
        return self.get_current_state() == StateEnum.CONSULT

    def transition_to_booking(self) -> None:
        self.set_state(StateEnum.BOOKING)

    def transition_to_consultation(self) -> None:
        self.set_state(StateEnum.CONSULT)

    def transition_to_behavior(self) -> None:
        self.set_state(StateEnum.BEHAVIOR)

    def can_transition_to(self, target: StateEnum) -> bool:
        return target in ALLOWED_TRANSITIONS.get(self.get_current_state(), [])

    def get_state_description(self) -> str:
        return {
            StateEnum.CLASSIFY: "等待识别车主意图",
            StateEnum.BOOKING: "正在处理预约",
            StateEnum.CONSULT: "正在解答咨询",
            StateEnum.BEHAVIOR: "正在分析车主行为",
            StateEnum.OTHER: "暂不支持的话题",
        }.get(self.get_current_state(), "未知状态")

    def force_reset(self) -> None:
        self.reset_to_classify()