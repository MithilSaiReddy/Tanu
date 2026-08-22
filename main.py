#!/usr/bin/env python3
"""
Tanu - Voice assistant for DeskBot

Usage:
    python main.py tanu              # Start voice assistant
    python main.py tanu --text       # Text mode (no audio)
    python main.py onboard           # First-time setup
    python main.py serve             # Local API (HTTP + WebSocket)
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
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import argparse
import multiprocessing
import subprocess
import threading
import time
import signal
import webbrowser

from tanu import LOGO as TANU_LOGO
from tanu.config import load_config, workspace_path, get_active_provider
from tanu.identity import ensure_identity_files
from tanu.session import SessionManager
from tanu.agent import HeartbeatService, CronService


def cmd_onboard(args):
    from tanu.onboard import run_onboard
    run_onboard()


def cmd_tanu(args):
    from tanu.config import load_config
    from tanu.plugins.voice.deskbot import DeskbotConnection

    cfg = load_config()
    mgr = SessionManager(cfg)
    ws = workspace_path(cfg)

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
        from tanu.tools.tanu_reminder import init_worker
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


def cmd_agent(args):
    """Start a terminal chat without initializing audio devices."""
    cfg = load_config()
    cmd_tanu_text(cfg, SessionManager(cfg))


def cmd_serve(args):
    from tanu.config import load_config
    from tanu.server import run_server
    cfg = load_config()
    port = getattr(args, "port", 7337) or 7337
    run_server(cfg, port=port, quiet=True)


def cmd_status(args):
    from tanu import __version__
    from tanu.config import CONFIG_FILE, load_config

    cfg = load_config()
    pname, api_key, api_base, model = get_active_provider(cfg)
    ws = workspace_path(cfg)

    print(f"\n🎙️ Tanu v{__version__}")
    print(f"  Config: {CONFIG_FILE}")
    print(f"  Configured: {'yes' if pname else 'no'}")
    print(f"  Provider: {pname or '-'} / {model or '-'}")
    print(f"  Workspace: {ws}")
    print(f"  Local API: python main.py serve → http://localhost:7337\n")


def _run_server(port: int):
    """Run the tanu server in a subprocess (quiet, API-only, no browser)."""
    from tanu.config import load_config
    from tanu.server import run_server
    cfg = load_config()
    run_server(cfg, port=port, quiet=True)


def cmd_update(args):
    from tanu.updater import run_update

    rc = run_update(
        check=getattr(args, "check", False),
        stash=getattr(args, "stash", False),
        force=getattr(args, "force", False),
        yes=getattr(args, "yes", False),
        deps=not getattr(args, "no_deps", False),
        build=not getattr(args, "no_build", False),
    )
    raise SystemExit(rc)


def cmd_desk(args):
    ROOT = Path(__file__).parent

    GODOT_BINS = [
        ROOT / "build" / "tanu-godot",
        ROOT / "build" / "tanu-godot-arm64",
        ROOT / "build" / "tanu",
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
    sub.add_parser("serve", help="Local HTTP/WebSocket API")
    sub.add_parser("status", help="Show status")
    sub.add_parser("desk", help="Desktop app (Godot + server)")
    sub.add_parser("agent", help="Terminal chat (no audio)")

    p_update = sub.add_parser("update", help="Update Tanu from GitHub")
    p_update.add_argument("--check", action="store_true", help="Check for updates without pulling")
    p_update.add_argument("--stash", action="store_true", help="Auto-stash local changes before pulling")
    p_update.add_argument("--force", action="store_true", help="Skip the dirty-tree check")
    p_update.add_argument("-y", "--yes", dest="yes", action="store_true", help="Skip the confirmation prompt")
    p_update.add_argument("--no-deps", dest="no_deps", action="store_true", help="Skip pip reinstall")
    p_update.add_argument("--no-build", dest="no_build", action="store_true", help="Skip Godot rebuild")

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
        "agent": cmd_agent,
        "update": cmd_update,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
