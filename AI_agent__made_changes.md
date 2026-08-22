# AI Agent Changes

Date: 2026-08-22
Target branch: `checking-branch` (`main` is intentionally untouched)

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
- The initial 5 unit tests passed.
- Bash syntax validation passed for setup, build, and launch scripts.
- The installed-package CLI help loaded successfully without bytecode/build artifacts.
- `git diff --check` passed.

Full voice, Godot export, Gmail OAuth, and live LLM calls require their external binaries, credentials, and services and were not run during this lightweight local audit.

## Local runtime and latency update

- Bumped the package version to 2.1.0 for the runtime architecture update.
- Added a bounded in-process `LocalEventBus` for agent, tool, skill, session, and runtime communication without an external broker.
- Added `publish_event` and `read_events` tools plus a local `/api/events` diagnostics endpoint.
- Added a process-tree memory budget with a 600 MB soft limit, 800 MB hard limit, garbage-collection pressure handling, and a desktop watchdog that shuts down safely at the hard limit.
- Bounded warm sessions, conversation history, event history/payloads, streaming queues, voice queues, parallel tool workers, tool output, sub-agent iterations, LLM output, and retry counts.
- Made online Gmail/web tools and memory-heavier sub-agents opt-in, reducing the default LLM tool schema and keeping the standard runtime local except for its configured LLM.
- Shared the event bus and memory budget with sub-agents and refused expensive sub-agent/tool work during memory pressure.
- Moved Moonshine transcription out of the microphone callback, reduced default endpoint silence from 600 ms to 350 ms, and bounded pending utterances.
- Streamed Piper audio chunks directly to the output device and removed duplicated end-of-response speech queuing.
- Enabled streaming for final LLM responses after tool calls.
- Bounded skill loading plus file, directory, and shell-command output before it enters memory; shortened interactive LLM connection/retry limits.
- Fixed web search returning an empty result despite successful search results.
- Added runtime, event-bus, memory-pressure, and voice-buffer unit tests and replaced outdated architecture/data-flow documentation.

Validation after this update: 15 unit tests passed, all 45 Python files parsed,
shell syntax checks passed, runtime integration passed with network/sub-agent
tools disabled by default, and `git diff --check` passed.
