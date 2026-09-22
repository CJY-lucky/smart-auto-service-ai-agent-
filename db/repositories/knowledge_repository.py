"""知识库与 Embedding 缓存的数据访问。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from db.models import EmbeddingCache, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # -- 文档 -----------------------------------------------------------
    @staticmethod
    def _to_dict(document: KnowledgeDocument) -> Dict[str, Any]:
        return {
            "id": document.id,
            "content": document.content,
            "category": document.category,
            "keywords": list(document.keywords or []),
            "embedding": document.embedding,
            "is_active": int(document.is_active or 0),
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    def add_document(
        self,
        content: str,
        category: str,
        keywords: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
    ) -> int:
        with self._session_factory() as session:
            document = KnowledgeDocument(
                content=content,
                category=category,
                keywords=keywords or [],
                embedding=embedding,
                is_active=1,
            )
            session.add(document)
            session.commit()
            return document.id

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            document = session.get(KnowledgeDocument, doc_id)
            return self._to_dict(document) if document else None

    def get_all_documents(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(KnowledgeDocument).order_by(KnowledgeDocument.id)
            if not include_inactive:
                query = query.filter(KnowledgeDocument.is_active == 1)
            return [self._to_dict(item) for item in query.all()]

    def update_document(
        self,
        doc_id: int,
        *,
        content: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
    ) -> bool:
        with self._session_factory() as session:
            document = session.get(KnowledgeDocument, doc_id)
            if not document:
                return False
            if content is not None:
                document.content = content
            if category is not None:
                document.category = category
            if keywords is not None:
                document.keywords = keywords
            if embedding is not None:
                document.embedding = embedding
            session.commit()
            return True

    def delete_document(self, doc_id: int, soft_delete: bool = True) -> bool:
        with self._session_factory() as session:
            document = session.get(KnowledgeDocument, doc_id)
            if not document:
                return False
            if soft_delete:
                document.is_active = 0
            else:
                session.delete(document)
            session.commit()
            return True

    def get_categories(self) -> List[str]:
        with self._session_factory() as session:
            rows = (
                session.query(KnowledgeDocument.category)
                .filter(KnowledgeDocument.is_active == 1)
                .distinct()
                .all()
            )
            return [row[0] for row in rows if row[0]]

    def count_documents(self) -> int:
        with self._session_factory() as session:
            return session.query(KnowledgeDocument).filter(KnowledgeDocument.is_active == 1).count()

    # -- Embedding 缓存 --------------------------------------------------
    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def get_cached_embedding(self, text: str, model: str) -> Optional[List[float]]:
        text_hash = self.hash_text(text)
        with self._session_factory() as session:
            row = (
                session.query(EmbeddingCache)
                .filter(EmbeddingCache.text_hash == text_hash)
                .filter(EmbeddingCache.model == model)
                .one_or_none()
            )
            return list(row.embedding) if row and row.embedding else None

    def cache_embedding(self, text: str, model: str, embedding: List[float]) -> None:
        text_hash = self.hash_text(text)
        with self._session_factory() as session:
            row = (
                session.query(EmbeddingCache)
                .filter(EmbeddingCache.text_hash == text_hash)
                .filter(EmbeddingCache.model == model)
                .one_or_none()
            )
            if row is None:
                session.add(
                    EmbeddingCache(
                        text_hash=text_hash,
                        model=model,
                        text=text,
                        embedding=list(embedding),
                    )
                )
            else:
                row.embedding = list(embedding)
            session.commit()

    def clear_embedding_cache(self) -> int:
        with self._session_factory() as session:
            count = session.query(EmbeddingCache).delete()
            session.commit()
            return int(count)