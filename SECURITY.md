# Security Policy

Tanu can read files, run shell commands, and connect to third-party services.
Keep `restrict_to_workspace` enabled unless broader access is intentional, and
review tool calls before using Tanu with untrusted prompts or content.

The API binds to `127.0.0.1` by default and rejects non-local browser origins.
Do not expose port 7337 to a public network without adding authentication and
TLS in front of it.

Please report vulnerabilities privately through GitHub's security advisory
feature rather than opening a public issue. Do not include real API keys,
OAuth tokens, personal workspace files, or other secrets in reports.
