"""Verify reconstruction, temporal ambiguity and compressed pipeline handoff."""

import gzip
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

try:
    import pandas as pd
    import pyarrow
    from rl_boleta.parquet_adapter import Timing, convert, localize, reconstruct
    from rl_boleta.audit_parquet import inspect_frame
except ModuleNotFoundError:
    pd = None

from rl_boleta.data_pipeline import Config, prepare


def capture():
    return pd.DataFrame({
        "File_Date": ["2025-06-27 10:30:00"] * 9 + ["2025-06-27 10:30:01"],
        "Company": ["APPLE INC COM"] * 10, "Date": ["2025-06-27"] * 10,
        "Time": ["09:30:00"] * 10, "Shares_Top_of_Book": [100.0] * 10,
        "Prices_Top_of_Book": [100.05, 100.04, 100.03, 100.02, 100.01,
                               99.99, 99.98, 99.97, 99.96, 99.95],
        "Price_of_One_Share": [100.0] * 10, "Number_of_Shares_Sold": [1.0] * 10,
        "Transaction_type": ["asks"] * 5 + ["bids"] * 5,
    })


@unittest.skipIf(pd is None, "adapter tests require pandas/numpy/pyarrow")
class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(("AAPL",), 500, 500)
        self.timing = Timing("America/Sao_Paulo", "America/New_York")

    def record(self, frame=None, timing=None):
        frame = capture() if frame is None else frame
        info, _ = inspect_frame(frame)
        return reconstruct(frame.to_dict("records"), info.iloc[0].to_dict(),
                           {"source_sha256": "abc", "source_row_start": 0},
                           timing or self.timing, self.config)

    def test_capture_completion_and_raw_provenance(self):
        record = self.record()
        self.assertEqual(record["available_at"], "2025-06-27T13:30:01Z")
        self.assertEqual(record["trades"][0]["at"], "2025-06-27T13:30:00Z")
        self.assertEqual(record["asks"][0]["price"], 100.01)
        self.assertEqual(len(record["trades"]), 10)
        self.assertIsNone(record["book_at"])
        self.assertEqual(record["provenance"]["raw_capture_times"][-1], "2025-06-27 10:30:01")
        self.assertNotIn("estimated_book_at", record["provenance"])

    def test_declared_delay_does_not_shift_trade_or_capture(self):
        record = self.record(timing=replace(self.timing, source_delay_interpretation="availability-lag"))
        self.assertEqual(record["provenance"]["estimated_book_at"], "2025-06-27T10:30:01Z")
        self.assertEqual(record["available_at"], "2025-06-27T13:30:01Z")
        self.assertEqual(record["trades"][0]["at"], "2025-06-27T13:30:00Z")
        self.assertIsNone(record["book_at"])

    def test_dst_transition(self):
        self.assertEqual((localize("2025-03-07 10:30:00", "America/Sao_Paulo") -
                          localize("2025-03-07 09:30:00", "America/New_York")).total_seconds(), -3600)
        self.assertEqual((localize("2025-03-10 10:30:00", "America/Sao_Paulo") -
                          localize("2025-03-10 09:30:00", "America/New_York")).total_seconds(), 0)

    def test_ambiguous_or_nonexistent_clock_rejected(self):
        for value in ("2025-11-02 01:30:00", "2025-03-09 02:30:00"):
            with self.assertRaisesRegex(ValueError, "ambiguous or nonexistent"):
                localize(value, "America/New_York")

    def test_future_trade_rejected_without_previous_day_repair(self):
        frame = capture()
        frame["Time"] = "09:31:00"
        with self.assertRaisesRegex(ValueError, "later than available_at"):
            self.record(frame)

    def test_rollover_date_is_not_guessed(self):
        frame = capture()
        frame["File_Date"] = "2025-06-27 00:30:00"
        with self.assertRaisesRegex(ValueError, "date ambiguous"):
            self.record(frame)

    def test_whole_invalid_block_rejected(self):
        frame = capture()
        frame.loc[0, "Prices_Top_of_Book"] = float("nan")
        with self.assertRaisesRegex(ValueError, "incomplete_or_invalid_book"):
            self.record(frame)

    def test_compressed_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "raw.parquet"
            second = capture()
            second["File_Date"] = "2025-06-27 10:31:01"
            pd.concat([capture(), second], ignore_index=True).to_parquet(path)
            converted = root / "converted"
            report = convert([path], converted, self.config, self.timing)
            self.assertEqual(report["counts"]["accepted"], 2)
            output = next(converted.glob("*.jsonl.gz"))
            with gzip.open(output, "rt") as handle:
                raw = json.loads(handle.readline())
            result = prepare([output], root / "prepared", self.config)
            self.assertEqual(result["status"], "provisional_prepared")
            self.assertFalse(result["training_ready"])
            with (root / "prepared" / "snapshots.jsonl").open() as handle:
                self.assertEqual(json.loads(handle.readline())["provenance"], raw["provenance"])
            with self.assertRaises(FileExistsError):
                convert([path], converted, self.config, self.timing)

    def test_rejections_keep_source_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = capture()
            bad.loc[0, "Prices_Top_of_Book"] = float("nan")
            path = root / "raw.parquet"
            pd.concat([bad, capture(), capture().iloc[:2]], ignore_index=True).to_parquet(path)
            # Duplicate capture keys are rejected together, rather than choosing one.
            report = convert([path], root / "out", self.config, self.timing)
            self.assertEqual(report["counts"]["rejected"], 2)
            self.assertEqual(report["counts"]["trailing_rows"], 2)
            import csv
            with (root / "out" / "rejections.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["source_row_start"] for r in rows], ["0", "10", "20"])

    def test_mixed_company_block_is_not_silently_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = capture()
            frame.loc[0, "Company"] = "GENERAL ELECTRIC CO COM NEW"
            path = root / "mixed.parquet"
            frame.to_parquet(path)
            report = convert([path], root / "out", self.config, self.timing)
            self.assertEqual(report["counts"]["rejected"], 1)
            self.assertEqual(report["counts"].get("outside_universe", 0), 0)
            self.assertIn("bad_company_block", report["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
