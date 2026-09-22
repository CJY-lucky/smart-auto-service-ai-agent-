"""咨询流程处理器：检索 -> 生成 -> 记录行为。"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict

from .knowledge_retriever import KnowledgeRetriever
from .response_generator import ResponseGenerator

logger = logging.getLogger(__name__)

ROLE = "咨询机器人"


class ConsultationProcessor:
    """咨询流程。"""

    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever,
        response_generator: ResponseGenerator,
        behavior_service=None,
    ):
        self.knowledge_retriever = knowledge_retriever
        self.response_generator = response_generator
        self.behavior_service = behavior_service

    @property
    def _behavior(self):
        if self.behavior_service is None:
            from services.vehicle_behavior_service import VehicleBehaviorService

            self.behavior_service = VehicleBehaviorService()
        return self.behavior_service

    async def process_consultation(self, user_input: str) -> str:
        async for token in self.process_consultation_stream(user_input, session_id="api"):
            if token.startswith("[REPLY]"):
                yield_parts = token.split("]", 2)[-1]
                return yield_parts
        return ""

    async def process_consultation_stream(
        self, user_input: str, session_id: str = "web", owner_ref: str = "default_owner"
    ) -> AsyncGenerator[str, None]:
        try:
            documents = await self.knowledge_retriever.search_knowledge(user_input, top_k=3)
            async for token in self.response_generator.generate_response_stream(user_input, documents):
                yield token
            self._record_consultation_behavior(user_input, documents, session_id, owner_ref)
        except Exception as exc:  # pragma: no cover
            logger.error("咨询处理失败：%s", exc)
            yield f"[REPLY][{ROLE}]抱歉，处理您的问题时出了点问题，请稍后再试或直接致电门店。"

    def _record_consultation_behavior(
        self, user_input: str, documents, session_id: str, owner_ref: str
    ) -> None:
        try:
            categories = sorted({doc.get("category", "未知") for doc in documents or []})
            self._behavior.record_behavior(
                "consultation",
                owner_ref=owner_ref,
                action_data={
                    "question": user_input,
                    "knowledge_docs_used": len(documents or []),
                    "categories": categories,
                },
                session_id=session_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("记录咨询行为失败：%s", exc)

    async def handle_unrelated_request(self, user_input: str, shared_state=None) -> AsyncGenerator[str, None]:
        """这句话不在咨询范围内：给出澄清式回复，并把状态交还调度器。"""

        if shared_state is not None:
            from config.constants import StateEnum

            shared_state.value = StateEnum.CLASSIFY

        yield self.response_generator.create_unrelated_message()
        clarification = (
            "这个问题我可能理解得不够准确。您是想了解保养项目、价格和周期，"
            "还是想约个时间到店？直接说一句就行，比如“明天上午10点换机油”。"
        )
        yield f"[REPLY][{ROLE}]"
        for char in clarification:
            yield char