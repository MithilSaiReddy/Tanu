"""
tanu/updater.py — `python3 main.py update`.

Self-update from the configured git remote (GitHub). Pulls new commits
fast-forward-only, then optionally reinstalls Python deps. Never touches
config/ or workspace/ (both gitignored).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class GitError(RuntimeError):
    pass


def _git(args, cwd=None, check=True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH")
    if check and proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise GitError(msg or f"git {args[0]} failed")
    return proc


def _print(msg: str) -> None:
    print(f"[update] {msg}")


def _dirty_files(cwd: Path) -> list[str]:
    proc = _git(["status", "--porcelain"], cwd=cwd)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _branch_and_upstream(cwd: Path) -> tuple[str, str]:
    branch = _git(["branch", "--show-current"], cwd=cwd).stdout.strip()
    if not branch:
        raise GitError("not on a branch (detached HEAD) — checkout a branch first")
    upstream = _git(["rev-parse", "--abbrev-ref", "@{u}"], cwd=cwd).stdout.strip()
    return branch, upstream


def _pip_command(root: Path) -> list[str]:
    for candidate in (
        root / "venv" / "bin" / "python",
        root / "venv" / "Scripts" / "python.exe",
    ):
        if candidate.exists():
            return [str(candidate), "-m", "pip"]
    return [sys.executable, "-m", "pip"]


def _install_deps(root: Path) -> None:
    req = root / "requirements.txt"
    if not req.exists():
        _print("requirements.txt not found — skipping deps")
        return
    _print("Installing Python dependencies...")
    proc = subprocess.run([*_pip_command(root), "install", "-r", str(req)])
    if proc.returncode == 0:
        _print("Dependencies up to date")
    else:
        _print(f"pip install failed (exit {proc.returncode})")


def _pop_stash(cwd: Path) -> None:
    proc = _git(["stash", "pop"], cwd=cwd, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        print(f"[update] stash pop reported: {msg}")
        print("[update] your changes were stashed — resolve manually or recover via `git stash list`.")
    else:
        _print("local changes restored from stash.")


def run_update(*, check=False, stash=False, force=False, yes=False, deps=True, build=True) -> int:
    # 1. git repo + origin remote
    try:
        toplevel = _git(["rev-parse", "--show-toplevel"]).stdout.strip()
    except GitError as e:
        print(f"[update] not a git repository: {e}")
        return 1
    cwd = Path(toplevel)

    try:
        remote = _git(["remote", "get-url", "origin"], cwd=cwd).stdout.strip()
    except GitError:
        print("[update] no 'origin' remote configured — can't check for updates")
        return 1

    try:
        branch, upstream = _branch_and_upstream(cwd)
    except GitError as e:
        print(f"[update] {e}")
        return 1

    _print(f"repo: {remote}")
    _print(f"branch: {branch} (tracking {upstream})")

    # 2. dirty-tree guard (skipped for --check)
    dirty = _dirty_files(cwd)
    if dirty and not check and not force:
        if stash:
            _print("Stashing local changes...")
            _git(["stash", "push", "-m", "tanu-update"], cwd=cwd)
        else:
            print("[update] working tree has uncommitted changes:")
            for f in dirty:
                print(f"         {f}")
            print("[update] aborting — commit or stash first, or rerun with --stash / --force")
            return 1

    # 3. fetch + compare
    _print("Fetching updates...")
    _git(["fetch", "origin"], cwd=cwd)

    try:
        behind = int(_git(["rev-list", "--count", f"HEAD..{upstream}"], cwd=cwd).stdout.strip() or 0)
        ahead = int(_git(["rev-list", "--count", f"{upstream}..HEAD"], cwd=cwd).stdout.strip() or 0)
    except GitError as e:
        print(f"[update] could not compare with {upstream}: {e}")
        return 1

    if ahead:
        _print(f"{ahead} local commit(s) not pushed yet (won't be lost)")

    if behind == 0:
        if dirty and stash:
            _pop_stash(cwd)
        print("[update] already up to date.")
        return 0

    commits = _git(["log", "--oneline", f"HEAD..{upstream}"], cwd=cwd).stdout.strip().splitlines()
    print(f"\n[update] {behind} update(s) available:")
    for c in commits:
        print(f"   {c}")
    print()

    if check:
        print("[update] --check: not pulling. Run `python3 main.py update` to apply.")
        return 0

    # 4. confirm
    if not yes:
        try:
            ans = input(f"[update] Pull {behind} commit(s)? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[update] cancelled.")
            return 0
        if ans not in ("y", "yes"):
            print("[update] cancelled.")
            return 0

    # 5. pull (fast-forward only)
    try:
        _git(["pull", "--ff-only"], cwd=cwd)
    except GitError as e:
        print(f"[update] pull failed: {e}")
        print("[update] you may have diverged from origin — pull manually (`git pull`) and resolve.")
        if dirty and stash:
            _pop_stash(cwd)
        return 1
    print(f"[update] pulled {behind} commit(s).")

    # restore stashed changes
    if dirty and stash:
        _pop_stash(cwd)

    # 6. deps
    if deps:
        _install_deps(cwd)
    else:
        _print("skipping dependency reinstall (--no-deps)")

    if not build:
        _print("--no-build is deprecated (no binary build needed anymore)")

    print("\n[update] done. config/ and workspace/ were not touched (gitignored).")
    return 0
