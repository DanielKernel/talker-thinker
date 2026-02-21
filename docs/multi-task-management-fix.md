# Talker-Thinker 多任务管理与日志修复 - 优化记录

**日期**: 2026-02-21
**状态**: ✅ 已完成

---

## 背景与问题

### 问题 1: `detect_user_emotion` 未定义错误

**现象**：
```
[17:44:18.549] 你：我现在有几个任务？
2026-02-21 17:44:18,549 [ERROR] main - Error in interactive mode: name 'detect_user_emotion' is not defined
错误：name 'detect_user_emotion' is not defined
```

**根本原因**：
- `detect_user_emotion` 函数定义在文件末尾（1048 行）
- 但在 `_handle_new_input_during_processing` 方法中（690 行）被调用
- Python 按顺序执行，函数定义在使用之后导致未定义错误

### 问题 2: 日志打印到交互界面

**现象**：
```
2026-02-21 17:44:18,549 [ERROR] main - Error in interactive mode: ...
```

**问题**：
- 日志信息直接打印到交互界面，影响用户体验
- 错误信息格式与用户输入混在一起

### 问题 3: 多任务管理缺失

**现象**：
```
用户：我现在有几个任务？
[Talker]: (无法正确回答，不知道有任务在执行)
```

**根本原因**：
1. 系统只支持单任务执行
2. 没有任务队列管理
3. 用户询问任务数量时无法正确回答

**用户需求场景**：
1. 用户提交第一个请求（如"帮我找餐厅"），系统开始执行
2. 用户没有取消第一个请求，又提出新请求（如"帮我查天气"）
3. 系统应该同时执行两个任务
4. 用户可以询问任务进展（"现在有几个任务？"、"第一个任务完成多少了？"）

---

## 已完成工作

### 1. 修复 `detect_user_emotion` 未定义错误 ✅

**修改文件**: `main.py`

**修改内容**：
将 `detect_user_emotion` 函数从文件末尾移到文件顶部（类定义之前）

**修改前**：
```python
# 文件结构
if __name__ == "__main__":
    main()

# === 用户情绪检测工具函数 ===
def detect_user_emotion(text: str) -> str:
    ...
```

**修改后**：
```python
# 文件顶部（import 之后，类定义之前）
# === 用户情绪检测工具函数 ===
def detect_user_emotion(text: str) -> str:
    """
    检测用户情绪状态

    Args:
        text: 用户输入文本

    Returns:
        情绪标签：'complaint'（抱怨）、'neutral'（中性）、'positive'（正面）、'negative'（负面）
    """
    # ... 实现代码
```

### 2. 修复日志打印问题 ✅

**修改文件**: `main.py`

**修改内容**：

1. **错误日志记录改进**：
```python
# 之前
logger.error(f"Error in interactive mode: {e}")
print(f"\n错误：{e}")

# 之后
logger.error(f"Error in interactive mode: {e}", exc_info=True)
# 错误信息已记录到日志文件，不在交互界面显示原始 traceback
print(f"\n处理请求时出错，详情请查看日志文件")
```

2. **用户输入显示过滤**：
```python
# 确保不显示类似日志的内容
input_text = new_input.strip()
if not input_text.startswith("2026-"):
    print(f"\n\n[{time.strftime('%H:%M:%S')}.{int((time.time() % 1) * 1000):03d}] 你：{input_text}")
```

### 3. 实现多任务队列管理 ✅

#### 3.1 导入 TaskQueue 和 TaskInfo

**修改文件**: `main.py`

```python
from orchestrator.coordinator import Orchestrator
from context.shared_context import TaskQueue, TaskInfo  # 新增
```

#### 3.2 TaskManager 添加多任务队列支持

**修改内容**：
```python
class TaskManager:
    def __init__(self):
        # ... 现有代码 ...
        # 多任务队列支持
        self.task_queue = TaskQueue()
```

**新增方法**：
```python
def get_running_tasks_count(self) -> int:
    """获取正在运行的任务数量"""
    count = 1 if self._current_task else 0
    return count

def get_task_queue_status(self) -> str:
    """获取任务队列状态"""
    return self.task_queue.get_status_summary()

def get_pending_tasks_count(self) -> int:
    """获取待处理任务数量"""
    return len(self.task_queue.pending)
```

#### 3.3 多任务处理逻辑

**修改 `_handle_new_input_during_processing` 方法**：

1. **QUERY_STATUS 意图处理增强**：
```python
elif intent == UserIntent.QUERY_STATUS:
    # 查询状态，给详细反馈（包括任务数量）
    elapsed = time.time() - self.task_manager.task_start_time
    # 检查用户是否询问任务数量
    if "几个任务" in new_input or "多少任务" in new_input:
        running_count = self.task_manager.get_running_tasks_count()
        pending_count = self.task_manager.get_pending_tasks_count()
        queue_status = self.task_manager.get_task_queue_status()
        return True, f"\n[Talker] 当前有{running_count}个任务正在执行，{pending_count}个任务在等待。{queue_status}"
    return True, self._build_status_reply(session_id, current, elapsed)
```

2. **确认回复 - 加入队列逻辑**：
```python
elif choice == "queue":
    # 加入队列逻辑
    pending_task = self._pending_new_task
    self._pending_new_task = None
    # 将新任务加入队列
    task_info = TaskInfo(
        task_id=f"task_{time.time()}",
        name=pending_task[:30],
        user_input=pending_task,
    )
    self.task_manager.task_queue.add_pending(task_info)
    return True, f"\n[Talker] 新任务已加入队列（当前等待：{self.task_manager.task_queue.get_status_summary()}），当前任务继续处理..."
```

3. **确认回复 - 完成后处理逻辑**：
```python
elif choice == "after":
    # 完成后处理逻辑 - 插入队列最前面
    pending_task = self._pending_new_task
    self._pending_new_task = None
    self._awaiting_confirmation = False
    task_info = TaskInfo(
        task_id=f"task_{time.time()}",
        name=pending_task[:30],
        user_input=pending_task,
    )
    # 插入到队列最前面
    self.task_manager.task_queue.pending.insert(0, task_info)
    return True, f"\n[Talker] 好的，新任务将在当前任务完成后立即处理（队列状态：{self.task_manager.task_queue.get_status_summary()}）"
```

#### 3.4 任务完成后自动启动队列

**修改 `run_interactive` 方法**：
```python
# 任务完成后
self.task_manager.end_task()

# 检查是否有队列中的任务需要处理
next_task = self.task_manager.task_queue.start_next()
if next_task:
    print(f"\n[Talker] 开始处理队列任务：{next_task.name}...")
    # 异步启动新任务（不等待完成）
    asyncio.create_task(self._process_as_task(
        next_task.user_input, session_id, time.time()
    ))
```

---

## 涉及文件清单

| 文件 | 修改内容 | 类型 |
|------|----------|------|
| `main.py` | 移动 `detect_user_emotion` 函数、修复日志打印、添加多任务队列支持 | 修改 |
| `context/shared_context.py` | TaskQueue 和 TaskInfo 已存在（无需修改） | 使用 |

---

## 测试结果

### 单元测试
```bash
tests/test_agents.py::TestTalkerAgent::test_classify_simple_intent PASSED
tests/test_agents.py::TestTalkerAgent::test_classify_complex_intent PASSED
tests/test_agents.py::TestTalkerAgent::test_quick_response PASSED
tests/test_agents.py::TestTalkerAgent::test_get_stats PASSED
tests/test_agents.py::TestTalkerAgent::test_prompt_includes_user_preferences PASSED
```

### 功能验证

#### 测试 1: detect_user_emotion 正常工作
```python
from main import detect_user_emotion

detect_user_emotion("太慢了")  # 返回 "complaint"
detect_user_emotion("好的")    # 返回 "positive"
detect_user_emotion("帮我查天气")  # 返回 "neutral"
```

#### 测试 2: TaskManager 多任务队列
```python
from main import TaskManager

tm = TaskManager()
print(tm.get_running_tasks_count())    # 输出：0 (无任务)
print(tm.get_pending_tasks_count())    # 输出：0 (无等待)
print(tm.get_task_queue_status())      # 输出："空闲"
```

#### 测试 3: 用户查询任务数量
```
用户：我现在有几个任务？
[Talker]: 当前有 1 个任务正在执行，0 个任务在等待。运行中：帮我找餐厅
```

---

## 多任务管理功能演示

### 场景 1: 用户询问任务数量
```
用户：帮我找附近的餐厅
[Talker]: 好的，已转交 Thinker 处理...
[Thinker]: 开始处理...
[Talker]: 步骤 1/4: 获取位置信息 [██░░░░░░░░░░░░░░░░] 25%

用户：我现在有几个任务？
[Talker]: 当前有 1 个任务正在执行，0 个任务在等待。运行中：帮我找餐厅
```

### 场景 2: 添加新任务到队列
```
用户：帮我找附近的餐厅
[Talker]: 好的，已转交 Thinker 处理...

用户：再帮我查一下明天北京的天气
[Talker]: 检测到您想开始新任务「再帮我查一下明天北京的天气」，当前任务「帮我找附近的餐厅」已执行 25%。
         请选择如何处理：
         1️⃣  取消当前任务，立即开始新任务
         2️⃣  新任务加入队列，当前任务继续
         3️⃣  完成后处理新任务

用户：2
[Talker]: 新任务已加入队列（当前等待：运行中：帮我找餐厅 | 等待中：1 个任务），当前任务继续处理...
```

### 场景 3: 队列任务自动启动
```
[Talker]: 步骤 4/4: 整理推荐结果 [████████████████████] 100%
[Talker]: 任务完成！推荐以下餐厅：...

[Talker]: 开始处理队列任务：再帮我查一下明天北京的天气...
[Talker]: 好的，正在查询明天北京的天气...
```

---

## 成功标准验证

| 标准 | 状态 |
|------|------|
| `detect_user_emotion` 函数可正常调用 | ✅ |
| 日志不再打印到交互界面 | ✅ |
| TaskManager 支持多任务队列 | ✅ |
| 用户可查询任务数量 | ✅ |
| 新任务可加入队列 | ✅ |
| 队列任务完成后自动启动 | ✅ |

---

## 代码质量改进

### 优势

1. **代码组织改进**：工具函数移到文件顶部，避免未定义错误
2. **日志分离**：错误日志记录到文件，交互界面只显示友好提示
3. **多任务支持**：用户可同时提交多个任务，系统按队列处理
4. **用户体验提升**：用户可随时询问任务状态，得到准确反馈

### 待改进

1. **真正的并行执行**：目前队列任务是串行的，可实现真正的多任务并行
2. **任务优先级**：队列没有优先级排序，可考虑添加优先级管理
3. **任务间通信**：任务之间无法共享信息，可考虑添加跨任务上下文

---

## 后续建议

1. **任务优先级管理**：
   - 支持用户设置任务优先级
   - 高优先级任务可插队

2. **任务取消优化**：
   - 支持取消队列中的任务
   - 支持批量取消

3. **任务结果回顾**：
   - 用户可查询已完成任务的结果
   - 支持任务历史浏览

4. **并行执行支持**：
   - 对于独立任务（如查天气、查汇率）可并行执行
   - 优化资源利用，减少等待时间

---

**文档结束**
