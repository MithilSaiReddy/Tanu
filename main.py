#!/usr/bin/env python3
"""
Tanu - Voice assistant for DeskBot

Usage:
    python main.py tanu              # Start voice assistant
    python main.py tanu --text       # Text mode (no audio)
    python main.py onboard           # First-time setup
    python main.py serve             # Web UI (HTTP + WebSocket)
    python main.py desk              # Desktop app (Godot + server)
    python main.py agent             # Chat in terminal

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
import multiprocessing
import subprocess
import threading
import time
import signal
import webbrowser

from bujji import LOGO as BUJJI_LOGO
from bujji.config import load_config, workspace_path, get_active_provider
from bujji.identity import ensure_identity_files
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
    from tanu.config import load_config
    from bujji.server import run_server
    cfg = load_config()
    port = getattr(args, "port", 7337) or 7337
    run_server(cfg, port=port, quiet=True)


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


def _run_server(port: int):
    """Run the bujji server in a subprocess (quiet, API-only, no browser)."""
    from tanu.config import load_config
    from bujji.server import run_server
    cfg = load_config()
    run_server(cfg, port=port, quiet=True)


def cmd_desk(args):
    ROOT = Path(__file__).parent

    GODOT_BINS = [
        ROOT / "build" / "tanu-godot",
        ROOT / "src" / "godot" / "build" / "tanu",
        ROOT / "build" / "tanu-godot.x86_64",
    ]

    ui_bin = None

    for b in GODOT_BINS:
        if b.exists():
            ui_bin = b
            break

    if not ui_bin:
        print("No Godot binary found. Build one first:")
        print()
        print("  1. Install Godot 4: https://godotengine.org/download")
        print("  2. Export: cd src/godot && godot --export-release linux")
        print("  3. Copy binary to build/tanu-godot")
        print()
        print("  Then run: python main.py desk")
        return

    print("Starting server + desktop app...")
    print(f"   Server:  http://localhost:7337")
    print(f"   WS:      ws://localhost:7337/ws/chat")
    print(f"   UI:      godot ({ui_bin})")

    try:
        from tanu.notifier import notify
        notify("Tanu", "Running in background.", timeout=4)
    except Exception:
        pass

    port = getattr(args, "port", 7337) or 7337
    server_proc = multiprocessing.Process(target=_run_server, args=(port,), daemon=True)
    server_proc.start()

    ui_env = os.environ.copy()
    if "LD_LIBRARY_PATH" in ui_env:
        del ui_env["LD_LIBRARY_PATH"]

    ui_proc = subprocess.Popen(
        [str(ui_bin)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=ui_env,
    )

    time.sleep(2.5)
    if ui_proc.poll() is not None:
        stderr_output = ui_proc.stderr.read()
        print("Godot app crashed:")
        if stderr_output:
            print(stderr_output)
        else:
            print("   (no stderr output)")
        server_proc.terminate()
        return

    cleanup_done = threading.Event()

    def cleanup(sig=None, frame=None):
        if cleanup_done.is_set():
            return
        cleanup_done.set()
        print("\nShutting down...")
        if ui_proc.poll() is None:
            ui_proc.terminate()
            try:
                ui_proc.wait(timeout=5)
            except Exception:
                pass
            if ui_proc.poll() is None:
                ui_proc.kill()
        server_proc.terminate()
        try:
            server_proc.join(timeout=5)
        except Exception:
            pass
        if server_proc.is_alive():
            server_proc.kill()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    import atexit
    atexit.register(cleanup)

    try:
        ui_proc.wait()
    except KeyboardInterrupt:
        cleanup()


def _ensure_workspace():
    """Scaffold missing identity files (USER.md, SOUL.md, etc.) on first run."""
    cfg = load_config()
    ws = workspace_path(cfg)
    ensure_identity_files(ws)
    user_md = ws / "USER.md"
    user_bak = ws / "USER.md.bak"
    if user_md.exists() and not user_bak.exists():
        user_bak.write_bytes(user_md.read_bytes())


def main():
    _ensure_workspace()
    parser = argparse.ArgumentParser(prog="tanu", description="🎙️ Voice assistant for DeskBot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("onboard", help="First-time setup")
    sub.add_parser("serve", help="Web UI")
    sub.add_parser("status", help="Show status")
    sub.add_parser("desk", help="Desktop app (Godot + server)")

    p_tanu = sub.add_parser("tanu", help="Start voice assistant")
    p_tanu.add_argument("--text", dest="text_mode", action="store_true", help="Text mode")
    p_tanu.add_argument("--simulate", action="store_true", help="Simulate voice")

    args = parser.parse_args()

    cmds = {
        "onboard": cmd_onboard,
        "tanu": cmd_tanu,
        "serve": cmd_serve,
        "status": cmd_status,
        "desk": cmd_desk,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()