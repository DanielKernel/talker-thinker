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
from agents.llm_client import LLMClient, StreamMetrics, create_llm_client


@dataclass
class IntentClassification:
    """意图分类结果"""
    intent_type: str
    complexity: TaskComplexity
    confidence: float
    reasoning: str = ""


@dataclass
class ResponseWithMetrics:
    """带指标的响应"""
    content: str = ""
    metrics: Optional[StreamMetrics] = None


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
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # 获取API密钥
        effective_api_key = api_key or settings.VOLCES_API_KEY or settings.OPENAI_API_KEY

        # 检查API密钥是否有效
        if not effective_api_key or effective_api_key.startswith("your-"):
            print("警告: 未配置有效的API密钥，请在 .env 文件中设置 VOLCES_API_KEY 或 OPENAI_API_KEY")
            self._api_key_configured = False
        else:
            self._api_key_configured = True

        self.llm = llm_client or create_llm_client(
            provider="openai",
            model=model or settings.TALKER_MODEL,
            api_key=effective_api_key,
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.name = "talker"
        self.timeout_ms = settings.TALKER_TIMEOUT_MS
        self.temperature = settings.TALKER_TEMPERATURE

        # 进度回调
        self._progress_callback: Optional[Callable] = None

        # 共享上下文引用（由外部设置）
        self._shared_context = None

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

    def set_shared_context(self, shared_context) -> None:
        """设置共享上下文"""
        self._shared_context = shared_context

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

    async def process_with_metrics(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[AsyncIterator[str], "StreamMetrics"]:
        """
        处理用户输入（带详细指标）

        Args:
            user_input: 用户输入
            context: 上下文信息

        Returns:
            tuple: (内容迭代器, 指标对象)
        """
        metrics = StreamMetrics()
        content_chunks = []

        async def generator():
            async for chunk in self.process(user_input, context):
                content_chunks.append(chunk)
                yield chunk
            # 从context获取指标（如果有）
            if context and "_llm_metrics" in context:
                metrics.input_tokens = context["_llm_metrics"].get("input_tokens", 0)
                metrics.output_tokens = context["_llm_metrics"].get("output_tokens", 0)
                metrics.ttft_ms = context["_llm_metrics"].get("ttft_ms", 0)
                metrics.tpot_ms = context["_llm_metrics"].get("tpot_ms", 0)
                metrics.tps = context["_llm_metrics"].get("tps", 0)
                metrics.total_time_ms = context["_llm_metrics"].get("total_time_ms", 0)

        return generator(), metrics

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

        # 复杂任务关键词 -> COMPLEX（优先判断）
        complex_keywords = [
            "分析", "比较", "评估", "设计", "规划", "优化",
            "深入", "详细解释", "原理解析", "多步", "步骤", "方案", "策略",
            "多个", "同时", "不同", "排名", "排列", "排序", "推荐",
            "最新", "实时", "评分", "打分", "对比", "综合",
            "详细", "完整", "全面", "汇总", "整理",
        ]
        if any(k in text for k in complex_keywords):
            return TaskComplexity.COMPLEX

        # 需要详细回答的关键词 -> MEDIUM
        detail_keywords = [
            "什么", "哪些", "特点", "特征", "功能", "介绍",
            "解释", "说明", "怎样", "如何", "为什么",
            "地址", "电话", "联系方式", "信息",
        ]
        if any(k in text for k in detail_keywords):
            return TaskComplexity.MEDIUM

        # 长文本 -> 中等
        if len(text) > 100:
            return TaskComplexity.MEDIUM

        # 默认返回None，让LLM分类
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
        # 检查API密钥
        if not self._api_key_configured:
            yield "请先配置API密钥。在 .env 文件中设置 VOLCES_API_KEY 或 OPENAI_API_KEY。"
            return

        prompt = self._build_response_prompt(user_input, context, "quick")

        try:
            has_content = False
            # 使用带指标的流式生成
            stream, metrics = await self.llm.stream_generate_with_metrics(
                prompt,
                max_tokens=200,
                temperature=self.temperature,
            )
            async for chunk in stream:
                has_content = True
                yield chunk

            # 保存指标到context
            if context is not None:
                context["_llm_metrics"] = {
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "ttft_ms": metrics.ttft_ms,
                    "tpot_ms": metrics.tpot_ms,
                    "tps": metrics.tps,
                    "total_time_ms": metrics.total_time_ms,
                }

            if not has_content:
                yield "抱歉，我暂时无法连接到模型服务。"
        except Exception as e:
            yield f"抱歉，处理时出现问题：{str(e)}"

    async def generate_progress_broadcast(
        self,
        original_query: str,
        recent_output: str,
        elapsed_time: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        根据上下文生成智能进度播报

        Args:
            original_query: 用户原始问题
            recent_output: Thinker最近的输出内容
            elapsed_time: 已耗时（秒）
            context: 上下文

        Returns:
            str: 进度播报消息
        """
        # 截取最近的输出（避免prompt过长）
        recent_snippet = recent_output[-500:] if len(recent_output) > 500 else recent_output

        prompt = f"""你是一个友好的助手，正在帮用户处理一个复杂任务。请根据当前进度，用一句话（不超过30字）向用户播报当前进度。

用户问题：{original_query}

已耗时：{elapsed_time:.0f}秒

当前处理进度：
{recent_snippet}

要求：
1. 根据实际处理内容描述进度，不要重复
2. 语气自然、友好
3. 简洁（不超过30字）
4. 如果正在规划，说"正在规划..."
5. 如果正在分析，说"正在分析..."
6. 如果正在对比，说"正在对比..."
7. 如果正在生成结果，说"正在整理结果..."

只输出一句话，不要解释："""

        try:
            # 使用快速响应（低token、低温度）
            response = await asyncio.wait_for(
                self.llm.generate(
                    prompt,
                    max_tokens=50,
                    temperature=0.3,
                ),
                timeout=2.0  # 2秒超时
            )
            return response.strip()
        except asyncio.TimeoutError:
            # 超时时返回基于时间的默认消息
            if elapsed_time < 10:
                return "正在处理中..."
            elif elapsed_time < 30:
                return "正在深入分析..."
            else:
                return "即将完成，请稍候..."
        except Exception:
            return f"已处理 {elapsed_time:.0f} 秒..."

    async def _medium_response(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """中等复杂度响应"""
        # 检查API密钥
        if not self._api_key_configured:
            yield "请先配置API密钥。在 .env 文件中设置 VOLCES_API_KEY 或 OPENAI_API_KEY。"
            return

        prompt = self._build_response_prompt(user_input, context, "medium")

        try:
            has_content = False
            # 使用带指标的流式生成
            stream, metrics = await self.llm.stream_generate_with_metrics(
                prompt,
                max_tokens=500,
                temperature=self.temperature,
            )
            async for chunk in stream:
                has_content = True
                yield chunk

            # 保存指标到context
            if context is not None:
                context["_llm_metrics"] = {
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "ttft_ms": metrics.ttft_ms,
                    "tpot_ms": metrics.tpot_ms,
                    "tps": metrics.tps,
                    "total_time_ms": metrics.total_time_ms,
                }

            if not has_content:
                yield "抱歉，我暂时无法连接到模型服务。"
        except Exception as e:
            yield f"抱歉，处理时出现问题：{str(e)}"

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
        # 检测是否是记忆相关问题
        memory_keywords = ["记得", "说过", "问过", "刚才", "之前", "上次", "历史"]
        is_memory_query = any(kw in user_input for kw in memory_keywords)

        # 构建对话历史（所有模式都使用）
        context_str = ""
        if context and "messages" in context:
            # 记忆相关问题使用更多历史
            history_limit = 15 if is_memory_query else 5
            recent = context["messages"][-history_limit:] if len(context["messages"]) > 1 else []
            if recent:
                context_str = "\n对话历史：\n" + "\n".join([
                    f"[{'用户' if m.get('role') == 'user' else '助手'}]: {m.get('content', '')[:200]}"
                    for m in recent
                ]) + "\n"

        if mode == "quick":
            # 根据问题类型调整系统提示
            if is_memory_query:
                system_hint = """你是一个友好、高效的对话助手。
用户正在询问之前的对话内容。请仔细查看对话历史，准确回忆用户之前提到的内容。
如果找到了相关内容，直接告诉用户；如果没找到，诚实地说明。"""
            else:
                system_hint = "你是一个友好、高效的对话助手。请简洁地回复用户。"

            return f"""{system_hint}
{context_str}
当前用户消息：{user_input}

要求：
1. 回复简洁（不超过100字）
2. 语气友好
3. 结合对话历史理解用户意图
4. 直接回答问题

回复："""

        elif mode == "medium":
            if is_memory_query:
                system_hint = """你是一个友好的对话助手。
用户正在询问之前的对话内容。请仔细查看对话历史，准确回忆并总结用户之前提到的内容。"""
            else:
                system_hint = "你是一个友好的对话助手。"

            return f"""{system_hint}
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
