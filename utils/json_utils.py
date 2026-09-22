"""JSON 解析工具。

大模型即使被要求"只输出 JSON"，也经常带上 ```json 代码块或前后解释文字，
所以统一在这里做一次稳健提取，避免每个 Agent 各写一份。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> Dict[str, Any]:
    """从任意文本中提取第一个 JSON 对象，失败返回空字典。"""

    if not text:
        return {}

    candidates = []
    fenced = _CODE_FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    balanced = _extract_balanced_object(text)
    if balanced:
        candidates.append(balanced)

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _extract_balanced_object(text: str) -> Optional[str]:
    """扫描出第一个括号配平的 JSON 对象片段。"""

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None