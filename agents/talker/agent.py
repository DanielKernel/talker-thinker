"""
Talker Agent - 对话者
负责快速响应、简单意图闭环、实时反馈
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from config import settings
from context.types import Message, ResponseLayer, TaskComplexity
from agents.llm_client import LLMClient, create_llm_client


@dataclass
class IntentClassification:
    """意图分类结果"""
    intent_type: str
    complexity: TaskComplexity
    confidence: float
    reasoning: str = ""


class TalkerAgent:
    """
    Talker Agent - 对话者

    核心职责：
    1. 快速响应（< 500ms）
    2. 简单意图闭环
    3. 实时反馈和进度播报
    4. 决定是否需要Thinker介入
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: Optional[str] = None,
    ):
        self.llm = llm_client or create_llm_client(
            provider="openai",
            model=model or settings.TALKER_MODEL,
        )
        self.name = "talker"
        self.timeout_ms = settings.TALKER_TIMEOUT_MS
        self.temperature = settings.TALKER_TEMPERATURE

        # 进度回调
        self._progress_callback: Optional[Callable] = None

        # 统计信息
        self._stats = {
            "total_requests": 0,
            "simple_responses": 0,
            "delegated_to_thinker": 0,
            "errors": 0,
        }

    def set_progress_callback(self, callback: Callable) -> None:
        """设置进度回调函数"""
        self._progress_callback = callback

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        处理用户输入

        Args:
            user_input: 用户输入
            context: 上下文信息

        Yields:
            str: 响应内容（支持流式输出）
        """
        self._stats["total_requests"] += 1
        start_time = time.time()

        try:
            # 1. 快速意图分类
            classification = await self.classify_intent(user_input, context)

            # 2. 根据复杂度选择响应策略
            if classification.complexity == TaskComplexity.SIMPLE:
                # 简单任务：直接响应
                self._stats["simple_responses"] += 1
                async for chunk in self._quick_response(user_input, context):
                    yield chunk

            elif classification.complexity == TaskComplexity.MEDIUM:
                # 中等任务：快速响应 + 提示深度思考
                async for chunk in self._medium_response(user_input, context):
                    yield chunk

            else:
                # 复杂任务：需要Thinker
                self._stats["delegated_to_thinker"] += 1
                async for chunk in self._complex_response(user_input, context):
                    yield chunk

        except Exception as e:
            self._stats["errors"] += 1
            yield f"抱歉，处理时出现问题：{str(e)}"

    async def classify_intent(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntentClassification:
        """
        快速意图分类

        Args:
            user_input: 用户输入
            context: 上下文

        Returns:
            IntentClassification: 分类结果
        """
        # 基于规则的快速分类
        complexity = self._quick_complexity_check(user_input)

        if complexity:
            return IntentClassification(
                intent_type="rule_based",
                complexity=complexity,
                confidence=0.8,
                reasoning="基于规则的快速分类",
            )

        # 使用LLM进行分类
        try:
            prompt = self._build_classification_prompt(user_input, context)
            response = await asyncio.wait_for(
                self.llm.generate(prompt, max_tokens=100, temperature=0.3),
                timeout=0.5,  # 500ms超时
            )
            return self._parse_classification_response(response)
        except asyncio.TimeoutError:
            # 超时时使用简单分类
            return IntentClassification(
                intent_type="timeout_fallback",
                complexity=TaskComplexity.SIMPLE,
                confidence=0.5,
                reasoning="分类超时，使用默认简单分类",
            )
        except Exception:
            return IntentClassification(
                intent_type="error_fallback",
                complexity=TaskComplexity.SIMPLE,
                confidence=0.5,
                reasoning="分类出错，使用默认简单分类",
            )

    def _quick_complexity_check(self, user_input: str) -> Optional[TaskComplexity]:
        """基于规则的快速复杂度检查"""
        text = user_input.lower()

        # 问候/寒暄 -> 简单
        greetings = ["你好", "嗨", "hi", "hello", "在吗", "在不在"]
        if any(g in text for g in greetings) and len(text) < 20:
            return TaskComplexity.SIMPLE

        # 简单计算 -> 简单
        if any(c in text for c in ["+", "-", "*", "/", "等于", "多少"]) and len(text) < 30:
            return TaskComplexity.SIMPLE

        # 简单查询 -> 简单
        simple_queries = ["天气", "时间", "日期", "几点"]
        if any(q in text for q in simple_queries) and len(text) < 30:
            return TaskComplexity.SIMPLE

        # 复杂关键词 -> 复杂
        complex_keywords = [
            "分析", "比较", "评估", "设计", "规划", "优化",
            "为什么", "怎么理解", "深入", "详细解释", "原理解析",
            "多步", "步骤", "方案", "策略",
        ]
        if any(k in text for k in complex_keywords):
            return TaskComplexity.COMPLEX

        # 中等长度 -> 中等
        if len(text) > 100:
            return TaskComplexity.MEDIUM

        return None

    def _build_classification_prompt(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建分类Prompt"""
        return f"""请判断以下用户请求的复杂度：

用户输入：{user_input}

复杂度标准：
1. simple - 简单问候、简单查询、一句话能回答的问题
2. medium - 需要简短解释、包含多个子问题
3. complex - 需要深度分析、多步推理、复杂规划

只返回复杂度级别（simple/medium/complex），不要解释。"""

    def _parse_classification_response(self, response: str) -> IntentClassification:
        """解析分类响应"""
        response = response.lower().strip()

        if "simple" in response:
            complexity = TaskComplexity.SIMPLE
        elif "complex" in response:
            complexity = TaskComplexity.COMPLEX
        elif "medium" in response:
            complexity = TaskComplexity.MEDIUM
        else:
            complexity = TaskComplexity.SIMPLE

        return IntentClassification(
            intent_type="llm_based",
            complexity=complexity,
            confidence=0.7,
            reasoning=f"LLM分类结果: {response}",
        )

    async def _quick_response(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """快速响应（简单任务）"""
        prompt = self._build_response_prompt(user_input, context, "quick")

        try:
            async for chunk in self.llm.stream_generate(
                prompt,
                max_tokens=200,
                temperature=self.temperature,
            ):
                yield chunk
        except Exception:
            yield "好的，我了解了。"

    async def _medium_response(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """中等复杂度响应"""
        # 先给一个即时反馈
        yield "好的，让我想想这个问题...\n\n"

        prompt = self._build_response_prompt(user_input, context, "medium")

        try:
            async for chunk in self.llm.stream_generate(
                prompt,
                max_tokens=500,
                temperature=self.temperature,
            ):
                yield chunk
        except Exception:
            yield "抱歉，处理时出现问题。"

    async def _complex_response(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """复杂任务响应（需要Thinker）"""
        # 给出即时反馈，表明需要深度思考
        yield "这个问题有点复杂，让我深度思考一下...\n\n"
        yield "[NEEDS_THINKER]"  # 特殊标记，表示需要Thinker

    def _build_response_prompt(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        mode: str = "quick",
    ) -> str:
        """构建响应Prompt"""
        if mode == "quick":
            return f"""你是一个友好、高效的对话助手。请简洁地回复用户。

用户：{user_input}

要求：
1. 回复简洁（不超过100字）
2. 语气友好
3. 直接回答问题

回复："""

        elif mode == "medium":
            context_str = ""
            if context and "messages" in context:
                recent = context["messages"][-3:]
                context_str = "\n".join([
                    f"[{m.get('role', 'user')}]: {m.get('content', '')}"
                    for m in recent
                ])

            return f"""你是一个友好的对话助手。

对话历史：
{context_str}

当前用户问题：{user_input}

请提供一个有帮助的回答（200字以内）："""

        return f"用户：{user_input}\n\n请回复："

    async def broadcast_progress(
        self,
        message: str,
        progress: Optional[float] = None,
    ) -> None:
        """
        播报进度

        Args:
            message: 进度消息
            progress: 进度百分比（0-100）
        """
        if self._progress_callback:
            await self._progress_callback({
                "agent": self.name,
                "message": message,
                "progress": progress,
                "timestamp": time.time(),
            })

    async def format_thinker_result(
        self,
        thinker_result: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        格式化Thinker的结果为自然口语

        Args:
            thinker_result: Thinker的原始输出
            context: 上下文

        Returns:
            str: 格式化后的口语表达
        """
        prompt = f"""请将以下内容转换为更自然、口语化的表达：

{thinker_result}

要求：
1. 保持核心内容不变
2. 使用更自然的口语表达
3. 适当分段，提高可读性
4. 不需要添加"根据搜索结果"等前缀

转换后的表达："""

        try:
            result = await self.llm.generate(
                prompt,
                max_tokens=len(thinker_result) + 200,
                temperature=0.5,
            )
            return result
        except Exception:
            return thinker_result

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "success_rate": (
                (self._stats["total_requests"] - self._stats["errors"])
                / max(self._stats["total_requests"], 1)
            ),
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_requests": 0,
            "simple_responses": 0,
            "delegated_to_thinker": 0,
            "errors": 0,
        }
