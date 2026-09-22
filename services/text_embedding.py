"""文本向量化与相似度工具。

带两级缓存（进程内存 + 数据库），避免同一段文本反复调用向量接口：
知识库重建索引、技师专长匹配都会高频复用同一批文本。
"""

from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional, Sequence

import numpy as np

from config.model_provider import create_embedding_model

logger = logging.getLogger(__name__)

_MEMORY_CACHE: Dict[str, List[float]] = {}
_MEMORY_CACHE_LIMIT = 2000
_EMBEDDER = None

TECHNICIAN_EMBEDDING_PATH = "data/technician_embeddings.pkl"


def get_embedder():
    """获取（并缓存）向量模型实例。"""

    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = create_embedding_model()
    return _EMBEDDER


def embedding_model_name() -> str:
    return getattr(get_embedder(), "model", "unknown")


def reset_embedder() -> None:
    """清空向量模型缓存（配置变更或测试用）。"""

    global _EMBEDDER
    _EMBEDDER = None
    _MEMORY_CACHE.clear()


def embed_input(text: str, use_cache: bool = True) -> List[float]:
    """把一段文本转成向量。"""

    if not text:
        return []

    key = f"{embedding_model_name()}::{text}"
    if use_cache and key in _MEMORY_CACHE:
        return _MEMORY_CACHE[key]

    if use_cache:
        cached = _load_db_cache(text)
        if cached:
            _store_memory(key, cached)
            return cached

    vector = [float(value) for value in get_embedder().embed_query(text)]
    if use_cache:
        _store_memory(key, vector)
        _save_db_cache(text, vector)
    return vector


def embed_inputs(texts: Sequence[str], use_cache: bool = True) -> List[List[float]]:
    """批量向量化（逐条走缓存，便于复用）。"""

    return [embed_input(text, use_cache=use_cache) for text in texts]


def _store_memory(key: str, vector: List[float]) -> None:
    if len(_MEMORY_CACHE) >= _MEMORY_CACHE_LIMIT:
        _MEMORY_CACHE.clear()
    _MEMORY_CACHE[key] = vector


def _db_repository():
    try:
        from db.db_router import get_database_router

        return get_database_router().knowledge
    except Exception:  # pragma: no cover - 数据库不可用时静默降级
        return None


def _load_db_cache(text: str) -> Optional[List[float]]:
    repository = _db_repository()
    if repository is None:
        return None
    try:
        cached = repository.get_cached_embedding(text, embedding_model_name())
        return list(cached) if cached else None
    except Exception:
        return None


def _save_db_cache(text: str, vector: List[float]) -> None:
    repository = _db_repository()
    if repository is None:
        return
    try:
        repository.cache_embedding(text, embedding_model_name(), vector)
    except Exception:  # pragma: no cover
        logger.debug("写入 Embedding 缓存失败，已忽略")


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """余弦相似度，任一向量为空返回 0。"""

    left_array = np.asarray(left, dtype="float32")
    right_array = np.asarray(right, dtype="float32")
    if left_array.size == 0 or right_array.size == 0:
        return 0.0
    denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
    if denominator == 0:
        return 0.0
    return float(np.dot(left_array, right_array) / denominator)


def rank_by_similarity(text: str, candidates: Sequence[str]) -> List[int]:
    """返回候选列表中与 text 最相似的下标，按相似度从高到低排序。"""

    if not candidates:
        return []
    target = np.asarray(embed_input(text), dtype="float32")
    if target.size == 0:
        return list(range(len(candidates)))

    scores = []
    for index, candidate in enumerate(candidates):
        scores.append((index, cosine_similarity(target, embed_input(candidate))))
    scores.sort(key=lambda item: item[1], reverse=True)
    return [index for index, _ in scores]


def find_best_match_indices(text: str, candidates: Sequence[str]) -> List[int]:
    """用 FAISS 索引做候选排序，接口与参考项目保持一致。"""

    if not candidates:
        return []

    import faiss

    candidate_vectors = np.asarray(
        [embed_input(candidate) for candidate in candidates], dtype="float32"
    )
    if candidate_vectors.ndim != 2 or candidate_vectors.shape[1] == 0:
        return list(range(len(candidates)))

    index = faiss.IndexFlatIP(candidate_vectors.shape[1])
    index.add(candidate_vectors)

    query = np.asarray([embed_input(text)], dtype="float32")
    if query.shape[1] != candidate_vectors.shape[1]:
        return list(range(len(candidates)))

    scores = min(len(candidates), 64)
    _, indices = index.search(query, scores)
    return [int(index_value) for index_value in indices[0] if index_value >= 0]


def save_technician_embeddings(embeddings, indices, path: str = TECHNICIAN_EMBEDDING_PATH) -> None:
    """把技师向量与索引落盘（文件缓存）。"""

    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        pickle.dump({"embeddings": embeddings, "indices": indices}, handle)


def load_technician_embeddings(path: str = TECHNICIAN_EMBEDDING_PATH):
    """读取技师向量缓存，不存在时返回 (None, None)。"""

    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "rb") as handle:
            data = pickle.load(handle)
        return data.get("embeddings"), data.get("indices")
    except Exception:  # pragma: no cover
        return None, None