"""任务分类 Agent：系统的主调度器。"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from config.constants import SharedState
from config.model_provider import create_chat_model

from .task_classification import (
    AgentRouter,
    ClassificationProcessor,
    StateManager,
    TaskClassifier,
    UnrelatedHandler,
)


class TaskClassificationAgent:
    """主调度器：识别意图并分派给专业 Agent。"""

    def __init__(
        self,
        booking_agent,
        consultant_agent,
        behavior_agent,
        *,
        llm=None,
        db_path: Optional[str] = None,
        shared_state: Optional[SharedState] = None,
    ):
        self.booking_agent = booking_agent
        self.consultant_agent = consultant_agent
        self.behavior_agent = behavior_agent

        self.llm = llm if llm is not None else create_chat_model(temperature=0)

        self.state_manager = StateManager(shared_state or SharedState())
        self.task_classifier = TaskClassifier(self.llm)
        self.agent_router = AgentRouter(
            booking_agent, consultant_agent, behavior_agent, self.state_manager, db_path
        )
        self.unrelated_handler = UnrelatedHandler(self.state_manager)
        self.classification_processor = ClassificationProcessor(
            self.task_classifier, self.state_manager, self.agent_router, self.unrelated_handler
        )
        self.state = self.state_manager.state
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        if self.booking_agent is not None and hasattr(self.booking_agent, "unrelated_callback"):
            self.booking_agent.unrelated_callback = self.handle_unrelated
        if self.consultant_agent is not None and hasattr(self.consultant_agent, "set_unrelated_callback"):
            self.consultant_agent.set_unrelated_callback(self.handle_unrelated_async)

    # ---------------------------------------------------------------- 主要接口
    async def classify_task_stream(
        self, task: str, owner_ref: str = "default_owner"
    ) -> AsyncGenerator[str, None]:
        async for token in self.classification_processor.process_task_stream(task, owner_ref):
            yield token

    async def classify_task(self, task: str) -> dict:
        return await self.classification_processor.process_task_sync(task)

    async def handle_unrelated(self, user_input: str) -> str:
        result = ""
        async for token in self.classification_processor.process_task_stream(user_input):
            result += token
        return result

    async def handle_unrelated_async(self, user_input: str) -> AsyncGenerator[str, None]:
        async for token in self.classification_processor.process_task_stream(user_input):
            yield token

    # ---------------------------------------------------------------- 扩展
    def get_classification_info(self) -> dict:
        return self.classification_processor.get_current_state_info()

    def reset_conversation(self) -> None:
        self.classification_processor.reset_conversation()

    def set_business_context(self, service_name: str = "汽车保养服务") -> None:
        self.unrelated_handler.set_business_context(service_name)