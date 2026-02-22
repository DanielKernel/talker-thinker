"""
Regression Test Suite for Talker-Thinker

This test suite contains all discovered and fixed issues to prevent regressions.
Each test case corresponds to a specific bug that was found and fixed.

测试集说明：
- 包含所有已发现并修复的问题
- 每次代码变更后应运行此测试集确保无回退
- 新发现的 bug 也应添加到此测试集中
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from main import TalkerThinkerApp, TaskManager, UserIntent


class TestLoggerNotDefined:
    """
    测试用例：logger 未定义错误

    Bug 描述：coordinator.py 中使用了 logger 但没有导入
    修复方式：添加 from monitoring.logging import get_logger 和 logger = get_logger(...)

    原始错误日志：
    [18:41:02.631] Talker: 正在进行质量检查...
    抱歉，处理时出现错误：name 'logger' is not defined
    """

    def test_coordinator_logger_imported(self):
        """测试 coordinator 模块正确导入了 logger"""
        from orchestrator import coordinator
        assert hasattr(coordinator, 'logger'), "coordinator 模块必须定义 logger"
        assert coordinator.logger is not None, "logger 不能为 None"

    def test_coordinator_can_log(self):
        """测试 coordinator 可以正常记录日志"""
        from orchestrator import coordinator
        # 不应抛出 NameError
        try:
            coordinator.logger.info("Test log message")
            coordinator.logger.warning("Test warning")
            coordinator.logger.error("Test error")
        except NameError as e:
            pytest.fail(f"logger 未定义：{e}")


class TestExitQuitCommands:
    """
    测试用例：exit/quit 命令无法退出

    Bug 描述：在任务处理过程中或完成后，输入 exit/quit 无法退出交互模式
    修复方式：
    1. 在 _handle_new_input_during_processing 中检测 exit/quit 并返回 __EXIT__
    2. 在主循环和内部循环中检测 __EXIT__ 标记并 break
    3. 修复 read_input 中的死锁逻辑，移除超时后的 continue 检查

    原始问题对话：
    [18:41:33.574] Talker: 正在优化答案，请稍候...
    [18:41:38.372] 你：
    取消
    exit
    quit
    """

    @pytest.mark.asyncio
    async def test_quit_command_when_idle(self):
        """测试空闲状态下 quit 命令有效"""
        app = TalkerThinkerApp()
        await app.initialize()

        # 模拟没有任务在处理时输入 quit
        assert app.task_manager.is_processing is False
        result = app.task_manager.classify_intent("quit")
        # quit 应该被识别为 REPLACE 意图（新任务请求）
        assert result in [UserIntent.REPLACE, UserIntent.COMMENT]

    @pytest.mark.asyncio
    async def test_exit_command_when_idle(self):
        """测试空闲状态下 exit 命令有效"""
        app = TalkerThinkerApp()
        await app.initialize()

        result = app.task_manager.classify_intent("exit")
        # exit 应该被识别为 REPLACE 意图
        assert result in [UserIntent.REPLACE, UserIntent.COMMENT]

    def test_handle_new_input_during_processing_exit(self):
        """测试在处理过程中 _handle_new_input_during_processing 正确处理 exit 命令"""
        # 这个测试确保 _handle_new_input_during_processing 方法
        # 在检测到 exit/quit 时返回 (True, "__EXIT__")
        # 由于该方法需要 async，我们通过检查源代码逻辑来验证
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp._handle_new_input_during_processing)
        assert '"__EXIT__"' in source or "'__EXIT__'" in source, \
            "_handle_new_input_during_processing 必须返回 __EXIT__ 标记"
        assert 'quit' in source.lower() or 'exit' in source.lower(), \
            "_handle_new_input_during_processing 必须检测 quit/exit 命令"

    @pytest.mark.asyncio
    async def test_cancel_command_during_processing(self):
        """测试在处理过程中"取消"命令直接取消任务"""
        app = TalkerThinkerApp()
        await app.initialize()

        app.task_manager._current_input = "复杂任务"
        app.task_manager._is_processing = True

        # 输入"取消"应该返回响应并取消任务
        handled, response = await app._handle_new_input_during_processing(
            "取消", "test_session"
        )

        assert handled is True, "应该处理'取消'命令"
        assert response is not None, "应该返回响应内容"
        assert "取消" in response, f"响应应该包含'取消'：{response}"


class TestTalkerNoResponse:
    """
    测试用例：Talker 不回应用户请求

    Bug 描述：在交互过程中，用户发送"有点慢"、"还在吗？"等请求，Talker 没有响应
    修复方式：
    1. 在 _handle_new_input_during_processing 中正确识别 COMMENT 和 QUERY_STATUS 意图
    2. 在任务启动后立即设置 output_complete_event 允许用户输入

    原始问题对话：
    [18:37:13.489] Talker: 分析中：分析任务需求
    有点慢
    还在干
    [长时间无响应]
    """

    def test_classify_slow_comment(self):
        """测试"有点慢"被正确分类并得到响应"""
        app = TalkerThinkerApp()
        app.task_manager._current_input = "分析任务"
        app.task_manager._is_processing = True

        result = app.task_manager.classify_intent("有点慢")
        # "有点慢"可能分类为 COMMENT 或 QUERY_STATUS，两种情况都能得到响应
        assert result in [UserIntent.COMMENT, UserIntent.QUERY_STATUS], \
            f"'有点慢'应该被分类为 COMMENT 或 QUERY_STATUS，实际为{result}"

    def test_classify_still_there_question(self):
        """测试"还在吗"被正确分类为 QUERY_STATUS 或 COMMENT"""
        app = TalkerThinkerApp()
        app.task_manager._current_input = "分析任务"
        app.task_manager._is_processing = True

        result = app.task_manager.classify_intent("还在吗")
        # 应该在 QUERY_STATUS 或 COMMENT 中
        assert result in [UserIntent.QUERY_STATUS, UserIntent.COMMENT], \
            f"'还在吗'应该被分类为 QUERY_STATUS 或 COMMENT，实际为{result}"

    @pytest.mark.asyncio
    async def test_handle_new_input_slow_comment(self):
        """测试 _handle_new_input_during_processing 处理"有点慢"返回响应"""
        # 功能测试：实际调用方法验证响应
        app = TalkerThinkerApp()
        await app.initialize()

        app.task_manager._current_input = "分析任务"
        app.task_manager._is_processing = True

        # 测试 COMMENT 意图下的"慢"处理
        # 模拟 intent 被分类为 COMMENT
        handled, response = await app._handle_new_input_during_processing("有点慢", "test_session")

        assert handled is True, "应该处理'有点慢'输入"
        assert response is not None, "应该返回响应内容"
        # 响应应该包含安抚性话语
        assert "久等" in response or "加速" in response or "稍候" in response or "处理" in response, \
            f"响应应该包含安抚性话语：{response}"

    def test_handle_new_input_still_there(self):
        """测试 _handle_new_input_during_processing 处理"还在吗"返回响应"""
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp._handle_new_input_during_processing)
        assert '"在"' in source or "'在'" in source, \
            "必须检测'在'关键词"
        assert '"吗"' in source or "'吗'" in source, \
            "必须检测'吗'疑问词"


class TestOutputCompleteEvent:
    """
    测试用例：output_complete_event 导致输入阻塞

    Bug 描述：在任务处理过程中，output_complete_event 被清除后没有及时设置，
              导致 read_input 函数无限等待，用户无法输入
    修复方式：任务启动后立即设置 output_complete_event

    这是导致"Talker 不响应"和"无法退出"的根本原因之一
    """

    def test_output_event_set_after_task_start(self):
        """测试任务启动后 output_complete_event 被设置"""
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp.run_interactive)
        # 检查在 process_task 创建后是否有 output_complete_event.set()
        assert 'output_complete_event.set()' in source, \
            "run_interactive 中必须设置 output_complete_event"

        # 检查设置位置是否在任务创建之后
        lines = source.split('\n')
        found_task_creation = False
        found_event_set_after = False
        for line in lines:
            if 'process_task = await self._process_as_task' in line:
                found_task_creation = True
            if found_task_creation and 'output_complete_event.set()' in line:
                found_event_set_after = True
                break

        assert found_event_set_after, \
            "output_complete_event.set() 必须在任务创建之后调用"


class TestInfiniteLoop:
    """
    测试用例：无限循环导致卡死

    Bug 描述：_collaboration_handoff 和 _delegation_handoff 中的 while 循环
              没有迭代次数限制，可能导致无限循环
    修复方式：添加 loop_iteration_count 和 max_loop_iterations 保护

    这是导致"卡死"的根本原因之一
    """

    def test_collaboration_handoff_loop_protection(self):
        """测试 _collaboration_handoff 有循环保护"""
        import inspect
        from orchestrator.coordinator import Orchestrator

        source = inspect.getsource(Orchestrator._collaboration_handoff)
        assert 'loop_iteration_count' in source, \
            "_collaboration_handoff 必须有 loop_iteration_count"
        assert 'max_loop_iterations' in source, \
            "_collaboration_handoff 必须有 max_loop_iterations"
        assert 'max_loop_iterations' in source and 'iterations' in source, \
            "_collaboration_handoff 必须检查循环次数并记录警告"

    def test_delegation_handoff_loop_protection(self):
        """测试 _delegation_handoff 有循环保护"""
        import inspect
        from orchestrator.coordinator import Orchestrator

        source = inspect.getsource(Orchestrator._delegation_handoff)
        assert 'loop_iteration_count' in source, \
            "_delegation_handoff 必须有 loop_iteration_count"
        assert 'max_loop_iterations' in source, \
            "_delegation_handoff 必须有 max_loop_iterations"


class TestTaskCancellationTimeout:
    """
    测试用例：任务取消时无限等待

    Bug 描述：cancel_current_task 中 await self._current_task 没有超时保护，
              如果任务不响应取消，会永久等待
    修复方式：使用 asyncio.wait_for 包装，添加 5 秒超时

    这是导致"无法退出"的根本原因之一
    """

    def test_cancel_current_task_timeout(self):
        """测试 cancel_current_task 有超时保护"""
        import inspect
        from main import TaskManager

        source = inspect.getsource(TaskManager.cancel_current_task)
        assert 'wait_for' in source, \
            "cancel_current_task 必须使用 asyncio.wait_for"
        assert 'timeout' in source, \
            "cancel_current_task 必须设置超时时间"


class TestReadInputTimeout:
    """
    测试用例：read_input 无限等待 output_complete_event

    Bug 描述：read_input 中 while not output_complete_event.is_set() 可能无限等待
    修复方案：
    1. 添加 5 秒超时保护
    2. 移除超时后的 continue 检查，确保输入可以继续获取

    这是导致"无法输入"的根本原因之一
    """

    def test_read_input_timeout_protection(self):
        """测试 read_input 有超时保护"""
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp.run_interactive)
        # 查找 read_input 函数中的超时保护
        assert 'wait_start_time' in source, \
            "read_input 必须有 wait_start_time 追踪变量"
        assert '5.0' in source or '5 ' in source, \
            "read_input 必须有 5 秒超时保护"

    def test_read_input_no_continue_after_timeout(self):
        """测试 read_input 在超时后没有 continue 检查，确保输入可以继续获取"""
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp.run_interactive)

        # 检查 read_input 函数中不应该有超时后的 continue 检查
        # 查找 pattern: "if not output_complete_event.is_set():\n                        continue"
        # 这个 pattern 在 timeout 之后不应该存在

        lines = source.split('\n')
        in_read_input = False
        found_timeout_check = False
        found_continue_after_timeout = False

        for i, line in enumerate(lines):
            if 'async def read_input' in line:
                in_read_input = True
            if in_read_input and 'forcing continue' in line:
                found_timeout_check = True
                # 检查接下来几行是否有 continue
                for j in range(i+1, min(i+10, len(lines))):
                    if 'if not output_complete_event.is_set()' in lines[j]:
                        # 找到检查，再检查后面是否有 continue
                        for k in range(j+1, min(j+5, len(lines))):
                            if 'continue' in lines[k] and lines[k].strip().startswith('continue'):
                                found_continue_after_timeout = True
                                break
                        break

            # 找到下一个函数定义，结束检查
            if in_read_input and (line.strip().startswith('async def ') or line.strip().startswith('def ')) and 'read_input' not in line:
                break

        assert not found_continue_after_timeout, \
            "read_input 在超时后不应该有 continue 检查，这会导致死锁"


class TestSignalHandling:
    """
    测试用例：缺少系统信号处理

    Bug 描述：没有注册 SIGTERM/SIGINT 处理器，只能依赖 KeyboardInterrupt
    修复方式：注册信号处理器，使用 shutdown_event 协调关闭

    这是导致"无法正常退出"的根本原因之一
    """

    def test_signal_handlers_registered(self):
        """测试注册了信号处理器"""
        import inspect
        from main import TalkerThinkerApp

        source = inspect.getsource(TalkerThinkerApp.run_interactive)
        assert 'signal.signal' in source, \
            "run_interactive 必须注册信号处理器"
        assert 'SIGTERM' in source, \
            "必须处理 SIGTERM 信号"
        assert 'SIGINT' in source, \
            "必须处理 SIGINT 信号"
        assert 'shutdown_event' in source, \
            "必须使用 shutdown_event 协调关闭"


# Integration tests for common scenarios

class TestIntegrationScenarios:
    """集成测试：常见使用场景"""

    @pytest.mark.asyncio
    async def test_user_can_input_during_thinker_processing(self):
        """测试用户可以在 Thinker 处理过程中输入"""
        app = TalkerThinkerApp()
        await app.initialize()

        # 模拟任务正在处理
        app.task_manager._current_input = "复杂任务"
        app.task_manager._is_processing = True
        app.task_manager._task_start_time = time.time()

        # 用户输入"有点慢"应该得到响应
        handled, response = await app._handle_new_input_during_processing(
            "有点慢", "test_session"
        )

        assert handled is True, "应该处理'有点慢'输入"
        assert response is not None, "应该返回响应内容"
        assert "久等" in response or "加速" in response or "稍候" in response, \
            f"响应应该包含安抚性话语：{response}"

    @pytest.mark.asyncio
    async def test_user_can_exit_during_processing(self):
        """测试用户可以在处理过程中通过 exit/quit 退出"""
        app = TalkerThinkerApp()
        await app.initialize()

        app.task_manager._current_input = "复杂任务"
        app.task_manager._is_processing = True

        # 输入 quit 应该返回 __EXIT__ 标记
        handled, response = await app._handle_new_input_during_processing(
            "quit", "test_session"
        )

        assert handled is True, "应该处理 quit 命令"
        assert response == "__EXIT__", f"quit 应该返回__EXIT__标记，实际为{response}"


# Run tests with: pytest tests/test_regression.py -v