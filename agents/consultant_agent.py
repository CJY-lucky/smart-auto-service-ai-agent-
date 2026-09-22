"""咨询 Agent 主控制器（RAG + 安全兜底）。"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator, Optional

from config.model_provider import create_chat_model

from .consultant import (
    ConsultationClassifier,
    ConsultationProcessor,
    KnowledgeRetriever,
    ResponseGenerator,
)


class ConsultantAgent:
    """咨询 Agent。"""

    def __init__(self, session_id: Optional[str] = None, *, llm=None, db_path: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.shared_state = None
        self.unrelated_callback = None
        self.llm = llm if llm is not None else create_chat_model(temperature=0.3)

        self.knowledge_retriever = KnowledgeRetriever(db_path)
        self.consultation_classifier = ConsultationClassifier(self.llm)
        self.response_generator = ResponseGenerator(self.llm)
        self.consultation_processor = ConsultationProcessor(
            self.knowledge_retriever, self.response_generator
        )

    async def __aenter__(self):
        await self.knowledge_retriever.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def set_shared_state(self, shared_state) -> None:
        self.shared_state = shared_state

    def set_unrelated_callback(self, callback) -> None:
        self.unrelated_callback = callback

    async def consult(self, user_input: str, owner_ref: str = "default_owner") -> str:
        await self.knowledge_retriever.initialize()
        return await self.consultation_processor.process_consultation(user_input)

    async def consult_stream(
        self, user_input: str, owner_ref: str = "default_owner"
    ) -> AsyncGenerator[str, None]:
        await self.knowledge_retriever.initialize()

        is_consultation = await self.consultation_classifier.is_consultation_related(user_input)
        if not is_consultation:
            async for token in self.consultation_processor.handle_unrelated_request(
                user_input, self.shared_state
            ):
                yield token
            return

        async for token in self.consultation_processor.process_consultation_stream(
            user_input, session_id=self.session_id, owner_ref=owner_ref
        ):
            yield token

        if self.shared_state is not None:
            from config.constants import StateEnum

            self.shared_state.value = StateEnum.CLASSIFY