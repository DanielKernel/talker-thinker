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

### 一键安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/your-repo/talker-thinker.git
cd talker-thinker

# 运行安装脚本（自动创建虚拟环境并安装依赖）
./setup.sh

# 激活虚拟环境
source .venv/bin/activate

# 配置 API 密钥
vim .env

# 运行交互模式
python main.py -i
```

### 手动安装

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖（国内用户使用清华镜像源）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# 配置 API 密钥
cp .env.example .env
vim .env
```

## 模型配置

默认使用火山引擎模型：

| 组件 | 模型 | 用途 |
|------|------|------|
| Talker | DeepSeek-V3.2 | 快速响应、意图分类 |
| Thinker | Kimi-K2-thinking | 深度推理、任务规划 |
| Base URL | https://ark.cn-beijing.volces.com/api/coding/v3 | API端点 |

在 `.env` 文件中配置：

```bash
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
VOLCES_API_KEY=your-api-key
TALKER_MODEL=DeepSeek-V3.2
THINKER_MODEL=Kimi-K2-thinking
```

## 运行

```bash
# 激活虚拟环境
source .venv/bin/activate

# 交互模式
python main.py -i

# 单次查询
python main.py -q "你好"

# 查看统计
python main.py --stats

# 退出虚拟环境
deactivate
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

## 项目结构

```
talker-thinker/
├── agents/                 # Agent模块
│   ├── talker/            # Talker Agent
│   ├── thinker/           # Thinker Agent
│   └── llm_client.py      # LLM客户端
├── orchestrator/          # 协调器
├── context/               # 上下文管理
├── skills/                # 技能系统
├── monitoring/            # 监控模块
├── config/                # 配置
├── tests/                 # 测试
├── main.py                # 主程序入口
├── setup.sh               # 一键安装脚本
├── requirements.txt       # 依赖列表
└── .env.example           # 环境变量模板
```

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

## 测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_agents.py -v

# 生成覆盖率报告
pytest --cov=. tests/
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

## 文档

详细设计文档请参阅：[docs/talker-thinker-collaboration-analysis.md](docs/talker-thinker-collaboration-analysis.md)

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！
