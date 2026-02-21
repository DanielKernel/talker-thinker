"""
IntentAdaptor - 动态 Prompt 适配器

根据用户意图动态调整 Prompt 模板
"""

from typing import Any, Dict, Optional


class IntentAdaptor:
    """
    意图适配器

    根据用户意图、任务复杂度等因素动态调整 Prompt
    """

    def __init__(self):
        # 意图到模板的映射
        self.intent_template_map = {
            "analysis": "thinker/analysis",
            "planning": "thinker/planning",
            "execution": "thinker/execution",
            "synthesis": "thinker/synthesis",
            "clarification": "talker/clarification",
            "quick_response": "talker/quick_response",
            "medium_response": "talker/medium_response",
        }

    def get_template_for_intent(self, intent: str) -> Optional[str]:
        """
        根据意图获取模板名称

        Args:
            intent: 用户意图

        Returns:
            str: 模板名称
        """
        # 简单匹配
        intent_lower = intent.lower()

        if any(k in intent_lower for k in ["分析", "analyze", "评估", "evaluate"]):
            return self.intent_template_map.get("analysis")
        elif any(k in intent_lower for k in ["规划", "plan", "计划", "方案"]):
            return self.intent_template_map.get("planning")
        elif any(k in intent_lower for k in ["执行", "execute", "做", "完成"]):
            return self.intent_template_map.get("execution")
        elif any(k in intent_lower for k in ["总结", "synthesize", "整合", "答案"]):
            return self.intent_template_map.get("synthesis")
        elif any(k in intent_lower for k in ["澄清", "clarify", "确认", "询问"]):
            return self.intent_template_map.get("clarification")

        # 默认返回 planning
        return self.intent_template_map.get("planning")

    def adapt_prompt(
        self,
        base_prompt: str,
        intent: str,
        complexity: str = "medium",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        根据意图和复杂度调整 Prompt

        Args:
            base_prompt: 基础 Prompt
            intent: 用户意图
            complexity: 任务复杂度 (simple/medium/complex)
            context: 上下文信息

        Returns:
            str: 调整后的 Prompt
        """
        context = context or {}

        # 根据复杂度调整温度提示
        complexity_hints = {
            "simple": "请简洁回答，不需要详细解释。",
            "medium": "请提供适度的解释和细节。",
            "complex": "请提供详细、全面的分析，包括多个角度和深度推理。",
        }

        hint = complexity_hints.get(complexity, complexity_hints["medium"])

        # 添加复杂度提示
        adapted_prompt = base_prompt + f"\n\n复杂度要求：{hint}"

        # 根据意图添加特殊指令
        if "analysis" in intent.lower() or "分析" in intent:
            adapted_prompt += "\n\n分析要求：\n1. 识别关键要素\n2. 分析相互关系\n3. 给出有洞察力的结论"

        elif "planning" in intent.lower() or "规划" in intent:
            adapted_prompt += "\n\n规划要求：\n1. 分解为可执行的步骤\n2. 考虑潜在风险\n3. 估算时间和资源"

        elif "clarification" in intent.lower() or "澄清" in intent:
            adapted_prompt += "\n\n澄清要求：\n1. 语气友好自然\n2. 一次只问一个关键问题\n3. 提供示例帮助用户理解"

        return adapted_prompt
