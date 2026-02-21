"""
TUI 问题修复测试：上下文错误与退出功能失效

测试用例覆盖：
1. 话题提取修复（买奶茶不应该变成手环）
2. 退出功能修复（quit/exit 应该能正常退出）
3. Thinker prompt 约束增强
"""

import pytest
import json
from unittest.mock import Mock, MagicMock


class TestTopicExtractionFix:
    """测试话题提取修复"""

    @pytest.fixture
    def orchestrator(self):
        """创建 Orchestrator 实例"""
        from orchestrator.coordinator import Orchestrator
        return Orchestrator(talker=None, thinker=None)

    def test_milk_tea_topic(self, orchestrator):
        """测试'买奶茶'正确提取为奶茶话题"""
        result = orchestrator._extract_topic("买奶茶")
        assert result == "奶茶", f"期望'奶茶'，得到'{result}'"

    def test_coffee_topic(self, orchestrator):
        """测试'买咖啡'正确提取为咖啡话题"""
        result = orchestrator._extract_topic("买咖啡")
        assert result == "咖啡", f"期望'咖啡'，得到'{result}'"

    def test_buy_car_topic(self, orchestrator):
        """测试'买车'正确提取为选车话题"""
        result = orchestrator._extract_topic("买车")
        assert result == "选车", f"期望'选车'，得到'{result}'"

    def test_restaurant_topic(self, orchestrator):
        """测试'找餐厅'正确提取为美食话题"""
        result = orchestrator._extract_topic("找餐厅")
        assert result == "美食", f"期望'美食'，得到'{result}'"

    def test_taxi_topic(self, orchestrator):
        """测试'打车'正确提取为打车话题"""
        result = orchestrator._extract_topic("打车")
        assert result == "打车", f"期望'打车'，得到'{result}'"

    def test_travel_topic(self, orchestrator):
        """测试'去旅游'正确提取为旅游话题"""
        result = orchestrator._extract_topic("去旅游")
        assert result == "旅游", f"期望'旅游'，得到'{result}'"

    def test_specific_topic_priority(self, orchestrator):
        """测试具体话题优先于通用话题"""
        # "买奶茶" 应该提取为"奶茶"而不是"购物"
        result = orchestrator._extract_topic("买奶茶")
        assert result == "奶茶", f"具体话题'奶茶'应该优先，得到'{result}'"

        # "买咖啡" 应该提取为"咖啡"而不是"购物"
        result = orchestrator._extract_topic("买咖啡")
        assert result == "咖啡", f"具体话题'咖啡'应该优先，得到'{result}'"


class TestExitFunctionalityFix:
    """测试退出功能修复"""

    def test_quit_exit_in_cancel_keywords(self):
        """测试 quit/exit 在 cancel 意图关键词中"""
        with open('data/keywords/base_keywords.json', 'r', encoding='utf-8') as f:
            keywords = json.load(f)

        cancel_keywords = keywords['intents']['cancel']

        assert 'quit' in cancel_keywords['english'], "quit 应该在 cancel 英文关键词中"
        assert 'exit' in cancel_keywords['english'], "exit 应该在 cancel 英文关键词中"

    def test_chinese_exit_keywords(self):
        """测试中文退出关键词"""
        with open('data/keywords/base_keywords.json', 'r', encoding='utf-8') as f:
            keywords = json.load(f)

        cancel_keywords = keywords['intents']['cancel']

        assert '退出' in cancel_keywords['keywords'], "'退出'应该在 cancel 中文关键词中"
        assert '离开' in cancel_keywords['keywords'], "'离开'应该在 cancel 中文关键词中"


class TestThinkerPromptConstraints:
    """测试 Thinker prompt 约束增强"""

    @pytest.fixture
    def thinker_agent(self):
        """创建 ThinkerAgent 实例"""
        from agents.thinker.agent import ThinkerAgent
        return ThinkerAgent()

    def test_prompt_has_constraints_section(self, thinker_agent):
        """测试 prompt 包含重要约束部分"""
        prompt = thinker_agent._build_planning_prompt("测试请求")
        assert "【重要约束】" in prompt, "Prompt 应该包含【重要约束】部分"

    def test_prompt_has_no_divergence_constraint(self, thinker_agent):
        """测试 prompt 包含不得偏离主题的约束"""
        prompt = thinker_agent._build_planning_prompt("测试请求")
        assert "不得偏离主题" in prompt, "Prompt 应该包含'不得偏离主题'的约束"

    def test_prompt_has_focus_constraint(self, thinker_agent):
        """测试 prompt 包含聚焦约束"""
        prompt = thinker_agent._build_planning_prompt("测试请求")
        assert "聚焦于此" in prompt, "Prompt 应该包含'聚焦于此'的约束"

    def test_prompt_has_planning_requirements(self, thinker_agent):
        """测试 prompt 包含规划要求"""
        prompt = thinker_agent._build_planning_prompt("测试请求")
        assert "【规划要求】" in prompt, "Prompt 应该包含【规划要求】部分"
        assert "复述用户需求" in prompt, "Prompt 应该要求复述用户需求"

    def test_prompt_with_context(self, thinker_agent):
        """测试带上下文的 prompt"""
        context = {
            'effective_input': '买奶茶，对比评分和价格',
            'session_summary': '用户想找附近奶茶店'
        }
        prompt = thinker_agent._build_planning_prompt(
            '按照评分和价格做个分析吧',
            context
        )

        # 验证上下文被注入
        assert "用户原始需求：买奶茶，对比评分和价格" in prompt
        assert "历史对话摘要：用户想找附近奶茶店" in prompt

        # 验证约束依然存在
        assert "【重要约束】" in prompt
        assert "不得偏离主题" in prompt


class TestMainExitHandling:
    """测试主循环退出处理"""

    def test_exit_marker_in_code(self):
        """测试__EXIT__标记存在"""
        with open('main.py', 'r', encoding='utf-8') as f:
            content = f.read()

        assert "__EXIT__" in content, "main.py 应该包含__EXIT__标记"
        assert 'response == "__EXIT__"' in content, "应该检测__EXIT__标记并退出"

    def test_exit_handling_in_handle_new_input(self):
        """测试_handle_new_input_during_processing 中的退出处理"""
        with open('main.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证退出命令优先处理
        assert 'if new_input.lower() in ("quit", "exit"):' in content
        assert 'await self.task_manager.cancel_current_task()' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
