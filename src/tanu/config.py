"""
tanu/config.py — unified configuration.

Config file:  ~/.tanu/config.json
Legacy file:  ~/.bujji/config.json  (migrated automatically on first load)
Project copy: config/config.json    (repo-root template, created by setup)
"""

import copy
import json
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
CONFIG_DIR         = Path.home() / ".tanu"
CONFIG_FILE        = CONFIG_DIR / "config.json"
LEGACY_CONFIG_DIR  = Path.home() / ".bujji"
LEGACY_CONFIG_FILE = LEGACY_CONFIG_DIR / "config.json"
WORKSPACE_DEFAULT  = CONFIG_DIR / "workspace"


def get_base_dir() -> Path:
    """Repository root (parent of the src/tanu package)."""
    return Path(__file__).resolve().parent.parent.parent


def get_asset_path(name: str) -> Path:
    """Path to a bundled asset (whisper.cpp, piper, …)."""
    return Path(__file__).resolve().parent / "assets" / name


def get_deskbot_config(cfg: dict) -> dict:
    """Deskbot config with resolved asset paths."""
    assets = Path(__file__).resolve().parent / "assets"

    defaults = {
        "whisper_bin":    str(assets / "whisper.cpp" / "build" / "bin" / "main"),
        "whisper_model":  str(assets / "whisper.cpp" / "models" / "ggml-tiny.en.bin"),
        "whisper_threads": 4,
        "piper_bin":      str(assets / "piper" / "piper"),
        "piper_model":    str(assets / "piper" / "voices" / "en_US-lessac-medium.onnx"),
    }

    dc = dict(cfg.get("deskbot", {}))
    for k, v in defaults.items():
        dc.setdefault(k, v)
    return dc


# ── Defaults ─────────────────────────────────────────────────────────────────
PROVIDER_DEFAULTS = {
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    "openai":     ("https://api.openai.com/v1",    "gpt-4o"),
    "ollama":     ("http://localhost:11434/v1",    "llama3"),
    "anthropic":  ("https://api.anthropic.com/v1", "claude-3-5-sonnet-latest"),
}

DEFAULT_CONFIG = {
    "active_provider": "",
    "agents": {
        "defaults": {
            "workspace": "workspace",
            "model": "",
            "max_tokens": 8192,
            "temperature": 0.7,
            "max_tool_iterations": 20,
            "restrict_to_workspace": False,
        }
    },
    "providers": {},
    "channels": {
        "telegram": {"enabled": False, "token": "", "allow_from": []},
        "discord":  {"enabled": False, "token": "", "allow_from": []},
    },
    "tools": {
        "web":  {"search": {"api_key": "", "max_results": 5}},
        "gmail": {"client_creds": ""},
    },
    "tool_paths": [],
}


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ── Load / save ─────────────────────────────────────────────────────────────

def _read_raw() -> dict:
    """Read on-disk config, migrating the legacy ~/.bujji location once."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)

    if LEGACY_CONFIG_FILE.exists():
        with open(LEGACY_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(
                f"[INFO] Migrated config {LEGACY_CONFIG_FILE} → {CONFIG_FILE}",
                file=sys.stderr,
            )
        except Exception:
            pass
        return data

    return {}


def load_config() -> dict:
    """Load config, deep-merge on-disk values over defaults."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    _deep_merge(cfg, _read_raw())

    # Voice / assistant sections
    if "tanu" not in cfg:
        cfg["tanu"] = {"voice_enabled": True, "stream_tts": True}
    if "wakeword" not in cfg:
        cfg["wakeword"] = {
            "enabled": False, "engine": "openwakeword",
            "model_path": "", "threshold": 0.5,
        }
    cfg["deskbot"] = get_deskbot_config(cfg)

    # Inject tool_paths for ToolRegistry auto-discovery
    tools_dir = str(Path(__file__).resolve().parent / "tools")
    if tools_dir not in [p.get("path") for p in cfg.get("tool_paths", [])]:
        cfg.setdefault("tool_paths", []).append(
            {"path": tools_dir, "package": "tanu.tools"}
        )

    return cfg


def save_config(cfg: dict) -> None:
    """Persist config to ~/.tanu/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── Accessors ───────────────────────────────────────────────────────────────

def get_active_provider(cfg: dict):
    """Return (provider_name, api_key, api_base, model)."""
    pname = cfg.get("active_provider", "")
    if not pname:
        return "", "", "", ""
    provider = cfg.get("providers", {}).get(pname, {})
    defaults = cfg.get("agents", {}).get("defaults", {})
    return (
        pname,
        provider.get("api_key", ""),
        provider.get("api_base", ""),
        defaults.get("model", ""),
    )


def workspace_path(cfg: dict) -> Path:
    """Resolve the configured workspace path (relative → repo root)."""
    ws = cfg.get("agents", {}).get("defaults", {}).get("workspace", "")
    if not ws:
        return WORKSPACE_DEFAULT
    p = Path(ws).expanduser()
    if not p.is_absolute():
        p = get_base_dir() / p
    return p
