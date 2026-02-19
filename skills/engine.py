"""
Skills Engine - 技能引擎
负责Skill的注册、发现和管理
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional

from skills.base import Skill


class SkillNotFoundError(Exception):
    """Skill未找到异常"""
    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillsEngine:
    """
    Skills引擎
    负责Skill的注册、发现和管理
    """

    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.skill_groups: Dict[str, List[str]] = defaultdict(list)
        self._skill_aliases: Dict[str, str] = {}

    def register_skill(self, skill: Skill) -> None:
        """
        注册Skill

        Args:
            skill: 要注册的Skill实例
        """
        self.skills[skill.name] = skill
        group = skill.metadata.group
        self.skill_groups[group].append(skill.name)

        # 注册别名
        for tag in skill.metadata.tags:
            if tag not in self._skill_aliases:
                self._skill_aliases[tag] = skill.name

    def unregister_skill(self, skill_name: str) -> bool:
        """
        注销Skill

        Args:
            skill_name: Skill名称

        Returns:
            bool: 是否成功注销
        """
        if skill_name not in self.skills:
            return False

        skill = self.skills[skill_name]
        group = skill.metadata.group

        # 从组中移除
        if skill_name in self.skill_groups[group]:
            self.skill_groups[group].remove(skill_name)

        # 从别名中移除
        self._skill_aliases = {
            k: v for k, v in self._skill_aliases.items() if v != skill_name
        }

        # 从主字典中移除
        del self.skills[skill_name]
        return True

    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """
        获取Skill

        Args:
            skill_name: Skill名称或别名

        Returns:
            Optional[Skill]: Skill实例或None
        """
        # 先尝试直接查找
        if skill_name in self.skills:
            return self.skills[skill_name]

        # 尝试通过别名查找
        if skill_name in self._skill_aliases:
            return self.skills.get(self._skill_aliases[skill_name])

        return None

    def list_skills(self, group: Optional[str] = None) -> List[Skill]:
        """
        列出所有Skills

        Args:
            group: 可选的组名过滤

        Returns:
            List[Skill]: Skill列表
        """
        if group:
            skill_names = self.skill_groups.get(group, [])
            return [self.skills[name] for name in skill_names if name in self.skills]
        return list(self.skills.values())

    def list_skill_names(self, group: Optional[str] = None) -> List[str]:
        """
        列出所有Skill名称

        Args:
            group: 可选的组名过滤

        Returns:
            List[str]: Skill名称列表
        """
        if group:
            return self.skill_groups.get(group, [])
        return list(self.skills.keys())

    def search_skills(self, query: str) -> List[Skill]:
        """
        搜索Skills

        Args:
            query: 搜索查询

        Returns:
            List[Skill]: 匹配的Skill列表
        """
        query_lower = query.lower()
        results = []

        for skill in self.skills.values():
            # 在名称中搜索
            if query_lower in skill.name.lower():
                results.append(skill)
                continue

            # 在描述中搜索
            if query_lower in skill.description.lower():
                results.append(skill)
                continue

            # 在标签中搜索
            if any(query_lower in tag.lower() for tag in skill.metadata.tags):
                results.append(skill)
                continue

        return results

    def get_skill_schema(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        获取Skill的参数schema

        Args:
            skill_name: Skill名称

        Returns:
            Optional[Dict]: JSON Schema或None
        """
        skill = self.get_skill(skill_name)
        if skill:
            return skill.get_schema()
        return None

    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有Skill的schema

        Returns:
            Dict[str, Dict]: {skill_name: schema}
        """
        return {name: skill.get_schema() for name, skill in self.skills.items()}

    def get_groups(self) -> List[str]:
        """
        获取所有Skill组

        Returns:
            List[str]: 组名列表
        """
        return list(self.skill_groups.keys())

    def get_stats(self) -> Dict[str, Any]:
        """
        获取引擎统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "total_skills": len(self.skills),
            "total_groups": len(self.skill_groups),
            "groups": {
                group: len(skills)
                for group, skills in self.skill_groups.items()
            },
            "skills_by_latency_target": {
                f"<{skill.metadata.latency_target_ms}ms": sum(
                    1 for s in self.skills.values()
                    if s.metadata.latency_target_ms == skill.metadata.latency_target_ms
                )
                for skill in self.skills.values()
            },
        }

    def clear(self) -> None:
        """清空所有Skills"""
        self.skills.clear()
        self.skill_groups.clear()
        self._skill_aliases.clear()


# 全局引擎实例
_global_engine: Optional[SkillsEngine] = None


def get_global_engine() -> SkillsEngine:
    """获取全局引擎实例"""
    global _global_engine
    if _global_engine is None:
        _global_engine = SkillsEngine()
    return _global_engine


def register_skill(skill: Skill) -> None:
    """注册Skill到全局引擎"""
    get_global_engine().register_skill(skill)


def get_skill(skill_name: str) -> Optional[Skill]:
    """从全局引擎获取Skill"""
    return get_global_engine().get_skill(skill_name)
