"""模型工厂：把环境变量翻译成可用的聊天模型与向量模型。

设计取舍：
- 底层用 LangChain 的 OpenAI 兼容实现（符合项目技术栈）；
- 上层只暴露一个很小的接口（acomplete / astream / embed），这样单元测试可以
  直接注入假模型，不需要联网、也不需要真实的 API Key；
- 没有配置密钥时不抛异常，而是返回 None，让 Agent 走规则兜底逻辑。
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CHAT_PROVIDERS = {"deepseek", "qwen", "zhipu", "openai", "openai-compatible", "azure"}
EMBEDDING_PROVIDERS = {"openai", "qwen", "zhipu", "azure", "openai-compatible", "local"}

DEFAULT_CHAT_CONFIG: Dict[str, Dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-plus"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
}

DEFAULT_EMBEDDING_CONFIG: Dict[str, Dict[str, str]] = {
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "text-embedding-v3"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "embedding-3"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "text-embedding-3-small"},
}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_chat_provider() -> str:
    return (_env("MODEL_PROVIDER", "deepseek") or "deepseek").strip().lower()


def get_embedding_provider() -> str:
    return (_env("EMBEDDING_PROVIDER", "local") or "local").strip().lower()


def is_llm_configured() -> bool:
    """是否具备调用大模型的条件。"""

    provider = get_chat_provider()
    if provider == "azure":
        return bool(_env("AZURE_OPENAI_API_KEY") and _env("AZURE_OPENAI_ENDPOINT"))
    return bool(_env("LLM_API_KEY"))


class ChatModel:
    """最小聊天模型接口。"""

    provider: str = "unknown"
    model: str = "unknown"

    async def acomplete(
        self, messages: Sequence[Dict[str, str]], temperature: Optional[float] = None
    ) -> str:
        raise NotImplementedError

    async def astream(
        self, messages: Sequence[Dict[str, str]], temperature: Optional[float] = None
    ) -> AsyncIterator[str]:
        """默认实现：整段生成后按字符吐出，子类可按需覆盖。"""

        text = await self.acomplete(messages, temperature=temperature)
        for char in text:
            yield char

    async def acomplete_json(
        self, messages: Sequence[Dict[str, str]], temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """要求模型输出 JSON，并做一次容错解析。"""

        from utils.json_utils import extract_json_object

        text = await self.acomplete(messages, temperature=temperature)
        return extract_json_object(text)


class LangChainChatModel(ChatModel):
    """基于 LangChain ChatOpenAI 的实现。"""

    def __init__(self, llm: Any, provider: str, model: str):
        self._llm = llm
        self.provider = provider
        self.model = model

    @staticmethod
    def _to_lc_messages(messages: Sequence[Dict[str, str]]) -> List[Any]:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        mapping = {"system": SystemMessage, "assistant": AIMessage, "user": HumanMessage}
        converted = []
        for message in messages:
            role = message.get("role", "user")
            converted.append(mapping.get(role, HumanMessage)(content=message.get("content", "")))
        return converted

    async def acomplete(
        self, messages: Sequence[Dict[str, str]], temperature: Optional[float] = None
    ) -> str:
        kwargs = {} if temperature is None else {"temperature": temperature}
        response = await self._llm.ainvoke(self._to_lc_messages(messages), **kwargs)
        return getattr(response, "content", str(response))

    async def astream(
        self, messages: Sequence[Dict[str, str]], temperature: Optional[float] = None
    ) -> AsyncIterator[str]:
        async for chunk in self._llm.astream(self._to_lc_messages(messages)):
            content = getattr(chunk, "content", "")
            if content:
                yield content


def create_chat_model(temperature: float = 0.0, *, required: bool = False) -> Optional[ChatModel]:
    """创建聊天模型；未配置密钥时返回 None（required=True 时抛错）。"""

    provider = get_chat_provider()
    if provider not in CHAT_PROVIDERS:
        raise ValueError(
            "不支持的 MODEL_PROVIDER=%r，可选：%s" % (provider, ", ".join(sorted(CHAT_PROVIDERS)))
        )

    if not is_llm_configured():
        if required:
            raise RuntimeError(
                "未检测到大模型密钥。请在 .env 中配置 LLM_API_KEY（DeepSeek 平台可获取）。"
            )
        logger.warning("未配置 LLM_API_KEY，聊天模型不可用，系统将使用规则兜底模式。")
        return None

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI
        from pydantic import SecretStr

        llm = AzureChatOpenAI(
            azure_deployment=_env("AZURE_OPENAI_DEPLOYMENT"),
            api_version=_env("AZURE_OPENAI_VERSION"),
            azure_endpoint=_env("AZURE_OPENAI_ENDPOINT"),
            api_key=SecretStr(_env("AZURE_OPENAI_API_KEY", "") or ""),
            temperature=temperature,
        )
        deployment = _env("AZURE_OPENAI_DEPLOYMENT", "azure") or "azure"
        return LangChainChatModel(llm, provider, deployment)

    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    defaults = DEFAULT_CHAT_CONFIG.get(provider, {})
    model = _env("LLM_MODEL", defaults.get("model")) or defaults.get("model") or "deepseek-chat"
    base_url = _env("LLM_BASE_URL", defaults.get("base_url"))

    kwargs: Dict[str, Any] = {
        "model": model,
        "api_key": SecretStr(_env("LLM_API_KEY", "") or ""),
        "temperature": temperature,
        "max_retries": 2,
        "timeout": 60,
    }
    if base_url:
        kwargs["base_url"] = base_url

    return LangChainChatModel(ChatOpenAI(**kwargs), provider, model)


class LocalHashEmbedding:
    """本地确定性向量：字符 n-gram 哈希 + L2 归一化。

    不是为了替代真实 Embedding，而是让项目在"零密钥、零网络"的情况下也能
    完整跑通（离线演示、单元测试、CI），同时保留同一个检索接口。
    """

    provider = "local"
    model = "local-hash-embedding"

    def __init__(self, dimension: int = 512):
        self.dimension = dimension

    def _vector(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        normalized = (text or "").strip().lower()
        if not normalized:
            return vector

        grams: List[str] = list(normalized.split())
        for size in (2, 3):
            limit = max(len(normalized) - size + 1, 0)
            grams.extend(normalized[i : i + size] for i in range(limit))

        for gram in grams:
            digest = hashlib.md5(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_query(self, text: str) -> List[float]:
        return self._vector(text)

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        return [self._vector(text) for text in texts]


class LangChainEmbedding:
    """OpenAI 兼容的 Embedding 封装。"""

    def __init__(self, embedding: Any, provider: str, model: str):
        self._embedding = embedding
        self.provider = provider
        self.model = model

    def embed_query(self, text: str) -> List[float]:
        return list(self._embedding.embed_query(text))

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        return [list(vector) for vector in self._embedding.embed_documents(list(texts))]


def create_embedding_model(*, required: bool = False):
    """创建向量模型；EMBEDDING_PROVIDER=local 时完全离线可用。"""

    provider = get_embedding_provider()
    if provider not in EMBEDDING_PROVIDERS:
        raise ValueError(
            "不支持的 EMBEDDING_PROVIDER=%r，可选：%s"
            % (provider, ", ".join(sorted(EMBEDDING_PROVIDERS)))
        )

    if provider == "local":
        return LocalHashEmbedding()

    api_key = _env("EMBEDDING_API_KEY") or _env("LLM_API_KEY")
    if not api_key:
        if required:
            raise RuntimeError("未配置 EMBEDDING_API_KEY，无法调用向量模型。")
        logger.warning("未配置 Embedding 密钥，自动降级为本地确定性向量。")
        return LocalHashEmbedding()

    if provider == "azure":
        from langchain_openai import AzureOpenAIEmbeddings
        from pydantic import SecretStr

        embedding = AzureOpenAIEmbeddings(
            azure_deployment=_env("AZURE_OPENAI_DEPLOYMENT_EMBEDDING"),
            api_version=_env("AZURE_OPENAI_EMBEDDING_VERSION", "2023-05-15"),
            azure_endpoint=_env("AZURE_OPENAI_ENDPOINT_EMBEDDING") or _env("AZURE_OPENAI_ENDPOINT"),
            api_key=SecretStr(_env("AZURE_OPENAI_API_KEY", "") or ""),
        )
        deployment = _env("AZURE_OPENAI_DEPLOYMENT_EMBEDDING", "azure") or "azure"
        return LangChainEmbedding(embedding, provider, deployment)

    from langchain_openai import OpenAIEmbeddings
    from pydantic import SecretStr

    defaults = DEFAULT_EMBEDDING_CONFIG.get(provider, {})
    model = _env("EMBEDDING_MODEL", defaults.get("model")) or defaults.get("model") or "text-embedding-3-small"
    base_url = _env("EMBEDDING_BASE_URL", defaults.get("base_url")) or _env("LLM_BASE_URL")

    kwargs: Dict[str, Any] = {
        "model": model,
        "api_key": SecretStr(api_key),
        # DashScope 等 OpenAI 兼容服务只接受纯文本，关闭 token 批量编码
        "check_embedding_ctx_length": False,
    }
    if base_url:
        kwargs["base_url"] = base_url

    return LangChainEmbedding(OpenAIEmbeddings(**kwargs), provider, model)