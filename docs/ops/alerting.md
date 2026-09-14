# Operational alerting (F230)

## What it is

A **minimal, optional** alert webhook. When the environment variable
`ALERT_WEBHOOK_URL` is set, the app POSTs a small JSON payload to that URL on:

- **Enrollment task failure** — the pipeline's outer error handler
  (`app/services/enrollment_manager.py`, `_run_pipeline_impl`).
- **Stuck-task recovery** — the heartbeat sweeper marking a run failed after
  `STALE_RUN_TIMEOUT_MINUTES` without a heartbeat (same module,
  `sweep_stale_runs`; driven by the lifespan sweeper in `main.py`).

## Default behavior

**OFF.** If `ALERT_WEBHOOK_URL` is unset, `app/services/alerts.py` functions
are no-ops — no network, no logging, no behavior change.

## Payload

```json
{
  "source": "udemy-enroller",
  "event": "enrollment_failed",
  "message": "Enrollment run 12 (user 4) failed: ...",
  "timestamp": "2026-08-16T18:00:00+00:00Z",
  "run_id": 12,
  "user_id": 4
}
```

Errors are classified: `enrollment_failed` (pipeline exception) and
`enrollment_stuck` (heartbeat timeout).

## Guarantees / limitations

- **Best-effort delivery:** failures (non-2xx, timeouts, transport errors)
  are logged at WARNING and **never raised** — alerting can never break the
  enrollment pipeline.
- **No secrets:** the webhook URL is read from the environment and never
  logged; payloads contain run/user ids only.
- 5-second HTTP timeout.
- Intended for simple chat/notification bots (Slack/Discord webhooks,
  ntfy.sh, healthchecks.io-style sinks). Not a replacement for proper
  monitoring.

## Setup

```bash
# host .env (owner-only) or the container environment
ALERT_WEBHOOK_URL=https://hooks.example.in/your-webhook
```

No restart ordering required; the value is read on each alert (env change
takes effect immediately, no code reload needed).