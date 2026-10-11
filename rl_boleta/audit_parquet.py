"""Read-only audit of legacy Cboe Parquet; no experimental dataset is produced.

Requires pandas, numpy and a pandas-compatible Parquet engine (e.g. pyarrow).
Snapshot candidates are ten consecutive original rows, never sorted/filtered
before reconstruction. Every candidate must independently match its structure.
"""

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["File_Date", "Company", "Date", "Time", "Shares_Top_of_Book",
        "Prices_Top_of_Book", "Price_of_One_Share", "Number_of_Shares_Sold", "Transaction_type"]
NUMERIC = COLS[4:8]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inspect_frame(frame):
    """Return candidate-level diagnostics and file-level row diagnostics."""
    missing = set(COLS) - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    n = len(frame) // 10
    data = frame.iloc[:n * 10]
    summary = {
        "rows": len(frame), "trailing_rows": len(frame) % 10,
        "columns": list(frame.columns),
        "nulls_by_column": {c: int(frame[c].isna().sum()) for c in COLS},
        "duplicate_rows": int(frame.duplicated(subset=COLS).sum()),
    }
    if not n:
        return pd.DataFrame(), summary
    company = data["Company"].fillna("").to_numpy().reshape(n, 10)
    side = data["Transaction_type"].fillna("").to_numpy().reshape(n, 10)
    captures = pd.to_datetime(data["File_Date"], format="mixed", errors="coerce").to_numpy().reshape(n, 10)
    dates = pd.to_datetime(data["Date"], format="mixed", errors="coerce").to_numpy().reshape(n, 10)
    capture_start, capture_end = captures.min(axis=1), captures.max(axis=1)
    time_strings = data["Time"].fillna("").astype(str)
    valid_clock = time_strings.str.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d")
    trade_stamps = pd.to_datetime(
        data["Date"].astype(str) + " " + time_strings.where(valid_clock, ""),
        format="%Y-%m-%d %H:%M:%S", errors="coerce",
    ).to_numpy().reshape(n, 10)
    # nanmax does not support datetime; use an explicit sentinel for diagnostics.
    trade_int = trade_stamps.astype("datetime64[ns]").astype("int64")
    latest_trade = trade_int.max(axis=1).astype("datetime64[ns]")
    all_trade_times = (~np.isnat(trade_stamps)).all(axis=1)
    numeric = {c: pd.to_numeric(data[c], errors="coerce").to_numpy(dtype=float).reshape(n, 10) for c in NUMERIC}
    prices, shares = numeric["Prices_Top_of_Book"], numeric["Shares_Top_of_Book"]
    trade_prices, trade_sizes = numeric["Price_of_One_Share"], numeric["Number_of_Shares_Sold"]
    asks, bids = prices[:, :5], prices[:, 5:]
    book_numeric = (np.isfinite(prices) & (prices > 0) & np.isfinite(shares) & (shares > 0)).all(axis=1)
    trade_numeric = (np.isfinite(trade_prices) & (trade_prices > 0) & np.isfinite(trade_sizes) & (trade_sizes >= 0)).all(axis=1)
    # Plain min/max propagate missing values: do not silently use fewer levels.
    best_ask, best_bid = asks.min(axis=1), bids.max(axis=1)
    mid = (best_ask + best_bid) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        spread = (best_ask - best_bid) / mid * 10000
        distance = np.max(np.abs(prices / mid[:, None] - 1), axis=1) * 10000
        trade_distance = np.abs(np.median(trade_prices, axis=1) / mid - 1) * 10000
    same_company = ((company == company[:, :1]).all(axis=1)) & (company[:, 0] != "")
    pattern = (side == np.array(["asks"] * 5 + ["bids"] * 5)).all(axis=1)
    seconds = (capture_end - capture_start) / np.timedelta64(1, "s")
    sane_capture = (~np.isnat(captures)).all(axis=1) & (seconds <= 2) & (seconds >= 0)
    capture_monotonic = (np.diff(captures, axis=1) >= np.timedelta64(0, "s")).all(axis=1)
    date_match = ((dates.astype("datetime64[D]") == captures.astype("datetime64[D]")).all(axis=1))
    distinct = (np.diff(np.sort(asks, axis=1), axis=1) > 0).all(axis=1) & (np.diff(np.sort(bids, axis=1), axis=1) > 0).all(axis=1)
    source_order = (np.diff(asks, axis=1) < 0).all(axis=1) & (np.diff(bids, axis=1) < 0).all(axis=1)
    trade_order = (np.diff(trade_int, axis=1) <= 0).all(axis=1) & all_trade_times
    fingerprints = pd.util.hash_pandas_object(data[COLS], index=False).to_numpy().reshape(n, 10)
    duplicate_snapshot = pd.DataFrame(fingerprints).duplicated(keep="first").to_numpy()
    ambiguous = pd.DataFrame({"company": company[:, 0], "at": capture_end}).duplicated(keep=False).to_numpy()
    structure = same_company & pattern & sane_capture & capture_monotonic & date_match
    uncrossed = best_bid < best_ask
    candidate = structure & book_numeric & trade_numeric & all_trade_times & distinct & uncrossed & ~ambiguous
    latest_series = pd.Series(latest_trade)
    trade_seconds = latest_series.dt.hour * 3600 + latest_series.dt.minute * 60 + latest_series.dt.second
    proxy_regular = (trade_seconds >= 9.5 * 3600) & (trade_seconds < 16 * 3600)
    result = pd.DataFrame({
        "source_row_start": np.arange(n) * 10, "company": company[:, 0],
        "capture_start": capture_start, "capture_end": capture_end, "latest_trade_naive": latest_trade,
        "capture_span_seconds": seconds,
        "wall_clock_gap_seconds": (capture_end - latest_trade) / np.timedelta64(1, "s"),
        "best_bid": best_bid, "best_ask": best_ask, "mid_price": mid,
        "spread_bps": spread, "max_depth_distance_bps": distance,
        "median_trade_mid_distance_bps": trade_distance,
        "bad_company_block": ~same_company, "bad_side_pattern": ~pattern,
        "bad_capture_time": ~(sane_capture & capture_monotonic & date_match),
        "incomplete_or_invalid_book": ~book_numeric,
        "incomplete_or_invalid_trades": ~trade_numeric, "missing_trade_time": ~all_trade_times,
        "duplicate_price_levels": ~distinct & book_numeric,
        "locked_or_crossed_book": ~uncrossed & book_numeric,
        "unexpected_book_row_order": ~source_order & book_numeric,
        "trade_time_not_descending": ~trade_order & all_trade_times,
        "duplicate_snapshot_within_file": duplicate_snapshot,
        "ambiguous_capture_key_within_file": ambiguous,
        "structurally_reconstructable": structure,
        "complete_candidate": candidate & ~duplicate_snapshot,
        "latest_trade_in_regular_hours_proxy": proxy_regular.to_numpy(),
    })
    # Severity thresholds are diagnostics/sensitivity only, not cleaning policy.
    for threshold in (100, 500, 1000):
        result[f"spread_over_{threshold}bps"] = (spread > threshold) & book_numeric
        result[f"depth_over_{threshold}bps"] = (distance > threshold) & book_numeric
        result[f"trade_mid_over_{threshold}bps"] = (trade_distance > threshold) & book_numeric & trade_numeric
        result[f"candidate_within_{threshold}bps"] = result["complete_candidate"] & (spread <= threshold) & (distance <= threshold)
    summary["capture_min"] = str(pd.to_datetime(frame["File_Date"], format="mixed", errors="coerce").min())
    summary["capture_max"] = str(pd.to_datetime(frame["File_Date"], format="mixed", errors="coerce").max())
    summary["same_timestamp_group_sizes"] = {str(k): int(v) for k, v in frame.groupby(["Company", "File_Date"]).size().value_counts().items()}
    return result, summary


def summarize(part):
    flags = part.select_dtypes(include="bool").columns
    out = {name: int(part[name].sum()) for name in flags}
    out["snapshots"] = len(part)
    return out


def run(paths, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    daily, assets, samples, time_stats, jump_samples = [], [], [], [], []
    total = Counter()
    core = Counter()
    regular = Counter()
    example_counts = Counter()
    previous = {}
    read_errors = []
    inputs = []
    with gzip.open(output_dir / "snapshots.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        for ordinal, path in enumerate(paths, 1):
            before = sha256(path)
            try:
                frame = pd.read_parquet(path)
                info, details = inspect_frame(frame)
            except Exception as exc:
                read_errors.append({"file": path.name, "error": str(exc)})
                continue
            if sha256(path) != before:
                raise ValueError(f"input changed: {path}")
            inputs.append({"file": path.name, "bytes": path.stat().st_size, "sha256": before, **details})
            if info.empty:
                continue
            info.insert(0, "source_file", path.name)
            flags = info.select_dtypes(include="bool").columns
            info.to_csv(handle, index=False, header=ordinal == 1)
            total.update(summarize(info))
            core_mask = info["capture_end"].between("2025-03-03", "2025-08-01", inclusive="left")
            core.update(summarize(info.loc[core_mask]))
            regular.update(summarize(info.loc[core_mask & info["latest_trade_in_regular_hours_proxy"]]))
            daily.append({"file": path.name, **summarize(info), "rows": len(frame), "trailing_rows": details["trailing_rows"]})
            for company, part in info.groupby("company", sort=True):
                for scope, selected in (("all", part), ("paper_period", part.loc[core_mask.loc[part.index]])):
                    if not selected.empty:
                        assets.append({"company": company, "scope": scope, **summarize(selected)})
                good = part.loc[part["complete_candidate"]].sort_values("capture_end")
                for threshold in (0, 100, 500, 1000):
                    selected = good if not threshold else good.loc[good[f"candidate_within_{threshold}bps"]]
                    if selected.empty:
                        continue
                    # Same-day jumps after each quality-screening scenario.
                    ratios = selected["mid_price"].pct_change().abs()
                    same_day = selected["capture_end"].dt.date.eq(selected["capture_end"].shift().dt.date)
                    for idx in selected.index[(ratios > .05) & same_day][:3]:
                        prev = selected.loc[:idx].iloc[-2]
                        row = selected.loc[idx]
                        jump_samples.append({"file": path.name, "company": company, "screen_bps": threshold,
                                             "previous_capture": str(prev["capture_end"]), "capture": str(row["capture_end"]),
                                             "previous_mid": prev["mid_price"], "mid": row["mid_price"],
                                             "absolute_return": ratios.loc[idx],
                                             "elapsed_seconds": (row["capture_end"] - prev["capture_end"]).total_seconds()})
                    total[f"same_day_jumps_gt5pct_screen_{threshold}"] += int(((ratios > .05) & same_day).sum())
                good = good.loc[good["candidate_within_500bps"]]
                if not good.empty:
                    last = previous.get(company)
                    if last is not None and last[0].date() == good.iloc[0]["capture_end"].date():
                        total["overlapping_dates_between_files"] += 1
                    previous[company] = (good.iloc[-1]["capture_end"], good.iloc[-1]["mid_price"])
            clean_times = info.loc[info["structurally_reconstructable"] & ~info["missing_trade_time"], "wall_clock_gap_seconds"]
            if len(clean_times):
                time_stats.append({"file": path.name, "date": str(info["capture_end"].min().date()),
                                   **{f"p{q}": float(clean_times.quantile(q / 100)) for q in (1, 10, 50, 90, 99)}})
            issue_names = [c for c in flags if c.startswith(("bad_", "incomplete_", "missing_", "locked_", "unexpected_", "duplicate_", "ambiguous_", "trade_mid_over_500", "depth_over_500"))]
            for issue in issue_names:
                remaining = max(0, 5 - example_counts[issue])
                for _, row in info.loc[info[issue]].head(remaining).iterrows():
                    start = int(row["source_row_start"])
                    raw = frame.iloc[start:start + 10].copy()
                    raw.insert(0, "source_row", np.arange(start, start + len(raw)))
                    samples.append({"issue": issue, "source_file": path.name, "source_row_start": start,
                                    "rows": json.loads(raw.to_json(orient="records", date_format="iso"))})
                    example_counts[issue] += 1
            print(f"[{ordinal}/{len(paths)}] {path.name}: {len(info)} candidates; {int(info['complete_candidate'].sum())} complete", flush=True)
    pd.DataFrame(daily).to_csv(output_dir / "by_file.csv", index=False)
    if assets:
        pd.DataFrame(assets).groupby(["scope", "company"], sort=True).sum().to_csv(output_dir / "by_asset.csv")
    pd.DataFrame(time_stats).to_csv(output_dir / "clock_gaps.csv", index=False)
    pd.DataFrame(jump_samples).to_csv(output_dir / "jump_examples.csv", index=False)
    with (output_dir / "raw_examples.json").open("w") as handle:
        json.dump(samples, handle, indent=2, allow_nan=False)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "audit_code_sha256": sha256(Path(__file__)),
              "python": sys.version, "pandas": pd.__version__, "numpy": np.__version__,
              "files_requested": len(paths), "files_read": len(inputs), "read_errors": read_errors,
              "totals": dict(total), "paper_period": dict(core), "paper_period_regular_trade_time_proxy": dict(regular),
              "inputs": inputs,
              "limitations": ["candidate IDs inferred from ten consecutive original rows; not original collector IDs",
                              "all capture and trade timestamps are naive; host timezone and source clock need confirmation",
                              "trade-time regular-hours proxy is not the book timestamp or an exchange calendar",
                              "duplicate snapshot/key checks are within each file; cross-file row identity is not certified",
                              "structural completeness does not establish quote accuracy or executable liquidity",
                              "thresholds are sensitivity diagnostics, not a selected cleaning policy",
                              "jumps are among successive retained candidates, possibly separated by gaps",
                              "no raw values are repaired, imputed or overwritten"]}
    report["output_sha256"] = {p.name: sha256(p) for p in sorted(output_dir.iterdir()) if p.is_file()}
    with (output_dir / "summary.json").open("w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = list(args.input_dir.glob("data_scrapping_*.parquet"))
    paths.sort(key=lambda p: (datetime.strptime(p.stem.removeprefix("data_scrapping_"), "%d_%m_%Y"), p.name))
    if not paths:
        parser.error("no raw Parquet files found")
    report = run(paths, args.output_dir)
    print(json.dumps({k: report[k] for k in ("files_read", "totals", "paper_period")}, indent=2))
    return 2 if report["read_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
