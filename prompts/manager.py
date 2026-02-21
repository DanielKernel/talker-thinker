"""
PromptMgr - Prompt 管理器

核心功能：
1. 模板加载（YAML 格式）
2. 变量注入
3. 注入器链（上下文、记忆、RAG）
4. 动态 Prompt 调整
"""

import os
import re
from typing import Any, Callable, Dict, List, Optional

import yaml


class PromptMgr:
    """
    Prompt 管理器

    使用示例：
        mgr = PromptMgr(template_dir="prompts/templates")
        mgr.register_injector(context_injector)
        prompt = mgr.build_prompt("thinker/planning", context)
    """

    def __init__(self, template_dir: str = "prompts/templates"):
        """
        初始化 PromptMgr

        Args:
            template_dir: 模板目录路径
        """
        self.template_dir = template_dir
        self.templates: Dict[str, str] = {}
        self.injectors: List[Callable] = []

        # 加载模板
        self._load_templates(template_dir)

    def _load_templates(self, template_dir: str) -> None:
        """
        加载所有 YAML 模板

        Args:
            template_dir: 模板目录
        """
        if not os.path.exists(template_dir):
            return

        for root, _, files in os.walk(template_dir):
            for file in files:
                if file.endswith(".yaml") or file.endswith(".yml"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, template_dir)
                    # 生成模板名称（去掉扩展名）
                    template_name = os.path.splitext(rel_path)[0].replace(os.sep, "/")

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = yaml.safe_load(f)
                            # 支持多种格式：
                            # 1. 直接字符串
                            # 2. 字典格式（system/user 等）
                            if isinstance(content, dict):
                                # 合并所有部分
                                parts = []
                                for key in ["system", "user", "context", "instruction", ""]:
                                    if key in content:
                                        parts.append(str(content[key]))
                                self.templates[template_name] = "\n\n".join(parts)
                            else:
                                self.templates[template_name] = str(content)
                    except Exception as e:
                        print(f"加载模板失败 {file_path}: {e}")

    def get_prompt(self, name: str, **kwargs) -> str:
        """
        获取 Prompt 模板并注入变量

        Args:
            name: 模板名称（如 "thinker/planning"）
            **kwargs: 模板变量

        Returns:
            str: 渲染后的 Prompt
        """
        template = self.templates.get(name)
        if not template:
            raise ValueError(f"Prompt template '{name}' not found. Available: {list(self.templates.keys())}")

        # 使用 {{variable}} 语法进行变量替换
        result = template
        for key, value in kwargs.items():
            placeholder = "{{" + key + "}}"
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)
            result = result.replace(placeholder, str(value))

        return result

    def register_injector(self, injector: Callable) -> None:
        """
        注册注入器

        Args:
            injector: 注入器函数，签名 (prompt: str, context: Dict) -> str
        """
        self.injectors.append(injector)

    def build_prompt(self, name: str, context: Dict[str, Any]) -> str:
        """
        构建完整 Prompt（包含所有注入）

        Args:
            name: 模板名称
            context: 上下文信息

        Returns:
            str: 完整的 Prompt
        """
        # 1. 获取基础模板
        base_prompt = self.get_prompt(name, **context)

        # 2. 应用注入器链
        for injector in self.injectors:
            base_prompt = injector(base_prompt, context)

        return base_prompt

    def reload(self) -> None:
        """重新加载所有模板（用于开发调试）"""
        self.templates.clear()
        self._load_templates(self.template_dir)

    def list_templates(self) -> List[str]:
        """列出所有可用模板"""
        return list(self.templates.keys())

    def add_template(self, name: str, content: str) -> None:
        """
        动态添加模板

        Args:
            name: 模板名称
            content: 模板内容
        """
        self.templates[name] = content


# ============ 内置注入器 ============

def context_injector(prompt: str, context: Dict[str, Any]) -> str:
    """
    上下文注入器

    将用户原始输入、历史对话摘要等注入到 Prompt 中
    """
    injections = []

    # 用户原始输入
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
        pref_items = []
        if "taste" in user_preferences:
            pref_items.append(f"口味偏好：{user_preferences['taste']}")
        if "budget" in user_preferences:
            pref_items.append(f"预算：{user_preferences['budget']}")
        if "car_type" in user_preferences:
            pref_items.append(f"车型偏好：{user_preferences['car_type']}")
        if "likes" in user_preferences:
            pref_items.append(f"喜好：{', '.join(user_preferences['likes'])}")
        if "dislikes" in user_preferences:
            pref_items.append(f"不喜好：{', '.join(user_preferences['dislikes'])}")
        if pref_items:
            injections.append("已知用户偏好：" + "；".join(pref_items))

    if injections:
        context_block = "\n" + "\n".join(injections) + "\n"
        # 在 prompt 中找到合适位置注入（在"用户"相关关键词后）
        pattern = r"(用户请求：[^\n]+\n)"
        match = re.search(pattern, prompt)
        if match:
            insert_pos = match.end()
            prompt = prompt[:insert_pos] + context_block + prompt[insert_pos:]
        else:
            prompt = context_block + prompt

    return prompt


def memory_injector(prompt: str, context: Dict[str, Any]) -> str:
    """
    记忆注入器

    将长期记忆、用户画像等信息注入到 Prompt 中
    """
    # 用户画像
    user_profile = context.get("user_profile")
    if user_profile:
        profile_info = f"\n用户画像：{user_profile}\n"
        prompt = profile_info + prompt

    return prompt


def rag_injector(prompt: str, context: Dict[str, Any]) -> None:
    """
    RAG 注入器

    将检索到的相关知识注入到 Prompt 中
    """
    # 检索结果
    retrieved_docs = context.get("retrieved_documents", [])
    if retrieved_docs:
        docs_text = "\n\n相关知识：\n" + "\n".join([
            f"- {doc.get('content', '')[:200]}"
            for doc in retrieved_docs[:5]  # 最多 5 条
        ])
        prompt = prompt + docs_text

    return prompt
