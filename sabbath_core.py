"""Sabbath, the pure logic: the weekly window, beginning and ending a rest, the basket, the digest.

No I/O here. Functions take the state dict (and the current time) and return *actions* for
``sabbath_store.perform``: ``{"type": "send"|"pause"|"resume", ...}``. Tested without Hermes.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
OX_SECONDS = 3600          # "/sabbath ox" lifts the rest for an hour
TRY_SECONDS = 120          # the two-minute Sabbath, to see it work
HISTORY_KEEP = 104         # two years of weeks
LOG_KEEP = 200


def new_state() -> dict:
    return {
        "v": 1,
        "keeping": False,                       # the weekly rhythm is on
        "owner": {"name": "", "channels": []},  # where Hermes says goodnight and good morning
        "begins": "sat 18:00",                  # weekday + local time the rest begins
        "hours": 24,
        "tz": "",                               # IANA name; "" = the host's local time
        "keep_running": [],                     # cron job ids or names that never rest
        "rest": None,                           # the rest in progress
        "ended_window": 0.0,                    # start of a weekly window ended early (don't restart it)
        "history": [],
        "log": [],
    }


def _log(state: dict, now: float, text: str) -> None:
    state["log"] = (state["log"] + [{"at": now, "text": text}])[-LOG_KEEP:]


def _name(state: dict) -> str:
    return state["owner"]["name"]


def _send(targets: list, text: str) -> list:
    return [{"type": "send", "target": t, "text": text} for t in targets]


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# --- time ---------------------------------------------------------------------

def _tz(state: dict):
    if state.get("tz"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(state["tz"])
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def parse_begins(text: str) -> tuple[int, int, int]:
    """'sat 18:00' -> (weekday 0-6, hour, minute). Raises ValueError on anything else."""
    parts = (text or "").strip().lower().replace(".", ":").split()
    if len(parts) != 2 or parts[0][:3] not in DAYS:
        raise ValueError("Use a day and a time, e.g. 'sat 18:00' or 'sun 00:00'.")
    hh, _, mm = parts[1].partition(":")
    h, m = int(hh), int(mm or 0)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("The time must be between 00:00 and 23:59.")
    return DAYS.index(parts[0][:3]), h, m


def window(state: dict, now: float) -> tuple[float, float]:
    """The weekly window (start, end) that is in progress now, or else the next one."""
    wd, h, m = parse_begins(state["begins"])
    hours = max(1, min(72, int(state["hours"] or 24)))
    local = datetime.fromtimestamp(now, _tz(state))
    start = (local - timedelta(days=(local.weekday() - wd) % 7)).replace(hour=h, minute=m, second=0, microsecond=0)
    if start.timestamp() > now:  # this week's start is still ahead: the last one began a week ago
        start -= timedelta(days=7)
    if start.timestamp() + hours * 3600 <= now:  # that one has ended: the next one
        start += timedelta(days=7)
    return start.timestamp(), start.timestamp() + hours * 3600


def when(state: dict, ts: float, now: float | None = None) -> str:
    """'Sunday 18:00', or 'today 18:00' / 'tomorrow 18:00' when that's clearer."""
    tz = _tz(state)
    d, today = datetime.fromtimestamp(ts, tz), datetime.fromtimestamp(now or time.time(), tz)
    gap = (d.date() - today.date()).days
    day = "today" if gap == 0 else "tomorrow" if gap == 1 else DAY_NAMES[d.weekday()]
    return f"{day} {d:%H:%M}"


def span(seconds: float) -> str:
    if seconds < 3600:
        return plural(max(1, round(seconds / 60)), "minute")
    if seconds < 2 * 86400:
        return plural(round(seconds / 3600), "hour")
    return plural(round(seconds / 86400), "day")


# --- the rest -----------------------------------------------------------------

def _keeps_running(state: dict, job: dict) -> bool:
    keep = {k.strip().lower() for k in state.get("keep_running") or [] if k.strip()}
    return str(job.get("id", "")).lower() in keep or str(job.get("name", "")).lower() in keep


def begin(state: dict, now: float, ends_at: float, jobs: list, kind: str = "weekly") -> list:
    """Begin a rest: Hermes's own scheduled jobs rest too, and Hermes says goodnight on your channel.
    ``jobs`` is Hermes's list of runnable cron jobs ({id, name, schedule})."""
    if state["rest"]:
        return []
    held = [{"id": j["id"], "name": j.get("name") or j["id"], "schedule": j.get("schedule", "")}
            for j in jobs if j.get("id") and not _keeps_running(state, j)]
    state["rest"] = {"started_at": now, "ends_at": ends_at, "kind": kind, "held": held,
                     "basket": state.pop("loose_basket", []), "ox": [], "ox_until": 0.0}
    _log(state, now, f"Rest began ({kind}); {plural(len(held), 'scheduled job')} resting until {when(state, ends_at, now)}.")
    name = f", {_name(state)}" if _name(state) else ""
    jobs_line = (f" {plural(len(held), 'scheduled job')} {'is' if len(held) == 1 else 'are'} resting too, and"
                 if held else "")
    text = ("🕯 Your Sabbath begins" + (" (a two-minute one, to see how it works)" if kind == "try" else "") + ". "
            f"The week's work is done{name}. Until {when(state, ends_at, now)} I'll keep quiet:{jobs_line} "
            "anything that comes up, we'll set aside for after. Go and be with the people you love.")
    return [{"type": "pause", "jobs": held, "until": ends_at}] + _send(state["owner"]["channels"], text)


def end(state: dict, now: float, early: bool = False) -> list:
    """End the rest: jobs wake (and catch up), and Hermes sends one gentle digest."""
    rest = state["rest"]
    if not rest:
        return []
    state["rest"] = None
    if early:  # don't let the weekly window start it again right away
        try:
            start, finish = window(state, now)
            if start <= now < finish:
                state["ended_window"] = start
        except ValueError:
            pass
    state["history"] = (state["history"] + [{
        "started_at": rest["started_at"], "ended_at": now, "kind": rest["kind"],
        "held": len(rest["held"]), "basket": len(rest["basket"]), "ox": len(rest["ox"]),
    }])[-HISTORY_KEEP:]
    _log(state, now, f"Rest ended{' early' if early else ''} after {span(now - rest['started_at'])}.")
    return [{"type": "resume", "jobs": rest["held"]}] + _send(state["owner"]["channels"], digest(state, rest, now))


def digest(state: dict, rest: dict, now: float) -> str:
    name = f", {_name(state)}" if _name(state) else ""
    lines = [f"☀ Welcome back{name}. You rested {span(now - rest['started_at'])}."]
    held, basket = rest["held"], rest["basket"]
    if held or basket or rest["ox"]:
        lines.append("While you rested:")
    if held:
        lines.append(f"• {plural(len(held), 'scheduled job')} waited ({', '.join(j['name'] for j in held[:4])}"
                     f"{'…' if len(held) > 4 else ''}); {'it picks' if len(held) == 1 else 'they pick'} up now.")
    if basket:
        lines.append(f"• You set aside {plural(len(basket), 'thing')} for this week:")
        lines += [f"   – {b['text']}" for b in basket]
    if rest["ox"]:
        lines.append(f"• You lifted the rest {plural(len(rest['ox']), 'time')} for something urgent.")
    if not (held or basket or rest["ox"]):
        lines.append("Nothing was waiting. Nothing needed you.")
    lines.append("May your week be good.")
    return "\n".join(lines)


def set_aside(state: dict, text: str, now: float) -> dict:
    """Put something in the basket for after the rest."""
    text = " ".join((text or "").split())[:300]
    if not text:
        raise ValueError("Nothing to set aside.")
    item = {"text": text, "at": now}
    if state["rest"]:
        state["rest"]["basket"].append(item)
    else:  # outside a rest the basket waits for the next digest anyway
        state.setdefault("loose_basket", []).append(item)
    _log(state, now, "Set aside: " + text)
    return item


def ox(state: dict, now: float, why: str = "") -> str:
    """'If your ox falls into a well on the Sabbath, will you not pull it out?' (Luke 14:5)"""
    rest = state["rest"]
    if not rest:
        return "You're not resting right now, so there's nothing to lift."
    rest["ox_until"] = now + OX_SECONDS
    rest["ox"].append({"at": now, "why": why[:200]})
    _log(state, now, "Rest lifted for an hour" + (f": {why}" if why else "."))
    return (f"🐂 The ox is in the well. I'll help fully until {when(state, rest['ox_until'], now)}, "
            "then we go back to resting. Your scheduled jobs stay asleep.")


def tick(state: dict, now: float, jobs_fn) -> list:
    """Begin or end the rest on time. ``jobs_fn()`` lists runnable cron jobs (only called to begin)."""
    rest = state["rest"]
    if rest and now >= rest["ends_at"]:
        return end(state, now)
    if rest or not state["keeping"]:
        return []
    start, finish = window(state, now)
    if start <= now < finish and state.get("ended_window") != start:
        return begin(state, now, finish, jobs_fn(), kind="weekly")
    return []


def context(state: dict, now: float) -> str | None:
    """What Hermes is told at the top of each turn while you rest."""
    rest = state["rest"]
    if not rest:
        return None
    who = _name(state) or "The user"
    if rest["ox_until"] > now:
        return (f"[Sabbath] {who} lifted their rest for something urgent until {when(state, rest['ox_until'], now)}. "
                "Help fully and efficiently with it.")
    return (f"[Sabbath] {who} is keeping a day of rest until {when(state, rest['ends_at'], now)}. Be a companion "
            "for rest, not for work: conversation, people, meals, walks, books, music, prayer, play, beauty. If "
            "they bring up work or a task that can wait, don't do it: in one warm line, offer to set it aside for "
            "after the rest and, if they agree, call sabbath_set_aside. If it truly can't wait, tell them they "
            "can send /sabbath ox (Luke 14:5, the ox in the well) and you'll help fully for an hour. Never "
            "lecture, and don't repeat this once said.")


def public_view(state: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    v = {k: state[k] for k in ("keeping", "owner", "begins", "hours", "tz", "keep_running", "history", "log")}
    try:
        start, finish = window(state, now)
        v["window"] = {"start": start, "end": finish, "start_label": when(state, start, now),
                       "end_label": when(state, finish, now), "weekday": parse_begins(state["begins"])[0]}
    except ValueError as exc:
        v["window"] = {"error": str(exc)}
    rest = state["rest"]
    v["rest"] = None if not rest else {**rest, "ends_label": when(state, rest["ends_at"], now),
                                       "left": max(0.0, rest["ends_at"] - now), "ox_active": rest["ox_until"] > now}
    v["hours_rested"] = round(sum(h["ended_at"] - h["started_at"] for h in state["history"]) / 3600, 1)
    v["loose_basket"] = state.get("loose_basket", [])
    v["now"] = now
    return v
