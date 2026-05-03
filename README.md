# AI Code Review Agent

A multi-agent system that automatically analyzes GitHub repositories and creates Jira tickets for discovered issues.

## What it does

1. **Phase 1** — Explores repository structure and architecture
2. **Phase 2** — Identifies code quality issues (security, error handling, test coverage)
3. **Phase 3** — Creates real Jira tickets for each finding

## Architecture

Coordinator Agent
├── Subagent 1: Repository structure analysis
├── Subagent 2: Code quality review
└── Subagent 3: Jira ticket generation

## Key concepts implemented

- **Scratchpad files** — persists findings outside conversation context
- **Subagent delegation** — context isolation for each analysis phase
- **State manifest** — crash recovery with JSON state persistence
- **Summary injection** — phase findings passed between subagents

## Tech stack

- Python 3.12
- Anthropic Claude API (claude-haiku)
- Jira MCP Server (custom SSE transport)
- httpx

## Setup

```bash
# Install dependencies
pip install anthropic httpx

# Set API key
export ANTHROPIC_API_KEY=your_key

# Start Jira MCP server (separate terminal)
cd ../jira-mcp
python mcp_server_sse.py

# Run the agent
python agent.py
```

## Output

- `scratchpad.md` — all findings from each phase
- `manifest.json` — session state for crash recovery
- Jira tickets created automatically in your project

## Related

- [jira-mcp](https://github.com/Valik1602/jira-mcp) — Custom Jira MCP server with 8 tools