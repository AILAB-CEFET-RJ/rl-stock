"""Attribute coverage failures to capture availability and quality, read-only.

Uses the original Parquet and the verified adapter's rejection decisions.
Counterfactual coverage is diagnostic only; never produces training data.
"""
import argparse
import bisect
import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import market_calendar
from .data_pipeline import digest, iso
from .session_replay import session_plan


def latest_age(times, decision):
    index = bisect.bisect_right(times, decision) - 1
    return None if index < 0 else decision - times[index]


def gap_state(raw_times, accepted_times, decision, max_age=60, has_file=True):
    """Times are sorted epoch seconds from this session only; future is unused."""
    accepted_age = latest_age(accepted_times, decision)
    raw_age = latest_age(raw_times, decision)
    if accepted_age is not None and accepted_age <= max_age:
        state = 'valid'
    elif not has_file:
        state = 'no_raw_file'
    elif raw_age is None:
        state = 'no_capture_since_open'
    elif raw_age > max_age:
        state = 'no_recent_capture'
    else:
        state = 'recent_capture_rejected'
    return state, raw_age, accepted_age


def write_rows(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(adapter_dir, episodes_dir, protocol_path, output_dir):
    import pandas as pd
    from .audit_parquet import inspect_frame
    from .parquet_adapter import COMPANY_TICKERS

    adapter_dir, episodes_dir, protocol_path, output_dir = map(
        Path, (adapter_dir, episodes_dir, protocol_path, output_dir))
    adapter_path, episode_path = adapter_dir/'manifest.json', episodes_dir/'manifest.json'
    adapter, episodes, protocol = [json.loads(p.read_text()) for p in
                                   (adapter_path, episode_path, protocol_path)]
    def verify(path, expected):
        if digest(path) != expected:
            raise ValueError(f'hash mismatch: {path}')
    assert adapter['status'] == 'provisional_converted'
    assert episodes['status'] == 'conditional_coverage_audited'
    verify(adapter_path, episodes['adapter_manifest']['sha256'])
    verify(protocol_path, episodes['protocol_sha256'])
    for name, sha in adapter['outputs'].items():
        verify(adapter_dir/name, sha)
    verify(episodes_dir/'required_failures.csv', episodes['outputs']['required_failures.csv'])
    rejection_lookup = {}
    with (adapter_dir/'rejections.csv').open() as handle:
        for row in csv.DictReader(handle):
            key = row['source_sha256'], int(row['source_row_start'])
            assert key not in rejection_lookup
            rejection_lookup[key] = row['reason']
    with (episodes_dir/'required_failures.csv').open() as handle:
        reference_failures = {(r['session_id'], r['decision_at']) for r in csv.DictReader(handle)}
    grouped = defaultdict(list)
    for source in adapter['inputs']:
        path = Path(source['path'])
        day, month, year = map(int, path.stem.removeprefix('data_scrapping_').split('_'))
        grouped[date(year, month, day)].append(source)
    first = date.fromisoformat(protocol['partitions']['train']['first'])
    last = date.fromisoformat(protocol['partitions']['test']['last'])
    tickers = protocol['tickers']
    max_age = protocol['data']['maximum_receipt_age_seconds']
    assert max_age == 60
    assert adapter['timing']['collection_timezone'] == 'America/Sao_Paulo'
    output_dir.mkdir(exist_ok=False, parents=True)
    totals, joint_totals, reason_points, ignored = Counter(), Counter(), Counter(), Counter()
    asset_totals = {t: Counter() for t in tickers}
    daily_rows, asset_rows, scenarios = [], [], []
    reproduced_failures = set()
    scenario_totals = Counter()
    age_limits = (60, 120, 180, 300)
    with gzip.open(output_dir/'asset_grid.csv.gz', 'wt', newline='') as asset_handle, \
         (output_dir/'joint_grid.csv').open('w', newline='') as joint_handle:
        asset_writer = csv.DictWriter(asset_handle, fieldnames=['session_id', 'decision_at', 'ticker',
            'warmup', 'state', 'raw_age_seconds', 'accepted_age_seconds', 'recent_rejection_reasons'])
        joint_writer = csv.DictWriter(joint_handle, fieldnames=['session_id', 'decision_at', 'warmup',
            'valid_assets', 'recent_raw_assets', 'quality_failed_assets', 'unavailable_assets', 'joint_cause'])
        asset_writer.writeheader(); joint_writer.writeheader()
        for day in market_calendar.dates(first, last):
            if market_calendar.window(day) is None:
                continue
            plan = session_plan(day, protocol['episode']['window_features'])
            opening, closing = plan.opening.timestamp(), plan.closing.timestamp()
            raw = {t: [] for t in tickers}
            accepted = {t: [] for t in tickers}
            rejected = {t: [] for t in tickers}
            raw_counts, rejected_counts = Counter(), Counter()
            for source in grouped[day]:
                path = Path(source['path']); verify(path, source['sha256'])
                frame = pd.read_parquet(path)
                info, _ = inspect_frame(frame)
                assert len(info) == source['counts']['candidates']
                classified = Counter()
                for block in info.to_dict('records'):
                    ticker = COMPANY_TICKERS.get(block['company'])
                    if not block['bad_company_block'] and ticker not in tickers and ticker is not None:
                        classified['outside_universe'] += 1
                        continue
                    reason = rejection_lookup.get((source['sha256'], int(block['source_row_start'])))
                    classified['rejected' if reason else 'accepted'] += 1
                    if block['bad_company_block'] or block['bad_capture_time'] or ticker not in tickers:
                        ignored['blocks_without_usable_asset_or_capture_time'] += 1
                        assert reason is not None
                        continue
                    at = pd.Timestamp(block['capture_end']).tz_localize(
                        adapter['timing']['collection_timezone']).timestamp()
                    if not opening <= at < closing:
                        continue
                    raw[ticker].append(at); raw_counts[ticker] += 1
                    if reason:
                        rejected[ticker].append((at, reason)); rejected_counts[ticker] += 1
                    else:
                        accepted[ticker].append(at)
                for key in ('accepted', 'rejected', 'outside_universe'):
                    assert classified[key] == source['counts'][key], (path, key, classified)
                verify(path, source['sha256'])
            for values in (raw, accepted):
                for times in values.values():
                    times.sort()
            for values in rejected.values():
                values.sort()
            rejection_times = {t: [x[0] for x in rejected[t]] for t in tickers}
            daily_asset = {t: Counter() for t in tickers}
            day_joint, day_scenarios = Counter(), Counter()
            leave_one_out = Counter()
            phase = {'warmup': Counter(), 'after_warmup': Counter()}
            for decision in plan.required_times:
                epoch = decision.timestamp(); warmup = decision <= plan.first_decision
                states, raw_ages, accepted_ages = {}, {}, {}
                for ticker in tickers:
                    state, raw_age, accepted_age = gap_state(raw[ticker], accepted[ticker], epoch,
                                                           max_age, bool(grouped[day]))
                    states[ticker] = state; raw_ages[ticker] = raw_age; accepted_ages[ticker] = accepted_age
                    totals[state] += 1; daily_asset[ticker][state] += 1; asset_totals[ticker][state] += 1
                    reasons = set()
                    if state == 'recent_capture_rejected':
                        left = bisect.bisect_left(rejection_times[ticker], epoch-max_age)
                        right = bisect.bisect_right(rejection_times[ticker], epoch)
                        reasons = {reason for _, reason in rejected[ticker][left:right]}
                        assert reasons, (day, ticker, decision)
                        for reason in reasons:
                            reason_points[reason] += 1
                    asset_writer.writerow(dict(session_id=str(day), decision_at=iso(decision),
                        ticker=ticker, warmup=warmup, state=state, raw_age_seconds=raw_age,
                        accepted_age_seconds=accepted_age, recent_rejection_reasons=' | '.join(sorted(reasons))))
                counts = Counter(states.values())
                missing = [t for t in tickers if states[t] != 'valid']
                unavailable = sum(counts[s] for s in ('no_raw_file', 'no_capture_since_open', 'no_recent_capture'))
                quality = counts['recent_capture_rejected']
                cause = ('valid' if not missing else 'no_raw_file' if not grouped[day] else
                         'mixed_capture_and_quality' if unavailable and quality else
                         'capture_unavailable' if unavailable else 'quality_only')
                if missing:
                    reproduced_failures.add((str(day), iso(decision)))
                day_joint[cause] += 1; joint_totals[cause] += 1
                phase['warmup' if warmup else 'after_warmup'][cause] += 1
                joint_writer.writerow(dict(session_id=str(day), decision_at=iso(decision), warmup=warmup,
                    valid_assets=counts['valid'], recent_raw_assets=len(tickers)-unavailable,
                    quality_failed_assets=quality, unavailable_assets=unavailable, joint_cause=cause))
                for limit in age_limits:
                    for name, ages in [('accepted', accepted_ages), ('raw_quality_ignored', raw_ages)]:
                        if all(age is not None and age <= limit for age in ages.values()):
                            day_scenarios[f'{name}_age_{limit}'] += 1
                for ticker in tickers:
                    if not missing or missing == [ticker]:
                        leave_one_out[ticker] += 1
            required = len(plan.required_times)
            for ticker in tickers:
                asset_rows.append(dict(session_id=str(day), ticker=ticker,
                    raw_captures=raw_counts[ticker], rejected_captures=rejected_counts[ticker],
                    required_points=required, valid_points=daily_asset[ticker]['valid'],
                    individually_complete=daily_asset[ticker]['valid']==required,
                    first_raw_at=iso(datetime.fromtimestamp(raw[ticker][0], timezone.utc)) if raw[ticker] else '',
                    first_accepted_at=iso(datetime.fromtimestamp(accepted[ticker][0], timezone.utc)) if accepted[ticker] else '',
                    raw_gap_median_seconds=float(pd.Series(raw[ticker]).diff().median()) if len(raw[ticker])>1 else '',
                    raw_gap_p95_seconds=float(pd.Series(raw[ticker]).diff().quantile(.95)) if len(raw[ticker])>1 else '',
                    raw_gaps_over_60s=sum(b-a>60 for a,b in zip(raw[ticker],raw[ticker][1:])),
                    joint_points_if_only_this_asset_removed=leave_one_out[ticker],
                    joint_complete_if_only_this_asset_removed=leave_one_out[ticker]==required,
                    **{s:daily_asset[ticker][s] for s in ('no_raw_file','no_capture_since_open','no_recent_capture','recent_capture_rejected')}))
            for limit in age_limits:
                for name in ('accepted', 'raw_quality_ignored'):
                    key = f'{name}_age_{limit}'
                    complete = day_scenarios[key] == required
                    scenario_totals[key+'_valid_points'] += day_scenarios[key]
                    scenario_totals[key+'_complete_sessions'] += complete
                    scenarios.append(dict(session_id=str(day), scenario=key, required_points=required,
                                          valid_points=day_scenarios[key], complete_session=complete))
            daily_rows.append(dict(session_id=str(day), raw_files=len(grouped[day]), required_points=required,
                **{s:day_joint[s] for s in ('valid','no_raw_file','capture_unavailable','quality_only','mixed_capture_and_quality')},
                warmup_valid=phase['warmup']['valid'],
                warmup_capture_unavailable=phase['warmup']['capture_unavailable'],
                warmup_quality_only=phase['warmup']['quality_only'],
                warmup_mixed=phase['warmup']['mixed_capture_and_quality']))
            print(json.dumps(daily_rows[-1]), flush=True)
    assert reproduced_failures == reference_failures, 'coverage differs from verified episode audit'
    write_rows(output_dir/'sessions.csv', daily_rows)
    write_rows(output_dir/'assets_by_session.csv', asset_rows)
    write_rows(output_dir/'counterfactual_coverage.csv', scenarios)
    summary = dict(status='diagnostic_only', training_ready=False,
        purpose='gap causes, no threshold changes, financial results or training dataset',
        session_count=len(daily_rows), joint_points=sum(joint_totals.values()),
        asset_points=sum(totals.values()), asset_states=dict(totals), joint_causes=dict(joint_totals),
        quality_reason_asset_points=dict(reason_points), ignored=dict(ignored),
        by_asset={t: dict(c) for t,c in asset_totals.items()},
        counterfactuals=dict(scenario_totals), reference_failures_exactly_reproduced=len(reference_failures),
        limitations=['Raw availability requires a usable asset label and capture time.',
                     'Recent raw captures can be invalid; counterfactuals are not usable books.',
                     'Quality rejection causes can overlap at an asset/grid point.',
                     '60 seconds is inclusive; no pre-open or future capture is used.',
                     'Capture availability does not measure book-market latency.'],
        source_manifests={str(p):digest(p) for p in (adapter_path, episode_path, protocol_path)},
        raw_inputs=adapter['inputs'], timing=adapter['timing'],
        code_sha256={str(p):digest(p) for p in (Path(__file__), Path(inspect_frame.__code__.co_filename))},
        outputs_sha256={p.name:digest(p) for p in sorted(output_dir.iterdir())})
    (output_dir/'manifest.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter-dir', type=Path, required=True)
    parser.add_argument('--episodes-dir', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter_dir, args.episodes_dir, args.protocol, args.output_dir)
    print(json.dumps({k:report[k] for k in ('joint_causes','asset_states','counterfactuals')}, indent=2))


if __name__ == '__main__':
    main()
