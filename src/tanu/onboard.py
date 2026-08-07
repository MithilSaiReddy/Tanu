"""
tanu/onboard.py — interactive configuration wizard.

Used by both `python3 main.py onboard` and `tanu onboard`.
Guides the user through provider selection, API key, model, and an
optional live connection test, then persists the config.
"""

from __future__ import annotations

import sys

from tanu import LOGO
from tanu.config import (
    PROVIDER_DEFAULTS,
    get_active_provider,
    load_config,
    save_config,
    workspace_path,
)

LOCAL_PROVIDERS = {"ollama"}


def _print_current(cfg: dict) -> None:
    """Show what is currently configured."""
    pname, api_key, api_base, model = get_active_provider(cfg)
    ws = workspace_path(cfg)

    print(f"\n{LOGO} Current configuration")
    print(f"   Provider:  {pname or '(none)'}")
    print(f"   Model:     {model or '(none)'}")
    print(f"   Workspace: {ws}")
    print()


def _resolve_provider(text: str) -> str | None:
    """Resolve a provider choice (number or name), or None if invalid."""
    text = (text or "").strip().lower()

    if not text:
        return None

    names = list(PROVIDER_DEFAULTS.keys())

    if text.isdigit():
        idx = int(text) - 1
        return names[idx] if 0 <= idx < len(names) else None

    for name in names:
        if text == name:
            return name

    return None


def _prompt_provider(cfg: dict) -> str | None:
    """Show the provider menu and get a valid choice. Returns None to quit."""
    print("Available LLM providers:")
    for i, (name, (api_base, model)) in enumerate(PROVIDER_DEFAULTS.items(), 1):
        marker = ""
        stored = cfg.get("providers", {}).get(name, {})
        if stored.get("api_key"):
            marker = "  (key set)"
        print(f"  {i:2}. {name:<12} default: {model}{marker}")

    while True:
        choice = input("\nChoose provider (number or name, Enter to quit): ").strip()
        if not choice:
            return None
        provider = _resolve_provider(choice)
        if provider is not None:
            return provider
        print(f"  Unknown provider '{choice}'. Pick a number or name from the list above.")


def _prompt_api_key(cfg: dict, provider: str) -> str:
    """Prompt for an API key, keeping an existing one if present."""
    existing = cfg.get("providers", {}).get(provider, {}).get("api_key", "")

    if provider in LOCAL_PROVIDERS:
        return existing or ""

    if existing:
        hint = " (Enter to keep existing key)"
    else:
        hint = " (no existing key)"
    key = input(f"Enter your {provider} API key{hint}: ").strip()

    if key:
        return key
    if existing:
        return existing
    return ""


def _prompt_model(provider: str, default_model: str) -> str:
    """Prompt for a model, defaulting to the provider's default."""
    model = input(f"Model (Enter = {default_model}): ").strip()
    return model or default_model


def _test_llm(provider: str, api_key: str, api_base: str, model: str) -> str:
    """Run a tiny live chat request. Returns the reply preview or raises."""
    from tanu.llm import LLMProvider

    llm = LLMProvider(provider, api_key, api_base, model, max_tokens=8)
    resp = llm.chat([{"role": "user", "content": "say hi"}], stream=False)
    preview = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    return preview[:80]


def run_onboard() -> None:
    """Run the interactive configuration wizard."""
    cfg = load_config()

    print(f"\n{LOGO} Welcome to Tanu\n")
    _print_current(cfg)

    provider = _prompt_provider(cfg)
    if provider is None:
        print("\nNothing changed. Run `python3 main.py tanu` to start.\n")
        return

    default_base, default_model = PROVIDER_DEFAULTS[provider]
    api_key = _prompt_api_key(cfg, provider)
    model = _prompt_model(provider, default_model)

    if not api_key and provider not in LOCAL_PROVIDERS:
        print(f"\n  [!] Warning: no API key set for '{provider}'. "
              f"The agent may fail when talking to the LLM.")

    test = input("\nTest the connection now? (y/N): ").strip().lower()
    if test in ("y", "yes"):
        print(f"\n  Testing {provider} / {model} ...")
        try:
            preview = _test_llm(provider, api_key, default_base, model)
            print(f"  [OK] Response: {preview}")
        except Exception as e:
            print(f"  [FAIL] {e}")
            keep = input("  Save anyway? (y/N): ").strip().lower()
            if keep not in ("y", "yes"):
                print("\nAborted. Nothing saved.\n")
                return

    cfg.setdefault("providers", {})[provider] = {
        "api_key": api_key,
        "api_base": default_base,
    }
    cfg["agents"]["defaults"]["model"] = model
    cfg["active_provider"] = provider
    save_config(cfg)

    print(f"\n✅ Config saved!")
    print(f"   Provider:  {provider}")
    print(f"   Model:     {model}")
    print(f"   Run:       python3 main.py tanu    (voice)")
    print(f"              python3 main.py tanu --text    (text)\n")
