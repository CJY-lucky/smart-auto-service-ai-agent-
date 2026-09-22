"""咨询提示词构建。

汽车保养涉及行车安全，所以提示词的约束比普通客服更严：
- 必须基于知识库回答，不允许编造价格、规格和期限；
- 高风险问题（仪表盘红灯、刹车异常）必须给出明确的"立即停车/尽快到店"指引；
- 知识库没有的内容要给兜底话术，而不是硬猜。
"""

from __future__ import annotations

from typing import Any, Dict, List

SAFETY_KEYWORDS = ["红灯", "机油灯", "水温", "冒烟", "刹车失灵", "刹不住", "异味", "焦味", "方向盘锁死", "异响严重"]


class PromptBuilder:
    """提示词与安全话术。"""

    def _system_prompt(self) -> str:
        return (
            "你是汽车快修保养门店的前台服务顾问，负责解答车主关于保养周期、项目价格、"
            "机油规格、故障灯含义、质保政策、门店位置与预约政策的问题。\n"
            "要求：\n"
            "1. 只依据提供的门店知识资料回答，不要编造价格、配件规格和质保期限；\n"
            "2. 如果资料里没有答案，礼貌说明并建议致电门店确认，不要猜；\n"
            "3. 涉及行车安全的问题，必须明确提醒车主停车或尽快到店检查；\n"
            "4. 语言简洁专业，像门店顾问在跟车主说话，不要罗列资料原文。"
        )

    def _classification_prompt(self) -> str:
        return (
            "判断用户这句话属于哪一类，只回答一个英文词：\n"
            "consult —— 咨询服务与价格、保养周期、故障灯、机油规格、质保、位置等问题；\n"
            "booking —— 想预约、改约、取消预约，或者直接说要做什么保养项目；\n"
            "other —— 与汽车保养完全无关（天气、股票、闲聊等）。\n"
            "只输出 consult、booking 或 other 中的一个。"
        )

    def build_classification_prompt(self, user_input: str) -> str:
        return f"{self._classification_prompt()}\n用户说：{user_input}"

    def build_consultation_prompt(self, user_input: str, knowledge_docs: List[Dict[str, Any]]) -> str:
        context = self.build_knowledge_context(knowledge_docs)
        safety = self.build_safety_note(user_input)
        return f"{self._system_prompt()}\n\n{context}\n{safety}\n车主问题：{user_input}\n\n请回答："

    @staticmethod
    def build_knowledge_context(knowledge_docs: List[Dict[str, Any]]) -> str:
        if not knowledge_docs:
            return "门店知识资料：暂无直接匹配的资料。"
        lines = ["门店知识资料："]
        for index, document in enumerate(knowledge_docs, 1):
            lines.append(f"{index}. 【{document.get('category', '资料')}】{document.get('content', '')}")
        return "\n".join(lines)

    @staticmethod
    def build_safety_note(user_input: str) -> str:
        if any(keyword in (user_input or "") for keyword in SAFETY_KEYWORDS):
            return (
                "注意：这是一个涉及行车安全的问题。回答里必须先给出安全提示"
                "（例如立即靠边停车、不要再继续行驶、联系救援或尽快到店），再解释原因。"
            )
        return ""

    @staticmethod
    def is_safety_critical(user_input: str) -> bool:
        return any(keyword in (user_input or "") for keyword in SAFETY_KEYWORDS)

    @staticmethod
    def safety_reply(user_input: str) -> str:
        if "刹车" in user_input:
            return "刹车相关的问题请不要继续行驶，建议就近靠边停车并联系我们安排救援或拖车。"
        return "请先靠边停车熄火，不要继续行驶，联系我们安排救援或直接到店检查。"