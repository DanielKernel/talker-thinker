"""
Skills测试
"""
import pytest

from skills.base import Skill, SkillResult
from skills.engine import SkillsEngine, SkillNotFoundError
from skills.invoker import SkillInvoker, SkillCache
from skills.examples.weather import WeatherSkill
from skills.examples.calculation import CalculatorSkill


class MockSkill(Skill):
    """模拟Skill用于测试"""

    @property
    def name(self) -> str:
        return "mock_skill"

    @property
    def description(self) -> str:
        return "A mock skill for testing"

    async def execute(self, params, context=None) -> SkillResult:
        self._start_timer()
        return self._create_success_result(
            data={"input": params},
            formatted=f"Processed: {params}",
        )


class TestSkillsEngine:
    """SkillsEngine测试类"""

    def test_register_skill(self, skills_engine):
        """测试注册Skill"""
        skill = MockSkill()
        skills_engine.register_skill(skill)

        assert "mock_skill" in skills_engine.list_skill_names()

    def test_unregister_skill(self, skills_engine):
        """测试注销Skill"""
        skill = MockSkill()
        skills_engine.register_skill(skill)
        result = skills_engine.unregister_skill("mock_skill")

        assert result is True
        assert "mock_skill" not in skills_engine.list_skill_names()

    def test_get_skill(self, skills_engine):
        """测试获取Skill"""
        skill = MockSkill()
        skills_engine.register_skill(skill)

        retrieved = skills_engine.get_skill("mock_skill")
        assert retrieved is skill

    def test_get_nonexistent_skill(self, skills_engine):
        """测试获取不存在的Skill"""
        assert skills_engine.get_skill("nonexistent") is None

    def test_search_skills(self, skills_engine):
        """测试搜索Skills"""
        skill = MockSkill()
        skills_engine.register_skill(skill)

        results = skills_engine.search_skills("mock")
        assert len(results) == 1
        assert results[0].name == "mock_skill"

    def test_get_stats(self, skills_engine):
        """测试获取统计"""
        skill = MockSkill()
        skills_engine.register_skill(skill)

        stats = skills_engine.get_stats()
        assert stats["total_skills"] == 1


class TestSkillInvoker:
    """SkillInvoker测试类"""

    @pytest.mark.asyncio
    async def test_invoke_skill(self):
        """测试调用Skill"""
        engine = SkillsEngine()
        skill = MockSkill()
        engine.register_skill(skill)

        invoker = SkillInvoker(skills_engine=engine)
        result = await invoker.invoke("mock_skill", {"test": "value"})

        assert result.success is True
        assert "Processed" in result.formatted

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_skill(self):
        """测试调用不存在的Skill"""
        engine = SkillsEngine()
        invoker = SkillInvoker(skills_engine=engine)

        with pytest.raises(SkillNotFoundError):
            await invoker.invoke("nonexistent", {})

    @pytest.mark.asyncio
    async def test_skill_caching(self):
        """测试Skill缓存"""
        engine = SkillsEngine()
        skill = MockSkill()
        engine.register_skill(skill)

        cache = SkillCache()
        invoker = SkillInvoker(skills_engine=engine, cache=cache)

        # 第一次调用
        result1 = await invoker.invoke("mock_skill", {"key": "value"})
        # 第二次调用（应该命中缓存）
        result2 = await invoker.invoke("mock_skill", {"key": "value"})

        assert result1.success is True
        assert result2.success is True


class TestWeatherSkill:
    """天气Skill测试"""

    @pytest.mark.asyncio
    async def test_get_weather(self):
        """测试获取天气"""
        skill = WeatherSkill()
        result = await skill.execute({"location": "北京", "date": "今天"})

        assert result.success is True
        assert "北京" in result.formatted


class TestCalculatorSkill:
    """计算器Skill测试"""

    @pytest.mark.asyncio
    async def test_addition(self):
        """测试加法"""
        skill = CalculatorSkill()
        result = await skill.execute({"expression": "2 + 3"})

        assert result.success is True
        assert "5" in result.formatted

    @pytest.mark.asyncio
    async def test_complex_expression(self):
        """测试复杂表达式"""
        skill = CalculatorSkill()
        result = await skill.execute({"expression": "2 + 3 * 4"})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        """测试无效表达式"""
        skill = CalculatorSkill()
        result = await skill.execute({"expression": "invalid"})

        assert result.success is False
