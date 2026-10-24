# Five-minute interview walkthrough

1. Start API and worker; sign in as partner.a@example.test.
2. Describe the problem: a usable tool needs a UI, access boundaries, deployment, and an operational owner.
3. Run the sample dataset. Observe queued -> completed. Open the report: 6 rows, 2 missing cells, 1 duplicate.
4. Download the JSON report. Explain that successful execution differs from clean data quality.
5. Sign out; sign in as partner.b@example.test. The first partner's job is absent. Automated tests also verify direct URL/report/cancel denial.
6. Sign in as engineer@example.test to demonstrate intentional cross-organization support access.
7. Sign in as admin@example.test and inspect the audit log.
8. Explain the API/worker/database split and show the retry, lease recovery, and stale-worker tests.
9. Walk through Compose, Kubernetes reference manifests, CI, and the runbook. Be explicit about which environments you actually deployed and tested.

## Accurate project description

Built an independent partner tool portal with a FastAPI REST service, a responsive web interface, organization-scoped access, and a durable background CSV validation worker. Implemented integration tests for access isolation, job lifecycle, retries, and recovery; added container/deployment configuration and operational documentation.

Only add deployment claims after actually running that environment. This project began as a portfolio build in October 2026; do not present it as earlier paid client work or a Meta deployment.
