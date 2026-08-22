"""Small, dependency-free security helpers shared by local interfaces."""

import copy
import re
from urllib.parse import urlparse


_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SECRET_KEYS = {
    "access_token",
    "api_key",
    "client_creds",
    "client_secret",
    "refresh_token",
    "token",
}


def safe_skill_name(value: object) -> str:
    """Validate a skill directory name and reject traversal or hidden paths."""
    name = str(value or "").strip().lower()
    if not _SKILL_NAME_RE.fullmatch(name):
        raise ValueError(
            "Skill name must be 1-64 lowercase letters, numbers, hyphens, or underscores"
        )
    return name


def origin_is_local(origin: str) -> bool:
    """Accept same-machine browser origins; native clients usually omit Origin."""
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    except ValueError:
        return False


def mask_secrets(config: dict) -> dict:
    """Return a deep copy with common credential fields safely masked."""
    masked = copy.deepcopy(config)

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in _SECRET_KEYS and isinstance(child, str) and child:
                    value[key] = child[:6] + "…" if len(child) > 6 else "…"
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(masked)
    return masked
