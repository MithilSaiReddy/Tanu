from __future__ import annotations

"""
tanu/server.py  —  v3.0

Migrated from http.server to aiohttp for WebSocket support.
HTTP + WebSocket on the same port (7337).

Endpoints
─────────
GET  /                         → API status page
GET  /api/config               → masked config (for display)
GET  /api/config/raw           → full config with real keys (populates forms)
POST /api/config               → deep-merge + save any config fields
POST /api/config/test-telegram → verify a Telegram bot token live
POST /api/config/test-llm      → ping LLM provider
GET  /api/status               → health summary
GET  /api/memory               → USER.md
POST /api/memory               → save USER.md
GET  /api/skills               → list skills
GET  /api/tools                → active tools
POST /api/chat                 → SSE streaming chat (backward compat)
POST /api/clear                → clear session history
GET  /ws/chat                  → WebSocket chat (new)
"""

import asyncio
import json
import queue
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web

from tanu.config import (
    CONFIG_FILE, PROVIDER_DEFAULTS, get_active_provider,
    load_config, save_config, workspace_path,
)
from tanu.session import SessionManager

# ── Gmail auth helpers ──────────────────────────────────────────────

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
GMAIL_TOKEN_FILE = "tanu/gmail_token.json"


def _gmail_ensure_deps() -> str | None:
    try:
        import google.auth  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        return "pip install google-auth google-auth-oauthlib google-api-python-client"
    return None


def _gmail_token_path(cfg) -> Path:
    return workspace_path(cfg) / GMAIL_TOKEN_FILE


def _gmail_is_authenticated(cfg) -> bool:
    return _gmail_token_path(cfg).exists()


SESSION_ID = "tanu-desktop"

_cfg: dict = {}
_mgr: Optional[SessionManager] = None
_gmail_current_flow: Optional[object] = None
_gmail_flow_lock = threading.Lock()


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _mask_config(cfg: dict) -> dict:
    import copy
    s = copy.deepcopy(cfg)
    for pname, pcfg in s.get("providers", {}).items():
        key = pcfg.get("api_key", "")
        if key and key not in ("ollama", ""):
            s["providers"][pname]["api_key"] = key[:8] + "…" if len(key) > 8 else "…"
    tg = s.get("channels", {}).get("telegram", {})
    if tg.get("token"):
        t = tg["token"]
        s["channels"]["telegram"]["token"] = t[:10] + "…" if len(t) > 10 else "…"
    dc = s.get("channels", {}).get("discord", {})
    if dc.get("token"):
        t = dc["token"]
        s["channels"]["discord"]["token"] = t[:10] + "…" if len(t) > 10 else "…"
    brave = s.get("tools", {}).get("web", {}).get("search", {}).get("api_key", "")
    if brave:
        s["tools"]["web"]["search"]["api_key"] = brave[:6] + "…"
    notion_key = s.get("tools", {}).get("notion", {}).get("api_key", "")
    if notion_key:
        s["tools"]["notion"]["api_key"] = notion_key[:6] + "…"
    return s


def _strip_masked(obj, depth=0):
    """Remove values containing '…' so masked display values never overwrite real keys."""
    if not isinstance(obj, dict) or depth > 8:
        return
    for k in list(obj.keys()):
        v = obj[k]
        if isinstance(v, str) and "…" in v:
            del obj[k]
        elif isinstance(v, dict):
            _strip_masked(v, depth + 1)


# ── GET Handlers ────────────────────────────────────────────────────

async def handle_index(request):
    return web.Response(
        text="Tanu API server running. WebSocket available at /ws/chat",
        content_type="text/plain",
    )


async def handle_get_status(request):
    pname, api_key, api_base, model = get_active_provider(_cfg)
    ws = workspace_path(_cfg)
    tg = _cfg.get("channels", {}).get("telegram", {})
    dc = _cfg.get("channels", {}).get("discord", {})
    brave = _cfg.get("tools", {}).get("web", {}).get("search", {}).get("api_key", "")
    tools = []
    try:
        from tanu.tools import ToolRegistry
        tools = [s["function"]["name"] for s in ToolRegistry(_cfg).schema()]
    except Exception:
        pass
    return web.json_response({
        "configured": bool(pname),
        "provider": pname or "",
        "model": model or "",
        "api_base": api_base or "",
        "workspace": str(ws),
        "ws_exists": ws.exists(),
        "tools": tools,
        "web_search": bool(brave),
        "telegram": {
            "enabled": tg.get("enabled", False),
            "has_token": bool(tg.get("token", "")),
            "allow_from": tg.get("allow_from", []),
        },
        "discord": {
            "enabled": dc.get("enabled", False),
            "has_token": bool(dc.get("token", "")),
            "allow_from": dc.get("allow_from", []),
        },
    })


async def handle_get_config(request):
    return web.json_response(_mask_config(_cfg))


async def handle_get_config_raw(request):
    return web.json_response(_cfg)


async def handle_get_memory(request):
    path = workspace_path(_cfg) / "USER.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return web.Response(text=text, content_type="text/plain; charset=utf-8")


async def handle_get_skills(request):
    ws = workspace_path(_cfg)
    out = []
    sd = ws / "skills"
    if sd.exists():
        for f in sorted(sd.glob("*/SKILL.md")):
            try:
                out.append({"name": f.parent.name, "content": f.read_text(encoding="utf-8"), "path": str(f)})
            except Exception:
                pass
    return web.json_response(out)


async def handle_get_tools(request):
    try:
        from tanu.tools import ToolRegistry
        tools = [{"name": s["function"]["name"], "description": s["function"]["description"]}
                 for s in ToolRegistry(_cfg).schema()]
        return web.json_response(tools)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_get_history(request):
    sid = request.query.get("session_id", SESSION_ID)
    limit = int(request.query.get("limit", "50"))
    offset = int(request.query.get("offset", "0"))
    hist = _mgr.history(sid) if _mgr else []
    total = len(hist)
    chunk = hist[offset:offset + limit]
    return web.json_response({"messages": chunk, "total": total, "offset": offset, "limit": limit})


# ── Gmail Auth Handlers ─────────────────────────────────────────────

async def handle_gmail_auth_url(request):
    global _gmail_current_flow
    err = _gmail_ensure_deps()
    if err:
        return web.json_response({"ok": False, "error": err})

    client_creds = _cfg.get("tools", {}).get("gmail", {}).get("client_creds", "")
    if not client_creds:
        return web.json_response({
            "ok": False, "error": "Gmail client credentials not configured",
            "help": "Add tools.gmail.client_creds in Settings → Tools or config.json",
        })

    try:
        client_config = json.loads(client_creds)
    except json.JSONDecodeError:
        return web.json_response({"ok": False, "error": "Invalid JSON in tools.gmail.client_creds"})

    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
    flow.redirect_uri = client_config["installed"]["redirect_uris"][0]
    auth_url, _ = flow.authorization_url(prompt="consent")

    with _gmail_flow_lock:
        _gmail_current_flow = flow
    return web.json_response({"ok": True, "auth_url": auth_url})


async def handle_gmail_auth_complete(request):
    global _gmail_current_flow
    body = await request.json()
    err = _gmail_ensure_deps()
    if err:
        return web.json_response({"ok": False, "error": err})

    with _gmail_flow_lock:
        if _gmail_current_flow is None:
            return web.json_response({"ok": False, "error": "No auth flow in progress. Click Connect first."})
        flow = _gmail_current_flow
        _gmail_current_flow = None

    code = (body.get("code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "error": "Authorization code is required"})

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        return web.json_response({"ok": False, "error": f"Token exchange failed: {e}"})

    token_path = _gmail_token_path(_cfg)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(flow.credentials.to_json())

    return web.json_response({"ok": True})


async def handle_gmail_status(request):
    ok = _gmail_is_authenticated(_cfg)
    return web.json_response({"ok": ok})


async def handle_gmail_disconnect(request):
    token_path = _gmail_token_path(_cfg)
    if token_path.exists():
        token_path.unlink()
    return web.json_response({"ok": True})


# ── POST Handlers ───────────────────────────────────────────────────

async def handle_post_config(request):
    global _cfg, _mgr
    body = await request.json()
    _strip_masked(body)
    _deep_merge(_cfg, body)
    save_config(_cfg)
    _mgr = SessionManager(_cfg)
    return web.json_response({"ok": True})


async def handle_post_test_telegram(request):
    body = await request.json()
    token = body.get("token", "").strip()
    if not token:
        return web.json_response({"ok": False, "error": "No token provided"})
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
        data = r.json()
        if data.get("ok"):
            bot = data["result"]
            return web.json_response({"ok": True, "username": bot.get("username"), "name": bot.get("first_name")})
        else:
            return web.json_response({"ok": False, "error": data.get("description", "Invalid token")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_post_test_llm(request):
    body = await request.json()
    pname = body.get("provider") or None
    api_key = body.get("api_key") or None
    api_base = body.get("api_base") or None
    model = body.get("model") or None
    if not pname:
        pname, api_key, api_base, model = get_active_provider(_cfg)
    if not pname:
        return web.json_response({"ok": False, "error": "No provider specified"})
    try:
        from tanu.llm import LLMProvider
        llm = LLMProvider(pname, api_key, api_base, model, max_tokens=8)
        resp = llm.chat([{"role": "user", "content": "say hi"}], stream=False)
        preview = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "")[:80]
        return web.json_response({"ok": True, "model": model, "preview": preview})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_post_memory(request):
    body = await request.json()
    ws = workspace_path(_cfg)
    ws.mkdir(parents=True, exist_ok=True)
    content = body.get("content", "")
    tmp = ws / "USER.tmp"
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(ws / "USER.md")
    return web.json_response({"ok": True, "bytes": len(content)})


async def handle_post_clear(request):
    body = await request.json()
    sid = body.get("session_id", "web:default")
    if _mgr:
        _mgr.clear(sid)
    return web.json_response({"ok": True})


async def handle_post_skill(request):
    body = await request.json()
    name = (body.get("name") or "").strip().replace(" ", "-").lower()
    content = (body.get("content") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Skill name is required"}, status=400)
    if not content:
        return web.json_response({"ok": False, "error": "Skill content is required"}, status=400)
    ws = workspace_path(_cfg)
    skill_dir = ws / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        return web.json_response({
            "ok": False,
            "error": f"Skill '{name}' already exists. Use update to edit it."
        }, status=409)
    skill_file.write_text(content, encoding="utf-8")
    return web.json_response({"ok": True, "name": name, "path": str(skill_file)})


async def handle_put_skill(request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    content = (body.get("content") or "").strip()
    if not name or not content:
        return web.json_response({"ok": False, "error": "name and content required"}, status=400)
    ws = workspace_path(_cfg)
    skill_file = ws / "skills" / name / "SKILL.md"
    if not skill_file.exists():
        return web.json_response({"ok": False, "error": f"Skill '{name}' not found"}, status=404)
    skill_file.write_text(content, encoding="utf-8")
    return web.json_response({"ok": True, "name": name})


async def handle_delete_skill(request):
    import shutil
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    ws = workspace_path(_cfg)
    skill_dir = ws / "skills" / name
    if not skill_dir.exists():
        return web.json_response({"ok": False, "error": f"Skill '{name}' not found"}, status=404)
    shutil.rmtree(skill_dir)
    return web.json_response({"ok": True, "name": name})


# ── SSE Chat (backward compat for web UI) ───────────────────────────

async def handle_post_chat(request):
    body = await request.json()
    message = (body.get("message") or "").strip()
    session_id = body.get("session_id") or "web:default"
    if not message:
        return web.json_response({"error": "Empty message"}, status=400)

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)

    q: queue.Queue = queue.Queue()
    final: list[str] = []

    def run():
        try:
            callbacks = {
                "on_token":      lambda t:    q.put({"type": "token",      "content": t}),
                "on_tool_start": lambda n, a: q.put({"type": "tool_start", "name": n, "args": a}),
                "on_tool_done":  lambda n, r: q.put({"type": "tool_done",  "name": n,
                                                      "result": r[:600] + ("…" if len(r) > 600 else "")}),
                "on_error":      lambda e:    q.put({"type": "error",      "content": e}),
            }
            agent = _mgr.get(session_id, callbacks=callbacks)
            history = _mgr.history(session_id)
            result = agent.run(message, history=history, stream=True)
            final.append(result or "")
        except Exception as e:
            q.put({"type": "error", "content": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            break
        await response.write(f"data: {json.dumps(item)}\n\n".encode())

    reply = "".join(final)
    _mgr.append(session_id, "user", message)
    _mgr.append(session_id, "assistant", reply)
    await response.write(f"data: {json.dumps({'type': 'done', 'content': reply})}\n\n".encode())
    await response.write_eof()
    return response


# ── WebSocket Chat ──────────────────────────────────────────────────

async def handle_ws_chat(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    session_id = request.query.get("session_id", "godot:main")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type", "")

                if msg_type == "chat":
                    message = (data.get("message") or "").strip()
                    if not message:
                        await ws.send_json({"type": "error", "message": "Empty message"})
                        continue
                    await _ws_stream_chat(ws, message, session_id)

                elif msg_type == "cancel":
                    pass  # TODO: implement cancellation

                elif msg_type == "config":
                    await ws.send_json({"type": "config", "data": _mask_config(_cfg)})

                elif msg_type == "status":
                    pname, _, _, model = get_active_provider(_cfg)
                    await ws.send_json({
                        "type": "status",
                        "provider": pname or "",
                        "model": model or "",
                    })

                else:
                    await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

            elif msg.type == web.WSMsgType.ERROR:
                break

    except Exception:
        pass

    return ws


async def _ws_stream_chat(ws: web.WebSocketResponse, message: str, session_id: str):
    """Run agent in thread, stream tokens over WebSocket."""
    q: queue.Queue = queue.Queue()

    def run():
        try:
            callbacks = {
                "on_token":      lambda t:    q.put({"type": "token",      "content": t}),
                "on_tool_start": lambda n, a: q.put({"type": "tool_start", "name": n, "args": a}),
                "on_tool_done":  lambda n, r: q.put({"type": "tool_done",  "name": n,
                                                      "result": r[:600] + ("…" if len(r) > 600 else "")}),
                "on_error":      lambda e:    q.put({"type": "error",      "content": e}),
            }
            agent = _mgr.get(session_id, callbacks=callbacks)
            history = _mgr.history(session_id)
            result = agent.run(message, history=history, stream=True)
            _mgr.append(session_id, "user", message)
            _mgr.append(session_id, "assistant", result or "")
            if result:
                q.put({"type": "response", "content": result})
        except Exception as e:
            q.put({"type": "error", "content": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

    await ws.send_json({"type": "state", "state": "thinking"})

    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            break
        if ws.closed:
            break
        await ws.send_json(item)

    if not ws.closed:
        await ws.send_json({"type": "done"})


# ── Circle check (for floating orb) ─────────────────────────────────

async def handle_get_circle_check(request):
    ws = workspace_path(_cfg)
    items = []

    try:
        rem_file = ws / "tanu" / "reminders.json"
        if rem_file.exists():
            data = json.loads(rem_file.read_text())
            now = datetime.now()
            due = [
                r for r in data.get("reminders", [])
                if not r.get("triggered")
                and datetime.fromisoformat(r["time"]) <= now
            ]
            if due:
                msgs = [r["message"] for r in due[:3]]
                if len(due) == 1:
                    items.append(f"Reminder: {msgs[0]}")
                else:
                    items.append(f"{len(due)} reminders due")
    except Exception:
        pass

    try:
        token_file = ws / "tanu" / "gmail_token.json"
        if token_file.exists():
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials.from_authorized_user_file(str(token_file))
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            results = service.users().messages().list(
                userId="me", q="in:inbox is:unread", maxResults=1
            ).execute()
            unread = results.get("resultSizeEstimate", 0)
            if unread > 0:
                items.append(f"{unread} unread")
    except Exception:
        pass

    if items:
        return web.json_response({"text": "  |  ".join(items), "type": "update"})

    import random
    if random.randint(1, 3) == 1:
        greetings = ["Hey!", "Hello there!", "All caught up!", "Ready when you are!"]
        return web.json_response({"text": random.choice(greetings), "type": "greeting"})
    else:
        return web.json_response({"text": None})


# ── App Setup ───────────────────────────────────────────────────────

def _build_app() -> web.Application:
    app = web.Application()

    # GET routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_get_status)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_get("/api/config/raw", handle_get_config_raw)
    app.router.add_get("/api/memory", handle_get_memory)
    app.router.add_get("/api/skills", handle_get_skills)
    app.router.add_get("/api/tools", handle_get_tools)
    app.router.add_get("/api/history", handle_get_history)
    app.router.add_get("/api/gmail/auth-url", handle_gmail_auth_url)
    app.router.add_get("/api/gmail/status", handle_gmail_status)
    app.router.add_get("/api/gmail/disconnect", handle_gmail_disconnect)
    app.router.add_get("/api/circle/check", handle_get_circle_check)

    # POST routes
    app.router.add_post("/api/config", handle_post_config)
    app.router.add_post("/api/config/test-telegram", handle_post_test_telegram)
    app.router.add_post("/api/config/test-llm", handle_post_test_llm)
    app.router.add_post("/api/memory", handle_post_memory)
    app.router.add_post("/api/chat", handle_post_chat)
    app.router.add_post("/api/clear", handle_post_clear)
    app.router.add_post("/api/gmail/auth-complete", handle_gmail_auth_complete)
    app.router.add_post("/api/skills", handle_post_skill)
    app.router.add_post("/api/skills/update", handle_put_skill)
    app.router.add_post("/api/skills/delete", handle_delete_skill)

    # WebSocket route
    app.router.add_get("/ws/chat", handle_ws_chat)

    return app


def run_server(cfg: dict, host: str = "127.0.0.1", port: int = 7337, quiet: bool = False) -> None:
    global _cfg, _mgr
    _cfg = cfg
    _mgr = SessionManager(cfg)

    app = _build_app()
    url = f"http://{host}:{port}"

    if not quiet:
        print(f"\n🎙️ Tanu server  →  {url}")
        print(f"   WebSocket     →  ws://{host}:{port}/ws/chat")
        print("   Press Ctrl+C to stop.\n")

        try:
            import webbrowser
            import threading as _t
            _t.Timer(0.6, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    web.run_app(app, host=host, port=port, print=None if quiet else None)
