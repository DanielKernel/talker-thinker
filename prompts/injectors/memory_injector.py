"""
记忆注入器

将长期记忆、用户画像等信息注入到 Prompt 中
"""

from typing import Any, Dict


class MemoryInjector:
    """记忆注入器"""

    def __init__(self):
        pass

    def __call__(self, prompt: str, context: Dict[str, Any]) -> str:
        """
        将记忆信息注入到 Prompt 中

        Args:
            prompt: 基础 Prompt
            context: 上下文信息

        Returns:
            str: 注入后的 Prompt
        """
        injections = []

        # 用户画像
        user_profile = context.get("user_profile")
        if user_profile:
            injections.append(f"用户画像：{user_profile}")

        # 长期记忆
        long_term_memory = context.get("long_term_memory")
        if long_term_memory:
            injections.append(f"长期记忆：{long_term_memory}")

        # 历史交互模式
        interaction_history = context.get("interaction_history")
        if interaction_history:
            injections.append(f"交互历史：{interaction_history}")

        if injections:
            memory_block = "\n\n--- 记忆信息 ---\n" + "\n".join(injections) + "\n---\n"
            # 添加到上下文信息之后
            prompt = prompt + memory_block

        return prompt
