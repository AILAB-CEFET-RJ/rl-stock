"""Training-only, unused displayed bid-capacity diagnostics; no policy returns."""
import argparse
import json
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
from pathlib import Path

from .data_pipeline import digest, iso
from .economic_kernel import number
from .masked_eligibility import read_eligible_session
from .masked_preparation import verify
from .missing_data_replay import MaskedDailyReplay, MaskedSessionEpisode

WINDOWS = (1, 2, 5, 10, 15, 30, 60, 120)


def bid_capacity(book, participation):
    participation = number(participation)
    if not 0 < participation <= 1:
        raise ValueError('participation must be in (0,1]')
    with localcontext() as ctx:
        ctx.prec = 50
        return sum(int((participation * q.size).to_integral_value(rounding=ROUND_FLOOR)) for q in book.bids)


def audit_session(session, tickers, *, initial_capital=100000, participation='.1', windows=WINDOWS):
    """Retrospective capacity, not a policy input or a promise to execute shares.

    Reference inventories are hypothetical quantities valued at causal entry.
    Concentrated references are separate per-asset stress cases, not one portfolio.
    No capacity is spent before each window: this is an optimistic capacity bound.
    """
    windows = tuple(windows)
    if not windows or any(type(w) is not int or w < 1 for w in windows) or len(set(windows)) != len(windows):
        raise ValueError('distinct positive integer window lengths required')
    capital = number(initial_capital)
    if capital <= 0:
        raise ValueError('positive capital required')
    episode = MaskedDailyReplay(tickers, initial_capital=capital, participation=participation).start(session.day, session.frames)
    if not isinstance(episode, MaskedSessionEpisode) or episode._missing_exit:
        raise ValueError('causal entry and complete covered exit required')
    entry = episode.plan.first_decision
    initial = episode._indexed[entry]
    tail = [f for at, f in sorted(episode._indexed.items()) if at > entry]
    assets = []
    with localcontext() as ctx:
        ctx.prec = 50
        for ticker in tickers:
            mid = initial.book(ticker).midpoint
            targets = {
                'equal_capital_reference': int((capital / len(tickers) / mid).to_integral_value(rounding=ROUND_FLOOR)),
                'concentrated_capital_stress': int((capital / mid).to_integral_value(rounding=ROUND_FLOOR)),
            }
            seen = set(); capacity = 0; valid = 0; positive = 0
            suffixes = {}; minimum = {name: (0 if qty == 0 else None) for name, qty in targets.items()}
            for length, frame in enumerate(reversed(tail), 1):
                book = next((b for b in frame.books if b.ticker == ticker), None)
                if book is not None:
                    valid += 1
                    if book.snapshot_id not in seen:
                        seen.add(book.snapshot_id)
                        fresh_capacity = bid_capacity(book, participation)
                        positive += fresh_capacity > 0
                        capacity += fresh_capacity
                for name, qty in targets.items():
                    if minimum[name] is None and capacity >= qty:
                        minimum[name] = length
                if length in windows:
                    suffixes[str(length)] = dict(capacity_shares=capacity, valid_grid_points=valid,
                        unique_captures=len(seen), positive_capacity_captures=positive,
                        reference_covered={name: capacity >= qty for name, qty in targets.items()})
            # Windows longer than the actual post-entry horizon are not silently shortened.
            for length in windows:
                if str(length) not in suffixes:
                    suffixes[str(length)] = None
            assets.append(dict(ticker=ticker,entry_midpoint=str(mid),reference_inventory_shares=targets,
                minimum_trailing_grid_points=minimum,entire_post_entry_capacity_shares=capacity,
                windows=suffixes))
    return dict(session_id=str(session.day),entry_at=iso(entry),exit_at=iso(episode.plan.liquidation),
        remaining_transitions=episode.plan.horizon,assets=assets)


def summarize(sessions, windows=WINDOWS):
    rows = [a for s in sessions for a in s['assets']]
    result = dict(market_sessions=len(sessions),asset_session_observations=len(rows),windows={})
    for window in windows:
        present = [a['windows'][str(window)] for a in rows if a['windows'][str(window)] is not None]
        result['windows'][str(window)] = dict(evaluable_asset_sessions=len(present),
            insufficient_horizon_asset_sessions=len(rows)-len(present),
            **{name+'_covered':sum(r['reference_covered'][name] for r in present)
               for name in ('equal_capital_reference','concentrated_capital_stress')})
    for name in ('equal_capital_reference','concentrated_capital_stress'):
        values = [a['minimum_trailing_grid_points'][name] for a in rows]
        finite = [v for v in values if v is not None]
        result[name] = dict(maximum_minimum_trailing_grid_points=max(finite,default=None),
            insufficient_entire_horizon=sum(v is None for v in values),
            minimum_window_histogram=dict(sorted(Counter(finite).items())))
    return result


def run(design_dir, output_dir):
    design_dir, output_dir = map(Path, (design_dir, output_dir))
    mp = design_dir/'manifest.json'; manifest = json.loads(mp.read_text())
    if manifest['status'] != 'frozen_two_scenario_date_design':
        raise ValueError('frozen two-scenario design required')
    anchors = {str(mp.resolve()): digest(mp)}; scenarios = {}; protocols = {}
    for scenario in ('all_gaps', 'short_gaps'):
        source = manifest['scenario_manifests'][scenario]
        verify(source['path'], source['sha256'])
        directory = Path(source['path']).parent
        child = json.loads(Path(source['path']).read_text())
        anchors[source['path']] = source['sha256']
        for name, expected in child['outputs_sha256'].items():
            path = directory/name; verify(path, expected); anchors[str(path.resolve())] = expected
        protocol = json.loads((directory/'protocol.json').read_text()); protocols[scenario] = protocol
        records = json.loads((directory/'sessions.json').read_text())
        dates = tuple(r['session_id'] for r in records if r['partition']=='train' and r['data_eligible'])
        if not dates or any(not '2025-03-03' <= day <= '2025-05-30' for day in dates):
            raise ValueError('nonempty March-May training dates only')
        scenarios[scenario] = dict(directory=directory,dates=dates)
        prep_path = Path(child['prepared_manifest']['path']); verify(prep_path, child['prepared_manifest']['sha256'])
        anchors[str(prep_path)] = child['prepared_manifest']['sha256']
        for r in json.loads(prep_path.read_text())['sessions']:
            if r['session_id'] in dates:
                anchors.update(r['canonical_inputs'])
                grid=prep_path.parent/r['grid_file']
                anchors[str(grid.resolve())]=digest(grid)
    reference = protocols['all_gaps']
    if any(p['tickers']!=reference['tickers'] or p['environment']!=reference['environment'] for p in protocols.values()):
        raise ValueError('shared economics and universe required')
    if not set(scenarios['short_gaps']['dates']) <= set(scenarios['all_gaps']['dates']):
        raise ValueError('secondary training set must be a subset')
    for path, expected in anchors.items():verify(path,expected)
    output_dir.mkdir(parents=True, exist_ok=False); sessions = []
    for day in scenarios['all_gaps']['dates']:
        s=read_eligible_session(scenarios['all_gaps']['directory'],date.fromisoformat(day),partition='train')
        e=reference['environment']
        row=audit_session(s,reference['tickers'],initial_capital=e['initial_capital_usd'],participation=e['participation_cap'])
        sessions.append(row)
        print(json.dumps(dict(session_id=day,status='capacity_audited')),flush=True)
    report=dict(status='train_only_unused_bid_capacity_audit',training_ready=False,
        strategies_run=False,policy_returns_computed=False,test_prices_accessed=False,validation_prices_accessed=False,
        windows_grid_points=list(WINDOWS),initial_capital_usd=reference['environment']['initial_capital_usd'],
        participation_cap=reference['environment']['participation_cap'],
        scenarios={name:summarize([r for r in sessions if r['session_id'] in spec['dates']]) for name,spec in scenarios.items()},
        sessions=sessions,limitations=[
            'Unused displayed bid capacity is an optimistic replay bound, not executable liquidity certification.',
            'Each capture counts once per window; prior policy sales could have consumed capacity.',
            'Entry-valued inventories are hypothetical; no portfolio was bought and no return calculated.',
            'Concentrated references are independent single-asset stress cases, not a simultaneous 18-asset portfolio.',
            'Trailing minima use future observed books retrospectively; never provide them to a policy.',
            'No data gap is identified as a market halt; no continuous market or closing auction reconstructed.'])
    path=output_dir/'diagnostics.json';path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for path_in,expected in anchors.items():verify(path_in,expected)
    code_files=(Path(__file__),Path(__file__).with_name('economic_kernel.py'),Path(__file__).with_name('missing_data_replay.py'),Path(__file__).with_name('masked_eligibility.py'),Path(__file__).with_name('masked_preparation.py'))
    out_manifest=dict(status=report['status'],created_at=iso(datetime.now(timezone.utc)),
        inputs_sha256=anchors,code_sha256={str(p):digest(p) for p in code_files},
        outputs_sha256={'diagnostics.json':digest(path)},scope='March-May training only; no trading or learning')
    (output_dir/'manifest.json').write_text(json.dumps(out_manifest,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();report=run(args.design_dir,args.output_dir)
    print(json.dumps(report['scenarios'],indent=2))


if __name__=='__main__':main()
