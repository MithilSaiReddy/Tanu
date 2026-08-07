"""
tanu/cli.py - Command-line interface
"""

import sys
import argparse
from pathlib import Path

from tanu import LOGO as BUJJI_LOGO


def cmd_onboard(args):
    from tanu.onboard import run_onboard

    run_onboard()


def cmd_tanu(args):
    cfg = load_tanu_config()
    from tanu.plugins.voice.deskbot import DeskbotConnection
    from tanu.agent import HeartbeatService, CronService
    from tanu.session import SessionManager

    ws = Path(cfg["agents"]["defaults"]["workspace"])
    mgr = SessionManager(cfg)

    conn = DeskbotConnection(cfg, mgr, None)
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
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🎙️ Shutting down...")


def cmd_status(args):
    from tanu.config import load_config
    from tanu import __version__

    cfg = load_config()
    pname, api_key, _, model = cfg.get("active_provider"), "", "", ""

    print(f"\n🎙️ Tanu v{__version__}")
    print(f"  Config: {cfg}")
    # ... simplified for now


def load_tanu_config():
    from tanu.config import load_config

    return load_config()


def main():
    parser = argparse.ArgumentParser(prog="tanu", description="🎙️ Voice assistant")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup")
    sub.add_parser("tanu", help="Start voice assistant")
    sub.add_parser("status", help="Show status")

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "tanu": cmd_tanu,
        "status": cmd_status,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
