from __future__ import annotations

"""
tanu/server.py  —  v3.0

Migrated from http.server to aiohttp for WebSocket support.
HTTP + WebSocket on the same port (7337).

Endpoints
─────────
GET  /                         → API status page
GET  /api/config               → masked config (for display)
GET  /api/config/raw           → masked config (legacy alias)
POST /api/config               → deep-merge + save any config fields
POST /api/config/test-telegram → verify a Telegram bot token live
POST /api/config/test-llm      → ping LLM provider
GET  /api/status               → health summary
GET  /api/memory               → USER.md
POST /api/memory               → save USER.md
GET  /api/skills               → list skills
GET  /api/tools                → active tools
GET  /api/events               → recent local runtime/skill events
POST /api/chat                 → SSE streaming chat (backward compat)
POST /api/clear                → clear session history
GET  /ws/chat                  → WebSocket chat (new)
"""

import asyncio
import json
import os
import queue
import signal
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
from tanu.runtime import MemoryWatchdog
from tanu.security import mask_secrets, origin_is_local, safe_skill_name
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


def _stream_queue_size() -> int:
    return max(16, min(int(_cfg.get("runtime", {}).get("stream_queue", 256)), 1024))


def _put_stream_item(q: queue.Queue, item, cancelled: threading.Event) -> None:
    """Apply backpressure without leaving a producer blocked after disconnect."""
    while not cancelled.is_set():
        try:
            q.put(item, timeout=0.1)
            return
        except queue.Full:
            continue


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _mask_config(cfg: dict) -> dict:
    return mask_secrets(cfg)


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
    memory_mb = _mgr.memory_budget.current_mb() if _mgr else 0.0
    memory_pressure = _mgr.memory_budget.pressure() if _mgr else "unknown"
    return web.json_response({
        "configured": bool(pname),
        "provider": pname or "",
        "model": model or "",
        "api_base": api_base or "",
        "workspace": str(ws),
        "ws_exists": ws.exists(),
        "tools": tools,
        "web_search": bool(brave),
        "memory": {
            "rss_mb": round(memory_mb, 1),
            "pressure": memory_pressure,
            "soft_limit_mb": _mgr.memory_budget.soft_limit_mb if _mgr else 0,
            "hard_limit_mb": _mgr.memory_budget.hard_limit_mb if _mgr else 0,
        },
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
    # Never expose stored credentials over HTTP. Kept as a compatibility alias.
    return web.json_response(_mask_config(_cfg))


@web.middleware
async def local_origin_only(request, handler):
    if not origin_is_local(request.headers.get("Origin", "")):
        raise web.HTTPForbidden(text="Remote browser origins are not allowed")
    return await handler(request)


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


async def handle_get_events(request):
    topic = request.query.get("topic", "").strip().lower()
    try:
        limit = max(1, min(int(request.query.get("limit", "20")), 50))
    except ValueError:
        return web.json_response({"error": "limit must be an integer"}, status=400)
    events = _mgr.event_bus.recent(topic=topic, limit=limit) if _mgr else []
    return web.json_response({"events": events})


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
    try:
        name = safe_skill_name(body.get("name"))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
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
    try:
        name = safe_skill_name(body.get("name"))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
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
    try:
        name = safe_skill_name(body.get("name"))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
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
        },
    )
    await response.prepare(request)

    q: queue.Queue = queue.Queue(maxsize=_stream_queue_size())
    final: list[str] = []
    cancelled = threading.Event()

    def run():
        try:
            callbacks = {
                "on_token":      lambda t:    _put_stream_item(q, {"type": "token", "content": t}, cancelled),
                "on_tool_start": lambda n, a: _put_stream_item(q, {"type": "tool_start", "name": n, "args": a}, cancelled),
                "on_tool_done":  lambda n, r: _put_stream_item(q, {"type": "tool_done", "name": n,
                                                                    "result": r[:600] + ("…" if len(r) > 600 else "")}, cancelled),
                "on_error":      lambda e:    _put_stream_item(q, {"type": "error", "content": e}, cancelled),
            }
            agent = _mgr.get(session_id, callbacks=callbacks)
            history = _mgr.history(session_id)
            result = agent.run(message, history=history, stream=True, cancel_event=cancelled)
            final.append(result or "")
        except Exception as e:
            _put_stream_item(q, {"type": "error", "content": str(e)}, cancelled)
        finally:
            _put_stream_item(q, None, cancelled)

    threading.Thread(target=run, daemon=True).start()

    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            break
        try:
            await response.write(f"data: {json.dumps(item)}\n\n".encode())
        except (ConnectionResetError, RuntimeError):
            cancelled.set()
            break

    if cancelled.is_set():
        return response

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
    q: queue.Queue = queue.Queue(maxsize=_stream_queue_size())
    cancelled = threading.Event()

    def run():
        try:
            callbacks = {
                "on_token":      lambda t:    _put_stream_item(q, {"type": "token", "content": t}, cancelled),
                "on_tool_start": lambda n, a: _put_stream_item(q, {"type": "tool_start", "name": n, "args": a}, cancelled),
                "on_tool_done":  lambda n, r: _put_stream_item(q, {"type": "tool_done", "name": n,
                                                                    "result": r[:600] + ("…" if len(r) > 600 else "")}, cancelled),
                "on_error":      lambda e:    _put_stream_item(q, {"type": "error", "content": e}, cancelled),
            }
            agent = _mgr.get(session_id, callbacks=callbacks)
            history = _mgr.history(session_id)
            result = agent.run(message, history=history, stream=True, cancel_event=cancelled)
            _mgr.append(session_id, "user", message)
            _mgr.append(session_id, "assistant", result or "")
            if result:
                _put_stream_item(q, {"type": "response", "content": result}, cancelled)
        except Exception as e:
            _put_stream_item(q, {"type": "error", "content": str(e)}, cancelled)
        finally:
            _put_stream_item(q, None, cancelled)

    threading.Thread(target=run, daemon=True).start()

    await ws.send_json({"type": "state", "state": "thinking"})

    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            break
        if ws.closed:
            cancelled.set()
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
    app = web.Application(middlewares=[local_origin_only], client_max_size=1024**2)

    # GET routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_get_status)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_get("/api/config/raw", handle_get_config_raw)
    app.router.add_get("/api/memory", handle_get_memory)
    app.router.add_get("/api/skills", handle_get_skills)
    app.router.add_get("/api/tools", handle_get_tools)
    app.router.add_get("/api/events", handle_get_events)
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
    memory_cfg = cfg.get("runtime", {}).get("memory", {})

    def on_memory_pressure(level: str, current_mb: float) -> None:
        _mgr.event_bus.publish(
            f"memory.{level}",
            {"rss_mb": round(current_mb, 1)},
            source="server",
        )
        if level == "hard":
            print(
                f"[ERROR] Memory hard limit reached: {current_mb:.1f} MB; stopping server",
                file=sys.stderr,
            )
            os.kill(os.getpid(), signal.SIGTERM)

    watchdog = MemoryWatchdog(
        _mgr.memory_budget,
        on_pressure=on_memory_pressure,
        interval_seconds=memory_cfg.get("watchdog_interval_seconds", 2.0),
    )
    watchdog.start()

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

    try:
        web.run_app(app, host=host, port=port, print=None if quiet else None)
    finally:
        watchdog.stop()
