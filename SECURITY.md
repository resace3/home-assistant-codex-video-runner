# Security policy

Report vulnerabilities privately through GitHub Security Advisories. Do not open a public issue containing tokens, entity IDs, state values, videos, prompts, private URLs, logs, or screenshots.

Supported versions: the latest release. Security release blockers include token leakage, arbitrary file access, unbounded external cost, raw-state egress, incomplete artifact publication, and secret-bearing public artifacts.

Before every push and release run full-history and working-tree Gitleaks scans. The `SUPERVISOR_TOKEN` must remain in the collector's in-memory HTTP client. Provider credentials remain runtime environment values. Logs are redacted and public CI uses synthetic inputs only.

