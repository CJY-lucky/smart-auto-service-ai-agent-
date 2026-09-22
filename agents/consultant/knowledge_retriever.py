"""知识检索器：把知识库服务的检索能力包装成 Agent 可用的形式。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """知识检索。"""

    def __init__(self, db_path: Optional[str] = None, knowledge_service: Optional[KnowledgeService] = None):
        self.knowledge_service = knowledge_service or KnowledgeService(db_path)
        self.initialized = False

    async def initialize(self) -> None:
        if not self.initialized:
            await self.knowledge_service.initialize()
            self.initialized = True

    async def search_knowledge(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.initialized:
            await self.initialize()
        documents = await self.knowledge_service.search(query, top_k=top_k)
        if documents:
            logger.info(
                "知识检索命中 %s 条：%s",
                len(documents),
                "、".join(f"{doc.get('category')}({doc.get('score'):.2f})" for doc in documents),
            )
        else:
            logger.info("知识检索未命中：%s", query)
        return documents or []