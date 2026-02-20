import asyncio

import pytest

from context.shared_context import SharedContext
from main import TalkerThinkerApp, TaskManager, UserIntent
from agents.llm_client import MockLLMClient
from agents.talker.agent import TalkerAgent
from agents.thinker.agent import ThinkerAgent
from orchestrator.coordinator import Orchestrator


class TestP0IntentHandling:
    @pytest.mark.asyncio
    async def test_cancel_intent_priority(self):
        manager = TaskManager()
        task = asyncio.create_task(asyncio.sleep(60))
        manager.start_task(task, "帮我分析买车方案")

        intent = manager.classify_intent("不买了")
        assert intent == UserIntent.REPLACE

        await manager.cancel_current_task()

    @pytest.mark.asyncio
    async def test_short_text_topic_switch(self):
        manager = TaskManager()
        task = asyncio.create_task(asyncio.sleep(60))
        manager.start_task(task, "帮我分析买车方案")

        intent = manager.classify_intent("吃饭")
        assert intent == UserIntent.REPLACE

        await manager.cancel_current_task()

    @pytest.mark.asyncio
    async def test_waiting_question_has_talker_reply(self):
        app = TalkerThinkerApp()
        task = asyncio.create_task(asyncio.sleep(60))
        app.task_manager.start_task(task, "帮我对比新能源车")

        handled, response = await app._handle_new_input_during_processing("你在干啥", "test-session")
        assert handled is True
        assert response is not None
        assert "正在处理" in response

        await app.task_manager.cancel_current_task()

    @pytest.mark.asyncio
    async def test_slow_comment_should_not_cancel(self):
        manager = TaskManager()
        task = asyncio.create_task(asyncio.sleep(60))
        manager.start_task(task, "详细对比滴滴和高德打车")

        intent = manager.classify_intent("有点慢")
        assert intent in (UserIntent.COMMENT, UserIntent.QUERY_STATUS)

        await manager.cancel_current_task()


class TestP1SharedContextFlow:
    def _create_orchestrator(self) -> Orchestrator:
        llm = MockLLMClient(response_delay=0.01)
        talker = TalkerAgent(llm_client=llm)
        thinker = ThinkerAgent(llm_client=llm)
        return Orchestrator(talker=talker, thinker=thinker)

    @pytest.mark.asyncio
    async def test_collaboration_handoff_returns_on_clarification(self):
        orchestrator = self._create_orchestrator()
        shared = SharedContext(user_input="帮我选车")
        context = {"shared": shared, "messages": []}

        async def mock_plan_task(user_input, ctx):
            return type("Plan", (), {"steps": [{"name": "分析", "description": "分析需求"}]})()

        async def mock_needs_clarification(user_input, plan, ctx):
            return True, "信息不足", ["预算"]

        async def mock_question(user_input, missing_info, ctx):
            return "您的预算范围大概是多少？"

        orchestrator.thinker.plan_task = mock_plan_task
        orchestrator.thinker.needs_clarification = mock_needs_clarification
        orchestrator.thinker.generate_clarification_question = mock_question

        chunks = []
        async for chunk in orchestrator._collaboration_handoff("帮我选车", context):
            chunks.append(chunk)

        merged = "".join(chunks)
        assert "预算范围" in merged
        assert "Thinker: 开始处理" not in merged
        assert shared.needs_clarification() is True

    @pytest.mark.asyncio
    async def test_shared_stage_mapping(self):
        orchestrator = self._create_orchestrator()
        stage = orchestrator._stage_from_shared_progress("executing")
        assert stage.value == "executing"
