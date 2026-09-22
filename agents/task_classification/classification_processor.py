"""分类流程处理器：串起"分类 -> 路由 -> 兜底"的完整流程。"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict

from config.constants import IntentCategory

from .agent_router import AgentRouter
from .state_manager import StateManager
from .task_classifier import TaskClassifier
from .unrelated_handler import UnrelatedHandler

logger = logging.getLogger(__name__)


class ClassificationProcessor:
    """流程控制。"""

    def __init__(
        self,
        task_classifier: TaskClassifier,
        state_manager: StateManager,
        agent_router: AgentRouter,
        unrelated_handler: UnrelatedHandler,
    ):
        self.task_classifier = task_classifier
        self.state_manager = state_manager
        self.agent_router = agent_router
        self.unrelated_handler = unrelated_handler

    async def process_task_stream(
        self, task: str, owner_ref: str = "default_owner"
    ) -> AsyncGenerator[str, None]:
        try:
            if self.state_manager.should_classify():
                result = await self.task_classifier.classify_task(task)
                category = result.get("category", IntentCategory.OTHER.value)
                confidence = result.get("confidence", 0.0)
                yield (
                    "[THOUGHT][归类机器人]判断意图为"
                    f"{TaskClassifier.get_category_description(category)}（置信度 {confidence}）"
                )

                if category == IntentCategory.BOOKING.value:
                    async for token in self.agent_router.route_to_booking(task, owner_ref):
                        yield token
                elif category == IntentCategory.CONSULT.value:
                    async for token in self.agent_router.route_to_consultation(task, owner_ref):
                        yield token
                elif category == IntentCategory.VEHICLE_PROFILE.value:
                    async for token in self.agent_router.route_to_vehicle_profile(task, owner_ref):
                        yield token
                elif category == IntentCategory.BEHAVIOR.value:
                    async for token in self.agent_router.route_to_behavior(task, owner_ref):
                        yield token
                else:
                    async for token in self.unrelated_handler.handle_unrelated_async(task):
                        yield token
            else:
                if self.state_manager.is_in_booking_flow():
                    async for token in self.agent_router.route_to_booking(task, owner_ref):
                        yield token
                elif self.state_manager.is_in_consultation_flow():
                    async for token in self.agent_router.route_to_consultation(task, owner_ref):
                        yield token
                else:
                    async for token in self.agent_router.handle_unsupported_task("other"):
                        yield token
        except Exception as exc:  # pragma: no cover
            logger.exception("处理任务失败")
            yield f"[ERROR]处理任务时出错：{exc}"
            self.state_manager.force_reset()

    async def process_task_sync(self, task: str, owner_ref: str = "default_owner") -> Dict[str, Any]:
        """非流式入口，返回归类结果（给 /api/task/classify 用）。"""

        result = await self.task_classifier.classify_task(task)
        return {
            "task": task,
            "category": result.get("category"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "description": TaskClassifier.get_category_description(result.get("category", "")),
            "source": result.get("source"),
        }

    def get_current_state_info(self) -> Dict[str, Any]:
        return {
            "current_state": self.state_manager.get_current_state().value,
            "state_description": self.state_manager.get_state_description(),
            "available_services": self.agent_router.get_available_services(),
            "can_classify": self.state_manager.should_classify(),
        }

    def reset_conversation(self) -> None:
        self.state_manager.force_reset()
        self.unrelated_handler.reset_reply_rotation()