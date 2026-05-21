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

## Status

Work in progress.
