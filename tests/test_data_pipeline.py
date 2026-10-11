"""Synthetic regression tests for financial data integrity and causality."""

import copy
import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rl_boleta.data_pipeline import Config, align_snapshots, digest, prepare, validate_snapshot


def snapshot(ticker="AAPL", at="2026-10-05T09:30:00-04:00", identity="capture-1"):
    return {
        "schema_version": 1,
        "snapshot_id": identity,
        "ticker": ticker,
        "source": "synthetic",
        "available_at": at,
        "book_at": None,
        "bids": [{"price": 99.99 - level * 0.01, "size": 100 + level} for level in range(5)],
        "asks": [{"price": 100.01 + level * 0.01, "size": 200 + level} for level in range(5)],
        "trades": [{"at": "2026-10-05T13:29:00Z", "price": 100.0, "size": 10 + index} for index in range(10)],
    }


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(("AAPL", "TSLA"), max_spread_bps=100, max_depth_distance_bps=500)

    def normalize(self, records, config=None):
        return [validate_snapshot(r, config or self.config) for r in records]

    def write_input(self, directory, records, name="raw.jsonl"):
        path = Path(directory) / name
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    def test_levels_and_all_ten_trades_remain_separate(self):
        record = snapshot()
        record["bids"].reverse()
        normalized = validate_snapshot(record, self.config)
        rows = list(align_snapshots([normalized], replace(self.config, tickers=("AAPL",))))
        row, failure = rows[0]
        self.assertIsNone(failure)
        self.assertEqual(row["AAPL_bid_price_1"], 99.99)
        self.assertAlmostEqual(row["AAPL_bid_price_5"], 99.95)
        self.assertEqual(row["AAPL_trade_size_1"], 10)
        self.assertEqual(row["AAPL_trade_size_10"], 19)
        self.assertEqual(len(normalized["trades"]), 10)  # identical prices are legitimate trades
        self.assertIsNone(row["AAPL_book_at"])

    def test_alignment_never_uses_future_asset_snapshot(self):
        records = self.normalize([
            snapshot(), snapshot("TSLA", "2026-10-05T09:30:01-04:00"),
            snapshot("AAPL", "2026-10-05T09:31:00-04:00", "a-2"),
        ])
        rows = list(align_snapshots(records, self.config))
        self.assertIsNone(rows[0][0])
        self.assertIn("TSLA:missing_past_snapshot", rows[0][1]["reason"])
        self.assertEqual(rows[1][0]["TSLA_snapshot_age_seconds"], 59)
        self.assertEqual(rows[1][0]["AAPL_snapshot_id"], "a-2")

    def test_old_snapshots_expire_and_do_not_carry_to_next_session(self):
        records = self.normalize([
            snapshot(), snapshot("TSLA"),
            snapshot("AAPL", "2026-10-05T09:32:00-04:00", "a-2"),
            snapshot("AAPL", "2026-10-06T09:30:00-04:00", "a-3"),
        ])
        rows = list(align_snapshots(records, self.config))
        self.assertIn("TSLA:stale_snapshot", rows[2][1]["reason"])
        self.assertIn("TSLA:missing_past_snapshot", rows[-1][1]["reason"])

    def test_grid_uses_session_clock_and_daylight_saving_time(self):
        record = snapshot(at="2026-11-02T09:30:00-05:00")
        rows = list(align_snapshots(self.normalize([record]), replace(self.config, tickers=("AAPL",))))
        self.assertEqual(rows[0][0]["decision_at"], "2026-11-02T14:30:00Z")

    def test_integrity_failures_are_rejected_instead_of_repaired(self):
        variants = []
        record = snapshot(); record["available_at"] = "2026-10-05T09:30:00"; variants.append(record)
        record = snapshot(); record["asks"] = record["asks"][:4]; variants.append(record)
        record = snapshot(); record["trades"] = record["trades"][:9]; variants.append(record)
        record = snapshot(); record["bids"][0]["size"] = None; variants.append(record)
        record = snapshot(); record["bids"][0]["price"] = float("nan"); variants.append(record)
        record = snapshot(); record["asks"][0]["price"] = 90; variants.append(record)
        record = snapshot(); record["bids"][4]["price"] = 32.7; variants.append(record)
        record = snapshot(); record["bids"][4] = copy.deepcopy(record["bids"][0]); variants.append(record)
        record = snapshot(); record["trades"][0]["at"] = "2026-10-05T13:31:00Z"; variants.append(record)
        record = snapshot(); record["book_at"] = "2026-10-05T13:31:00Z"; variants.append(record)
        record = snapshot(); record["trades"][0]["size"] = -1; variants.append(record)
        record = snapshot(); record["schema_version"] = True; variants.append(record)
        record = snapshot(); record["ticker"] = "GE"; variants.append(record)
        for record in variants:
            with self.subTest(record=record), self.assertRaises(ValueError):
                validate_snapshot(record, self.config)

    def test_same_instant_with_different_offsets_is_not_future(self):
        record = snapshot()
        record["trades"][0]["at"] = "2026-10-05T10:30:00-03:00"
        self.assertEqual(validate_snapshot(record, self.config)["trades"][0]["at"], "2026-10-05T13:30:00Z")

    def test_manifest_rejections_deduplication_and_immutable_output(self):
        invalid = snapshot(identity="invalid"); invalid["bids"][0]["size"] = None
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_input(directory, [snapshot(), snapshot("TSLA"), snapshot(), invalid])
            before = source.read_bytes()
            output = Path(directory) / "prepared"
            report = prepare([source], output, self.config)
            self.assertEqual(report["counts"]["accepted_snapshots"], 2)
            self.assertEqual(report["counts"]["duplicate_snapshots"], 1)
            self.assertEqual(report["counts"]["rejected_snapshots"], 1)
            self.assertEqual(report["counts"]["aligned_rows"], 1)
            self.assertEqual(report["inputs"][0]["sha256"], digest(source))
            for name, sha in report["outputs"].items():
                self.assertEqual(digest(output / name), sha)
            self.assertEqual(source.read_bytes(), before)
            with (output / "market.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["AAPL_trade_size_10"], "19.0")
            with (output / "rejected_snapshots.csv").open() as handle:
                self.assertEqual(next(csv.DictReader(handle))["source_line"], "4")
            with self.assertRaises(FileExistsError):
                prepare([source], output, self.config)

    def test_conflicting_identity_or_capture_time_aborts(self):
        for same_id in (True, False):
            second = snapshot(identity="capture-1" if same_id else "another-id")
            second["trades"][0]["size"] = 99
            with tempfile.TemporaryDirectory() as directory:
                source = self.write_input(directory, [snapshot(), second])
                output = Path(directory) / "prepared"
                with self.assertRaisesRegex(ValueError, "conflicting|ambiguous"):
                    prepare([source], output, self.config)
                self.assertFalse(output.exists())

    def test_unsorted_input_with_fractional_seconds_is_sorted_by_time(self):
        records = [snapshot(at="2026-10-05T09:30:00.500-04:00", identity="later"), snapshot()]
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_input(directory, records)
            output = Path(directory) / "prepared"
            config = replace(self.config, tickers=("AAPL",))
            report = prepare([source], output, config)
            self.assertEqual(report["counts"]["aligned_rows"], 1)
            with (output / "market.csv").open() as handle:
                self.assertEqual(next(csv.DictReader(handle))["AAPL_snapshot_id"], "capture-1")

    def test_no_joint_coverage_is_reported_without_fabricating_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_input(directory, [snapshot()])
            report = prepare([source], Path(directory) / "prepared", self.config)
            self.assertEqual(report["status"], "no_aligned_rows")
            self.assertEqual(report["counts"]["aligned_rows"], 0)

    def test_old_processed_files_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dados_final.csv"
            with self.assertRaisesRegex(ValueError, "legacy CSV/Parquet"):
                prepare([source], Path(directory) / "prepared", self.config)

    def test_deduplication_across_files_and_replay_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.write_input(directory, [snapshot()], "first.jsonl")
            second = self.write_input(directory, [snapshot(), snapshot("TSLA")], "second.jsonl")
            a = prepare([first, second], Path(directory) / "a", self.config)
            b = prepare([second, first], Path(directory) / "b", self.config)
            self.assertEqual(a["counts"]["duplicate_snapshots"], 1)
            self.assertEqual(a["outputs"], b["outputs"])

    def test_missing_json_and_excessive_spread_are_audited(self):
        record = snapshot()
        record["asks"] = [{"price": 102 + level, "size": 10} for level in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_input(directory, [record])
            with source.open("a") as handle:
                handle.write("{malformed\n")
            output = Path(directory) / "prepared"
            report = prepare([source], output, self.config)
            self.assertEqual(report["counts"]["rejected_snapshots"], 2)
            self.assertEqual(report["status"], "no_aligned_rows")
            self.assertIn("spread exceeds configured limit", report["rejected_snapshot_reasons"])

    def test_invalid_grid_configuration_fails_early(self):
        for kwargs in ({"frequency_seconds": 0}, {"max_age_seconds": -1},
                       {"tickers": ("AAPL", "AAPL")}, {"session_end": "09:00"},
                       {"max_spread_bps": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(self.config, **kwargs)


if __name__ == "__main__":
    unittest.main()
