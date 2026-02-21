# Talker 回应消息优化计划

## 优化日期

2026-02-21

## 问题描述

用户反馈在当前对话系统中，Talker 的回应消息存在以下问题：

1. **重复信息问题**：例如"正在整合分析结果"后面又跟着"即将完成，正在整合答案..."
2. **信息前后排布问题**：步骤描述不一致，如前面显示"步骤 1/4、步骤 2/4..."，后面又出现"[步骤 2]..."的原始格式
3. **消息冗余**：同一概念用不同表述重复播报

### 示例问题对话

```
[21:52:59.646] Talker: 正在整合分析结果...✓ 完成 (25269ms) 即将完成，正在整合答案...
[21:53:15.697] Talker: 步骤 4/4: 整合结果并生成答案 [████████████████████] 100%
```

## 问题分析

### 1. 消息去重机制不完善

- `_generate_stage_broadcast()` 在 SYNTHESIZING 阶段有多个相似模板随机选择
- `_try_rewrite_thinker_output()` 对 Thinker 输出的重写规则产生冗余

### 2. 两路输出未协调

- `_collaboration_handoff()` 中同时存在定时器播报和 Thinker 输出劫持
- 当 Thinker 输出被重写时，心跳播报可能同时触发，导致重复

### 3. 模板去重粒度不够

- `used_message_templates` 按阶段记录，但同一阶段内短时间仍可能输出相似消息

## 优化方案

### 1. 重构 `_try_rewrite_thinker_output()` 方法

**优先级重写规则**：
1. 静默处理（无意义标记）- `_is_silent_marker()`
2. 步骤标记（最具体，优先匹配）- `_try_rewrite_step_marker()`
3. 整合/答案标记（使用统一映射表）- `_try_rewrite_synthesize_marker()`
4. 思考/规划/分析标记 - `_try_rewrite_thinking_marker()`

### 2. 增强去重机制 - 基于消息指纹

**新增方法**：
- `_is_semantic_duplicate()`: 检测消息是否为语义重复
- `_extract_semantic_keywords()`: 提取消息的语义关键词

**ProgressState 新增字段**：
- `recent_message_fingerprints`: 最近消息指纹列表（用于语义去重）

### 3. 优化 SYNTHESIZING 阶段播报模板

按时间顺序使用不同模板，避免随机选择导致重复：
- 0-10 秒： "正在整合分析结果，请稍候..."
- 10-20 秒： "正在整理最终答案..."
- 20-30 秒： "即将完成，正在进行质量检查..."
- 30 秒+： "正在优化答案，感谢耐心等待..."

### 4. 协调心跳播报与输出劫持

在 Thinker 输出劫持逻辑中增加语义去重检查：
```python
if self._is_semantic_duplicate(talker_rewrite):
    # 跳过播报，但重置计时器
    last_broadcast_time = current_time
    continue
```

## 修改文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `orchestrator/coordinator.py` | 修改 | 核心优化：重写规则、去重机制、播报协调 |

## 测试结果

### 功能测试

```bash
pytest tests/ -v
# 83 passed, 1 warning
```

### 验证标准

1. [x] 不出现语义重复的连续播报
2. [x] 步骤格式始终保持一致（"步骤 X/Y"格式统一）
3. [x] SYNTHESIZING 阶段播报有序递进，不来回切换
4. [x] 所有现有测试通过

## 关键技术实现

### 语义指纹提取

```python
def _extract_semantic_keywords(self, text: str) -> str:
    """提取消息的语义关键词"""
    # 移除时间戳、进度条等变量
    text = re.sub(r'\d+s', '', text)
    text = re.sub(r'\[.+?\]', '', text)
    text = re.sub(r'[░█\d%]', '', text)

    # 保留核心动词和名词
    keywords = re.findall(r'[整合 | 分析 | 规划 | 执行 | 检查 | 优化 | 答案 | 结果 | 步骤]', text)
    return ''.join(sorted(set(keywords)))
```

### 语义去重检查

```python
def _is_semantic_duplicate(self, message_text: str) -> bool:
    """检测消息是否为语义重复"""
    keywords = self._extract_semantic_keywords(message_text)
    fingerprint = f"{self._progress_state.current_stage.value}:{keywords}"

    # 检查最近 5 条消息
    recent_fingerprints = self._progress_state.recent_message_fingerprints[-5:]
    if fingerprint in recent_fingerprints:
        return True

    # 添加新指纹
    self._progress_state.recent_message_fingerprints.append(fingerprint)
    # 限制列表长度为 10
    if len(self._progress_state.recent_message_fingerprints) > 10:
        self._progress_state.recent_message_fingerprints = self._progress_state.recent_message_fingerprints[-10:]
    return False
```

## 总结

本次优化通过以下措施解决了 Talker 回应消息的重复和冗余问题：

1. **结构化重写规则**：将 Thinker 输出重写逻辑拆分为 4 个独立的辅助方法，按优先级顺序调用
2. **语义去重**：基于消息指纹检测语义重复，避免短时间内播报相似内容
3. **时间分段播报**：SYNTHESIZING 阶段按 elapsed_time 分段使用不同模板，避免随机选择导致的重复
4. **播报协调**：在输出劫持时进行语义去重检查，避免与心跳播报冲突

优化后，用户体验显著提升，消息播报更加清晰、一致。
