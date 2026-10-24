# Release checklist

- Run python -m unittest discover -s tests -v and node --check app/static/app.js.
- Build the Docker image and run the same functional workflow against MySQL.
- Verify partner isolation, report download, cancellation, and restart recovery.
- Confirm no .env, .local, credentials, client files, or personal resume content are tracked.
- Review dependency updates and image vulnerabilities.
- Tag the image with the Git commit; avoid mutable production tags.
- Set a fixed HTTPS origin, secure cookies, SSO, ingress limits, and managed secrets for external deployment.
- Verify backup restoration, retention policy, alerts, rollback, and support ownership.
- Record environment, commit, test results, and known limits.

## Authoring verification

12 automated unittest cases passed locally against SQLite and a real loopback HTTP server. JavaScript syntax check passed. Browser smoke testing covers partner sign-in, sample submission, and report review. Docker engine was not running; MySQL/container/Kubernetes execution is pending. GitHub Actions is configuration until a remote run succeeds.
