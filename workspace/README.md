# Tanu Workspace

## Config Location

**Edit config at:** `/home/mithil/Documents/Work/tanu/bujji/bujji/config.json`

| File | Purpose |
|------|---------|
| `config.json` | LLM providers, API keys, channels, email |
| `tanu.json` | Voice settings, reminders, tasks |

## Quick Setup

1. Run Tanu:
   ```bash
   python main.py tanu --text
   ```

## Gmail Setup

**One command:**
```bash
python main.py setup-gmail
```

## Tanu Commands

### Tasks
- "create a task to buy groceries"
- "show my tasks"
- "complete task [title]"

### Reminders
- "remind me at 3pm to call mom"
- "remind me in 30 minutes"
- "show reminders"

### Email (after Gmail setup)
- "check my emails"
- "send email to John"
- "reply to that"

### Quick
- "what time is it"
- "set timer for 10 minutes"
- "calculate 15% of 200"

## Running Tanu

```bash
python main.py tanu          # Voice mode
python main.py tanu --text   # Text mode (for testing)
```

## Background Services

Tanu runs continuously:
- **Reminder worker**: Checks every 10 seconds, notifies via voice
- **Heartbeat**: Checks every 5 minutes for periodic tasks

## Identity Files

| File | Purpose |
|------|---------|
| `SOUL.md` | Tanu's purpose and beliefs |
| `IDENTITY.md` | Tanu's personality |
| `AGENT.md` | How Tanu responds |
| `USER.md` | About you (Mithil) |
| `BACKSTORY.md` | Tanu's origin |
| `HEARTBEAT.md` | Periodic tasks |

Edit these to customize Tanu.
