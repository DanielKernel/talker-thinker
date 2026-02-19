# Talker-Thinker 系统优化方案

## 目录
1. [播报系统优化](#1-播报系统优化)
2. [记忆系统优化](#2-记忆系统优化)
3. [技能系统优化](#3-技能系统优化)
4. [Agent协作与上下文融合](#4-agent协作与上下文融合)（⭐核心架构优化）
5. [全双工交互优化](#5-全双工交互优化)
6. [实施优先级](#6-实施优先级)
7. [测试验证](#7-测试验证)
8. [参考资料](#8-参考资料)

---

## 1. 播报系统优化

### 1.1 问题诊断

原始实现存在两个核心问题：

1. **Talker长时间不播报**：播报逻辑只在Thinker没有新输出时才检查，当Thinker持续输出时播报条件永不触发
2. **Talker重复播报**：缺乏有效的内容去重机制

### 1.2 参考的最佳实践

基于以下2026年最新实践：
- [LangGraph Platform](https://www.langchain.com/langgraph) - 原生token-by-token流式输出
- [Microsoft AI Agent可视化指南](https://blog.csdn.net/yzx991013/article/details/158100867) - 思维链可视化
- [Spring AI Alibaba](https://juejin.cn/post/7583139562735501355) - 交错输出类型设计

关键洞察：
- 思考过程可视化：显示Agent每一步的"内心独白"
- 长任务进度流：永不留用户对着空白屏幕
- "三要素"可视化：做了什么、为什么、怎么做

### 1.3 实施的改进

#### 1.3.1 独立的播报时间检查机制

```python
# 之前的逻辑（只在无输出时检查）：
if output_index < len(thinker_output):
    # 处理输出...
else:
    # 这里才检查播报，导致持续输出时不播报

# 改进后的逻辑（每次循环都检查）：
while not thinker_complete:
    current_time = time.time()

    # === 每次循环都检查播报 ===
    broadcast_interval = get_broadcast_interval(elapsed)
    if current_time - last_broadcast_time >= broadcast_interval:
        # 执行播报...

    # 处理Thinker输出
    if output_index < len(thinker_output):
        # 处理输出...
```

#### 1.3.2 动态播报间隔

根据已耗时动态调整间隔（上限4秒）：
- 0-10秒：2.5秒间隔（初始频繁更新）
- 10-20秒：3.0秒间隔（中期稳定）
- 20秒+：4.0秒间隔（后期上限）

```python
def get_broadcast_interval(elapsed: float) -> float:
    if elapsed < 10:
        return 2.5  # 初始2.5秒
    elif elapsed < 20:
        return 3.0  # 中期3秒
    else:
        return 4.0  # 后期4秒（上限）
```

#### 1.3.3 内容哈希去重

使用 `阶段 + 步骤 + 时间桶(5秒)` 生成哈希，避免重复播报：

```python
def _hash_broadcast_content(self, stage: ThinkerStage, step: int, elapsed: float) -> str:
    elapsed_bucket = int(elapsed // 5) * 5  # 每5秒一个桶
    return f"{stage.value}_{step}_{elapsed_bucket}"
```

#### 1.3.4 多样化播报消息

根据时间和阶段动态选择播报内容：
- 初始阶段(initial)：详细介绍当前操作
- 进行中(progress)：显示处理进度
- 安抚(reassure)：告知用户系统仍在工作
- 紧急(urgent)：长时间等待时的安抚

### 1.4 涉及的文件

- `orchestrator/coordinator.py`:
  - `_collaboration_handoff()` - 协作模式的播报逻辑
  - `_delegation_handoff()` - 委托模式的播报逻辑
  - `_should_broadcast()` - 播报判断逻辑
  - `_generate_stage_broadcast()` - 播报消息生成
  - `_hash_broadcast_content()` - 内容哈希去重

---

## 2. 记忆系统优化

### 2.1 当前问题

**问题现象**：用户问"我问过买车，你记得吗？"，系统无法正确回忆之前的对话。

**根本原因**：

1. **内存存储而非持久化**：Orchestrator使用简单的`self._sessions`字典存储会话，程序重启后丢失
2. **SessionContext未被使用**：Redis会话上下文代码存在但未接入
3. **对话历史长度限制**：只保留最近5-10轮对话，早期信息丢失
4. **缺乏对话摘要**：没有长对话的压缩和关键信息提取
5. **无跨会话记忆**：每次启动都是新会话，无法关联历史会话

### 2.2 现有架构

系统已设计三层记忆架构但未完全启用：

```
L1: Working Context (内存)     - 当前轮次上下文
L2: Session Context (Redis)    - 24小时会话保持
L3: Long-term Memory (PostgreSQL) - 永久用户数据
```

### 2.3 优化方案

#### 2.3.1 短期优化：启用SessionContext

**目标**：将Orchestrator的内存存储迁移到Redis

**步骤**：
1. 在Orchestrator初始化时创建SessionContext实例
2. 替换`self._sessions`字典为Redis操作
3. 添加消息时同步写入Redis
4. 启动时从Redis恢复会话

```python
# orchestrator/coordinator.py
class Orchestrator:
    def __init__(self, ...):
        # 添加
        self.session_context = SessionContext()

    async def _get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        # 从Redis获取或创建
        if not await self.session_context.exists(session_id):
            await self.session_context.set_session_data(
                session_id, "created_at", time.time()
            )
        return {
            "messages": await self.session_context.get_messages(session_id),
            "created_at": await self.session_context.get_session_data(session_id, "created_at"),
        }
```

#### 2.3.2 中期优化：对话摘要系统

**目标**：长对话自动压缩，保留关键信息

**实现**：
1. 每N轮对话后生成摘要
2. 摘要包含：用户意图、关键实体、决策结果
3. 下次对话时注入摘要作为上下文

```python
# context/summarizer.py 已存在，需要启用
class ConversationSummarizer:
    async def summarize(self, messages: List[Message]) -> str:
        # 使用LLM生成摘要
        # 关键实体提取
        # 意图归纳
```

#### 2.3.3 长期优化：跨会话记忆

**目标**：用户级长期记忆，记住用户偏好和历史

**实现**：
1. 添加用户ID标识
2. 重要事件写入LongTermMemory
3. 用户偏好学习
4. 启动时加载用户画像

```python
# 关键实体记忆
await long_term_memory.save_event(
    user_id="user_123",
    event_type="topic_interest",
    event_data={"topic": "买车", "mentioned_at": time.time()}
)

# 用户偏好学习
await long_term_memory.learn_user_preference(
    user_id="user_123",
    category="travel",
    preference="prefers_ride_hailing"
)
```

### 2.4 上下文注入改进

在Agent处理前注入记忆上下文：

```python
async def process(self, user_input: str, session_id: str, ...):
    # 构建完整上下文
    context = {
        # 当前输入
        "current_input": user_input,

        # 短期记忆：最近对话
        "recent_messages": await self.session_context.get_messages(session_id, limit=10),

        # 中期记忆：会话摘要
        "session_summary": await self.session_context.get_summary(session_id),

        # 长期记忆：用户偏好
        "user_preferences": await self.long_term_memory.get_user_preferences(user_id),

        # 关键实体：之前讨论过的话题
        "mentioned_topics": await self.long_term_memory.get_user_events(
            user_id, event_type="topic_interest"
        ),
    }
```

### 2.5 涉及的文件

- `orchestrator/coordinator.py` - 集成记忆系统
- `context/session_context.py` - Redis会话存储
- `context/long_term_memory.py` - 长期记忆
- `context/summarizer.py` - 对话摘要
- `context/working_context.py` - 工作上下文

---

## 3. 技能系统优化

### 3.1 当前问题

**问题现象**：Skills系统存在但未被使用

**根本原因**：
1. **Skills未注册**：示例skills(weather, search, calculation)没有注册到引擎
2. **Thinker未调用Skills**：规划中可能识别出需要的skill，但实际执行时没有调用
3. **Skill Invoker未注入**：Thinker Agent有`set_skill_invoker()`方法但未被调用

### 3.2 现有架构

```
skills/
├── base.py          # Skill基类定义
├── engine.py        # SkillsEngine - 注册/发现/管理
├── invoker.py       # SkillInvoker - 调用/缓存/重试
└── examples/
    ├── weather.py      # 天气查询skill
    ├── search.py       # 搜索skill
    └── calculation.py  # 计算skill
```

### 3.3 优化方案

#### 3.3.1 初始化时注册Skills

```python
# orchestrator/coordinator.py 或 main.py
from skills.engine import get_global_engine
from skills.examples.weather import WeatherSkill
from skills.examples.search import SearchSkill
from skills.examples.calculation import CalculationSkill

def initialize_skills():
    engine = get_global_engine()
    engine.register_skill(WeatherSkill())
    engine.register_skill(SearchSkill())
    engine.register_skill(CalculationSkill())
```

#### 3.3.2 将SkillInvoker注入Thinker

```python
# orchestrator/coordinator.py
class Orchestrator:
    def __init__(self, ...):
        # 初始化Skills
        self.skills_engine = get_global_engine()
        self.skill_invoker = SkillInvoker(self.skills_engine)

        # 注入到Thinker
        self.thinker.set_skill_invoker(self.skill_invoker)
```

#### 3.3.3 改进Thinker的Skill调用

当前Thinker在`execute_step()`中检查skill，但参数提取过于简单：

```python
# 当前实现
def _extract_skill_params(self, step, context, previous_results):
    params = {}
    desc = step.get("description", "")
    params["query"] = desc  # 太简单
    params["text"] = desc
    return params

# 改进：使用LLM提取参数
async def _extract_skill_params_with_llm(self, step, skill_schema, context):
    prompt = f"""
    从以下步骤描述中提取技能参数：
    步骤：{step.get('description')}
    技能参数要求：{skill_schema}

    输出JSON格式的参数：
    """
    response = await self.llm.generate(prompt)
    return json.loads(response)
```

#### 3.3.4 增加更多实用Skills

建议添加的Skills：
1. **TimeSkill** - 获取当前时间、日期
2. **MemorySkill** - 查询/存储用户记忆
3. **CalculatorSkill** - 数学计算
4. **WebSearchSkill** - 网络搜索（对接搜索API）

### 3.4 Skill调用流程

```
用户输入 → Talker分类
    ↓
复杂任务 → Thinker规划
    ↓
规划包含skill需求（如"需要调用天气查询"）
    ↓
execute_step() → 检测skill需求
    ↓
SkillInvoker.invoke() → 执行skill
    ↓
结果返回给Thinker继续处理
```

### 3.5 涉及的文件

- `orchestrator/coordinator.py` - Skills初始化和注入
- `agents/thinker/agent.py` - Skill调用逻辑
- `skills/engine.py` - Skills引擎
- `skills/invoker.py` - Skill调用器
- `skills/examples/*.py` - 示例Skills

---

## 4. Agent协作与上下文融合（⭐核心架构优化）

### 4.1 当前问题

**核心痛点**：Talker和Thinker互相不感知对方内容，上下文记忆没有共享

```
当前流程（问题）：
┌─────────┐     ┌─────────┐     ┌─────────┐
│  用户   │────▶│ Talker  │────▶│ Thinker │
└─────────┘     └─────────┘     └─────────┘
                    │               │
                    ▼               ▼
               只知道自己      只知道自己
               的输出          的输出

问题：
1. Talker不知道Thinker分析到了哪一步
2. Thinker不知道Talker和用户说了什么
3. 用户无法在Thinker处理时通过Talker澄清问题
4. 错过了"边处理边澄清"的交互机会
```

### 4.2 理想的协作模式

**目标**：实现"边交互边澄清"的效果

```
理想流程：
┌─────────┐     ┌─────────┐     ┌─────────┐
│  用户   │◀───▶│ Talker  │◀───▶│ Thinker │
└─────────┘     └─────────┘     └─────────┘
     │              │               │
     │              │               │
     └──────────────┴───────────────┘
                    │
                    ▼
              共享上下文池
         ┌────────────────────┐
         │ - 用户原始问题      │
         │ - Talker的对话记录  │
         │ - Thinker的分析进度 │
         │ - 澄清问答历史      │
         │ - 用户偏好信息      │
         └────────────────────┘
```

### 4.3 核心改进方案

#### 4.3.1 共享上下文池（SharedContext）

**设计目标**：Talker和Thinker都能读写同一个上下文

```python
# context/shared_context.py
@dataclass
class SharedContext:
    """Talker和Thinker共享的上下文"""

    # 用户信息
    user_input: str                    # 原始问题
    user_clarifications: List[str]     # 用户的澄清回答

    # Talker的输出
    talker_broadcasts: List[str]       # 播报记录
    talker_interactions: List[Dict]    # 与用户的交互

    # Thinker的进度
    thinker_stage: str                 # 当前阶段
    thinker_partial_results: List[str] # 中间结果
    thinker_questions: List[str]       # Thinker想问用户的问题

    # 融合信息
    clarified_intent: str              # 澄清后的意图
    extracted_entities: Dict           # 提取的实体
    constraints: List[str]             # 约束条件
```

#### 4.3.2 Thinker向Talker请求澄清

**场景**：Thinker分析过程中发现信息不足，通过Talker向用户提问

```python
# agents/thinker/agent.py
class ThinkerAgent:
    async def execute_step(self, step, context, previous_results):
        # 检测是否需要澄清
        if self._needs_clarification(step, previous_results):
            # 生成澄清问题
            question = await self._generate_clarification_question(
                step, context, previous_results
            )

            # 通过共享上下文请求Talker澄清
            context["shared"].thinker_questions.append(question)
            context["shared"].awaiting_clarification = True

            # 暂停当前步骤，等待澄清
            return StepResult(
                step_name=step.get("name"),
                status="awaiting_clarification",
                clarification_needed=question,
            )

        # 正常执行...
```

#### 4.3.3 Talker处理澄清交互

**场景**：Talker检测到Thinker需要澄清，主动询问用户

```python
# orchestrator/coordinator.py
async def _collaboration_handoff(self, user_input, context, ...):
    # ... Thinker处理中 ...

    # 检查Thinker是否需要澄清
    if context.get("shared", {}).get("awaiting_clarification"):
        questions = context["shared"].thinker_questions

        # Talker向用户提问
        for q in questions:
            yield f"\n[{ts}] Talker: {q}"

        # 进入等待澄清模式
        user_answer = await self._wait_for_user_clarification()
        context["shared"].user_clarifications.append({
            "question": q,
            "answer": user_answer,
        })
        context["shared"].awaiting_clarification = False

        # 通知Thinker继续，带上澄清信息
        context["shared"].clarified_intent = self._update_intent_with_clarification(
            context["shared"].clarified_intent,
            user_answer
        )
```

#### 4.3.4 双向信息流

**Talker → Thinker 的信息**：
- 用户的原始表达（口语化）
- 用户的澄清回答
- 用户的情绪反馈
- 交互过程中的新信息

**Thinker → Talker 的信息**：
- 当前处理阶段
- 中间分析结果
- 需要澄清的问题
- 预计完成时间

```python
# 信息流实现
class Orchestrator:
    async def process(self, user_input, session_id, ...):
        # 创建共享上下文
        shared = SharedContext(user_input=user_input)
        context = {"shared": shared, ...}

        # Talker和Thinker都能访问shared
        # Talker可以写入 user_clarifications
        # Thinker可以读取并更新 clarified_intent
```

### 4.4 边交互边澄清的流程示例

```
用户: 帮我选一款适合家用的SUV

[Talker] 好的，需要深度分析，已转交给Thinker处理
[Thinker] [思考] 正在分析任务...

[Talker] Thinker正在分析您的需求...

[Thinker] [规划] 共3个步骤

[Talker] 已理解需求，正在制定方案...

[Thinker] [步骤1] 分析车型...发现问题：预算范围不明确

[Talker] 您好，想确认一下您的预算范围大概是多少？
         这样我能更精准地为您推荐。

用户: 20-30万吧

[Talker] 收到，已更新您的预算为20-30万

[Thinker] [步骤1] 在预算20-30万范围内筛选SUV...

[Talker] 筛选中: 20-30万价位家用SUV...

[Thinker] [步骤2] 对比车型性能...

[Thinker] [答案] 推荐...
```

### 4.5 实现步骤

1. **创建SharedContext数据结构**
   - 文件：`context/shared_context.py`
   - 定义共享数据字段

2. **修改Orchestrator**
   - 在`_collaboration_handoff`中创建共享上下文
   - 实现澄清等待循环

3. **修改Thinker**
   - 添加`_needs_clarification()`检测
   - 添加`_generate_clarification_question()`生成问题
   - 支持暂停/恢复机制

4. **修改Talker**
   - 检测Thinker的澄清请求
   - 自然地向用户提问
   - 收集并格式化用户的回答

### 4.6 涉及的文件

- `context/shared_context.py`（新建）- 共享上下文定义
- `orchestrator/coordinator.py` - 澄清循环实现
- `agents/thinker/agent.py` - 澄清检测和问题生成
- `agents/talker/agent.py` - 澄清交互处理

---

## 5. 全双工交互优化

### 5.1 当前状态

已实现基础全双工：
- 用户可以在Thinker处理时发送新消息
- 支持意图分类（CONTINUE/REPLACE/MODIFY/QUERY_STATUS）
- 支持任务打断和取消

### 5.2 待优化项

#### 5.2.1 更智能的意图分类

当前使用关键词匹配，可以改进为LLM理解：

```python
async def classify_user_intent_with_llm(self, new_input: str, current_task: str) -> UserIntent:
    prompt = f"""
    用户正在等待系统处理一个任务：{current_task}
    用户现在说：{new_input}

    请判断用户的意图：
    - REPLACE: 取消当前任务，开始新任务
    - MODIFY: 修改/补充当前任务
    - QUERY_STATUS: 查询当前进度
    - CLARIFY: 回答系统的澄清问题

    只返回意图类型。
    """
    response = await self.llm.generate(prompt)
    return UserIntent(response.strip().upper())
```

#### 5.2.2 任务暂停/恢复

不只是取消，支持暂停和恢复：

```python
class TaskState(Enum):
    RUNNING = "running"
    PAUSED = "paused"      # 新增：暂停
    CANCELLED = "cancelled"
    COMPLETED = "completed"
```

#### 5.2.3 交互式确认

对于重要操作，增加确认步骤：

```python
# 用户想取消时
[Talker] 您确定要取消当前的分析任务吗？已经完成60%了。
用户: 是的，取消吧
[Talker] 好的，已取消。有其他需要帮助的吗？
```

---

## 6. 实施优先级

### P0 - 立即修复
- [x] 播报系统优化（已完成）
- [x] 动态播报间隔（已完成）
- [x] 记忆相关问题的快速修复（已完成）

### P1 - 近期优化
- [ ] 启用SessionContext进行会话存储
- [ ] 初始化时注册Skills
- [ ] 创建SharedContext实现上下文共享
- [ ] 实现Thinker向Talker请求澄清的机制

### P2 - 中期规划
- [ ] 对话摘要系统
- [ ] 改进Skill参数提取
- [ ] 添加用户ID支持
- [ ] LLM意图分类替代关键词匹配
- [ ] 任务暂停/恢复机制

### P3 - 长期规划
- [ ] 跨会话长期记忆
- [ ] 用户偏好学习
- [ ] 更多实用Skills
- [ ] 交互式确认机制

---

## 7. 测试验证

### 7.1 播报系统测试
```bash
# 运行交互模式
python main.py -i

# 测试复杂任务，观察播报频率和内容
# 预期：每2.5-4秒播报一次，内容不重复
```

### 7.2 记忆系统测试
```bash
# 测试对话记忆
1. 用户：我想买车
2. 用户：推荐几款SUV
3. 用户：我问过买车，你记得吗？
# 预期：系统应能回忆起买车话题
```

### 7.3 Skills测试
```bash
# 测试Skill调用
1. 用户：今天北京天气怎么样？
# 预期：调用WeatherSkill获取天气信息
```

### 7.4 边交互边澄清测试
```bash
# 测试澄清机制
1. 用户：帮我选一款SUV
# 预期：系统应该主动询问预算、用途等
2. 用户：20-30万，家用
# 预期：系统继续分析，带着新信息
```

### 7.5 全双工交互测试
```bash
# 测试任务打断
1. 用户：帮我分析下新能源车市场...
2. (等待几秒后) 用户：算了，直接推荐一款吧
# 预期：系统应识别为REPLACE意图，切换到推荐任务
```

---

## 8. 参考资料

- [LangGraph Platform - Streaming](https://www.langchain.com/langgraph)
- [豆包AI助手 2026深度解读](https://blog.csdn.net/yzx991013/article/details/158100867)
- [AI Agent思维可视化](https://juejin.cn/post/7583139562735501355)
- [CommonGround Thinking Indicator](https://github.com/Intelligent-Internet/CommonGround)
- [Spring AI Alibaba - Interleaved Output](https://juejin.cn/post/7583139562735501355)

---

## 9. 更新日志

### 2026-02-20
- 完成播报系统优化：独立时间检查、动态间隔、内容去重
- 完成记忆问题快速修复：检测记忆关键词、扩展历史范围
- 创建优化方案文档
- 规划Agent协作与上下文融合方案（SharedContext）
- 规划边交互边澄清机制
