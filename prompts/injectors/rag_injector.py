"""
RAG 注入器

将检索到的相关知识注入到 Prompt 中
"""

from typing import Any, Dict, List


class RAGInjector:
    """RAG 注入器"""

    def __init__(self, max_docs: int = 5, max_doc_length: int = 200):
        """
        初始化 RAG 注入器

        Args:
            max_docs: 最大文档数
            max_doc_length: 每个文档最大长度
        """
        self.max_docs = max_docs
        self.max_doc_length = max_doc_length

    def __call__(self, prompt: str, context: Dict[str, Any]) -> str:
        """
        将检索到的知识注入到 Prompt 中

        Args:
            prompt: 基础 Prompt
            context: 上下文信息（包含 retrieved_documents）

        Returns:
            str: 注入后的 Prompt
        """
        retrieved_docs = context.get("retrieved_documents", [])

        if not retrieved_docs:
            return prompt

        # 限制文档数量和长度
        docs = retrieved_docs[: self.max_docs]
        doc_lines = []

        for i, doc in enumerate(docs, 1):
            content = doc.get("content", "") if isinstance(doc, dict) else str(doc)
            if len(content) > self.max_doc_length:
                content = content[: self.max_doc_length] + "..."
            doc_lines.append(f"{i}. {content}")

        if doc_lines:
            rag_block = "\n\n--- 相关知识 ---\n" + "\n".join(doc_lines) + "\n---\n"
            prompt = prompt + rag_block

        return prompt
