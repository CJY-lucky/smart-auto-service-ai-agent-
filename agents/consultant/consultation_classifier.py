"""咨询分类器：判断一句话是不是"咨询类"问题。"""

from __future__ import annotations

from .prompt_builder import PromptBuilder

CONSULT_KEYWORDS = [
    "多少钱", "价格", "收费", "贵", "报价", "多久", "多长时间", "多少公里", "周期",
    "怎么", "为什么", "什么原因", "能不能", "可以吗", "是不是", "故障灯", "亮灯", "报警",
    "异响", "抖动", "跑偏", "磨损", "机油规格", "标号", "质保", "保修", "营业时间",
    "几点", "地址", "怎么走", "停车", "优惠", "会员",
]

BOOKING_HINTS = ["预约", "约一下", "帮我约", "改约", "取消预约", "要换", "想换", "过来做"]


class ConsultationClassifier:
    """咨询意图判断。"""

    def __init__(self, llm=None):
        self.llm = llm
        self.prompt_builder = PromptBuilder()

    async def is_consultation_related(self, user_input: str) -> bool:
        if self.llm is not None:
            try:
                prompt = self.prompt_builder.build_classification_prompt(user_input)
                answer = (await self.llm.acomplete([{"role": "user", "content": prompt}], temperature=0)).strip().lower()
                if "consult" in answer:
                    return True
                if "booking" in answer or "other" in answer:
                    return False
            except Exception:
                pass
        return self._rule_based(user_input)

    @staticmethod
    def _rule_based(user_input: str) -> bool:
        text = user_input or ""

        # 明显的预约表达（有时间 + 项目，或要求推荐项目）不算咨询
        if any(hint in text for hint in BOOKING_HINTS):
            return False

        from agents.task_classification.task_classifier import RECOMMEND_WORDS, TIME_HINTS, TaskClassifier

        has_time = any(hint in text for hint in TIME_HINTS)
        has_item = TaskClassifier._has_item_keyword(text)
        if has_time and has_item:
            return False
        if has_item and any(word in text for word in RECOMMEND_WORDS):
            return False

        from .prompt_builder import PromptBuilder

        if PromptBuilder.is_safety_critical(text):
            return True
        if any(keyword in text for keyword in CONSULT_KEYWORDS):
            return True
        return text.strip().endswith(("?", "？", "吗", "呢"))