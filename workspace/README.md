# Tanu Workspace

This directory contains Tanu's local identity, memory, task, reminder, skill,
and integration data. Runtime files may contain personal information and are
ignored by Git.

## Start Tanu

```bash
python3 main.py onboard       # Configure an LLM provider
python3 main.py agent         # Terminal chat without audio
python3 main.py tanu --text   # Text assistant mode
python3 main.py tanu          # Voice assistant mode
python3 main.py desk          # Godot desktop client + local server
```

## Included capabilities

- Workspace-scoped file and shell tools
- Tasks, reminders, timers, calculations, and web search
- Optional Gmail read/search/send tools
- User memory in `USER.md` and agent notes in `MEMORY.md`
- Custom skills in `skills/<name>/SKILL.md`

## Privacy

Keep API keys in `~/.tanu/config.json`, not in this directory. Do not commit
generated `USER.md`, backups, lock files, OAuth tokens, reminder data, or task
data. Leave `restrict_to_workspace` enabled unless broader filesystem access is
intentional.
