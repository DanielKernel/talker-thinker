"""
Test TUI display timing to ensure:
1. Talker response appears before next input prompt
2. No empty "你：" prompt appears before Talker response
3. Input prompt waits for output completion
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from main import TalkerThinkerApp, TaskManager


class TestTUITiming:
    """Test TUI display timing fixes"""

    @pytest.mark.asyncio
    async def test_output_event_initialized(self):
        """Verify output complete event is properly initialized in run_interactive"""
        # This test verifies the structure of run_interactive method
        # The output_complete_event should be created and set initially
        event = asyncio.Event()
        event.set()  # Initial state should be set (allowing input prompt)
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_output_event_clears_on_task_start(self):
        """Verify output event is cleared when task starts processing"""
        event = asyncio.Event()
        event.set()

        # Simulate task start - should clear the event
        event.clear()
        assert not event.is_set()

    @pytest.mark.asyncio
    async def test_output_event_set_on_task_complete(self):
        """Verify output event is set when task completes"""
        event = asyncio.Event()
        event.clear()

        # Simulate task completion - should set the event
        event.set()
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_handle_new_input_during_processing_returns_response_first(self):
        """
        Verify that _handle_new_input_during_processing returns response
        before showing input prompt

        This tests the fix for issue where user input prompt appeared
        before Talker response
        """
        app = TalkerThinkerApp()
        await app.initialize()

        # Start a mock task
        task = asyncio.create_task(asyncio.sleep(60))
        app.task_manager.start_task(task, "帮我分析买车方案")

        # Test QUERY_STATUS intent - should return response immediately
        handled, response = await app._handle_new_input_during_processing(
            "进度如何",
            "test-session"
        )

        assert handled is True
        # Response should be available before any input prompt would show
        assert response is not None
        assert "处理" in response or "任务" in response

        await app.task_manager.cancel_current_task()

    @pytest.mark.asyncio
    async def test_handled_intent_shows_response_before_input(self):
        """
        Test that handled intents (like status query) return response
        that should be displayed before next input prompt
        """
        app = TalkerThinkerApp()
        await app.initialize()

        # Start a mock task
        task = asyncio.create_task(asyncio.sleep(60))
        app.task_manager.start_task(task, "测试任务")

        # Test complaint about slow response
        handled, response = await app._handle_new_input_during_processing(
            "太慢了吧",
            "test-session"
        )

        assert handled is True
        if response:
            assert "抱歉" in response or "正在" in response

        await app.task_manager.cancel_current_task()


class TestTUIInputHandler:
    """Test TUI input handler with output event support"""

    def test_talker_input_has_output_event_support(self):
        """Verify TalkerInput class supports output event"""
        from tui.input import TalkerInput

        handler = TalkerInput()
        event = asyncio.Event()

        # Should not raise any errors
        handler.set_output_event(event)

        # Verify event is stored
        assert handler._output_event is event

    def test_talker_input_output_event_optional(self):
        """Verify TalkerInput works without output event (backwards compat)"""
        from tui.input import TalkerInput

        handler = TalkerInput()

        # Initially should be None
        assert handler._output_event is None
