"""任务分类器：判断车主这句话该交给哪个 Agent。

有模型时用模型；没有模型时用打分规则。两条路的输出结构一致，
上层不需要关心里面怎么判的。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from config.constants import IntentCategory
from config.time_config import time_config

BOOKING_WORDS = ["预约", "约一下", "帮我约", "改约", "取消预约", "安排", "到店", "过来做", "想换", "要换", "做保养", "顺便"]
TIME_HINTS = ["今天", "明天", "后天", "上午", "下午", "晚上", "点", "号", "周"]
PROFILE_WORDS = ["档案", "保养记录", "我的车", "查一下", "里程", "车牌", "什么时候到期", "上次保养"]
BEHAVIOR_WORDS = ["习惯", "偏好", "分析", "统计", "喜欢", "常来", "画像"]
QUESTION_WORDS = ["多少钱", "多久", "多少公里", "为什么", "怎么", "能不能", "是不是", "是什么", "怎么办", "吗", "呢"]

OFFTOPIC_WORDS = ["天气", "股票", "基金", "新闻", "笑话", "游戏", "电影", "音乐", "政治", "聊聊天"]

RECOMMEND_WORDS = ["该做什么", "要做什么", "推荐", "建议", "按里程", "该保养", "帮我看看"]

CONSULT_WORDS = [
    "多少钱", "价格", "收费", "报价", "多久", "多少公里", "周期", "为什么", "怎么",
    "能不能", "是不是", "故障灯", "亮灯", "报警", "异响", "抖动", "跑偏", "机油", "规格",
    "质保", "保修", "营业时间", "几点", "地址", "停车", "优惠", "会员", "区别", "要不要",
]

CATEGORY_DESCRIPTION = {
    IntentCategory.BOOKING.value: "预约工单 - 车主想安排、修改或取消保养",
    IntentCategory.CONSULT.value: "知识咨询 - 车主在问保养相关的问题",
    IntentCategory.VEHICLE_PROFILE.value: "车辆档案 - 车主在查询自己的车辆信息",
    IntentCategory.BEHAVIOR.value: "车主行为 - 车主在看自己的用车习惯或推荐",
    IntentCategory.OTHER.value: "其他 - 与汽车保养无关",
}


class TaskClassifier:
    """意图分类。"""

    def __init__(self, llm=None):
        self.llm = llm

    async def classify_task(self, text: str) -> Dict[str, Any]:
        if self.llm is not None:
            try:
                result = await self._classify_with_llm(text)
                if result:
                    return result
            except Exception:
                pass
        return self.classify_rules(text)

    async def _classify_with_llm(self, text: str) -> Dict[str, Any]:
        system_prompt = (
            "你是汽车保养门店智能前台的调度器，请判断车主这句话属于哪一类，"
            "只输出 JSON，不要解释，不要代码块。\n"
            "类别取值：booking（想预约/改约/取消/直接说要做某个保养项目）、"
            "consult（咨询服务价格、保养周期、故障灯、规格政策等）、"
            "vehicle_profile（查询自己的车辆档案、里程、保养记录）、"
            "behavior（查看自己的习惯偏好或要个性化推荐）、"
            "other（与汽车保养无关）。\n"
            '{"category": "booking", "confidence": 0.9, "reason": "简短理由"}'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"当前时间：{time_config.current_datetime_str()}\n车主说：{text}"},
        ]
        data = await self.llm.acomplete_json(messages, temperature=0)
        category = str(data.get("category", "")).strip().lower()
        if category not in CATEGORY_DESCRIPTION:
            return {}
        return {
            "category": category,
            "confidence": float(data.get("confidence", 0.7) or 0.7),
            "reason": str(data.get("reason", "")),
            "source": "llm",
        }

    @staticmethod
    def _has_item_keyword(text: str) -> bool:
        """文本里是否出现了具体的保养项目（机油、刹车片、四轮定位……）。"""

        from config.service_catalog import SERVICE_ITEMS, resolve_item_code

        if resolve_item_code(text) is not None:
            return True
        return any(
            keyword and keyword in text
            for item in SERVICE_ITEMS.values()
            for keyword in list(item.keywords) + [item.name]
        )

    @staticmethod
    def classify_rules(text: str) -> Dict[str, Any]:
        raw = text or ""
        stripped = raw.strip()
        scores: Dict[str, float] = {category: 0.0 for category in CATEGORY_DESCRIPTION}
        reasons: Dict[str, str] = {}

        # 与汽车保养完全无关的话题，直接归类为 other
        for word in OFFTOPIC_WORDS:
            if word in raw:
                return {
                    "category": IntentCategory.OTHER.value,
                    "confidence": 0.7,
                    "reason": f"出现无关话题词“{word}”",
                    "source": "rule",
                }

        has_time = any(hint in raw for hint in TIME_HINTS)
        has_item = TaskClassifier._has_item_keyword(raw)
        is_question = stripped.endswith(("?", "？", "吗", "呢")) or any(
            word in raw for word in QUESTION_WORDS
        )

        # ---- 预约 ----
        booking_score = 0.0
        for word in BOOKING_WORDS:
            if word in raw:
                booking_score += 2
                reasons[IntentCategory.BOOKING.value] = f"出现预约动作词“{word}”"
                break
        if has_time and has_item:
            booking_score += 2
            reasons.setdefault(IntentCategory.BOOKING.value, "同时给出了时间和保养项目")
        if has_time:
            booking_score += 1
        if has_item and any(word in raw for word in RECOMMEND_WORDS):
            booking_score += 3
            reasons.setdefault(IntentCategory.BOOKING.value, "车主想让我们推荐该做的项目")
        if stripped.startswith(("我", "帮", "要", "想")) and not is_question:
            booking_score += 0.5
        scores[IntentCategory.BOOKING.value] = booking_score

        # ---- 咨询 ----
        consult_score = 0.0
        for word in CONSULT_WORDS:
            if word in raw:
                consult_score += 2
                reasons[IntentCategory.CONSULT.value] = f"出现咨询词“{word}”"
                break
        if is_question:
            consult_score += 1.5
        if any(word in raw for word in QUESTION_WORDS):
            consult_score += 1
            reasons.setdefault(IntentCategory.CONSULT.value, "车主在问原因或做法")
        scores[IntentCategory.CONSULT.value] = consult_score

        # ---- 车辆档案 ----
        for word in PROFILE_WORDS:
            if word in raw:
                scores[IntentCategory.VEHICLE_PROFILE.value] += 2
                reasons[IntentCategory.VEHICLE_PROFILE.value] = f"出现档案查询词“{word}”"
                break

        # ---- 行为分析 ----
        for word in BEHAVIOR_WORDS:
            if word in raw:
                scores[IntentCategory.BEHAVIOR.value] += 2
                reasons[IntentCategory.BEHAVIOR.value] = f"出现行为分析词“{word}”"
                break

        best = max(scores, key=lambda key: scores[key])
        # 预约与咨询打平时，只要出现了明确的时间+项目，就按预约处理
        if booking_score > 0 and booking_score >= consult_score and has_time:
            best = IntentCategory.BOOKING.value

        if scores[best] <= 0:
            return {
                "category": IntentCategory.OTHER.value,
                "confidence": 0.3,
                "reason": "没有匹配到任何业务关键词",
                "source": "rule",
            }

        confidence = min(0.5 + scores[best] * 0.1, 0.95)
        return {
            "category": best,
            "confidence": round(confidence, 2),
            "reason": reasons.get(best, "规则打分"),
            "source": "rule",
        }
    @staticmethod
    def get_category_description(category: str) -> str:
        return CATEGORY_DESCRIPTION.get(category, "未知类别")