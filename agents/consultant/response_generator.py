"""回答生成：优先用大模型润色，没有模型时基于检索结果拼装。

安全兜底：无论走哪条路，高风险问题都会在回答前加上明确的安全提示。
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List

from .prompt_builder import PromptBuilder

ROLE = "咨询机器人"


class ResponseGenerator:
    """咨询回答生成器。"""

    def __init__(self, llm=None):
        self.llm = llm
        self.prompt_builder = PromptBuilder()

    async def generate_response(self, user_input: str, knowledge_docs: List[Dict[str, Any]]) -> str:
        text = ""
        async for token in self.generate_response_stream(user_input, knowledge_docs):
            text += token
        return text

    async def generate_response_stream(
        self, user_input: str, knowledge_docs: List[Dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        yield f"[REPLY][{ROLE}]"

        prefix = ""
        if self.prompt_builder.is_safety_critical(user_input):
            prefix = self.prompt_builder.safety_reply(user_input) + "\n"

        if self.llm is None:
            body = self._fallback_answer(user_input, knowledge_docs)
            for char in prefix + body:
                yield char
            return

        try:
            prompt = self.prompt_builder.build_consultation_prompt(user_input, knowledge_docs)
            buffer = ""
            async for chunk in self.llm.astream([{"role": "user", "content": prompt}], temperature=0.3):
                buffer += chunk
            answer = buffer.strip() or self._fallback_answer(user_input, knowledge_docs)
            for char in prefix + answer:
                yield char
        except Exception:
            body = self._fallback_answer(user_input, knowledge_docs)
            for char in prefix + body:
                yield char

    def _fallback_answer(self, user_input: str, knowledge_docs: List[Dict[str, Any]]) -> str:
        if not knowledge_docs:
            return (
                "抱歉，门店资料里没有查到相关信息，建议您致电门店确认，我们会给您准确的答复。"
                "如果您想约个时间到店当面沟通，我也可以直接帮您安排。"
            )

        parts = []
        for document in knowledge_docs[:2]:
            content = (document.get("content") or "").strip()
            if content:
                parts.append(content)
        answer = "\n".join(parts)
        answer += "\n如果和您车的实际情况有出入，建议到店让技师用检测设备确认一下。"
        return answer

    def create_unrelated_message(self) -> str:
        return f"[THOUGHT][{ROLE}]这个问题不属于保养咨询，我转回给归类机器人处理。"