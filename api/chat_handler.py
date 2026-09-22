"""对话入口：把用户输入交给多 Agent 链路处理。

这里是"单门店单会话"的简化实现，会话状态保存在进程内；
多门店 / 多用户场景可以把 agent 实例按 session 缓存即可。
"""

from __future__ import annotations

import logging
import uuid
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

GLOBAL_SESSION_ID = str(uuid.uuid4())
_AGENTS: dict = {}


def get_agents():
    """懒加载并复用一套 Agent 实例。"""

    if "task" not in _AGENTS:
        from agents.consultant_agent import ConsultantAgent
        from agents.service_booking_agent import ServiceBookingAgent
        from agents.task_classification_agent import TaskClassificationAgent
        from agents.vehicle_behavior_agent import VehicleBehaviorAgent

        booking_agent = ServiceBookingAgent(session_id=GLOBAL_SESSION_ID)
        consultant_agent = ConsultantAgent(session_id=GLOBAL_SESSION_ID)
        behavior_agent = VehicleBehaviorAgent()

        _AGENTS["task"] = TaskClassificationAgent(
            booking_agent, consultant_agent, behavior_agent
        )
        _AGENTS["booking"] = booking_agent
        _AGENTS["consultant"] = consultant_agent
        _AGENTS["behavior"] = behavior_agent
    return _AGENTS


def reset_agents() -> None:
    """清空缓存的 Agent（测试或配置变更后使用）。"""

    _AGENTS.clear()


async def ProcessUserInput_stream(
    user_input: str, owner_ref: str = "default_owner"
) -> AsyncGenerator[str, None]:
    """流式处理用户输入，产出带标记的 token 流。"""

    agents = get_agents()
    async for token in agents["task"].classify_task_stream(user_input, owner_ref):
        yield token


async def ProcessUserInput(user_input: str, owner_ref: str = "default_owner") -> str:
    """非流式版本。"""

    result = ""
    async for token in ProcessUserInput_stream(user_input, owner_ref):
        result += token
    return result