"""
上下文注入器

将用户原始输入、历史对话摘要、用户偏好等信息注入到 Prompt 中
"""

import json
from typing import Any, Dict


class ContextInjector:
    """上下文注入器"""

    def __init__(self):
        pass

    def __call__(self, prompt: str, context: Dict[str, Any]) -> str:
        """
        将上下文信息注入到 Prompt 中

        Args:
            prompt: 基础 Prompt
            context: 上下文信息

        Returns:
            str: 注入后的 Prompt
        """
        injections = []

        # 用户原始输入（可能经过澄清更新）
        effective_input = context.get("effective_input")
        if effective_input:
            injections.append(f"用户原始需求：{effective_input}")

        # 历史对话摘要
        session_summary = context.get("session_summary")
        if session_summary:
            injections.append(f"历史对话摘要：{session_summary}")

        # 用户偏好
        user_preferences = context.get("user_preferences", {})
        if user_preferences:
            pref_lines = self._format_preferences(user_preferences)
            if pref_lines:
                injections.append("已知用户偏好：\n" + "\n".join(pref_lines))

        if injections:
            context_block = "\n\n--- 上下文信息 ---\n" + "\n".join(injections) + "\n---\n"
            # 在 prompt 中找到合适位置注入
            prompt = self._inject_context(prompt, context_block)

        return prompt

    def _format_preferences(self, prefs: Dict[str, Any]) -> list:
        """格式化用户偏好"""
        lines = []

        if "taste" in prefs:
            lines.append(f"- 口味偏好：{prefs['taste']}")
        if "budget" in prefs:
            lines.append(f"- 预算：{prefs['budget']}")
        if "car_type" in prefs:
            lines.append(f"- 车型偏好：{prefs['car_type']}")
        if "likes" in prefs and isinstance(prefs["likes"], list):
            lines.append(f"- 喜好：{', '.join(prefs['likes'])}")
        if "dislikes" in prefs and isinstance(prefs["dislikes"], list):
            lines.append(f"- 不喜好：{', '.join(prefs['dislikes'])}")
        if "constraints" in prefs and isinstance(prefs["constraints"], list):
            lines.append(f"- 约束：{', '.join(prefs['constraints'])}")

        return lines

    def _inject_context(self, prompt: str, context_block: str) -> str:
        """将上下文注入到 Prompt 中的合适位置"""
        # 尝试在"用户"相关关键词后注入
        import re

        patterns = [
            r"(用户请求：[^\n]+\n)",
            r"(用户问题：[^\n]+\n)",
            r"(用户：[^\n]+\n)",
            r"(用户输入：[^\n]+\n)",
        ]

        for pattern in patterns:
            match = re.search(pattern, prompt)
            if match:
                insert_pos = match.end()
                return prompt[:insert_pos] + context_block + prompt[insert_pos:]

        # 如果没有找到合适位置，添加到开头
        return context_block + prompt
