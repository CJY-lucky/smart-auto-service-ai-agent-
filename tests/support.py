"""测试替身：假的大模型。"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence


class FakeChatModel:
    """按脚本返回内容的假模型，用来验证 Agent 的解析与分支逻辑。

    responses 可以是一个字符串（每次返回相同内容），也可以是列表（按顺序返回）。
    """

    provider = "fake"
    model = "fake-model"

    def __init__(self, responses: Any = "{}"):
        self.responses = responses
        self.calls: List[Sequence[Dict[str, str]]] = []
        self._index = 0

    def _next(self) -> str:
        if isinstance(self.responses, str):
            return self.responses
        if not self.responses:
            return "{}"
        value = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        return value

    async def acomplete(self, messages, temperature: Optional[float] = None) -> str:
        self.calls.append(messages)
        return self._next()

    async def astream(self, messages, temperature: Optional[float] = None) -> AsyncIterator[str]:
        text = await self.acomplete(messages, temperature)
        for char in text:
            yield char

    async def acomplete_json(self, messages, temperature: Optional[float] = None) -> Dict[str, Any]:
        text = await self.acomplete(messages, temperature)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}