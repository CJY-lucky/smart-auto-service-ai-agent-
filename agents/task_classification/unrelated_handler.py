"""无关请求处理：礼貌拒绝并引导回业务。"""

from __future__ import annotations

from typing import AsyncGenerator

from .state_manager import StateManager

DEFAULT_REPLIES = [
    "抱歉，这个问题我处理不了。我可以帮您安排保养预约，也能解答保养周期、价格和故障灯这类问题。",
    "不好意思，我主要负责汽车保养的咨询和预约。您要是想了解保养项目或者约个时间到店，我很乐意帮忙。",
    "这个问题超出了我的服务范围。需要我帮您看看这辆车该做什么保养吗？",
]


class UnrelatedHandler:
    """无关请求。"""

    def __init__(self, state_manager: StateManager, business_name: str = "汽车保养服务"):
        self.state_manager = state_manager
        self.business_name = business_name
        self._replies = list(DEFAULT_REPLIES)
        self._index = 0

    async def handle_unrelated_async(self, user_input: str) -> AsyncGenerator[str, None]:
        self.state_manager.reset_to_classify()
        reply = self._next_reply()
        yield "[REPLY][归类机器人]"
        for char in reply:
            yield char

    async def handle_unrelated_sync(self, user_input: str) -> str:
        self.state_manager.reset_to_classify()
        return self._next_reply()

    def _next_reply(self) -> str:
        reply = self._replies[self._index]
        self._index = (self._index + 1) % len(self._replies)
        return reply

    def set_business_context(self, business_name: str) -> None:
        self.business_name = business_name
        self._replies = [
            f"抱歉，这个问题我处理不了。我可以帮您处理{business_name}相关的咨询和预约。",
            f"不好意思，我主要负责{business_name}。要不要我帮您看看这辆车该做什么保养？",
            f"这个问题超出了我的服务范围。需要了解保养项目或者预约到店，随时告诉我。",
        ]

    def reset_reply_rotation(self) -> None:
        self._index = 0