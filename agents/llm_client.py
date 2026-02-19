"""
LLM客户端抽象层
支持多种LLM后端
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional


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

    async def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

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

    async def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

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
