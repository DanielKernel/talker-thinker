"""
Thinker Agent - 思考者
负责深度推理、长程规划、复杂任务处理
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from config import settings
from context.types import QualityScore, StepResult, TaskComplexity, TaskStatus
from agents.llm_client import LLMClient, StreamMetrics, create_llm_client


@dataclass
class TaskPlan:
    """任务规划"""
    intent: str
    constraints: List[str] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[Dict[str, str]] = field(default_factory=list)
    estimated_time: int = 0


class ThinkerAgent:
    """
    Thinker Agent - 思考者

    核心职责：
    1. 深度推理和分析
    2. 任务规划和拆解
    3. 步骤执行和协调
    4. 自我反思和质量控制
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
            self._api_key_configured = False
        else:
            self._api_key_configured = True

        self.llm = llm_client or create_llm_client(
            provider="openai",
            model=model or settings.THINKER_MODEL,
            api_key=effective_api_key,
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.name = "thinker"
        self.timeout_ms = settings.THINKER_TIMEOUT_MS
        self.temperature = settings.THINKER_TEMPERATURE

        # 进度回调
        self._progress_callback: Optional[Callable] = None

        # 技能调用器（可选）
        self._skill_invoker = None

        # 统计信息
        self._stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_steps": 0,
            "refinements": 0,
            "total_latency_ms": 0,
        }

    def set_progress_callback(self, callback: Callable) -> None:
        """设置进度回调函数"""
        self._progress_callback = callback

    def set_skill_invoker(self, invoker) -> None:
        """设置技能调用器"""
        self._skill_invoker = invoker

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        处理复杂任务

        Args:
            user_input: 用户输入
            context: 上下文信息

        Yields:
            str: 思考过程和结果（支持流式输出）
        """
        self._stats["total_tasks"] += 1
        start_time = time.time()

        # 累计指标
        total_input_tokens = 0
        total_output_tokens = 0
        total_ttft = 0
        llm_calls = 0

        try:
            # 1. 任务规划
            yield "[思考] 正在分析任务...\n"
            plan_start = time.time()
            plan = await self.plan_task(user_input, context)
            plan_time = (time.time() - plan_start) * 1000
            yield f"  ✓ 规划完成 ({plan_time:.0f}ms)\n"
            await self._report_progress("任务规划完成", 10)

            # 2. 展示规划
            yield f"\n[规划] 任务目标: {plan.intent}\n"
            yield f"[规划] 共{len(plan.steps)}个步骤\n\n"

            # 3. 逐步执行
            step_results: List[StepResult] = []
            for i, step in enumerate(plan.steps):
                step_num = i + 1
                progress = 10 + (step_num / len(plan.steps)) * 70

                yield f"[步骤{step_num}] {step.get('name', '执行中...')}...\n"
                await self._report_progress(
                    f"执行步骤{step_num}/{len(plan.steps)}",
                    progress,
                )

                # 执行步骤
                step_start = time.time()
                result = await self.execute_step(
                    step=step,
                    context=context,
                    previous_results=step_results,
                )
                step_results.append(result)
                step_time = (time.time() - step_start) * 1000

                if result.status == "success":
                    yield f"  ✓ 完成 ({step_time:.0f}ms)\n"
                else:
                    yield f"  ✗ 失败: {result.errors[0] if result.errors else '未知错误'}\n"

                self._stats["total_steps"] += 1

            # 4. 生成最终答案
            yield "\n[思考] 整合结果，生成最终答案...\n"
            await self._report_progress("生成最终答案", 85)

            answer_start = time.time()
            final_answer = await self.synthesize_answer(
                user_input=user_input,
                plan=plan,
                step_results=step_results,
                context=context,
            )
            answer_time = (time.time() - answer_start) * 1000

            # 5. 自我反思（可选）
            if settings.ENABLE_SELF_REFLECTION:
                yield "[思考] 检查答案质量...\n"
                await self._report_progress("质量检查", 95)

                quality = await self.reflect(
                    original_question=user_input,
                    answer=final_answer,
                    step_results=step_results,
                    context=context,
                )

                if quality.needs_revision and quality.overall_score < 80:
                    yield "[思考] 答案需要改进，正在优化...\n"
                    self._stats["refinements"] += 1

                    final_answer = await self.refine_answer(
                        original_question=user_input,
                        current_answer=final_answer,
                        quality=quality,
                        context=context,
                    )

            # 6. 输出最终结果
            await self._report_progress("完成", 100)
            self._stats["successful_tasks"] += 1

            yield "\n[答案]\n"
            yield final_answer

            # 保存指标到context
            total_time = (time.time() - start_time) * 1000
            if context is not None:
                context["_llm_metrics"] = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "ttft_ms": total_ttft,
                    "tpot_ms": total_time / max(total_output_tokens, 1),
                    "tps": total_output_tokens / (total_time / 1000) if total_time > 0 else 0,
                    "total_time_ms": total_time,
                }

        except Exception as e:
            self._stats["failed_tasks"] += 1
            yield f"\n[错误] 处理失败: {str(e)}\n"
            yield "[建议] 请稍后重试或简化您的问题"

        finally:
            elapsed = (time.time() - start_time) * 1000
            self._stats["total_latency_ms"] += elapsed

    async def plan_task(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskPlan:
        """
        规划任务

        Args:
            user_input: 用户输入
            context: 上下文

        Returns:
            TaskPlan: 任务规划
        """
        prompt = self._build_planning_prompt(user_input, context)

        try:
            response = await self.llm.generate(
                prompt,
                max_tokens=1000,
                temperature=self.temperature,
            )
            return self._parse_plan(response)
        except Exception:
            # 简单规划作为fallback
            return TaskPlan(
                intent=user_input[:100],
                steps=[{"name": "分析问题", "description": user_input}],
            )

    def _build_planning_prompt(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建规划Prompt"""
        skills_info = ""
        if self._skill_invoker:
            skills = self._skill_invoker.engine.list_skill_names()
            if skills:
                skills_info = f"\n可用技能: {', '.join(skills)}"

        return f"""作为一个任务规划专家，请分析以下用户请求并制定执行计划：

用户请求：{user_input}
{skills_info}

请输出JSON格式的计划：
{{
  "intent": "用户的核心意图（一句话）",
  "constraints": ["约束条件1", "约束条件2"],
  "steps": [
    {{
      "name": "步骤名称",
      "description": "详细描述",
      "skills": ["需要调用的技能"],
      "expected_output": "预期输出"
    }}
  ],
  "risks": [
    {{"risk": "风险描述", "mitigation": "缓解措施"}}
  ],
  "estimated_time": 预计秒数
}}

只输出JSON，不要其他内容。"""

    def _parse_plan(self, response: str) -> TaskPlan:
        """解析规划响应"""
        try:
            # 尝试提取JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return TaskPlan(
                    intent=data.get("intent", ""),
                    constraints=data.get("constraints", []),
                    steps=data.get("steps", []),
                    risks=data.get("risks", []),
                    estimated_time=data.get("estimated_time", 60),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback
        return TaskPlan(
            intent="处理用户请求",
            steps=[{"name": "分析", "description": "分析用户请求"}],
        )

    async def execute_step(
        self,
        step: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        previous_results: Optional[List[StepResult]] = None,
    ) -> StepResult:
        """
        执行单个步骤

        Args:
            step: 步骤定义
            context: 上下文
            previous_results: 之前步骤的结果

        Returns:
            StepResult: 步骤执行结果
        """
        step_name = step.get("name", "未命名步骤")
        start_time = time.time()

        try:
            # 检查是否需要调用技能
            skills = step.get("skills", [])
            intermediate_results = []

            if skills and self._skill_invoker:
                for skill_name in skills:
                    try:
                        # 构建技能参数
                        skill_params = self._extract_skill_params(
                            step, context, previous_results
                        )
                        result = await self._skill_invoker.invoke(
                            skill_name, skill_params, context
                        )
                        intermediate_results.append({
                            "skill": skill_name,
                            "output": result.formatted if result.success else result.error,
                        })
                    except Exception as e:
                        intermediate_results.append({
                            "skill": skill_name,
                            "output": f"技能调用失败: {str(e)}",
                        })

            # 使用LLM处理步骤
            prompt = self._build_step_prompt(step, context, previous_results)
            llm_result = await self.llm.generate(
                prompt,
                max_tokens=500,
                temperature=self.temperature,
            )

            latency = (time.time() - start_time) * 1000

            return StepResult(
                step_name=step_name,
                status="success",
                result=llm_result,
                intermediate_results=intermediate_results,
                skills_called=skills,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return StepResult(
                step_name=step_name,
                status="failed",
                result="",
                errors=[str(e)],
                latency_ms=latency,
            )

    def _build_step_prompt(
        self,
        step: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        previous_results: Optional[List[StepResult]] = None,
    ) -> str:
        """构建步骤执行Prompt"""
        prev_info = ""
        if previous_results:
            prev_info = "\n之前步骤的结果:\n" + "\n".join([
                f"- {r.step_name}: {r.result[:200]}"
                for r in previous_results[-3:]
            ])

        return f"""请执行以下步骤：

步骤名称：{step.get('name', '')}
步骤描述：{step.get('description', '')}
预期输出：{step.get('expected_output', '文字描述')}
{prev_info}

请直接输出执行结果："""

    def _extract_skill_params(
        self,
        step: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        previous_results: Optional[List[StepResult]] = None,
    ) -> Dict[str, Any]:
        """从上下文中提取技能参数"""
        # 简单实现：从步骤描述中提取
        params = {}
        desc = step.get("description", "")

        # 这里可以添加更智能的参数提取逻辑
        params["query"] = desc
        params["text"] = desc

        return params

    async def synthesize_answer(
        self,
        user_input: str,
        plan: TaskPlan,
        step_results: List[StepResult],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        整合步骤结果生成最终答案

        Args:
            user_input: 用户原始输入
            plan: 任务规划
            step_results: 步骤执行结果
            context: 上下文

        Returns:
            str: 最终答案
        """
        results_summary = "\n".join([
            f"【{r.step_name}】\n{r.result}"
            for r in step_results
        ])

        prompt = f"""基于以下分析结果，请回答用户的原始问题：

用户问题：{user_input}

分析过程：
{results_summary}

请提供一个完整、有帮助的回答："""

        return await self.llm.generate(
            prompt,
            max_tokens=1000,
            temperature=self.temperature,
        )

    async def reflect(
        self,
        original_question: str,
        answer: str,
        step_results: List[StepResult],
        context: Optional[Dict[str, Any]] = None,
    ) -> QualityScore:
        """
        自我反思

        Args:
            original_question: 原始问题
            answer: 当前答案
            step_results: 步骤结果
            context: 上下文

        Returns:
            QualityScore: 质量评分
        """
        prompt = f"""请评估以下答案的质量：

原始问题：{original_question}

答案：{answer}

请从以下维度评分（0-100）：
1. 完整性 - 是否完整回答了问题
2. 准确性 - 逻辑是否自洽，事实是否准确
3. 相关性 - 是否针对问题，有无冗余信息
4. 清晰性 - 语言是否清晰，结构是否合理
5. 实用性 - 是否有帮助，是否提供可操作建议

请输出JSON格式：
{{
  "completeness": 分数,
  "accuracy": 分数,
  "relevance": 分数,
  "clarity": 分数,
  "usefulness": 分数,
  "overall_score": 总分,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"],
  "needs_revision": true/false
}}"""

        try:
            response = await self.llm.generate(
                prompt,
                max_tokens=500,
                temperature=0.3,
            )

            # 解析JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return QualityScore(
                    overall_score=data.get("overall_score", 70),
                    completeness=data.get("completeness", 70),
                    accuracy=data.get("accuracy", 70),
                    relevance=data.get("relevance", 70),
                    clarity=data.get("clarity", 70),
                    usefulness=data.get("usefulness", 70),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                    needs_revision=data.get("needs_revision", False),
                )
        except Exception:
            pass

        # Fallback评分
        return QualityScore(
            overall_score=75,
            completeness=75,
            accuracy=75,
            relevance=75,
            clarity=75,
            usefulness=75,
            needs_revision=False,
        )

    async def refine_answer(
        self,
        original_question: str,
        current_answer: str,
        quality: QualityScore,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        改进答案

        Args:
            original_question: 原始问题
            current_answer: 当前答案
            quality: 质量评分
            context: 上下文

        Returns:
            str: 改进后的答案
        """
        issues_str = "\n".join([f"- {i}" for i in quality.issues])
        suggestions_str = "\n".join([f"- {s}" for s in quality.suggestions])

        prompt = f"""请改进以下答案：

原始问题：{original_question}

当前答案：{current_answer}

存在的问题：
{issues_str}

改进建议：
{suggestions_str}

请输出改进后的答案："""

        return await self.llm.generate(
            prompt,
            max_tokens=1200,
            temperature=self.temperature,
        )

    async def _report_progress(self, message: str, progress: float) -> None:
        """报告进度"""
        if self._progress_callback:
            await self._progress_callback({
                "agent": self.name,
                "message": message,
                "progress": progress,
                "timestamp": time.time(),
            })

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["total_tasks"]
        return {
            **self._stats,
            "success_rate": self._stats["successful_tasks"] / max(total, 1),
            "avg_latency_ms": self._stats["total_latency_ms"] / max(total, 1),
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_steps": 0,
            "refinements": 0,
            "total_latency_ms": 0,
        }
