#!/usr/bin/env python3
"""
Tanu - Voice assistant for DeskBot

Usage:
    python main.py tanu              # Start voice assistant
    python main.py tanu --text   # Text mode (no audio)
    python main.py onboard        # First-time setup
    python main.py serve         # Web UI
    python main.py agent        # Chat in terminal

Requirements:
    pip install -e .            # Install Tanu package
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_src_path = os.path.join(_script_dir, "src")
_bujji_path = os.path.join(_script_dir, "bujji")
_paths_to_add = [_src_path, _bujji_path]
for p in _paths_to_add:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import argparse
import threading
import time

from bujji import LOGO as BUJJI_LOGO
from bujji.config import load_config, workspace_path, get_active_provider
from bujji.session import SessionManager
from bujji.agent import HeartbeatService, CronService


def cmd_onboard(args):
    from bujji.config import load_config, PROVIDER_DEFAULTS, save_config

    print(f"\n{BUJJI_LOGO} Welcome to Tanu\n")
    cfg = load_config()

    print("Available LLM providers:")
    for i, (p, (_, model)) in enumerate(PROVIDER_DEFAULTS.items(), 1):
        print(f"  {i:2}. {p:<12}  default: {model}")

    choice = input("\nChoose provider (Enter = openrouter): ").strip()
    provider = list(PROVIDER_DEFAULTS.keys())[int(choice) - 1] if choice.isdigit() else "openrouter"

    api_key = input(f"Enter your {provider} API key: ").strip()
    default_model = PROVIDER_DEFAULTS[provider][1]
    model = input(f"Model (Enter = {default_model}): ").strip() or default_model

    cfg["providers"][provider] = {"api_key": api_key, "api_base": PROVIDER_DEFAULTS[provider][0]}
    cfg["agents"]["defaults"]["model"] = model
    cfg["active_provider"] = provider
    save_config(cfg)

    print(f"\n✅ Config saved!")
    print(f"   Run: python main.py tanu\n")


def cmd_tanu(args):
    from tanu.config import load_config
    from tanu.plugins.voice.deskbot import DeskbotConnection

    cfg = load_config()
    mgr = SessionManager(cfg)
    ws = Path(cfg["agents"]["defaults"]["workspace"])

    simulate = getattr(args, "simulate", False)
    text_mode = getattr(args, "text_mode", False)

    if text_mode:
        cmd_tanu_text(cfg, mgr)
        return

    display = None
    try:
        from tanu.plugins.voice.display import init_display
        display = init_display(cfg)
    except Exception:
        pass

    conn = DeskbotConnection(cfg, mgr, display, simulate=simulate)

    try:
        from tools.tanu_reminder import init_worker
        reminder_worker = init_worker(ws)
        reminder_worker.start()
    except Exception:
        reminder_worker = None

    heartbeat = HeartbeatService(mgr.get("tanu"), ws)
    cron = CronService(mgr.get("tanu"), ws)

    print(f"\n🎙️ Tanu voice assistant running")
    print("Press Ctrl+C to stop.\n")

    threads = [
        threading.Thread(target=conn.run, daemon=True),
        threading.Thread(target=heartbeat.start, daemon=True),
        threading.Thread(target=cron.start, daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🎙️ Shutting down...")
        if reminder_worker:
            reminder_worker.stop()


def cmd_tanu_text(cfg, mgr):
    from tanu.tools.speak_tool import set_print_mode
    ws = Path(cfg["agents"]["defaults"]["workspace"])

    set_print_mode(True)

    print(f"\n🎙️ Tanu text mode (Ctrl+D to exit)\n")

    import sys
    while True:
        try:
            line = input("You: ").strip()
            if not line:
                continue

            agent = mgr.get("tanu")
            result = agent.run(line, stream=False)
            if result:
                print(f"Tanu: {result}")
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            break


def cmd_serve(args):
    from bujji.server import run_server
    cfg = load_config()
    port = getattr(args, "port", 7337) or 7337
    run_server(cfg, port=port)


def cmd_status(args):
    from bujji import __version__
    from bujji.config import load_config

    cfg = load_config()
    pname, api_key, api_base, model = get_active_provider(cfg)
    ws = workspace_path(cfg)

    print(f"\n🎙️ Tanu v{__version__}")
    print(f"  Config: {cfg}")
    print(f"  Provider: {pname} / {model}")
    print(f"  Workspace: {ws}")
    print(f"  Web UI: python main.py serve → http://localhost:7337\n")


def main():
    parser = argparse.ArgumentParser(prog="tanu", description="🎙️ Voice assistant for DeskBot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup")
    sub.add_parser("serve", help="Web UI")
    sub.add_parser("status", help="Show status")

    p_tanu = sub.add_parser("tanu", help="Start voice assistant")
    p_tanu.add_argument("--text", dest="text_mode", action="store_true", help="Text mode")
    p_tanu.add_argument("--simulate", action="store_true", help="Simulate voice")

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "tanu": cmd_tanu,
        "serve": cmd_serve,
        "status": cmd_status,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()