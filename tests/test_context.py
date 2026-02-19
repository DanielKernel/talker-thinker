"""
WorkingContext测试
"""
import pytest

from context.working_context import WorkingContext
from context.types import Message


class TestWorkingContext:
    """WorkingContext测试类"""

    def test_create_context(self):
        """测试创建上下文"""
        context = WorkingContext()
        assert context.turn_id is not None
        assert len(context.messages) == 0
        assert len(context.agent_states) == 0

    def test_add_message(self, working_context):
        """测试添加消息"""
        msg = working_context.add_message("user", "你好")
        assert len(working_context.messages) == 1
        assert msg.role == "user"
        assert msg.content == "你好"

    def test_set_agent_state(self, working_context):
        """测试设置Agent状态"""
        state = working_context.set_agent_state(
            "talker",
            "working",
            current_task="test_task",
            progress=0.5,
        )
        assert "talker" in working_context.agent_states
        assert state.status == "working"
        assert state.progress == 0.5

    def test_temp_vars(self, working_context):
        """测试临时变量"""
        working_context.set_temp_var("key1", "value1")
        assert working_context.get_temp_var("key1") == "value1"
        assert working_context.get_temp_var("not_exist") is None
        assert working_context.get_temp_var("not_exist", "default") == "default"

    def test_get_recent_messages(self, working_context):
        """测试获取最近消息"""
        for i in range(10):
            working_context.add_message("user", f"消息{i}")

        recent = working_context.get_recent_messages(5)
        assert len(recent) == 5
        assert recent[-1].content == "消息9"

    def test_clear(self, working_context):
        """测试清空上下文"""
        working_context.add_message("user", "test")
        working_context.set_temp_var("key", "value")
        working_context.clear()

        assert len(working_context.messages) == 0
        assert len(working_context.temp_vars) == 0

    def test_to_dict(self, working_context):
        """测试转换为字典"""
        working_context.add_message("user", "test")
        data = working_context.to_dict()

        assert "turn_id" in data
        assert "messages" in data
        assert len(data["messages"]) == 1

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "turn_id": "test-id",
            "messages": [{"role": "user", "content": "test"}],
            "agent_states": {},
            "temp_vars": {"key": "value"},
            "start_time": 0,
            "version": 1,
        }
        context = WorkingContext.from_dict(data)

        assert context.turn_id == "test-id"
        assert len(context.messages) == 1
        assert context.temp_vars["key"] == "value"

    def test_get_last_user_message(self, working_context):
        """测试获取最后用户消息"""
        working_context.add_message("assistant", "hi")
        working_context.add_message("user", "hello")
        working_context.add_message("assistant", "hello!")

        last_user = working_context.get_last_user_message()
        assert last_user.content == "hello"

    def test_elapsed_time(self, working_context):
        """测试已经过时间"""
        import time
        time.sleep(0.1)
        assert working_context.elapsed_time > 0
