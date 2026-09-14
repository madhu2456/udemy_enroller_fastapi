# Alert webhook test-fire — owner runbook (A09 / F230)

**Status:** Owner-executes (no-claims lane) — recorded 2026-09-04. No agent
has fired a live alert; this doc + `scripts/test_fire_alert.py` are the
owner procedure.
**Audit basis:** `A09 alerting` (hygiene batch, v8.3-r2 registry) — the
A09/Logging-Monitoring gap for UE was F230 ("no external error alerting"),
already code-remediated (v7.18 delta: `ALERT_WEBHOOK_URL` optional error
notification, mock-tested). What was missing is a documented owner
test-fire; that gap is closed here.

## What exists (honest state)

- Wiring: `app/services/alerts.py` (`send_alert`, best-effort JSON POST,
  5s timeout, never raises, URL never logged). Call sites: enrollment
  failure + stuck-run sweeper (`app/services/enrollment_manager.py:128,499`).
- Config: `ALERT_WEBHOOK_URL` (`config/settings.py:154`, `.env.example:158`,
  default OFF/empty).
- Tests: `venv/bin/python -m pytest tests/test_alerts.py -q` (tail: `4 passed`)
  — unset no-op, JSON payload POST, non-2xx swallowed, transport-error
  swallowed.
- Ops doc: `docs/ops/alerting.md` (what/when/payload/limits).

## Safe test-fire (labeled TEST payload)

The script posts **one** alert with `event: "test_fire"`, `test: true`,
`"TEST alert — manual owner test-fire; safe to ignore"` — clearly labeled at
the sink, no enrollment data involved:

```bash
# 1. Point the env at your real sink (any ntfy.sh/Slack/Discord webhook):
ALERT_WEBHOOK_URL="https://your-sink/your-webhook" \
  venv/bin/python scripts/test_fire_alert.py
# Expect exit 0 + "posted with no delivery warning"

# 2. Verify at the sink: one message, event=test_fire, source=udemy-enroller,
#    test=true. If step 1 says "delivery WARNING", fix the URL/sink and retry.

# 3. Optional — raw curl equivalent (no repo code path, payload only):
curl -sS -X POST "https://your-sink/your-webhook" \
  -H 'Content-Type: application/json' \
  -d '{"source":"udemy-enroller","event":"test_fire","message":"TEST alert — manual owner test-fire; safe to ignore","timestamp":"2026-09-04T00:00:00Z","test":true}'
```

Script guarantees: unset `ALERT_WEBHOOK_URL` → prints the default-OFF no-op
and exits 0; delivery warning → exit 1 with the warning surfaced; the URL is
never printed. Syntax-checked via `python -m py_compile` + ruff (clean).

## Container caveat (owner action item — compose pass-through gap)

`docker-compose.yml` does **not** pass `ALERT_WEBHOOK_URL` to the web or
checker service (`environment:` lists have no entry; no `env_file:`), so a
host `.env` value alone does NOT reach the deployed app. To enable on the
server, the owner must add a pass-through line (mirroring the existing
`ALLOWED_HOSTS=${ALLOWED_HOSTS:-}` pattern) before the flip:

```yaml
# docker-compose.yml, both services' environment: lists
- ALERT_WEBHOOK_URL=${ALERT_WEBHOOK_URL:-}
```

then `docker compose up -d`. The web service is the only caller (enrollment
runs there); the checker loop does not call `send_alert` (verified by grep
2026-09-04). This compose edit is left to the owner (docker-compose.yml is
in another batch's in-flight set).

## Record the result

Note date + outcome in this doc's table when executed:

| Date | URL sink type | Result (exit 0/1, received at sink?) | Notes |
|---|---|---|---|
| — | — | not yet executed | owner-lane, no agent claims |
