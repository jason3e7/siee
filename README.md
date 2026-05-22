# SIEE — Secret Isolation Execution Environment

> **No more copy-pasting — AI agents iterate autonomously, without ever seeing your secrets.**

A lightweight local server that lets AI agents deploy and execute code against real API secrets — without ever exposing those secrets to the agent.

## Concept

The AI agent writes code and sends it to SIEE. SIEE executes it in an environment where secrets are available as environment variables. The agent only receives stdout/stderr — never the secret values.

```
AI Agent                    SIEE Server
  │                              │
  │── POST /deploy ─────────────▶│  (upload code)
  │── POST /exec ───────────────▶│  (run with injected secrets)
  │◀─ GET  /logs/{id} ──────────│  (stdout/stderr only)
```

The agent can write `os.environ['API_TOKEN']` in its code and the test will work — but the actual token value never appears in the agent's context window.

### No more copy-pasting

The traditional workflow requires you to manually copy secrets into your environment, paste test outputs back into the chat, and switch context between your terminal and the AI conversation. SIEE eliminates this entirely:

- **No copying secrets**: the AI never needs to know the token value — it just writes code that reads from `os.environ`
- **No pasting results**: the AI calls `get_log` to retrieve stdout/stderr directly, without you lifting a finger
- **Fully automated loop**: deploy → exec → get_log is a tight feedback loop the AI drives end-to-end

This is the key motivation behind SIEE: not just secret isolation, but enabling a fully automated development workflow where the AI can iterate on real API integration without human intervention between steps.

## Design Philosophy

This follows the same philosophy as **GitHub Actions Secrets**:

> Code can *use* a secret. The developer (or AI) never *sees* the secret value.

In GitHub Actions, you define secrets in the repository settings. Your workflow can reference `${{ secrets.MY_TOKEN }}`, and the runner injects it at execution time. The secret never appears in logs — GitHub actively masks it. Developers write the workflow without knowing the secret value.

SIEE applies the same model to AI-assisted development:

| | GitHub Actions | SIEE |
|---|---|---|
| Who writes the code | Developer | AI Agent |
| Where secrets live | GitHub repository settings | SIEE server environment variables |
| How secrets are injected | Runner environment | Subprocess environment |
| What the author sees | Workflow result (pass/fail) | stdout / stderr |
| Can the author read the secret? | No | No |

## Threat Model

SIEE is designed to prevent **passive secret leakage** — the scenario where a secret accidentally enters the AI agent's context:

- An `.env` file read into the conversation
- A config file containing a token included as context
- A secret pasted directly into the chat

By keeping secrets exclusively on the SIEE server, they are structurally absent from the AI's context window regardless of what the agent reads or generates.

SIEE does **not** prevent an AI agent from deliberately writing code to print secret values. It is a trust boundary for passive isolation, not a sandbox against adversarial agents.

## Use Case

You are building a project that integrates with external APIs. You use an AI agent (e.g. Claude Code) to write and iterate on the code. The API tokens required for real integration tests should never appear in the conversation — but the tests still need to run against the real API.

SIEE sits between the agent and the execution environment, holding the secrets and returning only results. The agent can autonomously iterate — deploy a fix, run the tests, read the output, deploy another fix — without you needing to paste anything or intervene between steps.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/jason3e7/siee.git
cd siee
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your secrets

Secrets are just environment variables on the SIEE machine. Set them before starting the server:

```bash
export MY_API_KEY="sk-real-token-here"
export DATABASE_URL="postgres://..."
```

Or put them in a `.env` file and load it:

```bash
export $(cat .env | xargs)
```

### 3. Configure allowed commands

Edit `ALLOWED_COMMANDS` at the top of `server.py` to control what the AI agent is permitted to run:

```python
ALLOWED_COMMANDS = {
    "pytest": [sys.executable, "-m", "pytest"],
    "run":    [sys.executable, "main.py"],
}
```

### 4. Start the servers

```bash
# Terminal 1 — REST API (port 5000)
python server.py

# Terminal 2 — MCP server for AI agents (port 5001)
python mcp_server.py
```

To enable verbose logging:

```bash
DEBUG=1 python server.py
DEBUG=1 python mcp_server.py
```

### 5. Connect an AI agent

On the AI agent's machine, add to `~/.claude/settings.json` or `.claude/settings.json`:

```json
{
  "mcpServers": {
    "siee": {
      "type": "sse",
      "url": "http://<SIEE_HOST>:5001/sse"
    }
  }
}
```

Restart Claude Code. The agent will have access to three tools:

| Tool | Description |
|------|-------------|
| `deploy` | Upload files to the execution environment |
| `exec_command` | Run a whitelisted command, returns `exec_id` |
| `get_log` | Poll execution status and stdout/stderr |

### 6. Run tests

```bash
pytest tests/ -v
```

## Status

Work in progress.
