"""Sabbath — your agent never rests. Now it rests with you.

Once a week (say, Saturday 18:00 for 24 hours) Hermes keeps a day of rest with you: it says
goodnight on your phone, pauses its own scheduled jobs, keeps you company in anything but work,
sets aside what can wait, and when the rest ends sends one gentle digest while the jobs catch up.
"""

from __future__ import annotations

import fcntl
import json
import logging
import threading
import time

from . import sabbath_core as core
from . import sabbath_store as store

log = logging.getLogger("sabbath")
TICK_SECONDS = 20
HERE_WINDOW = 120  # seconds a "/sabbath here" seen at the gateway stays claimable
_ctx = None


def _settings() -> dict:
    if _ctx is None:
        return {}
    return {k: _ctx.get_config(k, default) for k, default in store.SETTINGS.items()}


def _sync(state: dict) -> None:
    store.apply_settings(state, _settings())


# --- every turn: while you rest, Hermes is told so ----------------------------------

def _on_llm_call(platform=None, **_kw):
    if platform in ("cron",):  # Hermes' own jobs are asleep anyway
        return None
    try:
        with store.locked_state() as s:
            ctx_text = core.context(s, time.time())
        return {"context": ctx_text} if ctx_text else None
    except Exception as exc:  # never block a turn
        log.warning("sabbath context failed: %s", exc)
        return None


async def _on_gateway_message(event=None, **_kw):
    """Remember the chat a '/sabbath here' came from (the command itself may run in the plugin host)."""
    try:
        if (event.text or "").strip().lower().startswith("/sabbath here"):
            src = event.source
            platform = getattr(src.platform, "value", src.platform)
            with store.locked_state() as s:
                s["here_pending"] = {"chat": f"{platform}:{src.chat_id}", "at": time.time()}
    except Exception as exc:
        log.debug("sabbath here capture failed: %s", exc)
    return None


# --- background: begin and end on time (one process at a time) ----------------------

def _ticker(stop: threading.Event) -> None:
    lock_file = open(store.data_dir() / "ticker.lock", "w")
    held = False
    while not stop.wait(0 if not held else TICK_SECONDS):
        try:
            if not held:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = True
                except OSError:
                    stop.wait(TICK_SECONDS)
                    continue
            with store.locked_state() as s:
                _sync(s)
                actions = core.tick(s, time.time(), store.runnable_jobs)
            store.perform(actions)
        except Exception as exc:
            log.warning("sabbath tick failed: %s", exc)
    lock_file.close()


# --- /sabbath -----------------------------------------------------------------------

USAGE = "/sabbath [status | here | now [hours] | try | end | ox [why] | keep | stop | doctor]"


def _session_chat() -> str:
    """platform:chat of the messaging conversation running this command ('' elsewhere)."""
    try:
        from gateway.session_context import get_session_env
        platform = get_session_env("HERMES_SESSION_PLATFORM", "").strip().lower()
        chat = get_session_env("HERMES_SESSION_CHAT_ID", "").strip()
        if platform and chat and platform not in ("cli", "tui", "desktop", "local", "api_server"):
            return f"{platform}:{chat}"
    except Exception:
        pass
    return ""


def _current_chat() -> str:
    try:
        from gateway.session_context import get_session_env
        platform = get_session_env("HERMES_SESSION_PLATFORM", "").strip().lower()
        chat = get_session_env("HERMES_SESSION_CHAT_ID", "").strip()
        if platform and chat and platform not in ("cli", "tui", "desktop", "local", "api_server"):
            return f"{platform}:{chat}"
    except Exception:
        pass
    with store.locked_state() as s:
        pend = s.pop("here_pending", None)
    if pend and time.time() - pend["at"] < HERE_WINDOW:
        return pend["chat"]
    return ""


def _status(s: dict) -> str:
    now = time.time()
    v = core.public_view(s, now)
    lines = ["🕯 Sabbath"]
    if v["rest"]:
        r = v["rest"]
        lines.append(f"Resting until {r['ends_label']} ({core.span(r['left'])} left)"
                     + (" · lifted for something urgent" if r["ox_active"] else ""))
        lines.append(f"Jobs resting: {len(r['held'])} · Set aside: {len(r['basket'])}")
    elif "error" in v["window"]:
        lines.append(v["window"]["error"])
    else:
        w = v["window"]
        lines.append((f"Weekly: {w['start_label']} → {w['end_label']}" if s["keeping"]
                      else f"Weekly rest is off (would be {w['start_label']} → {w['end_label']}): /sabbath keep"))
    lines.append(f"Says goodnight on: {', '.join(c.split(':')[0].capitalize() for c in s['owner']['channels']) or '— (/sabbath here)'}")
    kept = [h for h in s["history"] if h["kind"] != "try"]
    if kept:
        lines.append(f"Rests kept: {len(kept)} · {v['hours_rested']:g} hours in all")
    return "\n".join(lines)


def run(raw: str) -> str:
    parts = (raw or "").strip().split()
    verb = parts[0].lower() if parts else "status"
    rest = " ".join(parts[1:])
    with store.locked_state() as s:
        _sync(s)
    if verb == "here":
        chat = _current_chat()
        if not chat:
            return "Send /sabbath here from the chat where you want Hermes to say goodnight (Telegram, Signal…)."
        with store.locked_state() as s:
            s["owner"]["channels"] = [chat]
            core._log(s, time.time(), f"Hermes will say goodnight on {chat.split(':')[0].capitalize()}.")
        store.notify_desktop()
        return f"Got it. When your Sabbath begins and ends, I'll write to you here on {chat.split(':')[0].capitalize()}."
    if verb == "now":
        try:
            hours = float(rest) if rest else None
        except ValueError:
            return "Usage: /sabbath now [hours]"
        with store.locked_state() as s:
            hours = hours or s["hours"]
        return store.begin_now(max(0.1, min(72.0, hours)) * 3600, here=_session_chat())
    if verb == "try":
        return store.begin_now(core.TRY_SECONDS, kind="try", here=_session_chat())
    if verb == "end":
        return store.end_now(here=_session_chat())
    if verb == "ox":
        with store.locked_state() as s:
            out = core.ox(s, time.time(), rest)
        store.notify_desktop()
        return out
    if verb in ("keep", "stop"):
        with store.locked_state() as s:
            s["keeping"] = verb == "keep"
            core._log(s, time.time(), "Weekly rest on." if s["keeping"] else "Weekly rest off.")
            out = _status(s)
        store.notify_desktop()
        return out
    if verb == "doctor":
        with store.locked_state() as s:
            issues = store.doctor(s)
        return "All set." if not issues else "\n".join("• " + i for i in issues)
    with store.locked_state() as s:
        return _status(s) if verb in ("status", "") else USAGE


# --- tools ----------------------------------------------------------------------------

TOOLS = {
    "sabbath_set_aside": {
        "description": "During the user's Sabbath (day of rest), put a task or worry they agreed can wait into "
                       "the basket for after the rest. It comes back to them in the digest when the rest ends.",
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string", "description": "The thing set aside, in a short line in the user's words."},
        }, "required": ["item"]},
    },
    "sabbath_status": {
        "description": "Whether the user is resting now, until when, what is set aside, and their weekly rhythm.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _tool(name):
    def handler(args: dict, **_kw) -> str:
        try:
            with store.locked_state() as s:
                if name == "sabbath_set_aside":
                    item = core.set_aside(s, args.get("item", ""), time.time())
                    out = {"set_aside": item["text"], "note": "In the basket; it comes back in the digest."}
                else:
                    v = core.public_view(s)
                    out = {k: v[k] for k in ("keeping", "rest", "window", "hours_rested")}
            store.notify_desktop()
            return json.dumps(out)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
    return handler


def register(ctx):
    global _ctx
    _ctx = ctx
    for name, spec in TOOLS.items():
        ctx.register_tool(name=name, toolset="sabbath", schema={"name": name, **spec},
                          handler=_tool(name), emoji="🕯")
    ctx.register_hook("pre_llm_call", _on_llm_call)
    ctx.register_hook("pre_gateway_dispatch", _on_gateway_message)
    ctx.register_command("sabbath", run, description="A weekly day of rest, kept with Hermes",
                         args_hint="[status|here|now|try|end|ox|keep|stop]")
    stop = threading.Event()
    threading.Thread(target=_ticker, args=(stop,), name="sabbath-ticker", daemon=True).start()
    ctx.on_unload(stop.set)
