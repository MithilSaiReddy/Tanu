"""
tanu/cli.py - Command-line interface
"""

import sys
import argparse
from pathlib import Path

from bujji import LOGO as BUJJI_LOGO


def cmd_onboard(args):
    from bujji.config import load_config, PROVIDER_DEFAULTS, save_config

    print(f"\n{BUJJI_LOGO} Welcome to Tanu\n")
    cfg = load_config()

    print("Available LLM providers:")
    for i, (p, (_, model)) in enumerate(PROVIDER_DEFAULTS.items(), 1):
        print(f"  {i:2}. {p:<12}  default: {model}")

    choice = input("\nChoose provider (Enter = openrouter): ").strip()
    provider = (
        list(PROVIDER_DEFAULTS.keys())[int(choice) - 1]
        if choice.isdigit()
        else "openrouter"
    )

    api_key = input(f"Enter your {provider} API key: ").strip()
    model = (
        input(f"Model (Enter for default): ").strip() or PROVIDER_DEFAULTS[provider][1]
    )

    cfg["providers"][provider] = {
        "api_key": api_key,
        "api_base": PROVIDER_DEFAULTS[provider][0],
    }
    cfg["agents"]["defaults"]["model"] = model
    save_config(cfg)
    print(f"\n✅ Config saved!\n")


def cmd_tanu(args):
    cfg = load_tanu_config()
    from tanu.plugins.voice.deskbot import DeskbotConnection
    from bujji.agent import HeartbeatService, CronService
    from bujji.session import SessionManager

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
    from bujji.config import load_config
    from bujji import __version__

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
