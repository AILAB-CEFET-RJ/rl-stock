"""Measure joint causal coverage on the audit's naive capture-time clock.

This is a feasibility diagnostic, not a market session or training dataset.
It uses the paper's 18 companies (GE excluded), March--July 2025.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rl_boleta.audit_parquet import sha256

PAPER_COMPANIES = (
    "APPLE INC COM", "TESLA INC COM", "MICROSOFT CORP COM", "CISCO SYS INC COM",
    "FORD MTR CO DEL COM", "CITIGROUP INC COM NEW", "FREEPORT-MCMORAN INC CL B",
    "BK OF AMERICA CORP COM", "COCA COLA CO COM", "INTEL CORP COM",
    "GENERAL MTRS CO COM", "AMERICAN AIRLS GROUP INC COM",
    "NORWEGIAN CRUISE LINE HLDG LTD SHS", "JPMORGAN CHASE & CO COM",
    "PFIZER INC COM", "MORGAN STANLEY COM NEW", "DELTA AIR LINES INC DEL COM NEW",
    "NEWMONT CORP COM",
)


def joint_coverage(part, grid, companies, age_seconds):
    covered = np.ones(len(grid), dtype=bool)
    for company in companies:
        times = part.loc[part["company"] == company, "capture_end"].sort_values().to_numpy()
        if not len(times):
            return np.zeros(len(grid), dtype=bool)
        indices = np.searchsorted(times, grid, side="right") - 1
        valid = indices >= 0
        ages = (grid - times[np.maximum(indices, 0)]) / np.timedelta64(1, "s")
        covered &= valid & (ages <= age_seconds)
    return covered


def run(audit_dir):
    audit_dir = Path(audit_dir)
    target = audit_dir / "joint_coverage.json"
    if target.exists() or (audit_dir / "joint_coverage_by_date.csv").exists():
        raise FileExistsError("coverage report already exists")
    columns = ["company", "capture_end", "complete_candidate", "candidate_within_100bps",
               "candidate_within_500bps", "candidate_within_1000bps"]
    chunks = []
    for chunk in pd.read_csv(audit_dir / "snapshots.csv.gz", usecols=columns, chunksize=100000):
        mask = chunk["capture_end"].between("2025-03-03", "2025-08-01", inclusive="left")
        chunks.append(chunk.loc[mask & chunk["company"].isin(PAPER_COMPANIES)])
    data = pd.concat(chunks, ignore_index=True)
    data["capture_end"] = pd.to_datetime(data["capture_end"], format="mixed")
    records = []
    for day, part in data.groupby(data["capture_end"].dt.date, sort=True):
        grid = pd.date_range(part["capture_end"].min().ceil("min"), part["capture_end"].max().floor("min"), freq="min").to_numpy()
        for screen in (0, 100, 500, 1000):
            column = "complete_candidate" if not screen else f"candidate_within_{screen}bps"
            eligible = part.loc[part[column]]
            for age in (60, 90, 120):
                covered = joint_coverage(eligible, grid, PAPER_COMPANIES, age)
                edges = np.diff(np.r_[False, covered, False].astype(int))
                lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
                records.append({"date": str(day), "screen_bps": screen, "max_age_seconds": age,
                                "grid_points": len(grid), "joint_points": int(covered.sum()),
                                "segments": len(lengths), "longest_segment_points": int(lengths.max()) if len(lengths) else 0,
                                "segments_at_least_51_points": int((lengths >= 51).sum())})
    daily = pd.DataFrame(records)
    daily.to_csv(audit_dir / "joint_coverage_by_date.csv", index=False)
    summaries = []
    for (screen, age), group in daily.groupby(["screen_bps", "max_age_seconds"], sort=True):
        summaries.append({"screen_bps": int(screen), "max_age_seconds": int(age),
                          "grid_points": int(group["grid_points"].sum()), "joint_points": int(group["joint_points"].sum()),
                          "joint_fraction": float(group["joint_points"].sum() / group["grid_points"].sum()),
                          "dates_with_joint_coverage": int((group["joint_points"] > 0).sum()),
                          "longest_segment_points": int(group["longest_segment_points"].max()),
                          "segments_at_least_51_points": int(group["segments_at_least_51_points"].sum())})
    report = {"companies": PAPER_COMPANIES, "period": ["2025-03-03", "2025-07-31"],
              "capture_dates": int(data["capture_end"].dt.date.nunique()), "scenarios": summaries,
              "inputs": {"snapshots.csv.gz": sha256(audit_dir / "snapshots.csv.gz")},
              "code_sha256": sha256(Path(__file__)),
              "output_sha256": sha256(audit_dir / "joint_coverage_by_date.csv"),
              "limitations": ["naive capture clock; no timezone assumption or market-session filtering",
                              "denominator is each observed day's first-to-last capture, not scheduled trading minutes",
                              "latest valid past capture, no future quotes and no cross-day carry",
                              "0 bps screen means no price-distance screen, not a zero-spread requirement",
                              "missing capture dates are outside the denominator",
                              "51 contiguous minute-grid points provide 50 observations plus one possible transition; "
                              "executable RL episodes require further simulator constraints"]}
    with target.open("w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, required=True)
    run(parser.parse_args().audit_dir)
