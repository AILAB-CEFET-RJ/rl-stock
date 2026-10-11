"""Regression checks for reconstruction without sorting/dropping raw rows."""

import unittest

try:
    import pandas as pd
    from rl_boleta.audit_parquet import inspect_frame
except ModuleNotFoundError:
    pd = None


def raw_capture(capture="2025-06-27 10:30:00"):
    return pd.DataFrame({
        "File_Date": [capture] * 10,
        "Company": ["APPLE INC COM"] * 10,
        "Date": ["2025-06-27"] * 10,
        "Time": ["09:30:00"] * 10,
        "Shares_Top_of_Book": [100.0] * 10,
        "Prices_Top_of_Book": [100.05, 100.04, 100.03, 100.02, 100.01,
                               99.99, 99.98, 99.97, 99.96, 99.95],
        "Price_of_One_Share": [100.0] * 10,
        "Number_of_Shares_Sold": [1.0] * 10,
        "Transaction_type": ["asks"] * 5 + ["bids"] * 5,
    })


@unittest.skipIf(pd is None, "audit tests require pandas/numpy")
class AuditTests(unittest.TestCase):
    def test_split_capture_second_can_be_reconstructed(self):
        frame = raw_capture()
        frame.loc[9, "File_Date"] = "2025-06-27 10:30:01"
        info, details = inspect_frame(frame)
        self.assertTrue(info.iloc[0]["complete_candidate"])
        self.assertEqual(info.iloc[0]["capture_span_seconds"], 1)
        self.assertEqual(info.iloc[0]["wall_clock_gap_seconds"], 3601)
        self.assertEqual(details["same_timestamp_group_sizes"], {"9": 1, "1": 1})

    def test_bad_capture_does_not_shift_later_ten_row_block(self):
        first, second = raw_capture(), raw_capture("2025-06-27 10:31:00")
        first.loc[2, "Company"] = "TESLA INC COM"
        info, _ = inspect_frame(pd.concat([first, second], ignore_index=True))
        self.assertTrue(info.iloc[0]["bad_company_block"])
        self.assertFalse(info.iloc[0]["structurally_reconstructable"])
        self.assertTrue(info.iloc[1]["complete_candidate"])
        self.assertEqual(info.iloc[1]["source_row_start"], 10)

    def test_missing_level_is_not_averaged_away(self):
        frame = raw_capture()
        frame.loc[0, "Prices_Top_of_Book"] = float("nan")
        info, _ = inspect_frame(frame)
        self.assertTrue(info.iloc[0]["incomplete_or_invalid_book"])
        self.assertFalse(info.iloc[0]["complete_candidate"])
        self.assertTrue(pd.isna(info.iloc[0]["best_ask"]))
        self.assertTrue(pd.isna(frame.loc[0, "Prices_Top_of_Book"]))

    def test_missing_trade_clock_and_trailing_row_are_counted(self):
        frame = raw_capture()
        frame.loc[0, "Time"] = None
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
        info, details = inspect_frame(frame)
        self.assertTrue(info.iloc[0]["missing_trade_time"])
        self.assertFalse(info.iloc[0]["complete_candidate"])
        self.assertEqual(details["trailing_rows"], 1)
        self.assertEqual(details["rows"], 11)

    def test_repeated_capture_is_distinguished_from_repeated_market_values(self):
        frame = raw_capture()
        info, _ = inspect_frame(pd.concat([frame, frame], ignore_index=True))
        self.assertEqual(int(info["duplicate_snapshot_within_file"].sum()), 1)
        self.assertTrue(info["ambiguous_capture_key_within_file"].all())
        info, _ = inspect_frame(pd.concat([frame, raw_capture("2025-06-27 10:31:00")], ignore_index=True))
        self.assertEqual(int(info["duplicate_snapshot_within_file"].sum()), 0)
        self.assertEqual(int(info["complete_candidate"].sum()), 2)

    def test_threshold_sensitivity_does_not_repair_extreme_quotes(self):
        frame = raw_capture()
        frame.loc[9, "Prices_Top_of_Book"] = 32.7
        info, _ = inspect_frame(frame)
        self.assertTrue(info.iloc[0]["complete_candidate"])
        self.assertFalse(info.iloc[0]["candidate_within_500bps"])
        self.assertAlmostEqual(info.iloc[0]["mid_price"], 100.0)
        self.assertEqual(frame.loc[9, "Prices_Top_of_Book"], 32.7)

    def test_joint_coverage_respects_availability_and_inclusive_expiry(self):
        from rl_boleta.audit_coverage import joint_coverage
        frame = pd.DataFrame({
            "company": ["AAPL", "TSLA"],
            "capture_end": pd.to_datetime(["2025-06-27 09:30:00", "2025-06-27 09:30:01"]),
        })
        grid = pd.date_range("2025-06-27 09:30:00", periods=3, freq="min").to_numpy()
        self.assertEqual(joint_coverage(frame, grid, ["AAPL", "TSLA"], 60).tolist(), [False, True, False])


if __name__ == "__main__":
    unittest.main()
