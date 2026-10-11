"""Coverage-only episode manifests: no policy, execution, returns or fitting.

Reuses the canonical adapter and preparer's causal alignment, one date at a
time, to bound memory. Eligibility remains conditional on explicit clock
assumptions; this diagnostic never certifies historical execution readiness.
"""
import argparse
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import data_pipeline, market_calendar
from .data_pipeline import Config, align_snapshots, digest, iso, load_snapshots, timestamp
from .session_replay import session_plan


def protocol_config(protocol, first, last):
    data, episode = protocol['data'], protocol['episode']
    if (data['calendar'] != market_calendar.NAME or data['grid_seconds'] != 60 or data['book_levels_per_side'] != 5 or
            data['recent_trades'] != 10 or episode['first_decision_index'] != episode['window_features']+1
            or episode['required_sequence_first_index'] != 1):
        raise ValueError('unsupported episode or data schema')
    return Config(tuple(protocol['tickers']), data['max_spread_bps'], data['max_depth_distance_bps'],
                  max_age_seconds=data['maximum_receipt_age_seconds'], calendar=data['calendar'],
                  session_first_date=str(first), session_last_date=str(last))


def _verify(path, expected):
    if digest(path) != expected:
        raise ValueError(f'provenance hash mismatch: {path}')


def build_manifest(adapter_dir, protocol_path, output_dir):
    adapter_dir, protocol_path, output_dir = map(Path, (adapter_dir, protocol_path, output_dir))
    adapter_path = adapter_dir/'manifest.json'
    adapter_sha, protocol_sha = digest(adapter_path), digest(protocol_path)
    adapter, protocol = (json.loads(p.read_text()) for p in (adapter_path, protocol_path))
    if adapter['status'] != 'provisional_converted':
        raise ValueError('completed canonical adapter manifest required')
    partitions = protocol['partitions']
    ranges = {key: (date.fromisoformat(v['first']), date.fromisoformat(v['last']))
              for key, v in partitions.items()}
    train, validation, test, refit = (ranges[k] for k in ('train', 'validation', 'test', 'final_refit'))
    if not (train[0] <= train[1] < validation[0] <= validation[1] < test[0] <= test[1]
            and refit == (train[0], validation[1])):
        raise ValueError('overlapping or inconsistent chronological partitions')
    for key, (first, last) in ranges.items():
        count = sum(market_calendar.window(d) is not None for d in market_calendar.dates(first, last))
        if count != partitions[key]['scheduled_sessions']:
            raise ValueError('declared calendar count mismatch')
    config = protocol_config(protocol, train[0], test[1])
    if adapter['timing']['source_delay_seconds'] != protocol['data']['source_delay_seconds']:
        raise ValueError('source delay differs from protocol')
    for key in ('tickers', 'max_spread_bps', 'max_depth_distance_bps', 'book_levels', 'recent_trades'):
        value = list(config.tickers) if key == 'tickers' else getattr(config, key)
        if adapter['config'][key] != value:
            raise ValueError(f'adapter configuration differs from protocol: {key}')
    grouped, sources = defaultdict(list), defaultdict(list)
    for name, sha in adapter['outputs'].items():
        if Path(name).name != name:
            raise ValueError('adapter output must be a local filename')
        _verify(adapter_dir/name, sha)
    for index, source in enumerate(adapter['inputs']):
        raw = Path(source['path'])
        _verify(raw, source['sha256'])
        match = re.fullmatch(r'data_scrapping_(\d+)_(\d+)_(\d+)\.parquet', raw.name)
        if not match:
            raise ValueError('explicit raw filename date required')
        day = date(int(match[3]), int(match[2]), int(match[1]))
        if not train[0] <= day <= test[1]:
            raise ValueError('input outside declared full period')
        name = f'snapshots_{index:04d}_{raw.stem}.jsonl.gz'
        if name not in adapter['outputs']:
            raise ValueError('canonical output missing from adapter manifest')
        grouped[day].append(adapter_dir/name)
        sources[day].append(source)
    output_dir.mkdir(parents=True, exist_ok=False)
    status_path = output_dir/'manifest.json'
    base = dict(schema_version=1, status='in_progress', training_ready=False,
                purpose='coverage only; no policy or financial outcomes',
                protocol_id=protocol['protocol_id'], protocol_sha256=protocol_sha,
                adapter_manifest=dict(path=str(adapter_path.resolve()), sha256=adapter_sha),
                timing=adapter['timing'], calendar=market_calendar.metadata(),
                code_sha256={p.name: digest(p) for p in (
                    Path(__file__), Path(data_pipeline.__file__), Path(market_calendar.__file__),
                    Path(__file__).with_name('session_replay.py'))},
                created_at=iso(datetime.now(timezone.utc)),
                limitations=['conditional on adapter clock assumptions',
                             'source delay recorded, not subtracted; capture-time grid',
                             'full coverage does not certify market prices or executable liquidity',
                             'no threshold relaxation or alternative segment selection'],
                partition_summary={}, outputs={})
    def save():
        status_path.write_text(json.dumps(base, indent=2, allow_nan=False)+'\n')
    save()
    records, excluded_counts = [], Counter()
    fields = ['session_id', 'partition', 'raw_files', 'accepted_captures', 'expected_grid_points',
              'valid_grid_points', 'required_points', 'valid_required_points', 'missing_required_points',
              'warmup_required_points', 'valid_warmup_points', 'startable', 'evaluable',
              'first_required_failure', 'first_runtime_failure', 'liquidation_observation_valid',
              'first_decision_at', 'liquidation_at', 'horizon', 'longest_valid_required_run']
    try:
        with (output_dir/'sessions.csv').open('w', newline='') as session_handle, \
             (output_dir/'required_failures.csv').open('w', newline='') as failure_handle, \
             gzip.open(output_dir/'alignment_trace.jsonl.gz', 'wt', encoding='utf-8') as trace:
            session_writer = csv.DictWriter(session_handle, fieldnames=fields); session_writer.writeheader()
            failure_writer = csv.DictWriter(failure_handle, fieldnames=['session_id', 'decision_at', 'reason']); failure_writer.writeheader()
            for day in market_calendar.dates(train[0], test[1]):
                bounds = market_calendar.window(day)
                if bounds is None:
                    excluded_counts['raw_files_on_closed_dates'] += len(grouped[day])
                    continue
                partition = next((key for key in ('train', 'validation', 'test')
                                  if ranges[key][0] <= day <= ranges[key][1]), None)
                if partition is None:
                    raise ValueError('scheduled date not assigned to a primary partition')
                daily_config = protocol_config(protocol, day, day)
                snapshots, rejected, inputs, duplicates = load_snapshots(grouped[day], daily_config)
                if rejected or duplicates:
                    raise ValueError('canonical inputs were rejected or duplicated on revalidation')
                for snapshot in snapshots:
                    if timestamp(snapshot['available_at'], 'available_at').astimezone(market_calendar.ZONE).date() != day:
                        raise ValueError('capture date differs from source-file date')
                    reason = data_pipeline.snapshot_session_failure(snapshot, daily_config)
                    if reason:
                        excluded_counts[reason] += 1
                plan = session_plan(day, protocol['episode']['window_features'])
                required = set(plan.required_times)
                valid, missing = set(), {}
                for row, failure in align_snapshots(snapshots, daily_config):
                    at = timestamp((row or failure)['decision_at'], 'decision_at')
                    if row:
                        valid.add(at)
                        trace.write(json.dumps(dict(session_id=str(day), decision_at=iso(at),
                            required=at in required, snapshots={t:dict(snapshot_id=row[f'{t}_snapshot_id'],
                                available_at=row[f'{t}_available_at']) for t in config.tickers}),
                            separators=(',', ':'))+'\n')
                    elif at in required:
                        missing[at] = failure['reason']
                        failure_writer.writerow(failure)
                warmup = {t for t in required if t <= plan.first_decision}
                startable = warmup <= valid
                later = sorted(t for t in missing if t > plan.first_decision)
                longest = run = 0
                for at in plan.required_times:
                    run = run+1 if at in valid else 0
                    longest = max(longest, run)
                record = dict(session_id=str(day), partition=partition, raw_files=len(grouped[day]),
                    accepted_captures=len(snapshots), expected_grid_points=len(required)+1,
                    valid_grid_points=len(valid), required_points=len(required),
                    valid_required_points=len(required & valid), missing_required_points=len(missing),
                    warmup_required_points=len(warmup), valid_warmup_points=len(warmup & valid),
                    startable=startable, evaluable=not missing,
                    first_required_failure=iso(min(missing)) if missing else None,
                    first_runtime_failure=iso(later[0]) if startable and later else None,
                    liquidation_observation_valid=plan.liquidation in valid,
                    first_decision_at=iso(plan.first_decision), liquidation_at=iso(plan.liquidation),
                    horizon=plan.horizon, longest_valid_required_run=longest)
                records.append(record); session_writer.writerow(record)
                print(json.dumps({k:record[k] for k in ('session_id', 'partition', 'startable', 'evaluable', 'valid_required_points')}), flush=True)
        for key, (first, last) in ranges.items():
            rows = [r for r in records if first.isoformat() <= r['session_id'] <= last.isoformat()]
            minimum = partitions[key].get('minimum_eligible_sessions')
            summary = dict(scheduled_sessions=len(rows), sessions_with_raw_files=sum(r['raw_files'] > 0 for r in rows),
                startable_sessions=sum(r['startable'] for r in rows), evaluable_sessions=sum(r['evaluable'] for r in rows),
                expected_grid_points=sum(r['expected_grid_points'] for r in rows),
                valid_grid_points=sum(r['valid_grid_points'] for r in rows),
                required_points=sum(r['required_points'] for r in rows),
                valid_required_points=sum(r['valid_required_points'] for r in rows),
                minimum_evaluable_sessions=minimum,
                minimum_met=None if minimum is None else sum(r['evaluable'] for r in rows) >= minimum)
            base['partition_summary'][key] = summary
            (output_dir/f'{key}.json').write_text(json.dumps(dict(partition=key, period=partitions[key],
                summary=summary, sessions=rows, training_ready=False,
                timing=adapter['timing'], protocol_sha256=protocol_sha), indent=2)+'\n')
        _verify(adapter_path, adapter_sha); _verify(protocol_path, protocol_sha)
        for name, sha in adapter['outputs'].items():
            _verify(adapter_dir/name, sha)
        for source in adapter['inputs']:
            _verify(Path(source['path']), source['sha256'])
        base.update(status='conditional_coverage_audited',
            coverage_feasible=all(base['partition_summary'][k]['minimum_met'] for k in ('train', 'validation', 'test')),
            excluded_counts=dict(excluded_counts), raw_inputs=adapter['inputs'],
            conversion_counts=adapter['counts'], conversion_rejection_reasons=adapter['rejection_reasons'])
        base['outputs'] = {p.name:digest(p) for p in sorted(output_dir.iterdir()) if p != status_path}
        save()
    except Exception as exc:
        base.update(status='failed', error=str(exc)); save()
        raise
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter-dir', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    report = build_manifest(args.adapter_dir, args.protocol, args.output_dir)
    print(json.dumps(report['partition_summary'], indent=2))


if __name__ == '__main__':
    main()
