"""
Skill Invoker - Skill调用器
负责Skill的调用、缓存和重试
"""
import asyncio
import hashlib
import json
from typing import Any, Callable, Dict, Optional

from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from skills.base import Skill, SkillResult
from skills.engine import SkillNotFoundError, SkillsEngine


class SkillTimeoutError(Exception):
    """Skill超时异常"""
    def __init__(self, skill_name: str, timeout_ms: int):
        self.skill_name = skill_name
        self.timeout_ms = timeout_ms
        super().__init__(f"Skill {skill_name} timed out after {timeout_ms}ms")


class SkillExecutionError(Exception):
    """Skill执行异常"""
    def __init__(self, skill_name: str, original_error: Exception):
        self.skill_name = skill_name
        self.original_error = original_error
        super().__init__(f"Skill {skill_name} execution failed: {original_error}")


class SkillCache:
    """Skill结果缓存"""

    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def _generate_key(self, skill_name: str, params: Dict[str, Any]) -> str:
        """生成缓存键"""
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()
        return f"{skill_name}:{params_hash}"

    async def get(self, skill_name: str, params: Dict[str, Any]) -> Optional[SkillResult]:
        """获取缓存结果"""
        key = self._generate_key(skill_name, params)
        return self.cache.get(key)

    async def set(
        self,
        skill_name: str,
        params: Dict[str, Any],
        result: SkillResult,
    ) -> None:
        """设置缓存结果"""
        key = self._generate_key(skill_name, params)
        self.cache[key] = result

    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()


class SkillInvoker:
    """
    Skill调用器
    负责Skill的调用、缓存和重试
    """

    def __init__(
        self,
        skills_engine: Optional[SkillsEngine] = None,
        cache: Optional[SkillCache] = None,
    ):
        self.engine = skills_engine or SkillsEngine()
        self.cache = cache or SkillCache(
            maxsize=1000,
            ttl=settings.CACHE_TTL_SECONDS,
        )
        self._hooks: Dict[str, List[Callable]] = {
            "before_invoke": [],
            "after_invoke": [],
            "on_error": [],
        }

    def add_hook(self, hook_type: str, callback: Callable) -> None:
        """
        添加钩子函数

        Args:
            hook_type: 钩子类型 (before_invoke, after_invoke, on_error)
            callback: 回调函数
        """
        if hook_type in self._hooks:
            self._hooks[hook_type].append(callback)

    async def _run_hooks(self, hook_type: str, *args, **kwargs) -> None:
        """运行钩子函数"""
        for callback in self._hooks.get(hook_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception:
                pass  # 忽略钩子错误

    async def invoke(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> SkillResult:
        """
        调用Skill

        Args:
            skill_name: Skill名称
            params: 调用参数
            context: 执行上下文
            use_cache: 是否使用缓存

        Returns:
            SkillResult: 执行结果

        Raises:
            SkillNotFoundError: Skill不存在
            SkillTimeoutError: Skill超时
            SkillExecutionError: Skill执行失败
        """
        # 1. 获取Skill
        skill = self.engine.get_skill(skill_name)
        if not skill:
            raise SkillNotFoundError(skill_name)

        # 2. 验证参数
        await skill.validate_params(params)

        # 3. 检查缓存
        if use_cache and settings.CACHE_ENABLED:
            cached_result = await self.cache.get(skill_name, params)
            if cached_result:
                return cached_result

        # 4. 运行前置钩子
        await self._run_hooks(
            "before_invoke",
            skill_name=skill_name,
            params=params,
            context=context,
        )

        # 5. 执行Skill（带重试）
        try:
            result = await self._execute_with_retry(
                skill, params, context or {}
            )

            # 6. 缓存结果
            if use_cache and settings.CACHE_ENABLED and result.success:
                await self.cache.set(skill_name, params, result)

            # 7. 运行后置钩子
            await self._run_hooks(
                "after_invoke",
                skill_name=skill_name,
                result=result,
            )

            return result

        except Exception as e:
            # 运行错误钩子
            await self._run_hooks(
                "on_error",
                skill_name=skill_name,
                error=e,
                params=params,
            )
            raise

    async def _execute_with_retry(
        self,
        skill: Skill,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillResult:
        """
        带重试的执行

        Args:
            skill: Skill实例
            params: 参数
            context: 上下文

        Returns:
            SkillResult: 执行结果
        """
        max_retries = skill.metadata.max_retries
        timeout_seconds = skill.metadata.timeout_ms / 1000

        for attempt in range(max_retries):
            try:
                # 设置超时
                result = await asyncio.wait_for(
                    skill.execute(params, context),
                    timeout=timeout_seconds,
                )
                return result

            except asyncio.TimeoutError:
                if attempt == max_retries - 1:
                    raise SkillTimeoutError(skill.name, skill.metadata.timeout_ms)
                await asyncio.sleep(2 ** attempt)  # 指数退避

            except Exception as e:
                if attempt == max_retries - 1:
                    raise SkillExecutionError(skill.name, e)
                await asyncio.sleep(2 ** attempt)

        # 不应该到达这里
        raise SkillExecutionError(skill.name, Exception("Unknown error"))

    async def invoke_batch(
        self,
        calls: list[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 5,
    ) -> list[SkillResult]:
        """
        批量调用Skills

        Args:
            calls: 调用列表 [{"skill": "name", "params": {...}}, ...]
            context: 共享上下文
            max_concurrent: 最大并发数

        Returns:
            List[SkillResult]: 结果列表
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def invoke_with_semaphore(call: Dict[str, Any]) -> SkillResult:
            async with semaphore:
                return await self.invoke(
                    call["skill"],
                    call.get("params", {}),
                    context,
                )

        tasks = [invoke_with_semaphore(call) for call in calls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def clear_cache(self) -> None:
        """清空缓存"""
        self.cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "cache_size": len(self.cache.cache),
            "cache_maxsize": self.cache.cache.maxsize,
        }
