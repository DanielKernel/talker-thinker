"""
Skills示例模块
"""
from skills.examples.calculation import CalculatorSkill, UnitConverterSkill
from skills.examples.search import KnowledgeSearchSkill, SearchSkill
from skills.examples.weather import WeatherSkill

__all__ = [
    "WeatherSkill",
    "SearchSkill",
    "KnowledgeSearchSkill",
    "CalculatorSkill",
    "UnitConverterSkill",
]
