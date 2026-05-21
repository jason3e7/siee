# SIEE — Secret Isolation Execution Environment

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

SIEE sits between the agent and the execution environment, holding the secrets and returning only results.

## Status

Work in progress.
