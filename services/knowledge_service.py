"""知识库服务：数据库存储 + FAISS 向量检索。

汽车保养直接关系到行车安全，所以咨询回答必须基于可控的知识来源，
不能完全依赖大模型自由发挥。这里负责把知识"存得好、取得准"。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from db.db_router import get_database_router
from services.text_embedding import embed_input, embedding_model_name

logger = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "content": "门店营业时间为每天上午 9:00 到晚上 20:00，全年无休，节假日正常营业。建议提前预约以免等位。",
        "category": "营业时间",
        "keywords": ["营业时间", "几点", "开门", "关门", "节假日"],
    },
    {
        "content": (
            "常规保养项目与参考价格：更换机油机滤 380 元起（约 40 分钟）；更换空气滤芯 120 元；"
            "更换空调滤芯 150 元；四轮换位 80 元；四轮定位 300 元；更换刹车片 680 元起；"
            "更换刹车油 260 元；更换防冻液 300 元；更换火花塞 480 元；更换电瓶 520 元起。具体以到店检测为准。"
        ),
        "category": "服务项目",
        "keywords": ["价格", "多少钱", "收费", "保养项目", "报价"],
    },
    {
        "content": (
            "保养周期建议：机油机滤每 1 万公里或 12 个月更换一次，以先到者为准；"
            "空气滤芯与空调滤芯每 2 万公里或 12 个月；刹车油与防冻液每 4 万公里或 24 个月；"
            "火花塞每 4 万公里；变速箱油每 6 万公里或 48 个月；刹车片建议每 4 万公里检查一次，厚度低于 3 毫米需要更换。"
        ),
        "category": "保养周期",
        "keywords": ["保养周期", "多久", "多少公里", "什么时候换"],
    },
    {
        "content": (
            "机油规格要根据车型和发动机选择：自然吸气发动机一般使用 5W-30 或 0W-20 半合成/全合成机油；"
            "涡轮增压发动机建议使用 0W-20 或 5W-40 全合成机油，并认准 API SP 或 ACEA C5 等级。"
            "带颗粒捕集器（GPF）的车型必须使用低灰分机油。我们会在开单前核对随车手册确认规格。"
        ),
        "category": "材料规格",
        "keywords": ["机油", "标号", "规格", "5W-30", "全合成", "涡轮增压"],
    },
    {
        "content": (
            "仪表盘机油压力灯（红色油壶形状）亮起时必须立即靠边停车熄火，继续行驶可能造成发动机报废，"
            "请联系救援或致电门店。电瓶灯、发动机故障灯（黄色）可以低速行驶，但应尽快到店用诊断电脑读取故障码。"
        ),
        "category": "故障灯",
        "keywords": ["故障灯", "仪表盘", "亮灯", "红灯", "报警"],
    },
    {
        "content": (
            "刹车异响常见原因：刹车片磨损到极限（金属片磨到刹车盘，表现为持续尖叫）、"
            "刹车盘表面锈蚀或有硬点（冷车响、热车消失）、刹车片与卡钳之间有异物。"
            "如果踩刹车时伴随抖动或跑偏，必须尽快到店检查制动系统。"
        ),
        "category": "故障排查",
        "keywords": ["异响", "刹车", "尖叫", "抖动", "跑偏"],
    },
    {
        "content": (
            "电瓶一般使用寿命 2-4 年。出现打火无力、启动时灯光变暗、启停功能失效、电瓶观察孔变黑都是老化信号。"
            "冬季气温骤降会让老旧电瓶提前失效，建议入冬前做一次电瓶健康检测（约 30 分钟，免费检测）。"
        ),
        "category": "电瓶",
        "keywords": ["电瓶", "亏电", "打不着火", "启动困难"],
    },
    {
        "content": (
            "四轮定位建议每 2 万公里或更换轮胎之后做一次；出现方向盘跑偏、轮胎单侧磨损、"
            "回正无力、高速抖动等情况需要及时做定位。四轮定位需要专用工位，耗时约 60 分钟。"
        ),
        "category": "轮胎底盘",
        "keywords": ["四轮定位", "跑偏", "吃胎", "方向盘"],
    },
    {
        "content": (
            "质保政策：更换的配件按厂家标准提供质保，原厂件质保期与主机厂一致，"
            "品牌件一般提供 12 个月或 2 万公里质保（以先到者为准）。工时服务本身提供 30 天质量问题返修。"
        ),
        "category": "质保政策",
        "keywords": ["质保", "保修", "返修", "保证"],
    },
    {
        "content": (
            "预约与改约政策：建议提前预约以减少等待时间；如需取消或改约，请至少提前 2 小时通知门店；"
            "多次爽约可能影响后续的优先排期。迟到超过 30 分钟，工位将释放给其他车主。"
        ),
        "category": "预约政策",
        "keywords": ["取消", "改约", "预约政策", "迟到"],
    },
    {
        "content": (
            "门店地址位于北京朝阳区建国路 88 号，地铁 1 号线大望路站 B 口步行 300 米即到，"
            "门口有免费停车位 6 个。建议到店前 10 分钟电话联系，前台会提前安排接待。"
        ),
        "category": "门店地址",
        "keywords": ["地址", "位置", "怎么去", "停车", "交通"],
    },
    {
        "content": (
            "出长途前的检查建议：检查轮胎气压与胎纹深度、四轮定位状态、刹车片厚度、机油与冷却液液位、"
            "电瓶健康度、雨刮与灯光。可以预约我们的全车检查服务，约 30 分钟，不收取检查费。"
        ),
        "category": "用车建议",
        "keywords": ["长途", "自驾", "出行", "全车检查"],
    },
]


class KnowledgeService:
    """知识库：存储、检索与索引维护。"""

    def __init__(self, db_path: Optional[str] = None, vector_dimension: int = 512):
        self.db = get_database_router(db_path).knowledge
        self.index = None
        self.document_ids: List[int] = []
        self.initialized = False
        self.vector_dimension = vector_dimension

    # ---------------------------------------------------------------- 初始化
    async def initialize(self) -> None:
        """载入知识、必要时写入种子数据，并构建向量索引。"""

        if self.initialized:
            return
        documents = self.db.get_all_documents()
        if not documents:
            logger.info("知识库为空，写入默认门店知识")
            self._seed_default_knowledge()
        self.build_index()
        self.initialized = True

    def _seed_default_knowledge(self) -> None:
        for entry in DEFAULT_KNOWLEDGE:
            text = self._text_for_embedding(entry["content"], entry["keywords"])
            self.db.add_document(
                content=entry["content"],
                category=entry["category"],
                keywords=entry["keywords"],
                embedding=embed_input(text),
            )

    @staticmethod
    def _text_for_embedding(content: str, keywords: Optional[List[str]] = None) -> str:
        return f"{content} {' '.join(keywords or [])}".strip()

    def build_index(self) -> None:
        """重建 FAISS 索引（文档增删改后调用）。"""

        documents = self.db.get_all_documents()
        vectors: List[List[float]] = []
        self.document_ids = []

        for document in documents:
            vector = document.get("embedding")
            if not vector:
                vector = embed_input(self._text_for_embedding(document["content"], document.get("keywords")))
                self.db.update_document(document["id"], embedding=vector)
            vectors.append(vector)
            self.document_ids.append(document["id"])

        if not vectors:
            self.index = None
            logger.info("知识库暂无可建立索引的文档")
            return

        import faiss

        matrix = np.asarray(vectors, dtype="float32")
        self.index = faiss.IndexFlatIP(matrix.shape[1])
        self.index.add(matrix)
        logger.info("知识库索引重建完成，共 %s 条（向量模型：%s）", len(vectors), embedding_model_name())

    # ---------------------------------------------------------------- 检索
    async def search(self, query: str, top_k: int = 3, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """混合检索：FAISS 向量召回 + 关键词命中加权。

        纯向量检索在中文短句上召回不稳定（尤其是离线确定性向量），
        因此把门店关键词命中作为加分项，保证"问价格能找到价格条目"。
        """

        if not self.initialized:
            await self.initialize()
        if self.index is None or not self.document_ids:
            return []

        query_vector = np.asarray([embed_input(query)], dtype="float32")
        if query_vector.shape[1] != self.index.d:
            self.build_index()
            if self.index is None or query_vector.shape[1] != self.index.d:
                return []

        candidate_count = min(max(top_k * 3, top_k), len(self.document_ids))
        scores, indices = self.index.search(query_vector, candidate_count)

        candidates: Dict[int, float] = {}
        for score, index in zip(scores[0], indices[0]):
            if index < 0 or index >= len(self.document_ids):
                continue
            candidates[self.document_ids[index]] = float(score)

        for document in self.db.get_all_documents():
            hits = self._keyword_hits(query, document)
            if hits:
                candidates[document["id"]] = candidates.get(document["id"], 0.0) + 0.25 * hits

        results: List[Dict[str, Any]] = []
        for doc_id, score in sorted(candidates.items(), key=lambda item: item[1], reverse=True):
            document = self.db.get_document(doc_id)
            if not document:
                continue
            if category and document.get("category") != category:
                continue
            document["score"] = round(float(score), 4)
            document["rank"] = len(results) + 1
            results.append(document)
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _keyword_hits(query: str, document: Dict[str, Any]) -> int:
        text = query or ""
        hits = 0
        for keyword in document.get("keywords") or []:
            if keyword and keyword in text:
                hits += 1
        category = document.get("category") or ""
        if category and category in text:
            hits += 1
        return hits
    def search_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [doc for doc in self.db.get_all_documents() if doc.get("category") == category]

    # ---------------------------------------------------------------- 管理
    async def add_document(
        self, content: str, category: str, keywords: Optional[List[str]] = None
    ) -> int:
        vector = embed_input(self._text_for_embedding(content, keywords))
        doc_id = self.db.add_document(content, category, keywords or [], vector)
        self.build_index()
        return doc_id

    async def update_document(
        self,
        doc_id: int,
        *,
        content: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> bool:
        current = self.db.get_document(doc_id)
        if not current:
            return False
        final_content = content if content is not None else current["content"]
        final_keywords = keywords if keywords is not None else current.get("keywords", [])
        vector = embed_input(self._text_for_embedding(final_content, final_keywords))
        success = self.db.update_document(
            doc_id, content=final_content, category=category, keywords=final_keywords, embedding=vector
        )
        if success:
            self.build_index()
        return success

    async def delete_document(self, doc_id: int, soft_delete: bool = True) -> bool:
        success = self.db.delete_document(doc_id, soft_delete=soft_delete)
        if success:
            self.build_index()
        return success

    def get_all_documents(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        return self.db.get_all_documents(include_inactive)

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_document(doc_id)

    def get_all_categories(self) -> List[str]:
        return self.db.get_categories()

    def get_documents_count(self) -> int:
        return self.db.count_documents()