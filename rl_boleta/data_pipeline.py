"""Validate new structured market snapshots and align them causally.

Run with ``python -m rl_boleta.data_pipeline --help``. Uses the standard
library so that data preparation does not require the RL environment.
"""

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from rl_boleta import market_calendar

UTC = timezone.utc
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Config:
    tickers: tuple[str, ...]
    max_spread_bps: float
    max_depth_distance_bps: float
    frequency_seconds: int = 60
    max_age_seconds: int = 60
    session_timezone: str = "America/New_York"
    session_start: str = "09:30"
    session_end: str = "16:00"
    book_levels: int = 5
    recent_trades: int = 10
    calendar: str = "configured-hours"
    session_first_date: str | None = None
    session_last_date: str | None = None
    temporal_policy: str = "capture-time"

    def __post_init__(self):
        if not self.tickers or len(set(self.tickers)) != len(self.tickers):
            raise ValueError("tickers must be nonempty and unique")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9.-]*", t) for t in self.tickers):
            raise ValueError("use explicit exchange symbols, such as AAPL and TSLA")
        for name in ("frequency_seconds", "max_age_seconds", "book_levels", "recent_trades"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_spread_bps", "max_depth_distance_bps"):
            number(getattr(self, name), name, positive=True)
        ZoneInfo(self.session_timezone)
        start, end = time.fromisoformat(self.session_start), time.fromisoformat(self.session_end)
        if start.tzinfo or end.tzinfo or start >= end:
            raise ValueError("session hours must be local times with start < end")
        if self.temporal_policy != "capture-time":
            raise ValueError("only capture-time alignment is supported; source time is unverified")
        if self.calendar not in ("configured-hours", market_calendar.NAME):
            raise ValueError("unknown market calendar")
        if self.calendar == market_calendar.NAME:
            if (self.session_timezone, self.session_start, self.session_end) != ("America/New_York", "09:30", "16:00"):
                raise ValueError("verified calendar requires its official New York core hours")
            if not self.session_first_date or not self.session_last_date:
                raise ValueError("verified calendar requires explicit first and last session dates")
            list(market_calendar.dates(date.fromisoformat(self.session_first_date), date.fromisoformat(self.session_last_date)))
        elif self.session_first_date or self.session_last_date:
            raise ValueError("date bounds require the verified calendar")


def number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected a number")
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"{name}: invalid numeric value")
    return float(value)


def timestamp(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name}: expected an ISO 8601 timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}: invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name}: timezone offset required")
    return result.astimezone(UTC)


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def validate_snapshot(record, config):
    """Return a normalized snapshot; never repair missing prices or timestamps."""
    if not isinstance(record, dict):
        raise ValueError("snapshot must be an object")
    if type(record.get("schema_version")) is not int or record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")
    for name in ("snapshot_id", "ticker", "source"):
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise ValueError(f"{name}: nonempty string required")
    if record["ticker"] not in config.tickers:
        raise ValueError("ticker outside the configured universe")
    available = timestamp(record.get("available_at"), "available_at")
    result = {name: record[name] for name in ("schema_version", "snapshot_id", "ticker", "source")}
    result["available_at"] = iso(available)
    # Optional book market time is not inferred from the capture time or trades.
    book_time = record.get("book_at")
    result["book_at"] = None
    if book_time is not None:
        book_time = timestamp(book_time, "book_at")
        if book_time > available:
            raise ValueError("book_at is later than available_at")
        result["book_at"] = iso(book_time)
    for side, reverse in (("bids", True), ("asks", False)):
        levels = record.get(side)
        if not isinstance(levels, list) or len(levels) < config.book_levels:
            raise ValueError(f"{side}: insufficient book depth")
        normalized = []
        for level in levels:
            if not isinstance(level, dict):
                raise ValueError(f"{side}: each level must be an object")
            normalized.append({
                "price": number(level.get("price"), f"{side}.price", positive=True),
                "size": number(level.get("size"), f"{side}.size", positive=True),
            })
        if len({level["price"] for level in normalized}) != len(normalized):
            raise ValueError(f"{side}: duplicate price levels")
        result[side] = sorted(normalized, key=lambda x: x["price"], reverse=reverse)
    bid, ask = result["bids"][0]["price"], result["asks"][0]["price"]
    if bid >= ask:
        raise ValueError("locked or crossed book")
    mid = (bid + ask) / 2
    if (ask - bid) / mid * 10000 > config.max_spread_bps:
        raise ValueError("spread exceeds configured limit")
    for side in ("bids", "asks"):
        for level in result[side][:config.book_levels]:
            if abs(level["price"] / mid - 1) * 10000 > config.max_depth_distance_bps:
                raise ValueError("book depth price exceeds configured distance from midpoint")
    trades = record.get("trades")
    if not isinstance(trades, list) or len(trades) < config.recent_trades:
        raise ValueError("insufficient recent trades")
    normalized = []
    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("each trade must be an object")
        trade_time = timestamp(trade.get("at"), "trade.at")
        if trade_time > available:
            raise ValueError("trade is later than available_at")
        normalized.append({
            "at": iso(trade_time),
            "price": number(trade.get("price"), "trade.price", positive=True),
            "size": number(trade.get("size"), "trade.size"),
        })
    # Stable ordering retains distinct trades with the same time/price/size.
    result["trades"] = sorted(normalized, key=lambda x: timestamp(x["at"], "at"), reverse=True)
    if "provenance" in record:
        if not isinstance(record["provenance"], dict):
            raise ValueError("provenance must be an object")
        # Copy JSON metadata without dropping temporal assumptions on validation.
        result["provenance"] = json.loads(json.dumps(record["provenance"], allow_nan=False))
    return result


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_snapshots(paths, config):
    """Audit every input record, with deterministic cross-file deduplication."""
    accepted, rejected, inputs = [], [], []
    identities, moments = {}, {}
    duplicate_count = 0
    for path in sorted(paths, key=lambda p: str(p.resolve())):
        before = digest(path)
        count = 0
        opener = gzip.open if path.name.endswith(".jsonl.gz") else open
        with opener(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                count += 1
                raw = None
                try:
                    raw = json.loads(line)
                    snapshot = validate_snapshot(raw, config)
                except (ValueError, TypeError) as exc:
                    rejected.append({
                        "source_file": str(path.resolve()), "source_line": line_number,
                        "reason": str(exc),
                        "snapshot_id": raw.get("snapshot_id", "") if isinstance(raw, dict) else "",
                    })
                    continue
                identity = (snapshot["ticker"], snapshot["snapshot_id"])
                moment = (snapshot["ticker"], snapshot["available_at"])
                # Conflicting identities or capture times cannot be resolved by row order.
                if identity in identities:
                    if identities[identity] != snapshot:
                        raise ValueError(f"conflicting snapshot identity: {identity}")
                    duplicate_count += 1
                    continue
                if moment in moments:
                    raise ValueError(f"ambiguous capture time: {moment}")
                identities[identity] = snapshot
                moments[moment] = snapshot
                accepted.append({**snapshot, "source_file": str(path.resolve()), "source_line": line_number})
        if digest(path) != before:
            raise ValueError(f"input changed during reading: {path}")
        inputs.append({"path": str(path.resolve()), "sha256": before, "records": count})
    accepted.sort(key=lambda s: (timestamp(s["available_at"], "available_at"), s["ticker"], s["snapshot_id"]))
    return accepted, rejected, inputs, duplicate_count


def feature_names(config):
    names = ["decision_at", "session_id", "segment_id", "step_in_segment"]
    for ticker in config.tickers:
        fields = ["snapshot_id", "available_at", "book_at", "snapshot_age_seconds", "mid_price", "spread_bps"]
        for side in ("bid", "ask"):
            for level in range(1, config.book_levels + 1):
                fields.extend((f"{side}_price_{level}", f"{side}_size_{level}"))
        for trade in range(1, config.recent_trades + 1):
            fields.extend((f"trade_at_{trade}", f"trade_price_{trade}", f"trade_size_{trade}"))
        names.extend(f"{ticker}_{field}" for field in fields)
    return names


def snapshot_session_failure(snapshot, config):
    """Classify calendar exclusions without deleting the validated raw snapshot."""
    if config.calendar == "configured-hours":
        return None
    at = timestamp(snapshot["available_at"], "available_at")
    day = at.astimezone(market_calendar.ZONE).date()
    if not date.fromisoformat(config.session_first_date) <= day <= date.fromisoformat(config.session_last_date):
        return "outside_requested_dates"
    bounds = market_calendar.window(day)
    if bounds is None:
        return "market_closed"
    start, end = bounds
    if at < start:
        return "before_session_open"
    if at >= end:
        return "at_or_after_session_close"
    return None


def align_snapshots(snapshots, config):
    """Yield (row, failure) for each grid point, using only available past data.

    The grid is anchored at the configured local session start. Sessions are
    capture-date groups in configured-hours mode. The verified calendar uses
    complete sessions, including missing days. No snapshot carries across opens.
    """
    tz = ZoneInfo(config.session_timezone)
    sessions = defaultdict(lambda: defaultdict(list))
    if config.calendar == market_calendar.NAME:
        for day in market_calendar.dates(date.fromisoformat(config.session_first_date), date.fromisoformat(config.session_last_date)):
            if market_calendar.window(day):
                sessions[day]  # Include sessions with no observations at all.
    for snapshot in snapshots:
        if snapshot_session_failure(snapshot, config):
            continue
        at = timestamp(snapshot["available_at"], "available_at")
        sessions[at.astimezone(tz).date()][snapshot["ticker"]].append((at, snapshot))
    for day, assets in sorted(sessions.items()):
        for values in assets.values():
            values.sort(key=lambda item: item[0])
        start = datetime.combine(day, time.fromisoformat(config.session_start), tz).astimezone(UTC)
        end = datetime.combine(day, time.fromisoformat(config.session_end), tz).astimezone(UTC)
        if config.calendar == market_calendar.NAME:
            start, end = (at.astimezone(UTC) for at in market_calendar.window(day))
        else:
            # Legacy exploratory mode: truncate at the last observed capture.
            last_capture = max(at for values in assets.values() for at, _ in values)
            end = min(end, last_capture)
        times = {ticker: [at for at, _ in values] for ticker, values in assets.items()}
        decision = start
        segment_number, segment_step = 0, 0
        previous_valid = False
        while decision < end or (config.calendar == "configured-hours" and decision == end):
            row = {"decision_at": iso(decision), "session_id": day.isoformat()}
            failures = []
            for ticker in config.tickers:
                index = bisect.bisect_right(times.get(ticker, []), decision) - 1
                if index < 0:
                    failures.append(f"{ticker}:missing_past_snapshot")
                    continue
                at, snapshot = assets[ticker][index]
                age = (decision - at).total_seconds()
                if age > config.max_age_seconds:
                    failures.append(f"{ticker}:stale_snapshot")
                    continue
                bid, ask = snapshot["bids"][0]["price"], snapshot["asks"][0]["price"]
                mid = (bid + ask) / 2
                values = {
                    "snapshot_id": snapshot["snapshot_id"], "available_at": iso(at),
                    "book_at": snapshot["book_at"], "snapshot_age_seconds": age,
                    "mid_price": mid, "spread_bps": (ask - bid) / mid * 10000,
                }
                for plural, side in (("bids", "bid"), ("asks", "ask")):
                    for level, quote in enumerate(snapshot[plural][:config.book_levels], 1):
                        values[f"{side}_price_{level}"] = quote["price"]
                        values[f"{side}_size_{level}"] = quote["size"]
                for index, trade in enumerate(snapshot["trades"][:config.recent_trades], 1):
                    for key, value in trade.items():
                        values[f"trade_{key}_{index}"] = value
                row.update({f"{ticker}_{key}": value for key, value in values.items()})
            if failures:
                previous_valid = False
                yield None, {"decision_at": iso(decision), "session_id": day.isoformat(), "reason": ";".join(failures)}
            else:
                if not previous_valid:
                    segment_number += 1
                    segment_step = 0
                row["segment_id"] = f"{day.isoformat()}:{segment_number:04d}"
                row["step_in_segment"] = segment_step
                segment_step += 1
                previous_valid = True
                yield row, None
            decision += timedelta(seconds=config.frequency_seconds)


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare(paths, output_dir, config):
    paths = [Path(p) for p in paths]
    if not paths or len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("provide distinct input files explicitly")
    if any(not p.name.endswith((".jsonl", ".jsonl.gz")) for p in paths):
        raise ValueError("expected structured .jsonl or .jsonl.gz snapshots; legacy CSV/Parquet is not supported")
    snapshots, rejected, inputs, duplicates = load_snapshots(paths, config)
    exclusions = []
    for snapshot in snapshots:
        reason = snapshot_session_failure(snapshot, config)
        if reason:
            exclusions.append({"snapshot_id": snapshot["snapshot_id"], "ticker": snapshot["ticker"],
                               "available_at": snapshot["available_at"], "reason": reason})
    output_dir = Path(output_dir)
    # An experimental dataset is immutable: choose another run directory.
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "snapshots.jsonl").open("w", encoding="utf-8") as handle:
        for snapshot in snapshots:
            handle.write(json.dumps(snapshot, sort_keys=True, allow_nan=False) + "\n")
    write_csv(output_dir / "rejected_snapshots.csv", ["source_file", "source_line", "reason", "snapshot_id"], rejected)
    write_csv(output_dir / "excluded_sessions.csv", ["snapshot_id", "ticker", "available_at", "reason"], exclusions)
    rows_count, skipped_count = 0, 0
    sessions = Counter()
    skipped_reasons = Counter()
    segment_rows = {}
    session_expected, session_rejected = Counter(), Counter()
    with (output_dir / "market.csv").open("w", encoding="utf-8", newline="") as market, (output_dir / "rejected_grid.csv").open("w", encoding="utf-8", newline="") as grid:
        writer = csv.DictWriter(market, fieldnames=feature_names(config))
        writer.writeheader()
        grid_writer = csv.DictWriter(grid, fieldnames=["decision_at", "session_id", "reason"])
        grid_writer.writeheader()
        for row, failure in align_snapshots(snapshots, config):
            session_expected[(failure or row)["session_id"]] += 1
            if failure:
                grid_writer.writerow(failure)
                skipped_count += 1
                session_rejected[failure["session_id"]] += 1
                skipped_reasons.update(failure["reason"].split(";"))
            else:
                writer.writerow(row)
                rows_count += 1
                sessions[row["session_id"]] += 1
                segment = segment_rows.setdefault(row["segment_id"], {
                    "segment_id": row["segment_id"], "session_id": row["session_id"],
                    "first_decision_at": row["decision_at"], "last_decision_at": row["decision_at"], "points": 0})
                segment["last_decision_at"] = row["decision_at"]
                segment["points"] += 1
    write_csv(output_dir / "segments.csv", ["segment_id", "session_id", "first_decision_at", "last_decision_at", "points"], segment_rows.values())
    write_csv(output_dir / "session_coverage.csv", ["session_id", "expected_points", "accepted_points", "rejected_points"], [
        {"session_id": day, "expected_points": count, "accepted_points": sessions[day], "rejected_points": session_rejected[day]}
        for day, count in sorted(session_expected.items())])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "prepared" if rows_count else "no_aligned_rows",
        "training_ready": False,
        "provisional_input_snapshots": sum(s.get("provenance", {}).get("provisional", False) is True for s in snapshots),
        "config": asdict(config), "inputs": inputs,
        "pipeline_sha256": digest(Path(__file__)),
        "calendar": {**market_calendar.metadata(), "code_sha256": digest(Path(market_calendar.__file__))} if config.calendar == market_calendar.NAME else None,
        "temporal_policy": {"alignment_clock": "available_at", "source_delay_correction": "none",
                            "session_interval": "[open, close)" if config.calendar == market_calendar.NAME else "observed configured hours",
                            "maximum_age_clock": "time since capture, not market book age",
                            "gap_policy": "split segments; no interpolation or carry across sessions"},
        "python_version": sys.version, "created_at": iso(datetime.now(UTC)),
        "counts": {"accepted_snapshots": len(snapshots), "rejected_snapshots": len(rejected),
                   "duplicate_snapshots": duplicates, "aligned_rows": rows_count, "rejected_grid_points": skipped_count,
                   "session_excluded_snapshots": len(exclusions), "segments": len(segment_rows),
                   "expected_sessions": len(session_expected), "sessions_without_aligned_rows": sum(not sessions[d] for d in session_expected)},
        "session_exclusion_reasons": dict(Counter(r["reason"] for r in exclusions)),
        "rejected_snapshot_reasons": dict(Counter(r["reason"] for r in rejected)),
        "rejected_grid_reasons": dict(skipped_reasons), "rows_per_session": dict(sessions),
        "limitations": ["capture-time alignment; source delay is not inferred",
                        "source book session cannot be certified from capture timestamps",
                        "market.csv is a market-data layer, not input for the legacy RL environment"],
        "outputs": {name: digest(output_dir / name) for name in (
            "snapshots.jsonl", "market.csv", "rejected_snapshots.csv", "rejected_grid.csv",
            "excluded_sessions.csv", "segments.csv", "session_coverage.csv")},
    }
    if rows_count and manifest["provisional_input_snapshots"]:
        manifest["status"] = "provisional_prepared"
    if config.calendar == "configured-hours":
        manifest["limitations"].append("configured-hours mode does not verify holidays or early closes")
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="explicit snapshot JSONL or JSONL.gz files")
    parser.add_argument("--output-dir", type=Path, required=True, help="new immutable run directory")
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--max-spread-bps", type=float, required=True)
    parser.add_argument("--max-depth-distance-bps", type=float, required=True)
    parser.add_argument("--frequency-seconds", type=int, default=60)
    parser.add_argument("--max-age-seconds", type=int, default=60)
    parser.add_argument("--session-timezone", default="America/New_York")
    parser.add_argument("--session-start", default="09:30")
    parser.add_argument("--session-end", default="16:00")
    parser.add_argument("--calendar", choices=("configured-hours", market_calendar.NAME), default="configured-hours")
    parser.add_argument("--session-first-date", help="inclusive ISO date; required with verified calendar")
    parser.add_argument("--session-last-date", help="inclusive ISO date; required with verified calendar")
    parser.add_argument("--temporal-policy", choices=("capture-time",), default="capture-time")
    args = parser.parse_args(argv)
    try:
        settings = {k: v for k, v in vars(args).items() if k not in ("input", "output_dir")}
        settings["tickers"] = tuple(args.tickers)
        config = Config(**settings)
        report = prepare(args.input, args.output_dir, config)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Data preparation failed: {exc}\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "output_dir": str(args.output_dir)}))
    return 0 if report["counts"]["aligned_rows"] else 2


if __name__ == "__main__":
    sys.exit(main())
