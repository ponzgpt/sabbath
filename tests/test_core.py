"""The promises Sabbath makes: on time, only its own jobs, nothing lost, never a lecture loop."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sabbath_core as core  # noqa: E402

TZ = "Europe/Madrid"
JOBS = [{"id": "a1", "name": "Daily Download", "schedule": "every day 06:00"},
        {"id": "b2", "name": "backup", "schedule": "every 6h"}]


def at(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(TZ)).timestamp()


def state(**kw):
    s = core.new_state()
    s.update({"keeping": True, "begins": "sat 18:00", "hours": 24, "tz": TZ, **kw})
    s["owner"] = {"name": "Ana", "channels": ["telegram:111"]}
    return s


class WindowTest(unittest.TestCase):
    def test_window_in_progress_and_next(self):
        s = state()
        # Tue 10 Nov 2026 -> next window Sat 14 Nov 18:00 to Sun 15 Nov 18:00
        self.assertEqual(core.window(s, at(2026, 11, 10, 9)), (at(2026, 11, 14, 18), at(2026, 11, 15, 18)))
        # Sunday noon: inside the window that began Saturday
        self.assertEqual(core.window(s, at(2026, 11, 15, 12))[0], at(2026, 11, 14, 18))
        # Sunday 18:00 sharp: that one is over, the next one is a week later
        self.assertEqual(core.window(s, at(2026, 11, 15, 18))[0], at(2026, 11, 21, 18))

    def test_bad_begins(self):
        for bad in ("someday 18:00", "sat 25:00", "18:00"):
            with self.assertRaises(ValueError):
                core.parse_begins(bad)


class RestTest(unittest.TestCase):
    def test_week_cycle(self):
        s = state(keep_running=["backup"])
        self.assertEqual(core.tick(s, at(2026, 11, 14, 17, 59), lambda: JOBS), [])
        acts = core.tick(s, at(2026, 11, 14, 18, 0), lambda: JOBS)
        pause = [a for a in acts if a["type"] == "pause"][0]
        self.assertEqual([j["id"] for j in pause["jobs"]], ["a1"])  # the backup never rests
        hello = [a for a in acts if a["type"] == "send"][0]
        self.assertEqual(hello["target"], "telegram:111")
        self.assertIn("Sabbath begins", hello["text"])
        self.assertIn("tomorrow 18:00", hello["text"])

        self.assertIn("day of rest", core.context(s, at(2026, 11, 15, 9)))
        core.set_aside(s, "Reply to the landlord", at(2026, 11, 15, 10))
        self.assertEqual(core.tick(s, at(2026, 11, 15, 17), lambda: JOBS), [])

        acts = core.tick(s, at(2026, 11, 15, 18, 0), lambda: JOBS)
        self.assertEqual([j["id"] for j in acts[0]["jobs"]], ["a1"])  # wakes only what it paused
        digest = acts[1]["text"]
        self.assertIn("Reply to the landlord", digest)
        self.assertIn("24 hours", digest)
        self.assertIsNone(s["rest"])
        self.assertIsNone(core.context(s, at(2026, 11, 15, 19)))
        self.assertEqual(len(s["history"]), 1)

    def test_ending_early_does_not_restart_the_same_window(self):
        s = state()
        core.tick(s, at(2026, 11, 14, 18), lambda: JOBS)
        core.end(s, at(2026, 11, 14, 20), early=True)
        self.assertEqual(core.tick(s, at(2026, 11, 14, 20, 1), lambda: JOBS), [])
        self.assertIsNone(s["rest"])
        self.assertTrue(core.tick(s, at(2026, 11, 21, 18), lambda: JOBS))  # next week it comes again

    def test_ox_lifts_for_an_hour_only(self):
        s = state()
        core.tick(s, at(2026, 11, 14, 18), lambda: JOBS)
        core.ox(s, at(2026, 11, 15, 9), "server down")
        self.assertIn("urgent", core.context(s, at(2026, 11, 15, 9, 30)))
        self.assertIn("day of rest", core.context(s, at(2026, 11, 15, 10, 1)))

    def test_off_means_off(self):
        s = state(keeping=False)
        self.assertEqual(core.tick(s, at(2026, 11, 14, 18, 30), lambda: JOBS), [])

    def test_try_and_basket_before_rest(self):
        s = state(keeping=False)
        core.set_aside(s, "Taxes", at(2026, 11, 10, 9))
        t0 = at(2026, 11, 10, 9, 1)
        core.begin(s, t0, t0 + core.TRY_SECONDS, JOBS, kind="try")
        self.assertEqual(core.tick(s, t0 + 60, lambda: JOBS), [])
        acts = core.tick(s, t0 + core.TRY_SECONDS, lambda: JOBS)
        self.assertIn("2 minutes", acts[1]["text"])
        self.assertIn("Daily Download", acts[1]["text"])
        self.assertIn("Taxes", acts[1]["text"])  # set aside before the rest, returned after it

    def test_plural_digest_quiet_rest(self):
        s = state()
        core.begin(s, 0.0, 3600.0, [], kind="now")
        text = core.end(s, 3600.0)[1]["text"]
        self.assertIn("Nothing was waiting", text)
        self.assertNotIn("job(s)", text)


if __name__ == "__main__":
    unittest.main()
