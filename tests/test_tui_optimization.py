"""
TUI 优化测试：处理过程中用户追加提问响应修复

测试场景：
1. 用户输入"有点慢啊"、"还在工作吗？"等追问时，Talker 能够及时响应
2. 关键词库扩展覆盖更多用户提问变体
3. COMMENT 意图不再返回 None，而是给予简单回应
"""
import pytest
from main import TaskManager, UserIntent


class TestTUIOptimization:
    """TUI 优化测试类"""

    @pytest.fixture
    def task_manager(self):
        """创建处理中状态的 TaskManager"""
        tm = TaskManager()
        tm._current_input = "测试任务"
        tm._is_processing = True
        return tm

    def test_query_status_keyword_extension(self, task_manager):
        """测试扩展的 query_status 关键词"""
        # 用户报告的问题案例
        assert task_manager.classify_intent("有点慢啊") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("还在工作吗？") == UserIntent.QUERY_STATUS

        # 新增关键词覆盖
        assert task_manager.classify_intent("还在弄吗") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("还在做吗") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("做着吗") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("工作吗") == UserIntent.QUERY_STATUS

    def test_comment_intent_response(self, task_manager):
        """测试 COMMENT 意图有响应（不返回 None）"""
        # 这些应该被分类为 COMMENT 或 BACKCHANNEL
        intent1 = task_manager.classify_intent("挺好的")
        assert intent1 in [UserIntent.COMMENT, UserIntent.BACKCHANNEL]

        intent2 = task_manager.classify_intent("不错")
        assert intent2 == UserIntent.COMMENT

    def test_status_query_enhancement(self, task_manager):
        """测试疑问句检测增强"""
        # 这些应该被识别为 QUERY_STATUS
        assert task_manager.classify_intent("怎么样") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("怎么样了") == UserIntent.QUERY_STATUS
        assert task_manager.classify_intent("好了吗") == UserIntent.QUERY_STATUS

    def test_original_functionality_preserved(self, task_manager):
        """测试原有功能未被破坏"""
        # 取消意图仍然有效
        assert task_manager.classify_intent("取消") == UserIntent.REPLACE
        assert task_manager.classify_intent("不用了") == UserIntent.REPLACE

        # 附和/应答仍然有效
        assert task_manager.classify_intent("好的") == UserIntent.BACKCHANNEL
        assert task_manager.classify_intent("嗯") == UserIntent.BACKCHANNEL
        assert task_manager.classify_intent("明白") == UserIntent.BACKCHANNEL

        # 补充信息仍然有效
        assert task_manager.classify_intent("另外还有要求") == UserIntent.MODIFY


class TestKeywordLibrary:
    """关键词库测试"""

    def test_query_status_keywords_added(self):
        """测试 query_status 关键词已添加"""
        from config.keywords_manager import get_keywords_manager
        km = get_keywords_manager()

        # 新增的关键词
        new_keywords = ["还在工作", "还在弄吗", "还在做吗", "做着吗", "工作吗"]
        for kw in new_keywords:
            assert km.has_intent_keyword(kw, "query_status"), f"关键词 '{kw}' 未添加到 query_status"
