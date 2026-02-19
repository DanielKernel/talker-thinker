"""
测试配置
"""
import asyncio
from typing import Generator

import pytest

from context.working_context import WorkingContext
from context.session_context import SessionContext
from skills.base import Skill, SkillResult
from skills.engine import SkillsEngine
from agents.llm_client import MockLLMClient
from agents.talker.agent import TalkerAgent
from agents.thinker.agent import ThinkerAgent
from orchestrator.coordinator import Orchestrator


@pytest.fixture
def event_loop():
    """事件循环fixture"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def working_context() -> WorkingContext:
    """工作上下文fixture"""
    return WorkingContext()


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """模拟LLM客户端fixture"""
    return MockLLMClient(response_delay=0.01)


@pytest.fixture
def talker_agent(mock_llm_client) -> TalkerAgent:
    """Talker Agent fixture"""
    return TalkerAgent(llm_client=mock_llm_client)


@pytest.fixture
def thinker_agent(mock_llm_client) -> ThinkerAgent:
    """Thinker Agent fixture"""
    return ThinkerAgent(llm_client=mock_llm_client)


@pytest.fixture
def orchestrator(talker_agent, thinker_agent) -> Orchestrator:
    """Orchestrator fixture"""
    return Orchestrator(talker=talker_agent, thinker=thinker_agent)


@pytest.fixture
def skills_engine() -> SkillsEngine:
    """Skills引擎fixture"""
    return SkillsEngine()
