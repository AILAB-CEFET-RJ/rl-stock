"""Calendar/session boundaries, missing-data denominator and segment integrity."""

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from rl_boleta import market_calendar
from rl_boleta.data_pipeline import Config, align_snapshots, prepare, validate_snapshot


def capture(at, identity="capture"):
    return {"schema_version": 1, "snapshot_id": identity, "ticker": "AAPL", "source": "synthetic",
            "available_at": at, "book_at": None,
            "bids": [{"price": 99.99 - i * .01, "size": 100} for i in range(5)],
            "asks": [{"price": 100.01 + i * .01, "size": 100} for i in range(5)],
            "trades": [{"at": at, "price": 100, "size": 1} for _ in range(10)]}


class CalendarTests(unittest.TestCase):
    def config(self, first="2025-07-03", last="2025-07-03", **kwargs):
        return Config(("AAPL",), 500, 500, calendar=market_calendar.NAME,
                      session_first_date=first, session_last_date=last, **kwargs)

    def normalize(self, records, config):
        return [validate_snapshot(r, config) for r in records]

    def test_complete_paper_calendar(self):
        days = list(market_calendar.dates(market_calendar.FIRST, market_calendar.LAST))
        self.assertEqual(sum(market_calendar.window(d) is not None for d in days), 105)
        for day in market_calendar.CLOSURES:
            self.assertIsNone(market_calendar.window(day))
        self.assertIsNone(market_calendar.window(date(2025, 7, 5)))

    def test_calendar_scope_and_bounds_are_explicit(self):
        for first, last in (("2025-03-02", "2025-03-03"), ("2025-07-31", "2025-08-01"),
                            ("2025-07-03", "2025-07-02")):
            with self.assertRaises(ValueError):
                self.config(first, last)
        with self.assertRaises(ValueError):
            Config(("AAPL",), 500, 500, calendar=market_calendar.NAME)
        with self.assertRaises(ValueError):
            replace(self.config(), session_end="17:00")
        with self.assertRaises(ValueError):
            replace(self.config(), temporal_policy="source-time")

    def test_early_close_grid_excludes_close_and_counts_missing_tail(self):
        config = self.config()
        records = self.normalize([capture("2025-07-03T09:30:00-04:00")], config)
        grid = list(align_snapshots(records, config))
        self.assertEqual(len(grid), 210)
        self.assertEqual(grid[-1][1]["decision_at"], "2025-07-03T16:59:00Z")
        self.assertEqual(sum(r is not None for r, _ in grid), 2)  # inclusive age=60
        self.assertIn("stale_snapshot", grid[-1][1]["reason"])

    def test_holiday_and_weekend_never_make_sessions(self):
        config = self.config("2025-07-04", "2025-07-06")
        records = self.normalize([capture("2025-07-04T09:30:00-04:00")], config)
        self.assertEqual(list(align_snapshots(records, config)), [])

    def test_premarket_and_closing_capture_cannot_seed_session(self):
        config = self.config(max_age_seconds=36000)
        records = self.normalize([capture("2025-07-03T09:29:59-04:00", "pre"),
                                  capture("2025-07-03T13:00:00-04:00", "close")], config)
        grid = list(align_snapshots(records, config))
        self.assertEqual(len(grid), 210)
        self.assertTrue(all(row is None for row, _ in grid))

    def test_missing_entire_day_and_dst_open(self):
        config = self.config("2025-03-07", "2025-03-10")
        grid = list(align_snapshots([], config))
        self.assertEqual(len(grid), 780)
        self.assertEqual(grid[0][1]["decision_at"], "2025-03-07T14:30:00Z")
        self.assertEqual(grid[390][1]["decision_at"], "2025-03-10T13:30:00Z")

    def test_segments_reset_after_gap_and_session(self):
        config = self.config("2025-07-02", "2025-07-03", max_age_seconds=1)
        records = self.normalize([
            capture("2025-07-02T09:30:00-04:00", "first"),
            capture("2025-07-02T09:32:00-04:00", "after-gap"),
            capture("2025-07-03T09:30:00-04:00", "next-day")], config)
        rows = [row for row, _ in align_snapshots(records, config) if row]
        self.assertEqual([r["segment_id"] for r in rows], ["2025-07-02:0001", "2025-07-02:0002", "2025-07-03:0001"])
        self.assertEqual([r["step_in_segment"] for r in rows], [0, 0, 0])

    def test_exclusions_and_empty_session_coverage_are_auditable(self):
        config = self.config("2025-07-02", "2025-07-04")
        records = [capture("2025-07-03T09:30:00-04:00", "valid"),
                   capture("2025-07-03T13:01:00-04:00", "late"),
                   capture("2025-07-04T09:30:00-04:00", "holiday")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "input.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in records))
            manifest = prepare([path], root / "out", config)
            self.assertEqual(manifest["counts"]["session_excluded_snapshots"], 2)
            self.assertEqual(manifest["counts"]["expected_sessions"], 2)
            self.assertEqual(manifest["counts"]["sessions_without_aligned_rows"], 1)
            self.assertEqual(manifest["counts"]["aligned_rows"] + manifest["counts"]["rejected_grid_points"], 600)
            self.assertIn("code_sha256", manifest["calendar"])
            with (root / "out" / "session_coverage.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["accepted_points"], "0")
            self.assertEqual(rows[0]["expected_points"], "390")
            with (root / "out" / "snapshots.jsonl").open() as handle:
                self.assertEqual(len(handle.readlines()), 3)  # exclusions retain originals


if __name__ == "__main__":
    unittest.main()
