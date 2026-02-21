# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Talker-Thinker is a dual-agent architecture for real-time AI interactions that balances fast response times with deep reasoning capabilities:

- **Talker Agent**: Fast responses (<500ms), simple intent resolution, real-time feedback
- **Thinker Agent**: Deep reasoning, task planning, self-reflection
- **Orchestrator**: Manages task scheduling, handoff between agents, context synchronization

## Commands

### Setup
```bash
# One-click installation
./setup.sh

# Activate virtual environment
source .venv/bin/activate
```

### Running
```bash
# Interactive mode (full-duplex communication)
python main.py -i

# Single query mode
python main.py -q "Your query here"

# View statistics
python main.py --stats
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_agents.py -v

# With coverage
pytest --cov=. tests/
```

### Code Quality
```bash
# Format code
black --line-length 100 .
isort .

# Lint
ruff check .

# Type checking
mypy .
```

### Docker Deployment
```bash
docker-compose up -d
```

## Architecture

### Core Modules

```
talker-thinker/
├── agents/
│   ├── talker/           # Fast response agent (<500ms)
│   ├── thinker/          # Deep reasoning agent
│   └── llm_client.py     # Unified LLM interface
├── orchestrator/
│   ├── coordinator.py    # Central orchestration, handoff management
│   └── scheduler.py      # Task scheduling (complexity-based)
├── context/
│   ├── session_context.py    # L2: Redis-backed session storage
│   ├── shared_context.py     # Talker-Thinker shared state
│   └── summarizer.py         # Conversation summarization
├── skills/
│   ├── engine.py         # Skill registration and discovery
│   ├── invoker.py        # Skill execution with retry/caching
│   └── base.py           # Skill base class
├── monitoring/
│   ├── metrics.py        # Prometheus metrics
│   └── logging.py        # Structured logging
└── config/
    └── settings.py       # Pydantic-based configuration
```

### Handoff Patterns

The orchestrator implements four collaboration patterns:

1. **Delegation**: Talker delegates complex tasks to Thinker
2. **Parallel**: Both agents work simultaneously
3. **Iterative**: Feedback-driven refinement cycles
4. **Collaboration**: Talker collects info, Thinker processes, Talker broadcasts progress

### Context Layers

- **L1 Working Context**: In-memory, current turn, <1ms access
- **L2 Session Context**: Redis-backed, 24-hour TTL
- **L3 Long-term Memory**: PostgreSQL, user profiles
- **L4 Knowledge Base**: Vector DB for RAG retrieval

## Key Configuration

Environment variables (`.env`):

```bash
# Default: Volces (Volcano Engine) API
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
VOLCES_API_KEY=your-api-key
TALKER_MODEL=DeepSeek-V3.2
THINKER_MODEL=Kimi-K2-thinking
```

## Development Notes

- Python 3.11+ required
- Uses `pydantic-settings` for configuration management
- Async-first codebase (asyncio)
- Skills are registered dynamically in `orchestrator/coordinator.py:_initialize_default_skills`
- Progress broadcasting uses dynamic interval calculation (4s → 6s → 8s based on elapsed time)
