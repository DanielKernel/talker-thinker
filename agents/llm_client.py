"""
LLM客户端抽象层
支持多种LLM后端
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLM客户端抽象基类"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """生成响应"""
        pass

    @abstractmethod
    async def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """使用消息列表生成响应"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式生成响应"""
        pass

    async def close(self) -> None:
        """关闭客户端，释放资源"""
        pass


class OpenAIClient(LLMClient):
    """OpenAI客户端（兼容OpenAI API格式的服务）"""

    def __init__(
        self,
        model: str = "DeepSeek-V3.2",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self._client = None
        self._api_key = api_key
        self._base_url = base_url
        self._http_client = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            import os
            from openai import AsyncOpenAI

            # 临时禁用代理环境变量，避免代理导致的问题
            proxy_vars = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                          'all_proxy', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']
            saved_proxy = {k: os.environ.get(k) for k in proxy_vars}
            for k in proxy_vars:
                os.environ.pop(k, None)

            try:
                # 创建独立的 HTTP 客户端（不带代理）
                self._http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                    proxy=None,  # 明确禁用代理
                )
            finally:
                # 恢复代理环境变量
                for k, v in saved_proxy.items():
                    if v is not None:
                        os.environ[k] = v

            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                http_client=self._http_client,
            )
        return self._client

    async def close(self) -> None:
        """关闭客户端，释放资源"""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None
                self._client = None

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = await self._get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        # 安全检查：确保响应有效
        if response.choices and len(response.choices) > 0:
            message = response.choices[0].message
            if message and message.content:
                return message.content
        return ""

    async def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = await self._get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        # 安全检查：确保响应有效
        if response.choices and len(response.choices) > 0:
            message = response.choices[0].message
            if message and message.content:
                return message.content
        return ""

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        stream = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            # 安全检查：确保 choices 不为空且 delta.content 存在
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content


class AnthropicClient(LLMClient):
    """Anthropic客户端"""

    def __init__(self, model: str = "claude-3-haiku-20240307", api_key: Optional[str] = None):
        self.model = model
        self._client = None
        self._api_key = api_key
        self._http_client = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            import os
            from anthropic import AsyncAnthropic

            # 临时禁用代理环境变量，避免代理导致的问题
            proxy_vars = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                          'all_proxy', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']
            saved_proxy = {k: os.environ.get(k) for k in proxy_vars}
            for k in proxy_vars:
                os.environ.pop(k, None)

            try:
                # 创建独立的 HTTP 客户端（不带代理）
                self._http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                    proxy=None,  # 明确禁用代理
                )
            finally:
                # 恢复代理环境变量
                for k, v in saved_proxy.items():
                    if v is not None:
                        os.environ[k] = v

            self._client = AsyncAnthropic(
                api_key=self._api_key,
                http_client=self._http_client,
            )
        return self._client

    async def close(self) -> None:
        """关闭客户端，释放资源"""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None
                self._client = None

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = await self._get_client()
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.content[0].text

    async def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = await self._get_client()

        # 转换消息格式
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            **kwargs,
        }
        if system_prompt:
            params["system"] = system_prompt

        response = await client.messages.create(**params)
        return response.content[0].text

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        async with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text


class MockLLMClient(LLMClient):
    """模拟LLM客户端（用于测试）"""

    def __init__(self, response_delay: float = 0.1):
        self.response_delay = response_delay

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        await asyncio.sleep(self.response_delay)
        return f"[模拟响应] 收到提示: {prompt[:50]}..."

    async def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        await asyncio.sleep(self.response_delay)
        last_user_msg = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            ""
        )
        return f"[模拟响应] 回复: {last_user_msg[:50]}..."

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        response = f"[模拟流式响应] {prompt[:30]}..."
        for char in response:
            await asyncio.sleep(0.02)
            yield char


def create_llm_client(
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """创建LLM客户端"""
    if provider == "openai":
        return OpenAIClient(
            model=model or "DeepSeek-V3.2",
            api_key=api_key,
            base_url=base_url,
        )
    elif provider == "anthropic":
        return AnthropicClient(model=model or "claude-3-haiku-20240307", api_key=api_key)
    elif provider == "mock":
        return MockLLMClient()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
