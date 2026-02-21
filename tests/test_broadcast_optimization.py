"""
TUI 问题修复测试：进度播报动态化与用户输入响应

测试场景：
1. 进度播报根据用户问题话题动态生成
2. 用户疑问句能得到适当回应
3. _generate_stage_broadcast 注入中间结果
"""
import pytest
from orchestrator.coordinator import Orchestrator, ThinkerStage
from context.shared_context import SharedContext


class TestBroadcastOptimization:
    """进度播报优化测试"""

    @pytest.fixture
    def orchestrator(self):
        """创建 Orchestrator 实例"""
        return Orchestrator()

    def test_topic_extraction_for_broadcast(self, orchestrator):
        """测试话题提取用于播报"""
        # 奶茶话题
        topic = orchestrator._extract_topic("帮我对比一下不同品牌的奶茶")
        assert topic == "奶茶"

        # 咖啡话题
        topic = orchestrator._extract_topic("想喝一杯咖啡，有什么推荐")
        assert topic == "咖啡"

        # 打车话题（注意：话题库中"打车"在"选车"之前）
        topic = orchestrator._extract_topic("帮我叫个车")
        assert topic in ["打车", "选车"]

        # 选车话题 - "SUV 车"会匹配到"选车"话题
        topic = orchestrator._extract_topic("我想买一辆 SUV 车，有什么推荐")
        assert topic in ["车", "选车"]

    def test_stage_broadcast_includes_topic(self, orchestrator):
        """测试播报包含话题关键词"""
        user_query = "帮我对比一下不同品牌的奶茶"

        # 测试 IDLE 阶段
        msg, template = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.IDLE,
            user_query=user_query,
            elapsed_time=5.0,
            partial_results=[]
        )
        assert "奶茶" in msg

        # 测试 ANALYZING 阶段
        msg, template = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.ANALYZING,
            user_query=user_query,
            elapsed_time=5.0,
            partial_results=[]
        )
        assert "奶茶" in msg

        # 测试 PLANNING 阶段
        msg, template = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.PLANNING,
            user_query=user_query,
            elapsed_time=5.0,
            partial_results=[]
        )
        assert "奶茶" in msg

    def test_stage_broadcast_injects_partial_result(self, orchestrator):
        """测试播报注入中间结果"""
        user_query = "帮我对比手机"
        partial_results = ["已获取 iPhone 15 参数"]

        # 测试 IDLE 阶段注入中间结果
        msg, template = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.IDLE,
            user_query=user_query,
            elapsed_time=5.0,
            partial_results=partial_results
        )
        # 中间结果应该被注入到播报中
        assert "iPhone" in msg or "已获取" in msg

    def test_different_queries_have_different_broadcasts(self, orchestrator):
        """测试不同问题有不同播报"""
        query1 = "帮我对比奶茶"
        query2 = "帮我选车"

        msg1, _ = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.ANALYZING,
            user_query=query1,
            elapsed_time=5.0
        )

        msg2, _ = orchestrator._generate_stage_broadcast(
            stage=ThinkerStage.ANALYZING,
            user_query=query2,
            elapsed_time=5.0
        )

        # 两个播报应该包含不同的话题
        assert "奶茶" in msg1
        assert "车" in msg2
        assert msg1 != msg2


class TestUserInputResponse:
    """用户输入响应测试"""

    @pytest.fixture
    def app_with_processing_task(self):
        """创建有处理中任务的 App"""
        from main import TalkerThinkerApp
        import asyncio

        app = TalkerThinkerApp()
        # 不初始化，因为我们只需要测试 _handle_new_input_during_processing 方法

        # 模拟处理中状态
        app.task_manager._current_input = "测试任务"
        app.task_manager._is_processing = True
        app.task_manager._task_start_time = __import__('time').time()

        return app

    @pytest.mark.asyncio
    async def test_question_with_status_words(self, app_with_processing_task):
        """测试包含疑问词和状态词的输入得到回应"""
        app = app_with_processing_task

        # 这些疑问句应该得到回应
        test_cases = [
            "还在分析吗？",
            "分析完了吗？",
            "好了没有？",
            "什么时候好？",
            "要等多久？",
        ]

        for test_input in test_cases:
            handled, response = await app._handle_new_input_during_processing(
                test_input,
                "test_session"
            )
            # 应该被处理并有回应
            assert handled is True
            assert response is not None
            # 回应不应该为空或者 __EXIT__ 标记
            assert response != "__EXIT__"

    @pytest.mark.asyncio
    async def test_fallback_for_unclassified_question(self, app_with_processing_task):
        """测试兜底机制：未被分类的疑问句得到默认回应"""
        app = app_with_processing_task

        # 这个输入包含疑问词但没有被分类为 QUERY_STATUS
        # 应该触发兜底机制
        test_input = "还在弄吗"

        handled, response = await app._handle_new_input_during_processing(
            test_input,
            "test_session"
        )

        # 应该被处理
        assert handled is True
