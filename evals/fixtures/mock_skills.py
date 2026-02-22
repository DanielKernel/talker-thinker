"""
Mock 技能模块

提供用于评测的 Mock 技能实现
"""
from typing import Any, Dict, List, Optional
from skills.base import Skill, SkillMetadata, SkillResult


class MockWeatherSkill(Skill):
    """Mock 天气技能"""

    @property
    def name(self) -> str:
        return "MockWeather"

    @property
    def description(self) -> str:
        return "Mock 天气查询技能，用于测试"

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """执行天气查询"""
        self._start_timer()

        city = params.get("city", "北京")

        # Mock 响应
        weather_data = {
            "北京": {"weather": "晴", "temp_low": 15, "temp_high": 25},
            "上海": {"weather": "多云", "temp_low": 18, "temp_high": 28},
            "广州": {"weather": "小雨", "temp_low": 22, "temp_high": 30},
            "深圳": {"weather": "晴", "temp_low": 24, "temp_high": 32},
        }

        data = weather_data.get(city, {"weather": "晴", "temp_low": 20, "temp_high": 28})

        return self._create_success_result(
            data=data,
            formatted=f"{city}{data['weather']}，气温{data['temp_low']}-{data['temp_high']}度",
        )


class MockSearchSkill(Skill):
    """Mock 搜索技能"""

    @property
    def name(self) -> str:
        return "MockSearch"

    @property
    def description(self) -> str:
        return "Mock 搜索技能，用于测试"

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """执行搜索"""
        self._start_timer()

        query = params.get("query", "")

        # Mock 搜索结果
        results = [
            {"title": f"关于{query}的搜索结果 1", "url": "https://example.com/1"},
            {"title": f"关于{query}的搜索结果 2", "url": "https://example.com/2"},
            {"title": f"关于{query}的搜索结果 3", "url": "https://example.com/3"},
        ]

        return self._create_success_result(
            data=results,
            formatted=f"找到 {len(results)} 条关于'{query}'的搜索结果",
        )


class MockCalculatorSkill(Skill):
    """Mock 计算器技能"""

    @property
    def name(self) -> str:
        return "MockCalculator"

    @property
    def description(self) -> str:
        return "Mock 计算器技能，用于测试"

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """执行计算"""
        self._start_timer()

        expression = params.get("expression", "")

        try:
            # 简单的安全计算
            result = eval(expression, {"__builtins__": {}}, {})
            return self._create_success_result(
                data=result,
                formatted=f"{expression} = {result}",
            )
        except Exception as e:
            return self._create_error_result(f"计算错误：{str(e)}")


class MockUnitConverterSkill(Skill):
    """Mock 单位转换技能"""

    @property
    def name(self) -> str:
        return "MockUnitConverter"

    @property
    def description(self) -> str:
        return "Mock 单位转换技能，用于测试"

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """执行单位转换"""
        self._start_timer()

        from_unit = params.get("from_unit", "")
        to_unit = params.get("to_unit", "")
        value = params.get("value", 0)

        # Mock 转换
        conversions = {
            ("公里", "英里"): lambda x: x * 0.621371,
            ("英里", "公里"): lambda x: x * 1.60934,
            ("千克", "磅"): lambda x: x * 2.20462,
            ("磅", "千克"): lambda x: x * 0.453592,
        }

        converter = conversions.get((from_unit, to_unit))
        if converter:
            result = converter(value)
            return self._create_success_result(
                data=result,
                formatted=f"{value} {from_unit} = {result:.2f} {to_unit}",
            )

        return self._create_error_result(f"不支持的单位转换：{from_unit} -> {to_unit}")


class MockKnowledgeSearchSkill(Skill):
    """Mock 知识检索技能"""

    @property
    def name(self) -> str:
        return "MockKnowledgeSearch"

    @property
    def description(self) -> str:
        return "Mock 知识检索技能，用于测试"

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """执行知识检索"""
        self._start_timer()

        query = params.get("query", "")

        # Mock 知识检索结果
        results = [
            {"title": f"知识条目 1: {query}", "content": f"这是关于{query}的详细说明..."},
            {"title": f"知识条目 2: {query}", "content": f"更多关于{query}的信息..."},
        ]

        return self._create_success_result(
            data=results,
            formatted=f"找到 {len(results)} 条相关知识",
        )


class MockSkillsEngine:
    """
    Mock 技能引擎

    用于评测时替代真实的 SkillsEngine
    """

    def __init__(self):
        self.skills = {
            "MockWeather": MockWeatherSkill(),
            "MockSearch": MockSearchSkill(),
            "MockCalculator": MockCalculatorSkill(),
            "MockUnitConverter": MockUnitConverterSkill(),
            "MockKnowledgeSearch": MockKnowledgeSearchSkill(),
        }
        self.registered_skills: List[str] = list(self.skills.keys())

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)

    def list_skills(self) -> List[str]:
        """列出所有已注册的技能"""
        return self.registered_skills

    async def execute_skill(
        self,
        name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """
        执行技能

        Args:
            name: 技能名称
            params: 执行参数
            context: 执行上下文

        Returns:
            SkillResult: 执行结果
        """
        skill = self.get_skill(name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"技能不存在：{name}",
            )

        return await skill.execute(params, context)

    def register_skill(self, name: str, skill: Skill) -> None:
        """注册技能"""
        self.skills[name] = skill
        self.registered_skills.append(name)
