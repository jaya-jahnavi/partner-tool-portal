# Architecture and decisions

## Identity and authorization

Users have a role and organization stored server-side. The browser cannot choose the organization for a submission. The API assigns it from the authenticated user. Partners can access any job in their own organization; engineers/admins can access all jobs. Direct detail, cancel, and report requests enforce the same rule. Inaccessible jobs return 404.

Passwords use salted scrypt. Cookies hold random opaque tokens; only token digests are stored. Sessions expire after 8 hours and logout deletes the server-side session. Mutations require a custom header and check browser Origin where present; no CORS is enabled. Public deployments must configure a fixed origin and secure cookies behind HTTPS.

Login throttling is per email (5 failures per 15-minute window). This is not a distributed abuse defense: an ingress/WAF should add IP and global limits. Demo seeding is an explicit command, never an automatic application startup behavior.

## Durable execution

API writes queued jobs to the relational database. Worker is a separate process; an API restart does not lose queued jobs. Workers conditionally update a candidate to running with a new token and lease. Only the successful claimant executes it.

Completed writes are fenced by worker token, running status, and lease deadline. A worker that dies is replaced after its 60-second lease expires. The third expired lease becomes a terminal failure. Exceptions retry at most three times. Cancellation changes state and removes the payload; stale workers cannot persist a report afterward.

This supports at-least-once execution with fenced result publication, not exactly-once processing. The validator is deterministic and side-effect-free. A future tool that sends messages or mutates external systems needs its own idempotency key and transactional-outbox design.

Inputs are bounded to 1 MB / 10,000 rows / 100 columns. These short deterministic jobs should finish within the lease. There is no hard execution timeout or lease heartbeat: unbounded or untrusted tools must run in resource-limited subprocesses or isolated job pods.

## Persistence and throughput

SQLite WAL is convenient for a single-machine demo. Compose uses MySQL. Bound SQL parameters prevent input from becoming SQL syntax. The SQL queue minimizes dependencies but is not intended for high throughput. Queue quotas are a best-effort count check; simultaneous requests may exceed 20. Production requires transactional per-organization quota accounting.

Raw uploaded content is deleted on terminal status. Derived reports remain in DB. DB backups can retain deleted payloads, so production retention must include backups. No blob-store storage or report expiration is implemented.

## Extension

A new tool should have a bounded input contract, version, explicit permission policy, deterministic outputs where possible, tests for failure/retry semantics, and an operator runbook. Add migrations before evolving deployed schemas; current startup DDL creates missing tables only.
