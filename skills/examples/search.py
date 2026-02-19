"""
搜索Skill示例
"""
from typing import Any, Dict, List, Optional

from skills.base import Skill, SkillResult


class SearchSkill(Skill):
    """
    网络搜索Skill
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "在网络上搜索信息"

    def _get_param_descriptions(self) -> list:
        return [
            ("query", "string", "搜索关键词"),
            ("limit", "integer", "返回结果数量，默认5"),
        ]

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        self._start_timer()

        query = params.get("query")
        limit = params.get("limit", 5)

        try:
            # 模拟搜索结果
            results = await self._search(query, limit)

            # 格式化输出
            formatted = self._format_results(results)

            return self._create_success_result(
                data=results,
                formatted=formatted,
                metadata={"query": query, "limit": limit},
            )

        except Exception as e:
            return self._create_error_result(str(e))

    async def _search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """执行搜索（模拟）"""
        # 模拟搜索结果
        mock_results = [
            {
                "title": f"关于'{query}'的搜索结果1",
                "url": f"https://example.com/result1?q={query}",
                "snippet": f"这是关于{query}的详细描述信息...",
            },
            {
                "title": f"关于'{query}'的搜索结果2",
                "url": f"https://example.com/result2?q={query}",
                "snippet": f"了解更多关于{query}的内容...",
            },
            {
                "title": f"关于'{query}'的搜索结果3",
                "url": f"https://example.com/result3?q={query}",
                "snippet": f"{query}相关的最新动态...",
            },
        ]

        return mock_results[:limit]

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果"""
        if not results:
            return "未找到相关结果"

        lines = ["找到以下结果：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['snippet']}")
            lines.append(f"   链接: {r['url']}\n")

        return "\n".join(lines)


class KnowledgeSearchSkill(Skill):
    """
    知识库搜索Skill
    """

    @property
    def name(self) -> str:
        return "knowledge_search"

    @property
    def description(self) -> str:
        return "在知识库中搜索相关信息"

    def _get_param_descriptions(self) -> list:
        return [
            ("query", "string", "搜索问题"),
            ("top_k", "integer", "返回结果数量，默认3"),
        ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._knowledge_base = None

    def set_knowledge_base(self, knowledge_base) -> None:
        """设置知识库"""
        self._knowledge_base = knowledge_base

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        self._start_timer()

        query = params.get("query")
        top_k = params.get("top_k", 3)

        try:
            if self._knowledge_base is None:
                return self._create_error_result("知识库未初始化")

            context_str, results = await self._knowledge_base.retrieve_with_context(
                query, top_k
            )

            return self._create_success_result(
                data={"results": results, "context": context_str},
                formatted=context_str if context_str else "未找到相关知识",
                metadata={"query": query, "top_k": top_k},
            )

        except Exception as e:
            return self._create_error_result(str(e))
