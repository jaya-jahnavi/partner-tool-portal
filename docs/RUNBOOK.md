# Operator runbook

## Service checks

- GET /health/live checks the API process.
- GET /health/ready checks database connectivity.
- GET /api/metrics as an engineer/admin returns job counts by state.
- Worker stdout contains job IDs and processing errors; no raw CSV is logged.
- Dashboard polling is every 3 seconds while the page is visible.

## Jobs remain queued

1. Confirm the worker process is running (local: python -m app.worker; Compose: docker compose logs worker).
2. Confirm API and worker point to the same database / PORTAL_DATA.
3. Check database connectivity and worker_poll_failed logs.
4. Restart the worker after correcting configuration. Queued jobs are durable.

## Jobs remain running

Wait for the 60-second lease. A healthy replacement worker reclaims it. At 3 exhausted attempts it fails permanently. Check worker exceptions before retrying manually by submitting a new job. Do not modify state rows while a worker is operating.

## API unavailable

Check readiness and DB connectivity. In Compose, inspect docker compose ps and docker compose logs api db. Restart the API after correcting the cause. Worker execution is independent.

## Report findings

A completed job with needs_attention is not an infrastructure incident. Inspect missing and duplicate counts, correct the CSV, and submit a new run. The original report remains available.

## Access problem

Check the user's server-side role/org. Partners cannot see another organization; engineers/admins intentionally can. /api/audit is administrator-only. Do not bypass checks or expose the database to a partner.

## Deployment and rollback

Use an immutable image tag. Verify tests and health endpoints before directing traffic. Keep the preceding tag available. Roll back API and worker together; ensure schema compatibility first. Startup DDL is not a migration framework.

## Suggested production alerting (not provisioned)

Queue age > 2 minutes, oldest running age > 90 seconds, sustained processing failures, DB connectivity failures, unexpected 401/403 spikes, and HTTP 5xx. Add a worker heartbeat and external monitoring before relying on unattended operation.

## Support handoff

Record impact, affected organization, job IDs, UTC timestamps, actions, owner, next update time, and resolution. Use documented China/US coverage windows agreed with the team; this repository does not imply any real on-call coverage.
