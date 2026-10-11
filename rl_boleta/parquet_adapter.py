"""Reconstruct legacy Cboe captures without reusing dissertation results.

Input files are explicit; output is provisional, compressed canonical JSONL.
Original ten-row blocks are never sorted or filtered before reconstruction.
"""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from rl_boleta import data_pipeline
from rl_boleta.audit_parquet import inspect_frame
from rl_boleta.data_pipeline import Config, UTC, digest, iso, validate_snapshot

# Explicit source labels, verified against the raw audit; GE is outside the paper.
COMPANY_TICKERS = {
    "APPLE INC COM": "AAPL", "TESLA INC COM": "TSLA",
    "MICROSOFT CORP COM": "MSFT", "CISCO SYS INC COM": "CSCO",
    "FORD MTR CO DEL COM": "F", "CITIGROUP INC COM NEW": "C",
    "FREEPORT-MCMORAN INC CL B": "FCX", "BK OF AMERICA CORP COM": "BAC",
    "COCA COLA CO COM": "KO", "INTEL CORP COM": "INTC",
    "GENERAL MTRS CO COM": "GM", "AMERICAN AIRLS GROUP INC COM": "AAL",
    "NORWEGIAN CRUISE LINE HLDG LTD SHS": "NCLH", "JPMORGAN CHASE & CO COM": "JPM",
    "PFIZER INC COM": "PFE", "MORGAN STANLEY COM NEW": "MS",
    "DELTA AIR LINES INC DEL COM NEW": "DAL", "NEWMONT CORP COM": "NEM",
    "GENERAL ELECTRIC CO COM NEW": "GE",
}


@dataclass(frozen=True)
class Timing:
    collection_timezone: str
    trade_timezone: str
    collection_timezone_status: str = "hypothesis"
    trade_timezone_status: str = "hypothesis"
    source_delay_seconds: int = 10800
    source_delay_interpretation: str = "unresolved"

    def __post_init__(self):
        ZoneInfo(self.collection_timezone)
        ZoneInfo(self.trade_timezone)
        for value in (self.collection_timezone_status, self.trade_timezone_status):
            if value not in ("hypothesis", "confirmed"):
                raise ValueError("timezone status must be hypothesis or confirmed")
        if type(self.source_delay_seconds) is not int or self.source_delay_seconds < 0:
            raise ValueError("source delay must be a nonnegative integer")
        if self.source_delay_interpretation not in ("unresolved", "availability-lag"):
            raise ValueError("unsupported delay interpretation")


def localize(value, zone):
    """Reject ambiguous/nonexistent wall times instead of guessing a DST fold."""
    naive = datetime.fromisoformat(str(value))
    if naive.tzinfo is not None:
        raise ValueError("raw timestamp unexpectedly contains timezone")
    candidates = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=ZoneInfo(zone), fold=fold).astimezone(UTC)
        if aware.astimezone(ZoneInfo(zone)).replace(tzinfo=None) == naive:
            candidates.add(aware)
    if len(candidates) != 1:
        raise ValueError("ambiguous or nonexistent local timestamp")
    return candidates.pop()


def reconstruct(rows, info, source, timing, config):
    """Return one canonical snapshot or reject the whole original block."""
    if not info["complete_candidate"]:
        flags = [name for name, value in info.items() if value and (
            name.startswith("bad_") or name.startswith("incomplete_") or name in (
                "missing_trade_time", "duplicate_price_levels", "locked_or_crossed_book",
                "ambiguous_capture_key_within_file", "duplicate_snapshot_within_file"))]
        raise ValueError(";".join(flags) or "incomplete_candidate")
    available = localize(info["capture_end"], timing.collection_timezone)
    trade_date = available.astimezone(ZoneInfo(timing.trade_timezone)).date()
    # Date was generated on the collection machine, not supplied by the exchange.
    # Without the original source date, day rollover cannot be reconstructed.
    if any(datetime.fromisoformat(str(r["Date"])).date() != trade_date for r in rows):
        raise ValueError("trade calendar date ambiguous across timezones")
    trades = [{"at": iso(localize(f"{trade_date} {r['Time']}", timing.trade_timezone)),
               "price": float(r["Price_of_One_Share"]),
               "size": float(r["Number_of_Shares_Sold"])} for r in rows]
    provenance = {
        **source, "provisional": True,
        "timing": asdict(timing),
        "trade_date_policy": "same calendar date only; reject timezone date rollover",
        "raw_capture_times": [str(r["File_Date"]) for r in rows],
        "raw_dates": [str(r["Date"]) for r in rows],
        "raw_trade_times": [str(r["Time"]) for r in rows],
        "raw_company": rows[0]["Company"],
        "source_delay_origin": "user-provided; not independently verified",
        "calendar_filtered": False,
    }
    if timing.source_delay_interpretation == "availability-lag":
        provenance["estimated_book_at"] = iso(available - timedelta(seconds=timing.source_delay_seconds))
        provenance["estimated_book_at_basis"] = "assumed fixed availability lag; not a source timestamp"
    levels = [{"price": float(r["Prices_Top_of_Book"]),
               "size": float(r["Shares_Top_of_Book"])} for r in rows]
    return validate_snapshot({
        "schema_version": 1,
        "snapshot_id": f"cboe:{source['source_sha256']}:{source['source_row_start']}",
        "ticker": COMPANY_TICKERS[rows[0]["Company"]], "source": "legacy-cboe-parquet",
        "available_at": iso(available), "book_at": None,
        "asks": levels[:5], "bids": levels[5:], "trades": trades,
        "provenance": provenance,
    }, config)


def convert(paths, output_dir, config, timing):
    paths = sorted((Path(p).resolve() for p in paths), key=str)
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("provide distinct explicit Parquet inputs")
    if any(p.suffix != ".parquet" for p in paths):
        raise ValueError("only raw Parquet inputs are supported")
    if config.book_levels != 5 or config.recent_trades != 10:
        raise ValueError("legacy captures contain exactly five levels per side and ten trades")
    if not set(config.tickers) <= set(COMPANY_TICKERS.values()):
        raise ValueError("ticker missing from explicit source mapping")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "status": "in_progress", "training_ready": False,
        "config": asdict(config), "timing": asdict(timing),
        "company_tickers": COMPANY_TICKERS, "inputs": [], "outputs": {},
        "counts": {}, "rejection_reasons": {},
        "created_at": iso(datetime.now(UTC)), "python_version": sys.version,
        "code_sha256": {"adapter": digest(Path(__file__)),
                        "validator": digest(Path(data_pipeline.__file__)),
                        "audit": digest(Path(inspect_frame.__code__.co_filename))},
        "limitations": ["timezone and delay assumptions remain explicit",
                        "book market timestamp is unknown; book_at remains null",
                        "no exchange calendar or session filtering; not a training dataset"],
    }
    manifest_path = output_dir / "manifest.json"

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    save()
    totals, reasons, seen_hashes = Counter(), Counter(), set()
    fields = ["source_file", "source_sha256", "source_row_start", "source_row_end", "reason"]
    try:
        with (output_dir / "rejections.csv").open("w", encoding="utf-8", newline="") as rejected:
            writer = csv.DictWriter(rejected, fieldnames=fields)
            writer.writeheader()
            for file_index, path in enumerate(paths):
                sha = digest(path)
                if sha in seen_hashes:
                    raise ValueError(f"duplicate input content: {path}")
                seen_hashes.add(sha)
                frame = pd.read_parquet(path)
                diagnostics, details = inspect_frame(frame)
                counts = Counter(rows=len(frame), candidates=len(diagnostics))
                name = f"snapshots_{file_index:04d}_{path.stem}.jsonl.gz"
                raw_rows = frame.to_dict("records")
                with gzip.open(output_dir / name, "wt", encoding="utf-8", compresslevel=6) as output:
                    for info in diagnostics.to_dict("records"):
                        start = int(info["source_row_start"])
                        source = {"source_file": str(path), "source_sha256": sha,
                                  "source_row_start": start, "source_row_end": start + 9}
                        company = info["company"]
                        # Unknown labels fail visibly; known assets outside universe are counted.
                        if (not info["bad_company_block"] and company in COMPANY_TICKERS
                                and COMPANY_TICKERS[company] not in config.tickers):
                            counts["outside_universe"] += 1
                            continue
                        try:
                            if company not in COMPANY_TICKERS:
                                raise ValueError(f"unmapped source company: {company}")
                            record = reconstruct(raw_rows[start:start + 10], info, source, timing, config)
                        except ValueError as exc:
                            counts["rejected"] += 1
                            reasons[str(exc)] += 1
                            writer.writerow({**source, "reason": str(exc)})
                            continue
                        output.write(json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
                        counts["accepted"] += 1
                    if details["trailing_rows"]:
                        start = len(diagnostics) * 10
                        writer.writerow({"source_file": str(path), "source_sha256": sha,
                                         "source_row_start": start, "source_row_end": len(frame) - 1,
                                         "reason": "trailing incomplete ten-row block"})
                        counts["trailing_rows"] = details["trailing_rows"]
                        reasons["trailing incomplete ten-row block"] += 1
                if digest(path) != sha:
                    raise ValueError(f"input changed during conversion: {path}")
                manifest["inputs"].append({"path": str(path), "sha256": sha, "counts": dict(counts)})
                manifest["outputs"][name] = digest(output_dir / name)
                totals.update(counts)
                print(json.dumps({"input": path.name, "counts": dict(counts)}), flush=True)
        manifest["outputs"]["rejections.csv"] = digest(output_dir / "rejections.csv")
        manifest["status"] = "provisional_converted"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        raise
    finally:
        manifest["counts"] = dict(totals)
        manifest["rejection_reasons"] = dict(reasons)
        save()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--max-spread-bps", type=float, required=True)
    parser.add_argument("--max-depth-distance-bps", type=float, required=True)
    parser.add_argument("--collection-timezone", required=True)
    parser.add_argument("--trade-timezone", required=True)
    parser.add_argument("--collection-timezone-status", choices=("hypothesis", "confirmed"), default="hypothesis")
    parser.add_argument("--trade-timezone-status", choices=("hypothesis", "confirmed"), default="hypothesis")
    parser.add_argument("--source-delay-seconds", type=int, default=10800)
    parser.add_argument("--source-delay-interpretation", choices=("unresolved", "availability-lag"), default="unresolved")
    args = parser.parse_args(argv)
    config = Config(tuple(args.tickers), args.max_spread_bps, args.max_depth_distance_bps)
    timing = Timing(**{k: v for k, v in vars(args).items() if k in Timing.__dataclass_fields__})
    report = convert(args.input, args.output_dir, config, timing)
    print(json.dumps({"status": report["status"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
