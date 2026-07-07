# Agent Testing with Promptfoo

End-to-end evaluation and red-team testing for the Azure AI Foundry harness agent using [promptfoo](https://github.com/promptfoo/promptfoo).

## Prerequisites

```bash
# Install promptfoo (Node ≥ 18 required)
npm install -g promptfoo

# Ensure your .env is populated (see ../.env.example)
# The provider.py shim reads HarnessConfig from environment variables.
```

## Directory Structure

```
tests/
├── promptfoo.yaml          # Root config — runs smoke + skills + tool_use + multi_turn
├── provider.py             # Python provider shim wrapping AgentRunner
├── suites/
│   ├── smoke.yaml          # Basic connectivity & sanity (4 tests)
│   ├── skills.yaml         # Skill dispatch correctness (6 tests)
│   ├── tool_use.yaml       # Web search & MCP invocation (6 tests)
│   ├── multi_turn.yaml     # Conversation continuity (6 tests across 3 sessions)
│   └── redteam.yaml        # Safety / adversarial probing (red team plugins)
├── fixtures/
│   └── sample_code.py      # Intentionally buggy Python for code-review tests
└── results/
    └── latest.json         # Written after each eval run (gitignored)
```

## Running Evaluations

### Full eval (all suites)
```bash
cd /path/to/azure-ai-foundry
npx promptfoo eval -c tests/promptfoo.yaml
```

### Single suite
```bash
npx promptfoo eval -c tests/suites/smoke.yaml
npx promptfoo eval -c tests/suites/skills.yaml
npx promptfoo eval -c tests/suites/tool_use.yaml
npx promptfoo eval -c tests/suites/multi_turn.yaml
```

### Open results in browser
```bash
npx promptfoo view
```

### Red team (separate command, hits live agent)
```bash
npx promptfoo redteam run -c tests/suites/redteam.yaml
```

> ⚠️ The red team run generates adversarial prompts via promptfoo's plugin system and sends them to the live Foundry agent. Each plugin generates 5–10 probes. `maxConcurrency: 1` is set to keep token usage predictable.

## Test Suites

| Suite | # Tests | Purpose | Typical Duration |
|---|---|---|---|
| `smoke` | 4 | Is the agent alive and coherent? | ~2 min |
| `skills` | 6 | Does it dispatch the right skill? | ~5 min |
| `tool_use` | 6 | Does it invoke web search / MCP? | ~8 min |
| `multi_turn` | 6 | Does it maintain conversation context? | ~6 min |
| `redteam` | ~80 (auto) | Safety and adversarial robustness | ~30–60 min |

## Multi-Turn Design

The provider shim ([`provider.py`](./provider.py)) maintains a `_sessions` dict that maps a `session_id` var to a Foundry `conversation_id`. Tests that share the same `session_id` are routed to the **same Foundry conversation**, enabling true multi-turn context.

```yaml
# Turn 1 — starts a new conversation
- vars:
    session_id: "my-session"
    message: "My name is Alice."

# Turn 2 — continues the same conversation
- vars:
    session_id: "my-session"
    message: "What is my name?"
```

Because promptfoo runs tests sequentially (`maxConcurrency: 1`), the turns execute in order.

## Assertion Types Used

| Type | What it checks |
|---|---|
| `not-empty` | Response is non-blank |
| `contains` | Literal substring present |
| `not-contains` | Literal substring absent |
| `equals` | Exact match |
| `javascript` | Custom JS expression on `output` |
| `llm-rubric` | LLM judge evaluates the response against a rubric |

## Pass Criteria

- **Smoke**: 100% pass required — if any smoke test fails, the agent is down.
- **Skills / Tool Use / Multi-Turn**: ≥ 80% pass expected.
- **Red Team**: Review findings report; 0 critical failures (agent must not leak secrets, execute unauthorized actions, or generate harmful content).

## Adding New Tests

1. Add cases to an existing suite YAML, or create a new `tests/suites/<name>.yaml`.
2. For new suites, add the path to the `import:` list in `promptfoo.yaml`.
3. Use `llm-rubric` for open-ended responses and `contains` / `equals` for deterministic ones.
