"""Cron goes through the public cronjob_manage tool, and only Sabbath's own pauses are resumed."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["HERMES_HOME"] = tempfile.mkdtemp()

import sabbath_store as store  # noqa: E402


class FakeCtx:
    def __init__(self, jobs):
        self.jobs, self.calls = jobs, []

    def dispatch_tool(self, name, args):
        assert name == "cronjob_manage"
        self.calls.append(args)
        if args["action"] == "list":
            keep = [j for j in self.jobs if args["include_disabled"] or j["enabled"]]
            return json.dumps({"success": True, "jobs": keep})
        job = next(j for j in self.jobs if j["job_id"] == args["job_id"])
        if args["action"] == "pause":
            job.update(enabled=False, state="paused", paused_reason=args["reason"])
        else:
            job.update(enabled=True, state="scheduled", paused_reason=None)
        return json.dumps({"success": True, "job": job})


def job(i, enabled=True, reason=None):
    return {"job_id": i, "name": i, "schedule": "every 1h", "enabled": enabled,
            "state": "scheduled" if enabled else "paused", "paused_reason": reason}


class Cron(unittest.TestCase):
    def tearDown(self):
        store.use(None)

    def test_pause_then_resume_only_what_sabbath_paused(self):
        ctx = FakeCtx([job("a"), job("b"), job("mine", enabled=False, reason="me")])
        store.use(ctx)
        state = {}
        jobs = store.runnable_jobs(state)
        self.assertEqual([j["id"] for j in jobs], ["a", "b"])
        self.assertEqual(store.pause_jobs(jobs, 0), jobs)
        self.assertTrue(all(c["reason"].startswith("Sabbath") for c in ctx.calls if c["action"] == "pause"))
        ctx.jobs[1].update(paused_reason="you paused it yourself mid-rest")
        store.resume_jobs(jobs + [{"id": "mine"}])
        resumed = [c["job_id"] for c in ctx.calls if c["action"] == "resume"]
        self.assertEqual(resumed, ["a"])

    def test_without_a_context_the_desktop_reads_the_last_list_and_queues(self):
        self.assertEqual(store.runnable_jobs({"jobs_seen": [{"id": "a"}]}), [{"id": "a"}])
        store.perform([{"type": "pause", "jobs": [{"id": "a"}], "until": 0}])
        self.assertEqual(store.read_state()["cron_queue"][0]["type"], "pause")


if __name__ == "__main__":
    unittest.main()
