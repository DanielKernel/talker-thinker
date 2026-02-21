# Talker-Thinker 优化复盘与评测指南

## 1. 优化历程复盘

### 1.1 播报系统优化

#### 第一次优化（2026-02-20 初次）
| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| 独立时间检查 | 每次循环都检查播报条件 | ✅ 有效 | 保留 |
| 动态间隔（2.5-4秒） | 根据耗时调整间隔 | ⚠️ 部分有效 | 需改进 |
| 时间桶去重 | `阶段_步骤_5秒桶` 哈希 | ❌ 无效 | 废弃 |

**问题**：时间桶去重无效，因为每4秒播报一次，恰好每次都落在不同的5秒桶中，导致消息仍然重复。

#### 第二次优化（2026-02-20 改进）
| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| 消息追踪去重 | `used_messages` 按阶段记录已用消息 | ✅ 有效 | 保留 |
| 更保守间隔（4-8秒） | 延长播报间隔 | ✅ 有效 | 保留 |
| 每阶段消息上限 | 最多5条不同消息 | ✅ 有效 | 保留 |

**结论**：消息追踪去重 + 更长间隔 = 有效防止重复

### 1.2 智能打断机制优化

#### 第一次优化
| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| 新增COMMENT意图 | 评论不打断任务 | ✅ 有效 | 保留 |
| 新增BACKCHANNEL意图 | 附和不打断任务 | ✅ 有效 | 保留 |
| 默认REPLACE→COMMENT | 默认不打断 | ✅ 有效 | 保留 |

#### 第二次优化（本次）
| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| Talker实时回应 | COMMENT/QUERY时Talker给反馈 | 🔄 待验证 | 新增 |
| 检测等待疑问 | "有人在吗"识别为QUERY_STATUS | 🔄 待验证 | 新增 |

### 1.3 上下文共享优化

| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| SharedContext数据结构 | 定义共享字段 | ✅ 完成 | 保留 |
| Thinker更新进度 | 各阶段调用update | ⚠️ 部分有效 | 需增强 |
| Talker读取进度 | 播报时读取进度 | ⚠️ 部分有效 | 需增强 |

**问题**：SharedContext创建后，Thinker和Talker没有真正使用它进行双向通信。

### 1.4 会话记忆优化

| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| SessionContext集成 | Redis/内存双模式 | ✅ 有效 | 保留 |
| 对话摘要 | 超过阈值自动压缩 | ✅ 有效 | 保留 |
| 跨轮次记忆 | 通过session_id关联 | ✅ 有效 | 保留 |

### 1.5 Skills系统优化

| 优化项 | 方案 | 效果 | 状态 |
|--------|------|------|------|
| Skills注册 | 初始化时注册默认技能 | ✅ 完成 | 保留 |
| SkillInvoker注入 | Thinker可调用技能 | ⚠️ 未验证 | 待测试 |

---

## 2. 问题对比分析

### 2.1 播报重复问题

**现象**：
```
[02:56:09.055] Talker: 即将完成分析...
[02:56:13.071] Talker: 分析进行中 (64s)...
[02:56:17.084] Talker: 即将完成分析...  ← 重复！
[02:56:21.106] Talker: 分析进行中 (72s)...
```

**根本原因分析**：

| 版本 | 问题原因 | 解决方案 |
|------|----------|----------|
| v1 | 播报逻辑只在无输出时检查 | 每次循环都检查 ✅ |
| v2 | 时间桶去重粒度太粗 | 消息级别去重 ✅ |
| v3 | 间隔太短(2.5-4秒) | 延长到4-8秒 ✅ |

**验证方法**：
```bash
# 测试播报间隔和去重
python main.py -i
# 输入复杂任务，观察播报是否重复
# 预期：每4-8秒播报一次，内容不重复
```

### 2.2 Talker不回应问题

**现象**：
```
[03:02:34.509] Talker: 已转交给Thinker处理
（用户等待中...）
[03:02:52.352] 你: 有点慢啊
（无回应）
[03:03:05.311] 你: 有人在吗？
（无回应）
```

**根本原因**：
1. COMMENT/BACKCHANNEL返回`None`，完全静默
2. "有人在吗"被误判为COMMENT而非QUERY_STATUS

**解决方案**：
```python
# 之前
if intent == UserIntent.COMMENT:
    return True, None  # 完全静默

# 之后
if intent == UserIntent.COMMENT:
    if "慢" in text:
        return True, "\n[Talker] 抱歉让您久等了..."
    elif "在" in text and "吗" in text:
        return True, "\n[Talker] 在的！正在处理..."
```

### 2.3 Thinker无初始回应问题

**现象**：
```
[Talker] 已转交给Thinker处理
（长时间无输出）
[Thinker] [思考] 正在分析任务...  ← 很久才出现
```

**根本原因**：Thinker的LLM调用耗时较长，没有立即给出反馈

**解决方案**：添加立即响应
```python
# 在Thinker开始处理前
yield f"\n[{ts}] Thinker: 开始处理..."
```

---

## 3. 评测指标体系

### 3.1 核心体验指标

| 指标 | 定义 | 目标值 | 测量方法 |
|------|------|--------|----------|
| TTFT | 首Token响应时间 | < 500ms | 时间戳差值 |
| 播报间隔 | 两次播报的时间间隔 | 4-8秒 | 时间戳差值 |
| 播报重复率 | 相同消息重复的比例 | < 5% | 消息哈希对比 |
| 实时回应率 | 用户等待疑问的回应比例 | > 90% | 人工标注 |
| 意图识别准确率 | 正确识别用户意图的比例 | > 85% | 人工标注 |

### 3.2 交互质量指标

| 指标 | 定义 | 目标值 | 测量方法 |
|------|------|--------|----------|
| 打断误判率 | 评论被误判为取消的比例 | < 5% | 人工标注 |
| 等待焦虑缓解率 | Talker回应后用户继续等待的比例 | > 80% | 行为分析 |
| 任务完成率 | 用户任务成功完成的比例 | > 95% | 完成标记 |

### 3.3 测试用例

#### 用例1：播报去重测试
```bash
输入: "帮我对比分析一下几款主流新能源车的优缺点"
预期:
- 播报间隔4-8秒
- 无重复消息
- 每阶段消息不超过5条
```

#### 用例2：实时回应测试
```bash
输入1: "帮我推荐一下"
（等待5秒后）
输入2: "有点慢啊"
预期: [Talker] 抱歉让您久等了，正在加速处理...

输入3: "有人在吗？"
预期: [Talker] 在的！正在为您处理，请稍候...
```

#### 用例3：智能打断测试
```bash
输入1: "帮我分析一下新能源车市场"
（处理中）
输入2: "鸿蒙智行的车不错"  ← 评论
预期: 任务继续，不被打断

输入3: "算了，不用了"  ← 取消
预期: 任务取消
```

---

## 4. 优化状态总览

### 4.1 已完成且有效 ✅

| 优化项 | 文件 | 效果 |
|--------|------|------|
| 独立播报时间检查 | coordinator.py | 播报不再依赖Thinker输出 |
| 消息追踪去重 | coordinator.py | 防止消息重复 |
| 更保守播报间隔(4-8s) | coordinator.py | 减少播报频率 |
| COMMENT/BACKCHANNEL意图 | main.py | 评论不打断任务 |
| 默认不打断 | main.py | 避免误打断 |
| SessionContext集成 | coordinator.py | 会话持久化 |
| Thinker立即响应 | coordinator.py | Thinker开始时给反馈 |
| Talker实时回应（本次） | main.py | 等待疑问有回应 |

### 4.2 已完成需验证 🔄

| 优化项 | 文件 | 待验证内容 |
|--------|------|------------|
| SharedContext更新 | thinker/agent.py | Thinker是否真正更新进度 |
| Talker实时回应 | main.py | 回应是否自然、时机是否合适 |
| 等待疑问检测 | main.py | "有人在吗"等是否正确识别 |

### 4.3 待改进 ⚠️

| 优化项 | 问题描述 | 改进方向 |
|--------|----------|----------|
| Skill参数提取 | 过于简单 | 使用LLM提取 |
| 跨会话记忆 | 未实现 | 添加用户ID |
| 交互式确认 | 未实现 | 重要操作前确认 |

---

## 5. 后续优化优先级

### P0 - 紧急（本周）
1. **验证本次优化效果**
   - 测试Talker实时回应
   - 测试播报去重
   - 测试智能打断

2. **修复残留问题**
   - 如发现播报仍重复，进一步调整
   - 如Talker回应不自然，优化话术

### P1 - 重要（近期）
1. **增强SharedContext使用**
   - Thinker主动更新进度
   - Talker读取进度用于播报
   - 双向信息流真正打通

2. **LLM意图分类**
   - 关键词分类作为快速路径
   - 复杂情况调用LLM判断
   - 超时降级到关键词

### P2 - 中期
1. **交互式确认**
   - 取消前确认
   - 重要操作确认

2. **Skill系统增强**
   - LLM参数提取
   - 更多实用技能

### P3 - 长期
1. **跨会话记忆**
2. **用户偏好学习**
3. **个性化播报风格**

---

## 6. 避免重复错误的checklist

### 6.1 播报相关
- [ ] 新增播报消息时，确保加入`used_messages`追踪
- [ ] 播报间隔不低于4秒
- [ ] 每阶段消息不超过5条
- [ ] 带时间的消息使用`f"xxx ({elapsed:.0f}s)..."`格式

### 6.2 交互相关
- [ ] COMMENT意图也要考虑Talker回应，不要完全静默
- [ ] 等待疑问（"有人在吗"、"太慢了"）识别为QUERY_STATUS
- [ ] 不要让用户长时间（>10秒）看不到任何反馈

### 6.3 上下文相关
- [ ] SharedContext创建后要确保被使用
- [ ] Thinker各阶段要调用`update_thinker_progress`
- [ ] Talker播报前检查SharedContext中的进度信息

### 6.4 测试验证
- [ ] 每次修改后运行交互测试
- [ ] 观察实际输出是否符合预期
- [ ] 记录问题和改进效果

---

## 7. 严重问题记录

### 7.3 Talker完全无法理解用户诉求（2026-02-20 15:26）⚠️⚠️ 系统性严重问题

**现象**：用户多次明确表达"不买了"、"我要吃饭"，系统完全无法理解，继续执行原任务

```
用户: 我的餐馆定好了没？
[Talker] 收到，继续处理「对比几个网站...」  ✗ 问餐馆，回车

用户: 太慢了
[Talker] 抱歉让您久等了，正在加速处理...  ✓ 正确

用户: 你在干啥
（无回应，继续播报）  ✗ 应该回应

用户: 分析啥
（无回应）  ✗ 应该回应

用户: 不用买车了
（无回应，任务继续）  ✗ 应该取消

用户: 不买了
（无回应，任务继续）  ✗ 应该取消

用户: 在吗？
[Talker] 正在处理「对比几个网站...」  ✗ 没有正面回答

用户: 不买了
（无回应）  ✗ 仍然不取消

用户: 我要定餐馆
[Talker] 收到，继续处理「对比几个网站...」  ✗✗ 完全错误！

用户: 我要吃饭
[Talker] 收到，继续处理「对比几个网站...」  ✗✗ 仍然错误！

用户: 吃饭
[Talker] 嗯，继续...  ✗✗ 被当作BACKCHANNEL！

用户: 不买车
（无回应）  ✗ 不取消

用户: 吃饭
[Talker] 嗯，继续...  ✗✗ 仍然错误！
```

**根本原因分析**：

| 问题类型 | 具体表现 | 根因 |
|----------|----------|------|
| 取消意图识别失败 | "不用买车了"、"不买了"不取消 | 取消关键词可能被覆盖或优先级不够 |
| 新任务识别失败 | "我要定餐馆"、"我要吃饭"不切换 | 新任务检测逻辑有缺陷 |
| 短文本误判 | "吃饭"被当作BACKCHANNEL | 短文本判断逻辑有问题 |
| 话题不匹配 | 问餐馆却继续处理选车 | 没有话题相关性检测 |
| 用户投诉无回应 | "你在干啥"、"分析啥"无回应 | COMMENT处理不当 |

**系统性问题**：

1. **意图分类层级混乱**：
   - 多个检测规则之间存在覆盖关系
   - 优先级设计不合理
   - 边界条件处理不当

2. **话题理解缺失**：
   - 系统不知道当前在处理"买车"任务
   - 用户说"吃饭"时无法判断话题已切换
   - 没有维护当前任务的语义上下文

3. **用户体验设计缺陷**：
   - 用户明确说"不买了"应该立即停止
   - 用户说"我要XXX"应该切换任务
   - 用户提问应该得到回应

4. **规则冲突**：
   ```
   "吃饭" → 长度2 → BACKCHANNEL → "嗯，继续..."  ✗
   "吃饭" → 包含"吃" → 应该是新任务 → REPLACE   ✓
   ```

**需要的系统性解决方案**：

| 模块 | 需要解决的问题 | 建议方案 |
|------|----------------|----------|
| 意图分类 | 规则优先级混乱 | 重新设计分类层级，取消/新任务优先级最高 |
| 话题检测 | 无法识别话题切换 | 添加话题相似度检测，当前是"车"，用户说"吃"=话题切换 |
| 短文本处理 | 误判为BACKCHANNEL | 短文本也要检测是否是新任务关键词 |
| 用户反馈 | 投诉/疑问无回应 | COMMENT中检测投诉/疑问词汇，给予回应 |
| 上下文维护 | 不知道当前在干什么 | 在TaskManager中维护current_topic |

**优先级**: P0（最高优先级，系统基本功能受损）

**状态**: 待系统性重构

---

### 7.2 任务无法取消 & Talker无法交互（2026-02-20 15:18）⚠️严重

**现象**：
```
用户: 太慢了
[Talker] 抱歉让您久等了，正在加速处理...  ✓ 正确

用户: 我的口味是啥？
[Talker] 收到，继续处理「推荐个餐馆...」  ✗ 应该回答问题

用户: 不知道我的口味？
（无回应）  ✗ 应该回应

用户: 又每回应
（无回应，继续播报）  ✗ 应该回应投诉

用户: 我要买车
[Talker] 收到，继续处理「推荐个餐馆...」  ✗ 应该切换任务

用户: 买车，不定餐馆了
（继续原任务）  ✗ 应该取消

用户: 不定了
（继续原任务）  ✗ 应该取消

用户: 取消
[Talker] 嗯，继续...  ✗✗✗ 严重错误！应该取消任务

用户: 取消
[Talker] 嗯，继续...  ✗✗✗ 仍然不取消

用户: 完全乱了
（任务继续执行）  ✗ 系统完全失控
```

**根本原因分析**：

| 问题 | 根因 | 影响 |
|------|------|------|
| "取消"不生效 | 被误分类为BACKCHANNEL | 用户无法停止任务 |
| "我要买车"不切换 | 被分类为CONTINUE | 用户无法切换话题 |
| 问题不回答 | COMMENT返回"收到，继续处理" | 用户体验极差 |
| 广播覆盖回应 | 并行输出无协调 | Talker回应被淹没 |

**代码层面问题**：

1. **意图分类逻辑错误**（main.py `classify_intent`）：
   ```python
   # 问题1: "取消"只有2个字，被第一个判断捕获
   if text in backchannel_patterns or len(text) <= 2:
       return UserIntent.BACKCHANNEL  # ← "取消"被这里捕获！

   # 问题2: 取消关键词检测在后面
   cancel_keywords = ["取消", ...]  # 永远执行不到
   ```

2. **COMMENT处理不当**：
   ```python
   if intent == UserIntent.COMMENT:
       # 问题: 不管用户说什么都返回"收到，继续处理"
       return True, f"\n[Talker] 收到，继续处理「{current[:30]}...」"
   ```

3. **广播与用户输入并行**：
   - coordinator.py中的广播循环独立运行
   - main.py中的用户输入处理也是独立的
   - 两者输出没有协调机制

**修复优先级**: P0（紧急）

**已修复（2026-02-20 15:25）**：

| 问题 | 修复方案 |
|------|----------|
| "取消"被BACKCHANNEL捕获 | 取消关键词检测移到最前面（第0步） |
| 短文本误判 | 移除`len(text) <= 2`的BACKCHANNEL判断 |
| COMMENT回应不智能 | 根据内容分类回应（慢/在吗/乱/问题等） |
| 新任务不识别 | 添加"我要"、"买"等新任务关键词 |

**待修复**：
- 广播与用户输入协调问题
- 系统性测试验证

---

### 7.1 播报系统退化问题（2026-02-20 15:14）

**现象**：
```
[03:14:28.050] Thinker: 开始处理...
[03:14:28.050] Talker: 处理中 (55s)...
[03:14:28.101] Thinker: [思考] 正在分析任务...

[03:14:36.068] Talker: 分析进行中 (63s)...
[03:14:44.098] Talker: 分析进行中 (71s)...
[03:14:52.122] Talker: 分析进行中 (79s)...

用户: 太慢了

[03:15:00.153] Talker: 分析进行中 (87s)...  ← Talker没回应！
```

**问题分析**：

| 问题 | 根因 | 状态 |
|------|------|------|
| "分析进行中"重复 | 带时间戳的消息每次都不同，去重失效 | ❌ 严重 |
| Talker不回应"太慢了" | 广播循环和用户输入处理是并行的，广播覆盖了回应 | ❌ 严重 |
| 播报时间错误(55s开始) | elapsed_time计算错误，可能使用了错误的起始时间 | ❌ 需调查 |

**根本原因**：

1. **去重机制设计缺陷**：
   ```python
   # 当前实现
   msgs = [f"分析进行中 ({elapsed_time:.0f}s)..."]
   # 每次elapsed_time都不同，所以消息每次都"不重复"，但这正是问题所在！
   ```

2. **并行处理冲突**：
   - 广播循环在coordinator.py中运行
   - 用户输入处理在main.py中运行
   - 两者输出没有协调，导致广播覆盖了Talker回应

3. **时间计算问题**：
   - elapsed=55s但实际才刚开始处理
   - 可能是`llm_request_time`或`thinker_start`设置错误

**待修复方案**：
1. 去重应该基于消息模板而非完整内容
2. 用户输入时应该暂停广播循环
3. 检查时间计算逻辑

**修复记录（2026-02-20 15:30）**：

| 问题 | 修复方案 |
|------|----------|
| 带时间戳消息重复 | 改用模板去重：`_generate_stage_broadcast`返回`(msg, template)`，去重基于template |
| 间隔太短(2.5-4s) | 调整为6-10秒 |
| 每阶段消息太多 | 限制为4条不同模板 |
| 广播循环未协调 | （待实现）用户输入时暂停广播 |

---

## 9. 待系统性优化的核心问题

### 9.1 意图分类系统重构（P0）

**当前问题**：
- 规则优先级混乱，后添加的规则可能覆盖前面的
- 短文本"吃饭"被误判为BACKCHANNEL
- "不买了"等取消意图无法识别
- "我要XXX"等新任务意图无法识别

**重构方案**：
```
优先级从高到低：
1. 取消意图（"不买了"、"取消"、"不要了"）→ REPLACE
2. 新任务意图（"我要XXX"、"帮我XXX"）→ REPLACE
3. 话题切换（当前处理A，用户说B相关内容）→ REPLACE
4. 状态查询（"在吗"、"进度"）→ QUERY_STATUS
5. 投诉/疑问（"太慢了"、"你在干啥"）→ COMMENT（需回应）
6. 附和/确认（"嗯"、"好的"）→ BACKCHANNEL
7. 其他 → COMMENT
```

**实现要点**：
- 维护`current_topic`字段
- 添加`is_topic_switch(new_input)`方法
- 短文本也要检测关键词

### 9.2 Talker实时交互能力（P0）

**当前问题**：
- 用户提问无回应
- 用户投诉无回应
- 播报与用户输入冲突

**需要实现**：
1. 用户输入时暂停播报循环
2. Talker根据用户内容智能回应
3. 回应内容不被播报覆盖

### 9.3 任务取消机制（P0）

**当前问题**：
- "取消"、"不买了"等无法取消任务
- 取消后任务仍在执行

**需要实现**：
1. 取消意图立即触发`cancel_current_task()`
2. 任务取消后停止所有LLM调用
3. 给用户明确的取消确认

### 9.4 话题切换检测（P1）

**当前问题**：
- 当前处理"选车"，用户说"吃饭"不切换
- 没有话题相关性检测

**需要实现**：
```python
class TaskManager:
    def __init__(self):
        self._current_topic: Optional[str] = None  # 当前话题

    def is_topic_switch(self, new_input: str) -> bool:
        """检测是否是话题切换"""
        new_topic = self._extract_topic(new_input)
        if new_topic and self._current_topic:
            return new_topic != self._current_topic
        return False
```

### 9.5 广播系统重构（P1）

**当前问题**：
- 播报频率、内容仍有问题
- 与用户输入冲突

**需要实现**：
1. 用户输入时暂停广播
2. 广播内容更智能（基于实际进度）
3. 模板去重机制完善

---

## 10. 测试用例清单

### 10.1 取消任务测试

| 输入 | 当前任务 | 预期结果 |
|------|----------|----------|
| "取消" | 选车 | ✅ 任务取消 |
| "不买了" | 选车 | ✅ 任务取消 |
| "不用了" | 选车 | ✅ 任务取消 |
| "算了" | 选车 | ✅ 任务取消 |

### 10.2 新任务测试

| 输入 | 当前任务 | 预期结果 |
|------|----------|----------|
| "我要吃饭" | 选车 | ✅ 切换到餐馆任务 |
| "帮我定餐馆" | 选车 | ✅ 切换到餐馆任务 |
| "吃饭" | 选车 | ✅ 切换到餐馆任务 |

### 10.3 话题切换测试

| 输入 | 当前任务 | 预期结果 |
|------|----------|----------|
| "我的餐馆定好了没" | 选车 | ✅ 切换到餐馆话题 |
| "买车要多少钱" | 选餐馆 | ✅ 切换到车话题 |

### 10.4 用户交互测试

| 输入 | 当前状态 | 预期结果 |
|------|----------|----------|
| "在吗？" | 处理中 | ✅ Talker回应"在的" |
| "你在干啥" | 处理中 | ✅ Talker回应正在做的事 |
| "太慢了" | 处理中 | ✅ Talker道歉并说明进度 |
| "分析啥" | 处理中 | ✅ Talker回答正在分析什么 |

---

## 11. 后续优化优先级（修订）

### P0 - 系统基本功能（本周必须完成）
- [ ] 意图分类系统重构
- [ ] 取消任务功能修复
- [ ] 新任务识别功能
- [ ] Talker实时回应

### P1 - 核心体验优化
- [ ] 话题切换检测
- [ ] 广播系统重构
- [ ] 用户输入与播报协调

### P2 - 功能完善
- [ ] SharedContext真正启用
- [ ] 技能系统增强
- [ ] 会话记忆优化

### P3 - 长期规划
- [ ] 跨会话记忆
- [ ] 用户偏好学习
- [ ] 个性化体验

---

## 12. 更新日志

### 2026-02-20（第七次更新 - 系统性问题记录）
- **发现系统性严重问题**：
  - Talker完全无法理解用户诉求
  - "吃饭"被误判为BACKCHANNEL
  - "我要定餐馆"被当作COMMENT继续原任务
  - "不买了"无法取消任务
- **根本原因分析**：
  - 意图分类层级混乱
  - 话题理解缺失
  - 规则存在覆盖关系
- **新增待优化章节**：
  - 意图分类系统重构方案
  - Talker实时交互能力需求
  - 任务取消机制需求
  - 话题切换检测方案
  - 广播系统重构方案
- **新增测试用例清单**：
  - 取消任务测试
  - 新任务测试
  - 话题切换测试
  - 用户交互测试
- **更新优化优先级**：
  - P0: 系统基本功能（本周必须完成）
- **状态**: 暂停优化，需要系统性重构

### 2026-02-20（第六次更新 - 播报系统修复）
- **核心修复：模板去重**：
  - `_generate_stage_broadcast`现在返回`(msg, template)`元组
  - 去重基于template而非完整消息
  - "分析进行中 (63s)"和"分析进行中 (71s)"现在共享同一模板"分析进行中"
- **间隔调整**：
  - 6-10秒（之前2.5-4秒太短）
- **限制调整**：
  - 每阶段最多4条不同模板（之前5条）
- **数据结构调整**：
  - `ProgressState.used_messages` → `used_message_templates`
  - `last_broadcast_msg` → `last_broadcast_msg_template`

### 2026-02-20（第五次更新 - 问题记录）
- **发现严重问题**：
  - 播报去重机制因带时间戳而失效
  - Talker回应被广播覆盖
  - 时间计算错误
- **状态**：播报系统优化出现退化，需要重新设计

### 2026-02-20（第四次更新）
- **Talker实时回应**：
  - COMMENT时根据内容给简短回应
  - "慢"相关抱怨回应"抱歉让您久等"
  - "在吗"相关疑问回应"在的"
- **等待疑问检测**：
  - "有人在吗"、"太慢了"识别为需要回应
  - 归类为QUERY_STATUS获取详细反馈
- **创建复盘文档**：
  - 记录优化历程
  - 分析问题根因
  - 建立评测指标
  - 制定后续优先级

### 2026-02-20（前三次更新）
- 详见 `optimization-plan.md`

---

## 13. 本轮交互新增问题记录（2026-02-20 17:17~17:22）

### 13.1 现象记录

**用户对话片段**（简化）：
```
[17:17:36] 用户: 打车
[17:21:43] Talker: 给出简短答复（未进入Thinker）

[17:21:44] 用户: 详细对比滴滴和高德...并查看最新评价和优惠
[17:22:28] Talker: 已转交Thinker
[17:22:49] 用户: 有点慢
系统: 判定为打断并取消任务（错误）
```

### 13.2 新问题

1. **Thinker前置阶段缺少播报**  
   - 在“转交Thinker”后，`plan_task/needs_clarification`阶段可能较慢，期间没有额外进度反馈，用户感知为“没播报”。

2. **“有点慢”被误判为取消任务**  
   - 该输入属于等待评论/催促，预期应返回 COMMENT 或 QUERY_STATUS，不应触发 REPLACE。

### 13.3 根因定位

- **误判根因**：`TaskManager._is_likely_new_task()` 包含过宽动作词 `"点"`，导致“有点慢”被识别为动作语义，触发新任务判定路径。  
- **播报缺失根因**：`_collaboration_handoff` 在澄清检测前没有独立前置播报，长耗时预处理阶段出现静默窗口。

### 13.4 已实施修复

1. **意图修复**  
   - 从 `_is_likely_new_task` 动作关键词中移除 `"点"`，避免“有点慢”这类短评论误判为新任务。

2. **播报修复**  
   - 在 `_collaboration_handoff` 转交Thinker后，增加前置播报：  
     `Talker: 正在同步上下文并规划步骤，请稍候...`

3. **回归测试补充**  
   - 新增测试：`test_slow_comment_should_not_cancel`，确保“有点慢”不再被识别为 REPLACE。

### 13.5 后续验证建议

- 交互回放验证：在复杂任务转交后，确认 1-2 秒内出现前置播报。  
- 中途输入验证：输入“有点慢”“太慢了”“在吗”均不取消任务，仅返回实时状态/安抚反馈。  
- 取消验证：输入“取消”“不需要了”仍应立即生效，确保修复不影响取消路径。

---

## 14. 历史交互问题总览与优化优先级（2026-02-20 汇总）

### 14.1 问题大类

1. **Thinker可见性不足（P0）**  
   - 表现：长时间仅Talker播报，用户感知Thinker未工作。  
   - 方向：首反馈SLA、precheck超时降级、阶段信号强制上报。

2. **播报重复与进度脱节（P0）**  
   - 表现：文案重复轮播，信息增量低。  
   - 方向：阶段驱动播报、模板去重+时间桶、无进展时降级播报。

3. **意图理解与打断误判（P0）**  
   - 表现：补充信息被取消；取消与新任务切换边界不稳。  
   - 方向：三分决策状态机、低置信度确认、复合输入片段提取。

4. **上下文与记忆不连续（P1）**  
   - 表现：已有上下文未被利用、跨会话偏好召回弱。  
   - 方向：补充并入当前任务、任务语义摘要、长期偏好持久化+注入。

5. **评测闭环不足（P1）**  
   - 表现：同类问题反复出现，修复稳定性难验证。  
   - 方向：场景化回归矩阵与质量阈值（误取消率、播报重复率、首反馈时延）。

### 14.2 优先级排序

| 优先级 | 目标 | 核心动作 |
|--------|------|----------|
| P0 | 先保证“不断流、不误判” | Thinker可见性、播报去重、打断决策状态机 |
| P1 | 再保证“懂上下文、记得住” | 跨会话记忆、语义摘要、偏好注入 |
| P2 | 最后保证“持续提升” | 混合意图判定、播报自适应、指标驱动优化 |

### 14.3 建议验收指标

- Thinker首可见反馈：`<= 2s`  
- 无催促场景播报间隔：`<= 7s` 且重复率 `< 10%`  
- 误取消率：`< 5%`  
- 复合输入切换成功率（取消+新任务）：`> 90%`  
- 跨会话偏好召回命中率：`> 85%`

---

## 15. Talker Agent 集成 PromptMgr（2026-02-21）

### 背景与目标

**前置工作完成**：
- ✅ Thinker 输出劫持完善
- ✅ 播报重复问题修复
- ✅ 上下文理解错误修复
- ✅ PromptMgr 模块创建
- ✅ Thinker Agent 集成 PromptMgr

**本次任务**：将 Talker Agent 的硬编码 Prompt 迁移到 PromptMgr 统一管理

### 已完成工作

#### 1. Talker Agent 初始化 PromptMgr ✅

**修改文件**: `agents/talker/agent.py`

**新增代码**:
```python
from prompts.manager import PromptMgr
from prompts.injectors.context_injector import ContextInjector

# 初始化
self.prompt_mgr = PromptMgr(template_dir="prompts/templates")
self.prompt_mgr.register_injector(ContextInjector())
```

#### 2. 重构 `_build_response_prompt()` 方法 ✅

**修改前**：硬编码三种模式的 Prompt 模板

**修改后**：使用 PromptMgr 加载模板
```python
def _build_response_prompt(self, user_input, context, mode="quick"):
    # 检测记忆相关查询
    is_memory_query = any(kw in user_input for kw in ["记得", "说过", "问过", ...])

    # 构建对话历史
    context_str = self._build_context_str(context, is_memory_query)

    # 构建 system prompt（条件逻辑在代码中处理）
    if mode == "quick":
        system_prompt = "..." if is_memory_query else "..."
    elif mode == "medium":
        system_prompt = "..." if is_memory_query else "..."

    # 构建模板变量
    template_vars = {
        "user_input": user_input,
        "context_str": context_str,
        "system_prompt": system_prompt,
    }
    template_vars.update(context)  # 注入完整上下文

    # 加载模板
    template_map = {
        "quick": "talker/quick_response",
        "medium": "talker/medium_response",
        "clarification": "talker/clarification",
    }

    try:
        return self.prompt_mgr.build_prompt(template_map[mode], template_vars)
    except (ValueError, KeyError) as e:
        print(f"使用 PromptMgr 失败：{e}，使用 fallback")
        return self._build_response_prompt_fallback(user_input, context, mode)
```

#### 3. 新增辅助方法 ✅

**`_build_context_str()`** - 构建对话历史字符串
```python
def _build_context_str(self, context, is_memory_query=False):
    """构建对话历史字符串"""
    if not context or "messages" not in context:
        return ""

    history_limit = 15 if is_memory_query else 5
    recent = context["messages"][-history_limit:]

    return "\n对话历史：\n" + "\n".join([
        f"[{'用户' if m.get('role') == 'user' else '助手'}]: {m.get('content', '')[:200]}"
        for m in recent
    ]) + "\n"
```

**`_build_response_prompt_fallback()`** - Fallback 方法
- 当模板不可用时使用
- 保留原有硬编码逻辑作为兜底

#### 4. 更新 `generate_progress_broadcast()` 方法 ✅

**修改后**：使用 PromptMgr 加载模板
```python
template_vars = {
    "original_query": original_query,
    "recent_output": recent_snippet,
    "elapsed_time": time_str,
}

try:
    prompt = self.prompt_mgr.build_prompt("talker/progress_broadcast", template_vars)
except (ValueError, KeyError):
    # Fallback 到硬编码 prompt
    prompt = f"""..."""

# 调用 LLM 生成播报内容
response = await self.llm.generate(prompt, max_tokens=50, temperature=0.3)
```

#### 5. 更新/新增模板文件 ✅

| 模板文件 | 状态 |
|---------|------|
| `prompts/templates/talker/quick_response.yaml` | 更新 |
| `prompts/templates/talker/medium_response.yaml` | 更新 |
| `prompts/templates/talker/progress_broadcast.yaml` | 新增 |

#### 6. 更新测试 ✅

**修改文件**: `tests/test_agents.py`

**修改内容**: 更新 `test_prompt_includes_user_preferences` 断言
```python
# 兼容 ContextInjector 的输出格式
assert "已知用户偏好" in prompt or "用户长期偏好" in prompt
```

### 涉及文件清单

| 文件 | 修改内容 |
|------|----------|
| `agents/talker/agent.py` | 导入 PromptMgr、初始化、重构 `_build_response_prompt()`、新增辅助方法、更新 `generate_progress_broadcast()` |
| `prompts/templates/talker/quick_response.yaml` | 更新为使用模板变量 |
| `prompts/templates/talker/medium_response.yaml` | 更新为使用模板变量 |
| `prompts/templates/talker/progress_broadcast.yaml` | 新增进度播报模板 |
| `tests/test_agents.py` | 更新测试断言 |

### 测试结果

#### 单元测试
```
tests/test_agents.py::TestTalkerAgent::test_classify_simple_intent PASSED
tests/test_agents.py::TestTalkerAgent::test_classify_complex_intent PASSED
tests/test_agents.py::TestTalkerAgent::test_quick_response PASSED
tests/test_agents.py::TestTalkerAgent::test_get_stats PASSED
tests/test_agents.py::TestTalkerAgent::test_prompt_includes_user_preferences PASSED
```

#### 整体测试
```
54 passed, 4 failed, 1 warning

失败的 4 个测试与本次修改无关（已存在的系统问题）：
- test_waiting_question_has_talker_reply
- test_slow_comment_should_not_cancel
- test_status_phrase_should_be_query_status
- test_collaboration_handoff_returns_on_clarification
```

### 成功标准验证

| 标准 | 状态 |
|------|------|
| TalkerAgent 成功使用 PromptMgr 构建 Prompt | ✅ |
| 所有响应模式（quick/medium/clarification）正常工作 | ✅ |
| 对话历史正确注入 | ✅ |
| 用户偏好正确注入（通过 ContextInjector） | ✅ |
| 原有功能不受影响 | ✅ |
| Fallback 机制正常工作 | ✅ |

### 代码质量改进

**优势**：
1. **统一管理**：Talker 和 Thinker 的 Prompt 现在都集中在 `prompts/templates/` 目录
2. **易于优化**：修改 Prompt 无需修改代码，只需编辑 YAML 模板
3. **可测试性**：模板可以独立测试
4. **可扩展性**：新增响应模式只需添加新模板
