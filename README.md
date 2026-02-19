# Talker-Thinker: 双Agent协同架构

一个基于最新研究的Talker-Thinker双Agent架构实现，支持实时响应与深度推理的协同工作。

## 核心特性

- **Talker Agent**: 快速响应（<500ms）、简单意图闭环、实时反馈
- **Thinker Agent**: 深度推理、任务规划、自我反思
- **Orchestrator**: 智能任务调度、Handoff管理、上下文同步
- **分层上下文**: L1-L4四层上下文管理（内存/Redis/PostgreSQL/向量数据库）
- **Skills系统**: 可扩展的技能引擎，支持动态加载
- **监控告警**: 完善的指标收集、日志记录和告警机制

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         用户交互层                           │
└────────────────────────────┬────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Orchestrator   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
 ┌──────▼──────┐      ┌─────▼──────┐      ┌─────▼──────┐
 │   Talker    │      │  Thinker   │      │   Skills   │
 │   Agent     │      │   Agent    │      │   Engine   │
 └─────────────┘      └────────────┘      └────────────┘
                             │
                    ┌────────▼────────┐
                    │ Context Store   │
                    │  (L1-L4)        │
                    └─────────────────┘
```

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/talker-thinker.git
cd talker-thinker

# 安装依赖
pip install -r requirements.txt

# 或使用 pip 安装
pip install -e .
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的API密钥
```

默认使用火山引擎模型：
- **Talker模型**: DeepSeek-V3.2（快速响应）
- **Thinker模型**: Kimi-K2-thinking（深度推理）
- **Base URL**: https://ark.cn-beijing.volces.com/api/coding/v3

### 运行

```bash
# 交互模式
python main.py -i

# 单次查询
python main.py -q "你好"

# 查看统计
python main.py --stats
```

## 使用示例

```python
import asyncio
from orchestrator.coordinator import Orchestrator

async def main():
    # 创建协调器
    orchestrator = Orchestrator()

    # 处理用户输入
    async for chunk in orchestrator.process("请分析量子计算的发展前景"):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

## 核心概念

### Talker Agent

负责快速响应用户：
- 意图分类（简单/中等/复杂）
- 简单问题直接回答
- 复杂问题转交Thinker
- 播报Thinker的进度

### Thinker Agent

负责深度推理：
- 任务规划和拆解
- 逐步执行
- 自我反思和质量控制
- 生成详细答案

### Handoff模式

支持四种Agent间交接模式：
1. **委托模式(Delegation)**: Talker委托给Thinker
2. **并行模式(Parallel)**: 两个Agent同时工作
3. **迭代模式(Iterative)**: 根据用户反馈迭代改进
4. **协作模式(Collaboration)**: Talker收集信息，Thinker处理

### 分层上下文

- **L1 Working Context**: 内存，当前轮次，<1ms
- **L2 Session Context**: Redis，会话历史，24小时TTL
- **L3 Long-term Memory**: PostgreSQL，用户档案，永久
- **L4 Knowledge Base**: 向量数据库，RAG检索

## 扩展开发

### 添加新Skill

```python
from skills.base import Skill, SkillResult

class MySkill(Skill):
    @property
    def name(self) -> str:
        return "my_skill"

    @property
    def description(self) -> str:
        return "My custom skill"

    async def execute(self, params, context=None) -> SkillResult:
        self._start_timer()
        # 实现你的逻辑
        return self._create_success_result(
            data={"result": "..."},
            formatted="处理完成",
        )
```

### 自定义LLM后端

```python
from agents.llm_client import LLMClient

class MyLLMClient(LLMClient):
    async def generate(self, prompt, max_tokens=1000, **kwargs) -> str:
        # 实现你的LLM调用逻辑
        pass
```

## 部署

### Docker

```bash
docker-compose up -d
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

## 监控

系统内置Prometheus指标暴露：

```python
from monitoring.metrics import get_metrics_collector

metrics = get_metrics_collector()
print(metrics.export_prometheus())
```

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_agents.py -v

# 生成覆盖率报告
pytest --cov=. tests/
```

## 文档

详细设计文档请参阅：[docs/talker-thinker-collaboration-analysis.md](docs/talker-thinker-collaboration-analysis.md)

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！
