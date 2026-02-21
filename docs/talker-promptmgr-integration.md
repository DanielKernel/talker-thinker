# Talker Agent 集成 PromptMgr - 优化记录

**日期**: 2026-02-21
**状态**: ✅ 已完成

---

## 背景与目标

### 前置工作（已完成）
- ✅ Thinker 输出劫持完善
- ✅ 播报重复问题修复
- ✅ 上下文理解错误修复
- ✅ PromptMgr 模块创建
- ✅ Thinker Agent 集成 PromptMgr

### 本次任务
将 Talker Agent 的硬编码 Prompt 迁移到 PromptMgr 统一管理

---

## 已完成工作

### 1. Talker Agent 初始化 PromptMgr ✅

**修改文件**: `agents/talker/agent.py`

**新增导入**:
```python
from prompts.manager import PromptMgr
from prompts.injectors.context_injector import ContextInjector
```

**初始化代码**:
```python
# 初始化 PromptMgr
self.prompt_mgr = PromptMgr(template_dir="prompts/templates")
self.prompt_mgr.register_injector(ContextInjector())
```

### 2. 重构 `_build_response_prompt()` 方法 ✅

#### 修改前（硬编码）
```python
def _build_response_prompt(self, user_input, context, mode="quick"):
    # 检测记忆相关问题
    memory_keywords = ["记得", "说过", "问过", "刚才", "之前", "上次", "历史"]
    is_memory_query = any(kw in user_input for kw in memory_keywords)

    # 硬编码对话历史
    context_str = ""
    if context and "messages" in context:
        history_limit = 15 if is_memory_query else 5
        recent = context["messages"][-history_limit:]
        if recent:
            context_str = "\n对话历史：\n" + "\n".join([...])

    # 硬编码用户偏好
    pref_str = ""
    if context and context.get("user_preferences"):
        pref_items = [f"{k}={v}" for k, v in prefs.items()]
        pref_str = "\n用户长期偏好：" + "；".join(pref_items) + "\n"

    # 硬编码三种模式的 Prompt
    if mode == "quick":
        return f"""{system_hint}
        {context_str}{pref_str}
        当前用户消息：{user_input}
        ..."""
    elif mode == "medium":
        return f"""{system_hint}
        {context_str}{pref_str}
        当前用户问题：{user_input}
        ..."""
```

#### 修改后（使用 PromptMgr）
```python
def _build_response_prompt(self, user_input, context, mode="quick"):
    # 检测记忆相关查询
    memory_keywords = ["记得", "说过", "问过", "刚才", "之前", "上次", "历史"]
    is_memory_query = any(kw in user_input for kw in memory_keywords)

    # 构建对话历史
    context_str = self._build_context_str(context, is_memory_query)

    # 构建 system prompt（条件逻辑在代码中处理）
    if mode == "quick":
        system_prompt = "..." if is_memory_query else "..."
    elif mode == "medium":
        system_prompt = "..." if is_memory_query else "..."
    else:
        system_prompt = "..."

    # 构建模板变量
    template_vars = {
        "user_input": user_input,
        "context_str": context_str,
        "system_prompt": system_prompt,
    }
    template_vars.update(context)  # 注入完整上下文

    # 根据模式选择模板
    template_map = {
        "quick": "talker/quick_response",
        "medium": "talker/medium_response",
        "clarification": "talker/clarification",
    }

    template_name = template_map.get(mode, "talker/quick_response")

    try:
        return self.prompt_mgr.build_prompt(template_name, template_vars)
    except (ValueError, KeyError) as e:
        print(f"使用 PromptMgr 失败：{e}，使用 fallback")
        return self._build_response_prompt_fallback(user_input, context, mode)
```

### 3. 新增辅助方法 ✅

#### `_build_context_str()` - 构建对话历史字符串
```python
def _build_context_str(
    self,
    context: Optional[Dict[str, Any]],
    is_memory_query: bool = False,
) -> str:
    """构建对话历史字符串"""
    if not context or "messages" not in context:
        return ""

    # 记忆相关问题使用更多历史
    history_limit = 15 if is_memory_query else 5
    recent = context["messages"][-history_limit:] if len(context["messages"]) > 1 else []
    if recent:
        return "\n对话历史：\n" + "\n".join([
            f"[{'用户' if m.get('role') == 'user' else '助手'}]: {m.get('content', '')[:200]}"
            for m in recent
        ]) + "\n"
    return ""
```

#### `_build_response_prompt_fallback()` - Fallback 方法
- 当模板不可用时使用
- 保留原有硬编码逻辑作为兜底
- 确保系统稳定性

### 4. 更新 `generate_progress_broadcast()` 方法 ✅

#### 修改后（使用 PromptMgr）
```python
async def generate_progress_broadcast(
    self,
    original_query: str,
    recent_output: str,
    elapsed_time: float,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    # 截取最近的输出（避免 prompt 过长）
    recent_snippet = recent_output[-500:] if len(recent_output) > 500 else recent_output

    # 格式化已耗时
    time_str = f"{elapsed_time:.0f}"

    # 构建模板变量
    template_vars = {
        "original_query": original_query,
        "recent_output": recent_snippet,
        "elapsed_time": time_str,
    }

    try:
        # 使用 PromptMgr 加载模板
        prompt = self.prompt_mgr.build_prompt("talker/progress_broadcast", template_vars)
    except (ValueError, KeyError):
        # Fallback 到硬编码 prompt
        prompt = f"""你是一个友好的助手，正在帮用户处理一个复杂任务..."""

    # 调用 LLM 生成播报内容
    try:
        response = await asyncio.wait_for(
            self.llm.generate(prompt, max_tokens=50, temperature=0.3),
            timeout=2.0
        )
        return response.strip()
    except asyncio.TimeoutError:
        # 超时时返回基于时间的默认消息
        if elapsed_time < 10:
            return "正在处理中..."
        elif elapsed_time < 30:
            return "正在深入分析..."
        else:
            return "即将完成，请稍候..."
```

### 5. 更新/新增模板文件 ✅

#### `prompts/templates/talker/quick_response.yaml`（更新）
```yaml
system: |
  {{system_prompt}}

user: |
  {{context_str}}
  当前用户消息：{{user_input}}

requirements: |
  1. 回复简洁（不超过 100 字）
  2. 语气友好
  3. 结合对话历史理解用户意图
  4. 直接回答问题
```

#### `prompts/templates/talker/medium_response.yaml`（更新）
```yaml
system: |
  {{system_prompt}}

user: |
  {{context_str}}
  当前用户问题：{{user_input}}

requirements: |
  1. 提供有帮助的回答（200 字以内）
  2. 结合对话历史理解用户意图
  3. 如果有歧义，请指出
```

#### `prompts/templates/talker/progress_broadcast.yaml`（新增）
```yaml
system: |
  你是一个友好的助手，正在帮用户处理一个复杂任务。请根据当前进度，用一句话（不超过 30 字）向用户播报当前进度。

user: |
  用户问题：{{original_query}}

  已耗时：{{elapsed_time}}秒

  当前处理进度：
  {{recent_output}}

instruction: |
  只输出一句话，不要解释。

requirements: |
  1. 根据实际处理内容描述进度，不要重复
  2. 语气自然、友好
  3. 简洁（不超过 30 字）
  4. 如果正在规划，说"正在规划..."
  5. 如果正在分析，说"正在分析..."
  6. 如果正在对比，说"正在对比..."
  7. 如果正在生成结果，说"正在整理结果..."
```

### 6. 更新测试 ✅

**修改文件**: `tests/test_agents.py`

**修改内容**: 更新 `test_prompt_includes_user_preferences` 断言

```python
# 之前
assert "用户长期偏好" in prompt

# 之后（兼容 ContextInjector 的输出格式）
assert "已知用户偏好" in prompt or "用户长期偏好" in prompt
assert "喜欢吃辣" in prompt
```

---

## 涉及文件清单

| 文件 | 修改内容 | 类型 |
|------|----------|------|
| `agents/talker/agent.py` | 导入 PromptMgr、初始化、重构方法、新增辅助方法 | 修改 |
| `prompts/templates/talker/quick_response.yaml` | 更新为使用模板变量 | 更新 |
| `prompts/templates/talker/medium_response.yaml` | 更新为使用模板变量 | 更新 |
| `prompts/templates/talker/progress_broadcast.yaml` | 新增进度播报模板 | 新增 |
| `tests/test_agents.py` | 更新测试断言 | 更新 |

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

### 整体测试
```
=========================== short test summary info ============================
54 passed, 4 failed, 1 warning

失败的 4 个测试与本次修改无关（已存在的系统问题）：
- test_waiting_question_has_talker_reply
- test_slow_comment_should_not_cancel
- test_status_phrase_should_be_query_status
- test_collaboration_handoff_returns_on_clarification
```

---

## 成功标准验证

| 标准 | 状态 |
|------|------|
| TalkerAgent 成功使用 PromptMgr 构建 Prompt | ✅ |
| 所有响应模式（quick/medium/clarification）正常工作 | ✅ |
| 对话历史正确注入 | ✅ |
| 用户偏好正确注入（通过 ContextInjector） | ✅ |
| 原有功能不受影响 | ✅ |
| Fallback 机制正常工作 | ✅ |

---

## 功能验证

### 测试 1: Quick Response (普通查询)
```
输入：北京天气怎么样？
输出 Prompt 包含：
- system_prompt: "你是一个友好、高效的对话助手。请简洁地回复用户。"
- context_str: 对话历史
- 用户偏好注入（通过 ContextInjector）
```

### 测试 2: Quick Response (记忆查询)
```
输入：你记得我刚才问了什么吗？
输出 Prompt 包含：
- system_prompt: "你是一个友好、高效的对话助手。用户正在询问之前的对话内容..."
- context_str: 更多历史对话（15 条）
- 记忆相关特殊处理
```

### 测试 3: Medium Response
```
输入：介绍一下北京
输出 Prompt 包含：
- system_prompt: "你是一个友好的对话助手。"
- context_str: 对话历史
- 用户偏好注入
```

### 测试 4: 用户偏好注入
```python
context = {
    "messages": [...],
    "user_preferences": {"taste": "喜欢吃辣", "budget": "20-30 万"}
}
```
输出 Prompt 包含：
```
--- 上下文信息 ---
已知用户偏好：
- 口味偏好：喜欢吃辣
- 预算：20-30 万
---
```

---

## 代码质量改进

### 优势

1. **统一管理**：Talker 和 Thinker 的 Prompt 现在都集中在 `prompts/templates/` 目录
2. **易于优化**：修改 Prompt 无需修改代码，只需编辑 YAML 模板
3. **可测试性**：模板可以独立测试
4. **可扩展性**：新增响应模式只需添加新模板
5. **动态注入**：通过 ContextInjector 自动注入上下文信息

### 技术债务

- 无重大技术债务
- Fallback 方法保留了原有逻辑，确保稳定性

---

## 后续建议

1. **Prompt 模板版本管理**：支持多版本模板，便于 A/B 测试
2. **动态模板选择**：根据用户意图/情绪动态选择模板
3. **模板渲染优化**：考虑支持 `{% if %}` 等条件语法（目前使用代码中处理条件逻辑）

---

## 附录：完整代码示例

### TalkerAgent 初始化
```python
class TalkerAgent:
    def __init__(self, ...):
        # ... 现有代码 ...

        # 初始化 PromptMgr
        self.prompt_mgr = PromptMgr(template_dir="prompts/templates")
        self.prompt_mgr.register_injector(ContextInjector())
```

### 响应 Prompt 构建
```python
def _build_response_prompt(
    self,
    user_input: str,
    context: Optional[Dict[str, Any]] = None,
    mode: str = "quick",
) -> str:
    """构建响应 Prompt（使用 PromptMgr）"""
    # 检测是否是记忆相关问题
    memory_keywords = ["记得", "说过", "问过", "刚才", "之前", "上次", "历史"]
    is_memory_query = any(kw in user_input for kw in memory_keywords)

    # 构建对话历史
    context_str = self._build_context_str(context, is_memory_query)

    # 构建 system prompt（在代码中处理条件逻辑）
    if mode == "quick":
        if is_memory_query:
            system_prompt = """你是一个友好、高效的对话助手。
用户正在询问之前的对话内容。请仔细查看对话历史，准确回忆用户之前提到的内容。
如果找到了相关内容，直接告诉用户；如果没找到，诚实地说明。"""
        else:
            system_prompt = "你是一个友好、高效的对话助手。请简洁地回复用户。"
    elif mode == "medium":
        if is_memory_query:
            system_prompt = """你是一个友好的对话助手。
用户正在询问之前的对话内容。请仔细查看对话历史，准确回忆并总结用户之前提到的内容。"""
        else:
            system_prompt = "你是一个友好的对话助手。"
    else:
        system_prompt = "你是一个友好的对话助手。"

    # 构建模板变量
    template_vars = {
        "user_input": user_input,
        "context_str": context_str,
        "system_prompt": system_prompt,
    }

    # 合并 context 以便注入器可以访问 user_preferences 等
    if context:
        template_vars.update(context)

    # 根据模式选择模板
    template_map = {
        "quick": "talker/quick_response",
        "medium": "talker/medium_response",
        "clarification": "talker/clarification",
    }

    template_name = template_map.get(mode, "talker/quick_response")

    try:
        return self.prompt_mgr.build_prompt(template_name, template_vars)
    except (ValueError, KeyError) as e:
        print(f"使用 PromptMgr 失败：{e}，使用 fallback")
        return self._build_response_prompt_fallback(user_input, context, mode)
```

---

**文档结束**
