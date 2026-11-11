"""Sabbath I/O: the state file, settings, Hermes's cron jobs, and sending.

Shared by the agent half (``__init__.py``) and the Desktop backend (``dashboard/plugin_api.py``),
which may run in different processes, so every read-modify-write holds an exclusive file lock.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import time
from pathlib import Path

try:
    from . import sabbath_core as core
except ImportError:  # loaded as a top-level module (Desktop backend, tests)
    import sabbath_core as core

log = logging.getLogger("sabbath")
PLUGIN_ID = "sabbath"
PAUSE_REASON = "Sabbath"  # jobs Sabbath paused carry this reason; only those are woken again

SETTINGS = {  # key -> default; plugin.yaml config_schema
    "owner_name": "",
    "begins": "sat 18:00",
    "hours": 24,
    "timezone": "",
    "keep_running": "",
}


def data_dir() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir
        path = Path(plugin_data_dir(PLUGIN_ID))
    except Exception:  # running outside Hermes (tests, scripts)
        path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "plugin-data" / PLUGIN_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextlib.contextmanager
def locked_state():
    """Yield the state dict under an exclusive lock and save it on exit."""
    d = data_dir()
    with open(d / "state.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = d / "state.json"
        try:
            state = {**core.new_state(), **json.loads(path.read_text())} if path.exists() else core.new_state()
        except ValueError:
            log.error("sabbath: state.json unreadable; keeping a copy and starting fresh")
            path.rename(d / f"state.broken.{int(time.time())}.json")
            state = core.new_state()
        yield state
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        os.replace(tmp, path)


def read_state() -> dict:
    with locked_state() as s:
        return json.loads(json.dumps(s))


def apply_settings(state: dict, settings: dict) -> None:
    """Settings › Plugins › Sabbath into the state (invalid values are ignored, the last good one stays)."""
    if str(settings.get("owner_name") or "").strip():
        state["owner"]["name"] = str(settings["owner_name"]).strip()
    begins = str(settings.get("begins") or "").strip()
    if begins:
        try:
            core.parse_begins(begins)
            state["begins"] = begins
        except ValueError:
            pass
    try:
        state["hours"] = max(1, min(72, int(settings.get("hours") or 24)))
    except (TypeError, ValueError):
        pass
    state["tz"] = str(settings.get("timezone") or "").strip()
    state["keep_running"] = [k.strip() for k in str(settings.get("keep_running") or "").split(",") if k.strip()]


# --- Hermes's own scheduled jobs, through the public cronjob_manage tool -----------
# Only the agent half has a plugin context to dispatch it. The Desktop backend reads the job list the
# agent's ticker keeps in the state, and queues its pauses and resumes for that ticker (<= 20 s).

_ctx = None


def use(ctx) -> None:
    global _ctx
    _ctx = ctx


def _cron(args: dict) -> dict:
    if _ctx is None:
        raise RuntimeError("no Hermes plugin context in this process")
    out = json.loads(_ctx.dispatch_tool("cronjob_manage", args) or "{}")
    if out.get("error") or out.get("success") is False:
        raise RuntimeError(out.get("error") or f"cronjob_manage {args.get('action')} failed")
    return out


def runnable_jobs(state: dict) -> list:
    """Hermes's runnable cron jobs ({id, name, schedule}); outside the agent, the last list it saw."""
    if _ctx is None:
        return list(state.get("jobs_seen") or [])
    try:
        jobs = _cron({"action": "list", "include_disabled": False})["jobs"]
    except Exception as exc:  # no cron here: nothing to hold
        log.info("sabbath: cron jobs unavailable (%s)", exc)
        return []
    state["jobs_seen"] = [{"id": j["job_id"], "name": j.get("name") or j["job_id"], "schedule": j.get("schedule") or ""}
                          for j in jobs if j.get("enabled", True) and j.get("state") != "paused"]
    return list(state["jobs_seen"])


def pause_jobs(jobs: list, until: float) -> list:
    """Pause each job; returns the ones actually paused."""
    paused = []
    reason = f"{PAUSE_REASON}: resting until {time.strftime('%a %H:%M', time.localtime(until))}"
    for j in jobs:
        try:
            _cron({"action": "pause", "job_id": j["id"], "reason": reason})
            paused.append(j)
        except Exception as exc:  # noqa: BLE001
            log.warning("sabbath: could not pause %s: %s", j["id"], exc)
    return paused


def resume_jobs(jobs: list) -> None:
    """Wake only the jobs Sabbath paused and nobody touched since (a job you paused yourself stays paused)."""
    try:
        listed = {j["job_id"]: j for j in _cron({"action": "list", "include_disabled": True})["jobs"]}
    except Exception as exc:  # noqa: BLE001
        log.warning("sabbath: could not list jobs to resume: %s", exc)
        return
    for j in jobs:
        job = listed.get(j["id"])
        if not job or not str(job.get("paused_reason") or "").startswith(PAUSE_REASON):
            continue
        try:
            _cron({"action": "resume", "job_id": j["id"]})
        except Exception as exc:  # noqa: BLE001
            log.warning("sabbath: could not resume %s: %s", j["id"], exc)


# --- sending ----------------------------------------------------------------------

def send_to(target: str, text: str) -> None:
    """One message to ``platform:ref`` through Hermes' own delivery."""
    # Public route only: the `hermes send` CLI (same delivery as the gateway, no agent loop), as an argv
    # list with no shell; the text goes over stdin.
    # ponytail: one process per message; swap for a public in-process send API when Hermes ships one.
    import importlib.util
    import shutil
    import subprocess
    import sys
    exe = shutil.which("hermes")
    if exe:
        cli = [exe]
    elif importlib.util.find_spec("hermes_cli"):  # inside Hermes but its launcher isn't on PATH: same entry point
        cli = [sys.executable, "-c", "import sys; from hermes_cli.main import main; sys.argv[0] = 'hermes'; sys.exit(main())"]
    else:
        raise RuntimeError("the hermes CLI is not on PATH")
    run = subprocess.run([*cli, "send", "--to", target, "--json"], input=text, capture_output=True, text=True, timeout=120)
    try:
        result = json.loads(run.stdout or "{}")
    except json.JSONDecodeError:
        result = {"error": (run.stderr or run.stdout or "send failed").strip()[:200]}
    if run.returncode != 0 or result.get("error") or result.get("success") is False:
        raise RuntimeError(result.get("error") or "send failed")


def perform(actions: list) -> None:
    cron = [a for a in actions if a["type"] in ("pause", "resume")]
    if cron and _ctx is None:  # Desktop backend: the agent's ticker carries these out
        with locked_state() as s:
            s["cron_queue"] = (s.get("cron_queue") or []) + cron
        actions = [a for a in actions if a not in cron]
    for a in actions:
        try:
            if a["type"] == "send":
                send_to(a["target"], a["text"])
            elif a["type"] == "pause":
                paused = pause_jobs(a["jobs"], a["until"])
                if len(paused) != len(a["jobs"]):  # the digest lists only what really rested
                    ids = {j["id"] for j in paused}
                    with locked_state() as s:
                        if s["rest"]:
                            s["rest"]["held"] = [j for j in s["rest"]["held"] if j["id"] in ids]
            elif a["type"] == "resume":
                resume_jobs(a["jobs"])
        except Exception as exc:  # noqa: BLE001 - a dead channel must not stop the rest
            log.warning("sabbath: %s failed: %s", a["type"], exc)
            with locked_state() as s:
                core._log(s, time.time(), f"Could not {a['type']}: {exc}")
    if actions:
        notify_desktop()


def notify_desktop() -> None:
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event(PLUGIN_ID, "state.changed", {})
    except Exception:
        pass


# --- the verbs, shared by the chat command and the Desktop page -----------------------

def _split_here(actions: list, here: str) -> tuple[list, str]:
    """A message meant for the chat the command came from becomes the command's reply (no duplicate)."""
    mine = [a for a in actions if a["type"] == "send" and here and a["target"] == here]
    return [a for a in actions if a not in mine], "\n".join(a["text"] for a in mine)


def begin_now(seconds: float, kind: str = "now", here: str = "") -> str:
    now = time.time()
    with locked_state() as s:
        if s["rest"]:
            return f"You're already resting, until {core.when(s, s['rest']['ends_at'], now)}."
        actions = core.begin(s, now, now + seconds, runnable_jobs(s), kind=kind)
        ends = core.when(s, s["rest"]["ends_at"], now)
        n = len(s["rest"]["held"])
    actions, reply = _split_here(actions, here)
    perform(actions)
    hint = "/sabbath ox if something truly can't wait; /sabbath end to stop early."
    if reply:
        return f"{reply}\n\n{hint}"
    return (f"🕯 Resting until {ends}. {core.plural(n, 'scheduled job')} {'is' if n == 1 else 'are'} resting too. "
            f"Talk to me about anything but work; {hint}")


def end_now(here: str = "") -> str:
    with locked_state() as s:
        actions = core.end(s, time.time(), early=True)
    actions, reply = _split_here(actions, here)
    perform(actions)
    return reply or ("☀ Your rest is over. Welcome back." if actions else "You weren't resting.")


def doctor(state: dict) -> list:
    issues = []
    if not state["owner"]["channels"]:
        issues.append("Hermes has nowhere to say goodnight and good morning: send /sabbath here from your phone.")
    if not state["keeping"]:
        issues.append("The weekly rest is off: /sabbath keep (or the switch on the Sabbath page).")
    try:
        core.parse_begins(state["begins"])
    except ValueError as exc:
        issues.append(f"Your start time can't be read: {exc}")
    return issues
