"""
tanu/cli.py - Command-line interface
"""

import sys
import argparse
from pathlib import Path

def cmd_onboard(args):
    from tanu.onboard import run_onboard

    run_onboard()


def cmd_tanu(args):
    cfg = load_tanu_config()
    from tanu.plugins.voice.deskbot import DeskbotConnection
    from tanu.plugins.voice.display import NullDisplay
    from tanu.agent import HeartbeatService, CronService
    from tanu.session import SessionManager

    from tanu.config import workspace_path

    ws = workspace_path(cfg)
    mgr = SessionManager(cfg)

    conn = DeskbotConnection(cfg, mgr, NullDisplay())
    heartbeat = HeartbeatService(mgr.get("tanu"), ws)
    cron = CronService(mgr.get("tanu"), ws)

    print(f"\n🎙️ Tanu voice assistant running")
    print("Press Ctrl+C to stop.\n")

    import threading

    threads = [
        threading.Thread(target=conn.run, daemon=True),
        threading.Thread(target=heartbeat.start, daemon=True),
        threading.Thread(target=cron.start, daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while not conn.stopped_event.wait(1):
            pass
    except KeyboardInterrupt:
        print("\n🎙️ Shutting down...")
        conn.stop()


def cmd_status(args):
    from tanu.config import CONFIG_FILE, get_active_provider, load_config, workspace_path
    from tanu import __version__

    cfg = load_config()
    pname, _, _, model = get_active_provider(cfg)

    print(f"\n🎙️ Tanu v{__version__}")
    print(f"  Config: {CONFIG_FILE}")
    print(f"  Configured: {'yes' if pname else 'no'}")
    print(f"  Provider: {pname or '-'} / {model or '-'}")
    print(f"  Workspace: {workspace_path(cfg)}")


def cmd_agent(args):
    """Start a terminal chat without initializing audio devices."""
    from tanu.session import SessionManager
    from tanu.tools.speak_tool import set_print_mode

    cfg = load_tanu_config()
    set_print_mode(True)
    agent = SessionManager(cfg).get("cli")
    print("\n🎙️ Tanu terminal chat (Ctrl+D to exit)\n")
    while True:
        try:
            message = input("You: ").strip()
            if message:
                print(f"Tanu: {agent.run(message, stream=False)}")
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            return


def load_tanu_config():
    from tanu.config import load_config

    return load_config()


def main():
    parser = argparse.ArgumentParser(prog="tanu", description="🎙️ Voice assistant")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup")
    sub.add_parser("tanu", help="Start voice assistant")
    sub.add_parser("status", help="Show status")
    sub.add_parser("agent", help="Terminal chat (no audio)")

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "tanu": cmd_tanu,
        "status": cmd_status,
        "agent": cmd_agent,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
