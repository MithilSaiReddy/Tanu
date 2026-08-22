# AI Agent Changes

Date: 2026-08-22
Branch: `codex/product-readiness`

## Reliability

- Added the missing `agent` terminal-chat command to both CLI entry points.
- Fixed the reminder worker import and consistent resolution of relative workspace paths.
- Fixed setup to create the configuration at the path the app actually reads: `~/.tanu/config.json`.
- Made Python detection portable on macOS/Linux and made `GODOT=/path/to/godot` work in `build.sh`.
- Simplified the all-integrations requirements file and included package assets in builds.

## Security and privacy

- Stopped the status command and HTTP config endpoints from exposing API keys, OAuth credentials, or tokens.
- Rejected non-local browser origins and limited API request bodies to 1 MiB.
- Blocked skill-name path traversal in create, update, and delete endpoints.
- Enabled workspace restriction by default for file and shell tools.
- Removed tracked personal memory backups, lock files, and runtime cron data; added ignore rules for them.
- Added `SECURITY.md` with safe deployment and vulnerability-reporting guidance.

## Open-source and distribution readiness

- Added the missing MIT `LICENSE` file and corrected package metadata.
- Removed a duplicate Piper voice model and updated the fallback path, reducing the packaged working tree by about 63 MB without removing voice support.
- Corrected setup, command, API, and workspace documentation that no longer matched the implementation.
- Added dependency-free security unit tests and a GitHub Actions workflow for Python 3.9/3.12 syntax, tests, and shell-script validation.

## Validation performed

- All Python sources parsed successfully.
- All 5 unit tests passed.
- Bash syntax validation passed for setup, build, and launch scripts.
- The installed-package CLI help loaded successfully without bytecode/build artifacts.
- `git diff --check` passed.

Full voice, Godot export, Gmail OAuth, and live LLM calls require their external binaries, credentials, and services and were not run during this lightweight local audit.
