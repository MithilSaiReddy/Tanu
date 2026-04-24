"""
tanu/config.py - Tanu-specific configuration
"""

import os
from pathlib import Path

# Base paths - resolve at runtime
def get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent

def get_asset_path(name: str) -> Path:
    """Get path to asset (whisper.cpp, piper, etc.)"""
    return get_base_dir() / "assets" / name


def get_deskbot_config(cfg: dict) -> dict:
    """Get deskbot config with resolved asset paths."""
    base = get_base_dir()
    assets = base / "assets"
    
    defaults = {
        "whisper_bin": str(assets / "whisper.cpp" / "build" / "bin" / "main"),
        "whisper_model": str(assets / "whisper.cpp" / "models" / "ggml-tiny.en.bin"),
        "whisper_threads": 4,
        "piper_bin": str(assets / "piper" / "piper"),
        "piper_model": str(assets / "piper" / "voices" / "en_US-lessac-medium.onnx"),
    }
    
    dc = cfg.get("deskbot", {})
    for k, v in defaults.items():
        if k not in dc:
            dc[k] = v
    return dc


def load_config() -> dict:
    """Load Tanu config (merges with defaults)."""
    from bujji.config import load_config as load_bujji_cfg
    
    cfg = load_bujji_cfg()
    
    # Ensure tanu section exists
    if "tanu" not in cfg:
        cfg["tanu"] = {"voice_enabled": True, "stream_tts": True}
    
    # Ensure deskbot section exists with resolved paths
    cfg["deskbot"] = get_deskbot_config(cfg)
    
    return cfg
