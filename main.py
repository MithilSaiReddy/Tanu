#!/usr/bin/env python3
"""
main.py — bujji CLI entry point

Usage:
    python main.py onboard              # First-time setup wizard
    python main.py serve                # Web UI → http://localhost:7337
    python main.py agent -m "..."       # Single message
    python main.py agent                # Interactive chat
    python main.py new-tool <name>      # Scaffold a new tool file
    python main.py setup-telegram       # Configure Telegram bot
    python main.py gateway              # Start messaging gateway
    python main.py status               # Show config and status

Requirements:
    pip install requests                # Always needed
    pip install discord.py              # Optional: Discord gateway
"""

import os
import sys
from pathlib import Path

# Fix: ensure bujji package is in path when running from repo root
_script_dir = os.path.dirname(os.path.abspath(__file__))
_bujji_path = os.path.join(_script_dir, "bujji")
if os.path.isdir(_bujji_path) and _bujji_path not in sys.path:
    sys.path.insert(0, _bujji_path)

import argparse
import textwrap
import threading
import time

from bujji import LOGO, __version__
from bujji.config import (
    CONFIG_FILE,
    POPULAR_MODELS,
    PROVIDER_DEFAULTS,
    WORKSPACE_DEFAULT,
    get_active_provider,
    load_config,
    save_config,
    workspace_path,
)
from bujji.session import SessionManager


# ─────────────────────────────────────────────────────────────────────────────
#  ONBOARD
# ─────────────────────────────────────────────────────────────────────────────


def cmd_onboard(args) -> None:
    print(f"\n{LOGO} Welcome to bujji v{__version__}\n")
    cfg = load_config()
    provider_list = list(PROVIDER_DEFAULTS.keys())

    print("Available LLM providers:")
    for i, (p, (_, model)) in enumerate(PROVIDER_DEFAULTS.items(), 1):
        print(f"  {i:2}. {p:<12}  default model: {model}")

    print("""
  Get API keys:
    openrouter → https://openrouter.ai/keys            (all models, free tier)
    openai     → https://platform.openai.com/api-keys
    anthropic  → https://console.anthropic.com/settings/keys
    groq       → https://console.groq.com/keys         (free & fast)
    google     → https://aistudio.google.com/app/apikey   (Gemini, free tier)
    ollama     → (no key needed — runs locally)
""")

    choice = input("Choose provider number (Enter = openrouter): ").strip()
    provider = (
        provider_list[int(choice) - 1]
        if choice.isdigit() and 1 <= int(choice) <= len(provider_list)
        else "openrouter"
    )
    print(f"\nSelected: {provider}")

    api_key = input(f"Enter your {provider} API key: ").strip()
    if provider == "ollama":
        api_key = api_key or "ollama"

    default_base, default_model = PROVIDER_DEFAULTS[provider]

    if provider in POPULAR_MODELS:
        print(f"\n  Popular {provider} models:")
        for m in POPULAR_MODELS[provider]:
            marker = "  ← default" if m == default_model else ""
            print(f"    • {m}{marker}")

    model = input(f"\nModel name (Enter = {default_model}): ").strip() or default_model

    cfg["providers"][provider] = {"api_key": api_key, "api_base": default_base}
    cfg["agents"]["defaults"]["model"] = model

    print("\n[Optional] Brave Search API key (https://brave.com/search/api)")
    print("           Free tier: 2,000 queries/month")
    brave = input("Brave API key (Enter to skip): ").strip()
    if brave:
        cfg["tools"]["web"]["search"]["api_key"] = brave

    ws = input(f"\nWorkspace directory (Enter = {WORKSPACE_DEFAULT}): ").strip()
    if ws:
        cfg["agents"]["defaults"]["workspace"] = ws

    # Telegram
    print("\n" + "─" * 52)
    print("  TELEGRAM SETUP  (optional — can be done later)")
    print("─" * 52)
    if input("Set up Telegram now? (y/N): ").strip().lower() == "y":
        from bujji.connections.telegram import setup_telegram_interactive

        setup_telegram_interactive(cfg)
    else:
        print("  [Skipped]  Run later:  python main.py setup-telegram")

    save_config(cfg)
    import pathlib

    ws_path = pathlib.Path(cfg["agents"]["defaults"]["workspace"]).expanduser()
    ws_path.mkdir(parents=True, exist_ok=True)
    (ws_path / "skills").mkdir(exist_ok=True)
    (ws_path / "cron").mkdir(exist_ok=True)

    print(f"\n✅ Config:    {CONFIG_FILE}")
    print(f"✅ Workspace: {ws_path}")
    print(f"\n💡 Tip: Open the web UI for a nicer experience:")
    print(f"   python main.py serve\n")


# ─────────────────────────────────────────────────────────────────────────────
#  SERVE  (web UI)
# ─────────────────────────────────────────────────────────────────────────────


def cmd_serve(args) -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("ERROR: pip install requests")

    cfg = load_config()
    port = getattr(args, "port", 5168) or 5168
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"

    from bujji.server import run_server

    run_server(cfg, host=host, port=port)


# ─────────────────────────────────────────────────────────────────────────────
#  NEW-TOOL  — scaffold a new tool file
# ─────────────────────────────────────────────────────────────────────────────

# Auth pattern templates
_AUTH_PATTERNS = {
    "bearer": '"Authorization": "Bearer " + _ctx.cred("{svc}.api_key")',
    "token": '"Authorization": "token " + _ctx.cred("{svc}.api_key")',
    "x-api": '"X-API-Key": _ctx.cred("{svc}.api_key")',
    "param": '# Pass key as a query param:  params={{"apikey": _ctx.cred("{svc}.api_key")}}',
    "none": "# No auth needed",
}

_TOOL_TEMPLATE = '''\
"""
bujji/tools/{filename}.py

{service_title} tools for bujji.

Setup
─────
1. Get your API key from: {api_url}
2. Add to ~/.bujji/config.json:
       "tools": {{
         "{svc}": {{
           "api_key": "your-key-here"
         }}
       }}
3. Save this file — bujji hot-reloads it instantly. No restart needed.

Tools
─────
{tool_list}
"""
from __future__ import annotations

from bujji.tools.base import HttpClient, ToolContext, param, register_tool


# ── Shared API client ─────────────────────────────────────────────────────────

def _{svc}_client(_ctx: ToolContext) -> HttpClient:
    return HttpClient(
        base_url = "{base_url}",
        headers  = {{
            {auth_header},
            "Content-Type": "application/json",
        }},
    )


# ─────────────────────────────────────────────────────────────────────────────
#  TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@register_tool(
    description=(
        "TODO: describe what this tool does and when the agent should use it. "
        "Be specific — the LLM uses this description to decide when to call it."
    ),
    params=[
        param("query", "Search query or input"),
        param("limit", "Max results to return", type="integer", default=10),
    ]
)
def {first_tool}(query: str, limit: int = 10, _ctx: ToolContext = None) -> str:
    client  = _{svc}_client(_ctx)
    results = client.get("/TODO_endpoint", params={{"q": query, "limit": limit}})

    items = results.get("items", [])          # ← adjust to actual response shape
    if not items:
        return f"No results for '{{query}}'."

    lines = [f"• {{item.get('name', '?')}}  —  {{item.get('url', '')}}" for item in items]
    return "\\n".join(lines)


# Add more tools below following the same pattern.
# Each function decorated with @register_tool becomes available to the agent
# immediately on next message — no restart needed.
#
# Checklist before shipping:
#   [x] Function name follows  service_action  pattern
#   [x] description= is a full sentence
#   [x] Every param() has a useful description
#   [x] Returns a non-empty string even when there are no results
#   [ ] Add credential key to DEFAULT_CONFIG in bujji/config.py
#   [ ] Add credential masking in bujji/server.py  (_mask_config)
#   [ ] Add UI input card in ui/index.html  (see README → Credentials)
'''


def cmd_new_tool(args) -> None:
    import pathlib
    import re

    raw_name = args.name.strip().lower()
    # Sanitise: only letters, digits, underscores
    svc = re.sub(r"[^a-z0-9_]", "_", raw_name).strip("_")
    if not svc:
        sys.exit(
            "ERROR: invalid tool name. Use letters and underscores, e.g. 'weather' or 'github'."
        )

    service_title = svc.replace("_", " ").title()
    filename = svc
    out_path = pathlib.Path(__file__).parent / "bujji" / "tools" / f"{filename}.py"

    print(f"\n{LOGO}  New tool scaffold: {service_title}\n{'─' * 52}")

    if out_path.exists():
        overwrite = (
            input(f"  ⚠️  bujji/tools/{filename}.py already exists. Overwrite? (y/N): ")
            .strip()
            .lower()
        )
        if overwrite != "y":
            print("  Aborted.")
            return

    # ── Ask 4 quick questions ─────────────────────────────────────────────

    api_url = (
        input(f"  API docs / key URL (Enter to skip): ").strip()
        or "https://example.com/api"
    )
    base_url = input(f"  API base URL (e.g. https://api.{svc}.com/v1): ").strip()
    if not base_url:
        base_url = f"https://api.{svc}.com/v1"

    print(f"\n  Auth pattern:")
    print(f"    1. Bearer token    (Authorization: Bearer <key>)  ← most common")
    print(f"    2. Token prefix    (Authorization: token <key>)")
    print(f"    3. X-API-Key       (X-API-Key: <key>)")
    print(f"    4. Query param     (?apikey=<key>)")
    print(f"    5. No auth needed")
    auth_choice = input("  Choose (Enter = 1): ").strip() or "1"
    auth_map = {"1": "bearer", "2": "token", "3": "x-api", "4": "param", "5": "none"}
    auth_key = auth_map.get(auth_choice, "bearer")
    auth_header = _AUTH_PATTERNS[auth_key].format(svc=svc)

    first_tool_default = f"{svc}_search"
    first_tool = input(
        f"\n  First tool function name (Enter = {first_tool_default}): "
    ).strip()
    if not first_tool:
        first_tool = first_tool_default
    first_tool = re.sub(r"[^a-z0-9_]", "_", first_tool.lower()).strip("_")

    # ── Write the file ────────────────────────────────────────────────────

    content = _TOOL_TEMPLATE.format(
        filename=filename,
        service_title=service_title,
        svc=svc,
        api_url=api_url,
        base_url=base_url,
        auth_header=auth_header,
        first_tool=first_tool,
        tool_list=f"  {first_tool}",
    )

    out_path.write_text(content, encoding="utf-8")

    print(f"\n  ✅ Created: bujji/tools/{filename}.py")
    print(f"\n  Next steps:")
    print(f"    1. Open bujji/tools/{filename}.py and fill in your API endpoints")
    print(f"    2. Add your credential to ~/.bujji/config.json:")
    print(f'         "tools": {{ "{svc}": {{ "api_key": "your-key" }} }}')
    print(f"    3. Add the key to DEFAULT_CONFIG in bujji/config.py")
    print(f"    4. Add masking in bujji/server.py  (_mask_config)")
    print(f"    5. Add a UI card in ui/index.html  (see README → Credentials)")
    print(f"\n  The tool is already live — no restart needed.")
    print(
        f"  Test it:  python main.py agent -m 'use {first_tool} to search for hello'\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SETUP-TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────


def cmd_setup_telegram(args) -> None:
    cfg = load_config()
    print(f"\n{LOGO} Telegram Setup\n{'─' * 52}")
    from bujji.connections.telegram import setup_telegram_interactive

    setup_telegram_interactive(cfg)
    save_config(cfg)
    print(f"\n✅ Saved to {CONFIG_FILE}")
    print(f"Start the bot:  python main.py gateway\n")


# ─────────────────────────────────────────────────────────────────────────────
#  SETUP-GMAIL
# ─────────────────────────────────────────────────────────────────────────────


def cmd_setup_gmail(args) -> None:
    print(f"\n🎙️ Gmail OAuth Setup\n{'─' * 52}\n")

    creds_file = (
        Path(__file__).parent / "bujji" / "bujji" / "tools" / "credentials.json"
    )
    token_file = (
        Path(__file__).parent / "bujji" / "bujji" / "tools" / "gmail_token.json"
    )

    if creds_file.exists():
        print("✅ credentials.json found\n")
        print("Starting OAuth flow...")
        print("(Browser will open automatically)\n")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            SCOPES = [
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
            ]

            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)

            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else SCOPES,
            }

            import json

            token_file.write_text(json.dumps(token_data, indent=2))

            print(f"\n✅ Gmail connected successfully!")
            print(f"   Token saved to: {token_file}")
            print(f"\nYou can now use Gmail commands in Tanu.")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("\nMake sure you have the google-auth libraries installed:")
            print("  pip install google-auth google-auth-oauthlib google-auth-httplib2")
    else:
        print("❌ credentials.json not found\n")
        print("Follow these steps:\n")
        print("1. Go to: https://console.cloud.google.com/")
        print("2. Create a new project (or select one)")
        print("3. Enable Gmail API:")
        print("   - Go to APIs & Services → Library")
        print("   - Search 'Gmail API' → Enable")
        print("4. Create OAuth credentials:")
        print("   - Go to APIs & Services → Credentials")
        print("   - Create Credentials → OAuth client ID")
        print("   - Application type: Desktop app")
        print("   - Name it 'Tanu'")
        print("5. Download the JSON file")
        print(f"\n6. Save it as: {creds_file}")
        print("\n7. Run this command again:")
        print("   python main.py setup-gmail")


# ─────────────────────────────────────────────────────────────────────────────
#  AGENT
# ─────────────────────────────────────────────────────────────────────────────


def cmd_agent(args) -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("ERROR: pip install requests")

    try:
        from bujji.agent import AgentLoop
        from bujji.session import SessionManager

        cfg = load_config()
        mgr = SessionManager(cfg)
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    stream = not getattr(args, "no_stream", False)
    session_id = "cli"

    import json

    def json_preview(d):
        return json.dumps(d, ensure_ascii=False)[:80]

    callbacks = {
        "on_token": lambda t: print(t, end="", flush=True),
        "on_tool_start": lambda n, a: print(
            f"\n{LOGO} [Tool] {n}({json_preview(a)})", file=sys.stderr
        ),
        "on_tool_done": lambda n, r: print(
            f"  → {r[:120].replace(chr(10), ' ')}", file=sys.stderr
        ),
        "on_error": lambda e: print(f"\n[ERROR] {e}", file=sys.stderr),
    }

    agent = mgr.get(session_id, callbacks=callbacks)

    if args.message:
        print(f"\n{LOGO}: ", end="", flush=True)
        result = agent.run(args.message, stream=stream)
        if result and not stream:
            print(result)
        print()
    else:
        print(
            f"\n{LOGO} Interactive mode  (Ctrl+C or /quit to exit, /clear to reset)\n"
        )
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                    print(f"Bye! {LOGO}")
                    break
                if user_input.lower() == "/clear":
                    mgr.clear(session_id)
                    print("[History cleared]")
                    continue

                print(f"\n{LOGO}: ", end="", flush=True)
                history = mgr.history(session_id)
                result = agent.run(user_input, history=history, stream=stream)
                if not stream and result:
                    print(result)
                print()

                mgr.append(session_id, "user", user_input)
                mgr.append(session_id, "assistant", result or "[streamed]")

            except (KeyboardInterrupt, EOFError):
                print(f"\n\nBye! {LOGO}")
                break


# ─────────────────────────────────────────────────────────────────────────────
#  GATEWAY
# ─────────────────────────────────────────────────────────────────────────────


def cmd_gateway(args) -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("ERROR: pip install requests")

    try:
        from bujji.agent import AgentLoop, HeartbeatService, CronService
        from bujji.session import SessionManager

        cfg = load_config()
        mgr = SessionManager(cfg)
        agent = mgr.get("gateway:default")
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    ws = workspace_path(cfg)
    channels_cfg = cfg.get("channels", {})
    active = []

    hb = HeartbeatService(agent, ws)
    cron = CronService(agent, ws)
    hb.start()
    cron.start()

    tg_cfg = channels_cfg.get("telegram", {})
    if tg_cfg.get("enabled") and tg_cfg.get("token"):
        from bujji.connections.telegram import TelegramChannel

        tg = TelegramChannel(tg_cfg["token"], tg_cfg.get("allow_from", []), cfg, mgr)
        threading.Thread(target=tg.run, daemon=True).start()
        active.append("Telegram")

    dc_cfg = channels_cfg.get("discord", {})
    if dc_cfg.get("enabled") and dc_cfg.get("token"):
        from bujji.connections.discord import DiscordChannel

        dc = DiscordChannel(dc_cfg["token"], dc_cfg.get("allow_from", []), cfg, mgr)
        threading.Thread(target=dc.run, daemon=True).start()
        active.append("Discord")

    if not active:
        print(f"\n{LOGO} No channels enabled.  Run: python main.py setup-telegram")
        hb.stop()
        cron.stop()
        return

    print(f"\n{LOGO} Gateway running.  Channels: {', '.join(active)}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{LOGO} Shutting down…")
        hb.stop()
        cron.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  DESKBOT
# ─────────────────────────────────────────────────────────────────────────────


def cmd_tanu(args) -> None:
    try:
        import requests
    except ImportError:
        sys.exit("ERROR: pip install requests")

    from bujji.config import get_repo_workspace

    cfg = load_config()
    ws = get_repo_workspace()
    ws.mkdir(parents=True, exist_ok=True)

    cfg["agents"]["defaults"]["workspace"] = str(ws)

    for identity_file in [
        "SOUL.md",
        "IDENTITY.md",
        "AGENT.md",
        "BACKSTORY.md",
        "USER.md",
        "HEARTBEAT.md",
    ]:
        src = Path(__file__).parent / "bujji" / "tanu" / identity_file
        dst = ws / identity_file
        if src.exists():
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            print(f"[Tanu] Installed {identity_file}")

    mgr = SessionManager(cfg)

    try:
        from bujji.connections.display import init_display

        display = init_display(cfg)
    except Exception:
        display = None

    if getattr(args, "text_mode", False):
        cmd_tanu_text(cfg, mgr)
        return

    simulate = getattr(args, "simulate", False)

    try:
        from bujji.connections.deskbot import DeskbotConnection
        from bujji.agent import HeartbeatService, CronService
        from bujji.tools.tanu_reminder import (
            init_worker,
            set_tts_queue,
            set_channel_fns,
        )
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    from bujji.config import get_repo_workspace

    ws = get_repo_workspace()

    reminder_worker = init_worker(ws)
    reminder_worker.start()

    heartbeat = HeartbeatService(mgr.get("tanu", agent_name="tanu", workspace=ws), ws)
    cron = CronService(mgr.get("tanu", agent_name="tanu", workspace=ws), ws)

    tanu_cfg = cfg.get("tanu", {})
    tg_cfg = cfg.get("channels", {}).get("telegram", {})
    dc_cfg = cfg.get("channels", {}).get("discord", {})

    def telegram_send(msg: str) -> None:
        from bujji.connections.telegram import send_message

        if tg_cfg.get("enabled") and tg_cfg.get("token"):
            send_message(tg_cfg["token"], tg_cfg.get("chat_id", ""), msg)

    def discord_send(msg: str) -> None:
        pass

    set_channel_fns(telegram_fn=telegram_send, discord_fn=discord_send)

    tanu_cfg = dict(cfg)
    tanu_cfg["agents"] = dict(cfg.get("agents", {}))
    tanu_cfg["agents"]["defaults"] = dict(cfg["agents"]["defaults"])
    tanu_cfg["agents"]["defaults"]["workspace"] = str(ws)

    conn = DeskbotConnection(
        tanu_cfg, mgr, display, simulate=simulate, agent_name="tanu", workspace=str(ws)
    )
    set_tts_queue(conn._tts_queue)

    threads = [
        threading.Thread(target=conn.run, daemon=True),
        threading.Thread(target=heartbeat.start, daemon=True),
        threading.Thread(target=cron.start, daemon=True),
    ]
    for t in threads:
        t.start()

    print(f"\n🎙️ Tanu voice assistant running")
    print("Press Ctrl+C to stop.\n")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print(f"\n🎙️ Shutting down...")
        reminder_worker.stop()
        heartbeat.stop()
        cron.stop()
        if display:
            display.show_idle()


def cmd_tanu_text(cfg: dict, mgr) -> None:
    from bujji.tools.speak_tool import set_print_mode
    from bujji.tools.tanu_reminder import init_worker
    from bujji.config import get_repo_workspace

    set_print_mode(True)

    ws = get_repo_workspace()
    ws.mkdir(parents=True, exist_ok=True)

    cfg["agents"]["defaults"]["workspace"] = str(ws)

    for identity_file in [
        "SOUL.md",
        "IDENTITY.md",
        "AGENT.md",
        "BACKSTORY.md",
        "USER.md",
        "HEARTBEAT.md",
    ]:
        src = Path(__file__).parent / "bujji" / "tanu" / identity_file
        dst = ws / identity_file
        if src.exists():
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            print(f"[Tanu] Installed {identity_file}")

    reminder_worker = init_worker(ws)
    reminder_worker.start()

    print(f"\n🎙️ Tanu text mode (Ctrl+D to exit)\n")

    while True:
        try:
            line = input("You: ").strip()
            if not line:
                continue

            print(f"You: {line}")
            agent = mgr.get("tanu", agent_name="tanu", workspace=ws)
            history = mgr.history("tanu")
            result = agent.run(line, history=history, stream=False)
            if result:
                print(f"Tanu: {result}")
            mgr.append("tanu", "user", line)
            mgr.append("tanu", "assistant", result or "")
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            reminder_worker.stop()
            break


def cmd_deskbot(args) -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("ERROR: pip install requests")

    cfg = load_config()
    mgr = SessionManager(cfg)

    try:
        from bujji.connections.display import init_display

        display = init_display(cfg)
    except Exception:
        display = NullDisplay() if "NullDisplay" in globals() else None

    if getattr(args, "text_mode", False):
        cmd_deskbot_text(cfg, mgr)
        return

    simulate = getattr(args, "simulate", False)

    try:
        from bujji.connections.deskbot import DeskbotConnection
        from bujji.agent import HeartbeatService, CronService
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    heartbeat = HeartbeatService(mgr.get("deskbot"), workspace_path(cfg))
    cron = CronService(mgr.get("deskbot"), workspace_path(cfg))

    conn = DeskbotConnection(cfg, mgr, display, simulate=simulate)

    threads = [
        threading.Thread(target=conn.run, daemon=True),
        threading.Thread(target=heartbeat.start, daemon=True),
        threading.Thread(target=cron.start, daemon=True),
    ]
    for t in threads:
        t.start()

    print(f"\n{LOGO} Deskbot voice assistant running")
    print("Press Ctrl+C to stop.\n")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print(f"\n{LOGO} Shutting down...")
        if display:
            display.show_idle()


class NullDisplay:
    """Fallback display when display module unavailable."""

    def show_idle(self) -> None:
        pass

    def show_partial(self, text: str) -> None:
        pass

    def show_listening(self) -> None:
        pass

    def show_thinking(self) -> None:
        pass

    def show_speaking(self) -> None:
        pass

    def show_error(self, msg: str) -> None:
        pass


def cmd_deskbot_text(cfg: dict, mgr) -> None:
    """Test mode: read from stdin, print agent response, no audio."""
    from bujji.tools.speak_tool import set_print_mode

    set_print_mode(True)

    print(f"\n{LOGO} Deskbot text mode (Ctrl+D to exit)\n")

    import sys
    import os

    if os.isatty(sys.stdin.fileno()):
        while True:
            print("You: ", end="", flush=True)
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            print(f"You: {line}")
            agent = mgr.get("deskbot")
            result = agent.run(line, stream=False)
            if result:
                print(f"{LOGO}: {result}")
    else:
        content = sys.stdin.read()
        agent = mgr.get("deskbot")
        result = agent.run(content, stream=False)
        if result:
            print(result)


# ─────────────────────────────────────────────────────────────────────────────
#  STATUS
# ─────────────────────────────────────────────────────────────────────────────


def cmd_status(args) -> None:
    import json

    cfg = load_config()
    pname, api_key, api_base, model = get_active_provider(cfg)
    ws = workspace_path(cfg)

    print(f"\n{LOGO} bujji v{__version__}")
    print(
        f"  Config:    {CONFIG_FILE}  {'✅' if CONFIG_FILE.exists() else '❌ missing'}"
    )
    print(f"  Workspace: {ws}  {'✅' if ws.exists() else '❌ missing'}")

    print(f"\n  LLM Provider:")
    if pname:
        masked = (api_key[:6] + "…") if api_key and len(api_key) > 6 else "(set)"
        print(f"    Provider : {pname}")
        print(f"    Model    : {model}")
        print(f"    API Base : {api_base}")
        print(f"    Key      : {masked}")
    else:
        print(f"    ⚠️  Not configured — run: python main.py onboard")

    print(f"\n  Channels:")
    for ch_name, ch_cfg in cfg.get("channels", {}).items():
        enabled = ch_cfg.get("enabled", False)
        print(f"    {'✅' if enabled else '  '} {ch_name}")

    brave = cfg["tools"]["web"]["search"].get("api_key", "")
    print(
        f"\n  Web search : {'✅ Brave API configured' if brave else '  not configured'}"
    )

    try:
        from bujji.tools import ToolRegistry

        registry = ToolRegistry(cfg)
        tool_names = [s["function"]["name"] for s in registry.schema()]
        print(f"\n  Tools ({len(tool_names)}): {', '.join(tool_names)}")
    except Exception as e:
        print(f"\n  Tools: (error — {e})")

    print(f"\n  Python : {sys.version.split()[0]}")
    try:
        import requests  # noqa

        print(f"  requests : ✅\n")
    except ImportError:
        print(f"  requests : ❌  pip install requests\n")

    print(f"  Web UI : python main.py serve  → http://localhost:7337\n")


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bujji",
        description=f"{LOGO} bujji  — Ultra-lightweight AI assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
  examples:
    python main.py onboard                        # first-time setup
    python main.py serve                          # web UI (recommended)
    python main.py agent -m "What's my disk usage?"
    python main.py agent                          # interactive chat
    python main.py new-tool weather               # scaffold a new tool
    python main.py new-tool github                # scaffold github tool
    python main.py gateway                        # Telegram / Discord bot
        """),
    )
    parser.add_argument("--version", action="version", version=f"bujji {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup wizard")
    sub.add_parser("setup-telegram", help="Configure the Telegram bot")
    sub.add_parser("setup-gmail", help="Setup Gmail OAuth2 connection")
    sub.add_parser("gateway", help="Start Telegram / Discord gateway")
    sub.add_parser("status", help="Show config and runtime status")

    p_deskbot = sub.add_parser("deskbot", help="Start deskbot voice assistant")
    p_deskbot.add_argument(
        "--text",
        dest="text_mode",
        action="store_true",
        help="Text mode (no audio, for testing)",
    )
    p_deskbot.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate voice input (type to speak, for testing without mic)",
    )

    p_tanu = sub.add_parser("tanu", help="Start Tanu voice assistant")
    p_tanu.add_argument(
        "--text",
        dest="text_mode",
        action="store_true",
        help="Text mode (no audio, for testing)",
    )
    p_tanu.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate voice input (type to speak, for testing without mic)",
    )

    p_serve = sub.add_parser(
        "serve", help="Open web UI in browser (http://localhost:7337)"
    )
    p_serve.add_argument("--port", type=int, default=7337)
    p_serve.add_argument("--host", type=str, default="127.0.0.1")

    p_agent = sub.add_parser("agent", help="Chat with the agent in the terminal")
    p_agent.add_argument("-m", "--message", type=str, metavar="TEXT")
    p_agent.add_argument("--no-stream", action="store_true")

    p_new_tool = sub.add_parser(
        "new-tool",
        help="Scaffold a new tool file (e.g. python main.py new-tool weather)",
    )
    p_new_tool.add_argument(
        "name",
        type=str,
        metavar="NAME",
        help="Service name for the tool, e.g. 'weather', 'github', 'linear'",
    )

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "setup-telegram": cmd_setup_telegram,
        "setup-gmail": cmd_setup_gmail,
        "serve": cmd_serve,
        "agent": cmd_agent,
        "new-tool": cmd_new_tool,
        "gateway": cmd_gateway,
        "status": cmd_status,
        "deskbot": cmd_deskbot,
        "tanu": cmd_tanu,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
