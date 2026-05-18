import unittest
import subprocess
import sys
from unittest.mock import patch

import run_all


class RunAllMykeibadbSyncTest(unittest.TestCase):
    def test_run_mykeibadb_daily_sync_invokes_sync_tool(self):
        calls = []

        def fake_run(cmd, cwd=None):
            calls.append((cmd, cwd))
            return 0

        with patch.object(run_all, "_run_subprocess", side_effect=fake_run):
            rc = run_all.run_mykeibadb_daily_sync(timeout_seconds=123)

        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][0][:4], [
            run_all.sys.executable,
            "-X",
            "utf8",
            str(run_all.BASE_DIR / "tools" / "mykeibadb_sync.py"),
        ])
        self.assertIn("--timeout", calls[0][0])
        self.assertIn("123", calls[0][0])

    def test_run_v2_daily_runs_runtime_check_before_preflight(self):
        calls = []

        def fake_run(cmd, cwd=None):
            calls.append(cmd)
            if "runtime_check.py" in str(cmd):
                return 1
            self.fail(f"unexpected subprocess after runtime failure: {cmd}")

        with patch.object(run_all, "_run_subprocess", side_effect=fake_run):
            rc = run_all.run_v2_daily(trace_id="trace-test")

        self.assertEqual(rc, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("runtime_check.py", str(calls[0]))
        self.assertIn("--strict", calls[0])

    def test_run_v2_runtime_check_strict_passes_strict_flag(self):
        calls = []

        def fake_run(cmd, cwd=None):
            calls.append(cmd)
            return 0

        with patch.object(run_all, "_run_subprocess", side_effect=fake_run):
            rc = run_all.run_v2_runtime_check("daily", strict=True)

        self.assertEqual(rc, 0)
        self.assertIn("runtime_check.py", str(calls[0]))
        self.assertIn("--profile", calls[0])
        self.assertIn("daily", calls[0])
        self.assertIn("--strict", calls[0])

    def test_help_exposes_runtime_strict_option(self):
        result = subprocess.run(
            [sys.executable, "run_all.py", "--help"],
            cwd=str(run_all.BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--runtime-strict", result.stdout)


if __name__ == "__main__":
    unittest.main()
