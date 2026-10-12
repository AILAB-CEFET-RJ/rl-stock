"""Coverage-only alternatives: causal late entry and per-asset unavailability.

No portfolio, executable-liquidity inference, reward, imputation or training.
Uses the verified grid of the original March--July 2025 data audit.
"""
import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .data_pipeline import digest, iso
from .session_replay import session_plan


def first_ready(joint, window=21):
    """Earliest readiness depends exclusively on a trailing valid window."""
    run = 0
    for index, valid in enumerate(joint):
        run = run+1 if valid else 0
        if run >= window:
            return index
    return None


def rolling_ready(values, window=21):
    run = 0
    ready = []
    for valid in values:
        run = run+1 if valid else 0
        ready.append(run >= window)
    return ready


def analyze_day(assets, window=21, minimum_horizon=2):
    n = len(next(iter(assets.values())))
    if not n or any(len(v)!=n for v in assets.values()):
        raise ValueError('aligned nonempty per-asset arrays required')
    joint = [all(v[i] for v in assets.values()) for i in range(n)]
    entry = first_ready(joint, window)
    exit_available = joint[-1]
    horizon = None if entry is None else n-1-entry
    starts = entry is not None and horizon >= minimum_horizon
    strict = starts and all(joint[entry:])
    masked = starts and exit_available
    mature = {t:rolling_ready(v,window) for t,v in assets.items()}
    gaps, longest_gap, gap_counts, fill_pairs = Counter(), Counter(), Counter(), Counter()
    no_asset_minutes = no_mature_minutes = all_mature_minutes = joint_missing_minutes = 0
    if starts:
        for ticker, values in assets.items():
            run = 0
            for valid in values[entry:]:
                if not valid:
                    if run==0:
                        gap_counts[ticker] += 1
                    run += 1; gaps[ticker] += 1
                    longest_gap[ticker] = max(longest_gap[ticker],run)
                else:
                    run = 0
            # Decisions stop two grid steps before exit; fill in next step.
            fill_pairs[ticker] = sum(values[i] and values[i+1] for i in range(entry,n-2))
        for i in range(entry,n-1):
            no_asset_minutes += not any(v[i] for v in assets.values())
            no_mature_minutes += not any(v[i] for v in mature.values())
            all_mature_minutes += all(v[i] for v in mature.values())
            joint_missing_minutes += not joint[i]
    return dict(entry_index=entry,remaining_transitions=horizon,
        causal_entry_available=starts,strict_continuous_from_causal_entry=strict,
        masked_coverage_candidate=masked,all_assets_exit_available=exit_available,
        missing_exit_assets=[t for t,v in assets.items() if not v[-1]],
        discretionary_points=0 if not starts else max(0,n-2-entry),
        minutes_without_any_current_asset=no_asset_minutes,
        minutes_without_any_full_window_asset=no_mature_minutes,
        discretionary_or_prefinal_points_all_full_window_assets=all_mature_minutes,
        joint_missing_points_before_exit=joint_missing_minutes,
        asset_missing_points=dict(gaps),asset_gap_runs=dict(gap_counts),
        asset_longest_gap_minutes=dict(longest_gap),
        potential_decision_fill_pairs_by_asset=dict(fill_pairs))


def run(input_dir, protocol_path, output_dir):
    input_dir, protocol_path, output_dir = map(Path,(input_dir,protocol_path,output_dir))
    manifest_path = input_dir/'manifest.json'
    source = json.loads(manifest_path.read_text())
    protocol = json.loads(protocol_path.read_text())
    if source['status']!='diagnostic_only':
        raise ValueError('completed gap audit required')
    source_inputs={str(Path(k).resolve()):v for k,v in source['source_manifests'].items()}
    if source_inputs.get(str(protocol_path.resolve()))!=digest(protocol_path):
        raise ValueError('protocol hash mismatch')
    grid_path = input_dir/'asset_grid.csv.gz'
    if digest(grid_path)!=source['outputs_sha256'][grid_path.name]:
        raise ValueError('grid hash mismatch')
    input_hashes={str(p):digest(p) for p in (manifest_path,grid_path,protocol_path)}
    tickers = protocol['tickers']; grouped = defaultdict(dict)
    with gzip.open(grid_path,'rt') as handle:
        for row in csv.DictReader(handle):
            key = row['session_id'],row['decision_at']
            block = grouped[key[0]].setdefault(key[1],{})
            if row['ticker'] in block or row['ticker'] not in tickers:
                raise ValueError('duplicate or unexpected asset')
            block[row['ticker']] = row['state']=='valid'
    if len(grouped)!=source['session_count']:
        raise ValueError('session count mismatch')
    output_dir.mkdir(parents=True,exist_ok=False)
    details, records = [], []
    summary = Counter(); partition_counts = defaultdict(Counter)
    window = protocol['episode']['window_features']+1
    for day, grid in sorted(grouped.items()):
        plan = session_plan(datetime.fromisoformat(day).date(),protocol['episode']['window_features'])
        expected = [iso(at) for at in plan.required_times]
        if set(grid)!=set(expected) or any(set(block)!=set(tickers) for block in grid.values()):
            raise ValueError('grid differs from calendar or universe')
        assets = {t:[grid[at][t] for at in expected] for t in tickers}
        result = analyze_day(assets,window)
        partition = next(k for k in ('train','validation','test') if
                         protocol['partitions'][k]['first']<=day<=protocol['partitions'][k]['last'])
        entry = result['entry_index']
        record = dict(session_id=day,partition=partition,
            entry_at=None if entry is None else expected[entry],exit_at=expected[-1],
            **{k:v for k,v in result.items() if not isinstance(v,(list,dict))})
        details.append(dict(**record,missing_exit_assets=result['missing_exit_assets'],
            assets={t:dict(missing_points=result['asset_missing_points'].get(t,0),
                gap_runs=result['asset_gap_runs'].get(t,0),
                longest_gap_minutes=result['asset_longest_gap_minutes'].get(t,0),
                potential_decision_fill_pairs=result['potential_decision_fill_pairs_by_asset'].get(t,0))
                for t in tickers}))
        records.append(record)
        for key in ('causal_entry_available','strict_continuous_from_causal_entry',
                    'masked_coverage_candidate','all_assets_exit_available'):
            summary[key] += result[key]; partition_counts[partition][key] += result[key]
        for horizon in (30,60,120):
            qualified = result['masked_coverage_candidate'] and result['remaining_transitions']>=horizon
            key = f'masked_candidate_min_{horizon}_remaining_transitions'
            summary[key] += qualified; partition_counts[partition][key] += qualified
        for gap_cap in (1,2,5,15,30):
            for horizon in (2,60):
                qualified=(result['masked_coverage_candidate'] and result['remaining_transitions']>=horizon
                    and max(result['asset_longest_gap_minutes'].values(),default=0)<=gap_cap)
                key=f'masked_candidate_gap_cap_{gap_cap}_min_horizon_{horizon}'
                summary[key] += qualified; partition_counts[partition][key] += qualified
    with (output_dir/'sessions.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    with (output_dir/'details.jsonl').open('w') as handle:
        for record in details:handle.write(json.dumps(record)+'\n')
    report = dict(status='coverage_alternatives_audited',training_ready=False,
        purpose='Compare coverage hypotheses; no protocol change or financial replay',
        created_at=iso(datetime.now(timezone.utc)),session_count=len(details),
        summary=dict(summary),partitions={k:dict(v) for k,v in partition_counts.items()},
        inputs=input_hashes,
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('session_replay.py'))},
        timing_evidence='docs/clock_transition_audit.md; no additional fixed 3h correction',
        rules=dict(warmup_points=window,entry='first complete trailing joint warmup; never choose a later run using future coverage',
            minimum_remaining_transitions=2,exit='original scheduled liquidation minute, all 18 accepted books required',
            gaps='unavailable assets never assumed tradable; inventory continuity is a modeling requirement, not simulated here',
            minimum_horizon_sensitivities=[30,60,120]),
        limitations=['Coverage at exit does not prove sufficient liquidation depth or a flat portfolio.',
            'Quote masks require a revised observation representation for missing history.',
            'Full-window masks measured separately require rewarming after an asset gap.',
            'Potential adjacent decision/fill pairs are retrospective diagnostics, not policy inputs.',
            'Reward and valuation across gaps remain unspecified; no training dataset produced.',
            'Masks and variable entry change the task and need a new versioned protocol.',
            'Common exit coverage is retrospective selection; report excluded dates explicitly.'],
        outputs_sha256={p.name:digest(p) for p in output_dir.iterdir()})
    for path,expected in input_hashes.items():
        if digest(Path(path))!=expected:raise ValueError(f'input changed: {path}')
    (output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.input_dir,args.protocol,args.output_dir)
    print(json.dumps(dict(summary=report['summary'],partitions=report['partitions']),indent=2))


if __name__=='__main__':main()
