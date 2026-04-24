# Tanu Workspace

Tanu - your personal AI assistant that handles the boring stuff so you can focus.

## Config Location

**Edit config at:** `/home/mithil/Documents/Work/tanu/bujji/bujji/config.json`

## Quick Setup

1. Run Tanu:
   ```bash
   python main.py tanu --text
   ```

## OAuth Setup

### Gmail Setup
```bash
python main.py setup-gmail
```

### Google Calendar Setup
```bash
python -m bujji.tools.cal_auth --setup
```

---

## Tanu Commands

### Tasks
- "create a task to buy groceries"
- "show my tasks"
- "complete task [title]"

### Reminders
- "remind me at 3pm to call mom"
- "remind me in 30 minutes"
- "show reminders"

### Email
- "check my emails"
- "send email to John"
- "reply to that"
- "search emails from alice"
- "show my drafts"
- "schedule email for tomorrow 9am"
- "block sender spam@email.com"

### Calendar
- "what's on my calendar today"
- "show this week"
- "schedule coffee with bob tomorrow 2pm"
- "create team meeting next monday 10am"
- "find free slots this week"
- "check conflicts tomorrow 3pm"
- "move that meeting to friday"

### Quick
- "what time is it"
- "set timer for 10 minutes"
- "calculate 15% of 200"

---

## Gmail Features

### Reading
- `tanu_fetch_emails` - Check inbox
- `tanu_get_email` - Read specific email
- `tanu_search_emails` - Search with Gmail syntax
- `tanu_fetch_threads` - View conversation threads

### Sending
- `tanu_send_email` - Send (supports CC, BCC, HTML)
- `tanu_send_attachment` - Send with files
- `tanu_forward_email` - Forward message
- `tanu_schedule_email` - Schedule for later
- `tanu_list_scheduled` - View pending
- `tanu_cancel_scheduled` - Cancel scheduled

### Templates
- `tanu_save_template` - Save reusable template
- `tanu_list_templates` - List templates
- `tanu_use_template` - Send using template

### Organization
- `tanu_mark_email` - Mark read/unread
- `tanu_archive_email` - Archive
- `tanu_delete_email` - Trash
- `tanu_batch_archive` - Archive by search
- `tanu_batch_delete` - Delete by search
- `tanu_list_labels` - List labels
- `tanu_manage_labels` - Add/remove labels

### Quick Actions
- `tanu_quick_archive_reply` - Archive + reply
- `tanu_snooze_email` - Snooze for later
- `tanu_mark_done` - Archive + mark done

### Spam & Block
- `tanu_report_spam` - Mark as spam
- `tanu_block_sender` - Block sender
- `tanu_unblock_sender` - Unblock
- `tanu_list_blocked` - List blocked

### Smart
- `tanu_email_stats` - Email statistics
- `tanu_important_senders` - Most contacted
- `tanu_auto_categorize` - Suggest labels

---

## Calendar Features

### Views
- `tanu_today` - Today's schedule
- `tanu_week` - This week overview
- `tanu_agenda` - Upcoming events
- `tanu_next_event` - What's next

### Events
- `tanu_create_event` - Create with full details
- `tanu_quick_event` - Natural language creation
- `tanu_update_event` - Update event
- `tanu_delete_event` - Delete event
- `tanu_search_events` - Search events

### Smart
- `tanu_free_slots` - Find available time
- `tanu_conflicts` - Check conflicts
- `tanu_snooze_event` - Move event

### Natural Language Examples
```
"coffee with bob tomorrow 2pm"
"team meeting next monday 10am"
"quick sync friday 3pm for 30 min"
"block out 2pm-4pm tomorrow"
```

---

## Running Tanu

```bash
python main.py tanu          # Voice mode
python main.py tanu --text   # Text mode (for testing)
python main.py agent         # Terminal chat
python main.py serve         # Web UI (http://localhost:7337)
```

## Background Services

Tanu runs continuously:
- **Reminder worker**: Checks every 10 seconds, notifies via voice
- **Heartbeat**: Checks every 5 minutes for periodic tasks
- **Scheduler**: Sends scheduled emails when due

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
