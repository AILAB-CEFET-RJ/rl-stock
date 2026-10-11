"""Read-only clock diagnostics around US DST transitions; no market dataset.

Run from the repository root with pandas/numpy/pyarrow installed:
    python -m scripts.audit_clock_transitions
"""
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from rl_boleta.audit_parquet import inspect_frame, sha256


def run():
    output = Path('results/clock_transitions_2026-10-08')
    output.mkdir(exist_ok=False, parents=True)
    windows = [(date(2025, 2, 24), date(2025, 3, 21)),
               (date(2025, 10, 20), date(2025, 11, 14))]
    paths = []
    for path in Path('data').glob('data_scrapping_*.parquet'):
        day, month, year = map(int, path.stem.removeprefix('data_scrapping_').split('_'))
        day = date(year, month, day)
        if any(start <= day <= end for start, end in windows):
            paths.append((day, path))
    records, inputs = [], []
    for day, path in sorted(paths):
        before = sha256(path)
        info, details = inspect_frame(pd.read_parquet(path))
        assert sha256(path) == before, f'Input changed: {path}'
        inputs.append({'path': str(path), 'sha256': before, 'rows': details['rows']})
        # Retain independent complete original ten-row blocks. Clock analysis
        # does not require tight spread or impose an assumed clock offset.
        selected = info.loc[info.complete_candidate].copy()
        selected['file_date'] = day.isoformat()
        sp = datetime.combine(day, time(12), ZoneInfo('America/Sao_Paulo')).utcoffset()
        ny = datetime.combine(day, time(12), ZoneInfo('America/New_York')).utcoffset()
        selected['sp_minus_ny_seconds'] = (sp - ny).total_seconds()
        selected['utc_minus_ny_seconds'] = -ny.total_seconds()
        selected['period'] = ('march_before' if day < date(2025, 3, 9) else
                              'march_after' if day.month == 3 else
                              'november_before' if day < date(2025, 11, 2) else
                              'november_after')
        records.append(selected[['file_date', 'period', 'company', 'capture_end',
                                 'latest_trade_naive', 'wall_clock_gap_seconds',
                                 'latest_trade_in_regular_hours_proxy',
                                 'sp_minus_ny_seconds', 'utc_minus_ny_seconds']])
        print(f'{day}: {len(selected)} complete blocks', flush=True)
    data = pd.concat(records, ignore_index=True)
    data['sp_ny_age_seconds'] = data.wall_clock_gap_seconds - data.sp_minus_ny_seconds
    data.to_csv(output / 'clock_blocks.csv.gz', index=False)
    daily = []
    comparisons = []
    for subset, selected in [('all_complete', data), ('trade_clock_0930_1600', data.loc[data.latest_trade_in_regular_hours_proxy])]:
        for (period, day), group in selected.groupby(['period', 'file_date']):
            gaps = group.wall_clock_gap_seconds
            daily.append({'subset': subset, 'period': period, 'date': day,
                          'blocks': len(group), 'assets': group.company.nunique(),
                          'expected_sp_minus_ny_seconds': group.sp_minus_ny_seconds.iloc[0],
                          **{f'gap_q{q}': gaps.quantile(q / 100) for q in [1, 5, 50, 95]},
                          'sp_ny_age_median': group.sp_ny_age_seconds.median()})
        for period, group in selected.groupby('period'):
            hypotheses = {
                'capture_SP_source_NY': group.sp_minus_ny_seconds,
                'capture_SP_source_NY_fixed_3h_delay': group.sp_minus_ny_seconds + 10800,
                'same_clock': 0,
                'capture_UTC_source_NY': group.utc_minus_ny_seconds,
            }
            for hypothesis, offset in hypotheses.items():
                residual = group.wall_clock_gap_seconds - offset
                comparisons.append({'subset': subset, 'period': period,
                                    'hypothesis': hypothesis, 'blocks': len(group),
                                    'days': group.file_date.nunique(),
                                    'negative_fraction': (residual < 0).mean(),
                                    'within_60s_fraction': residual.between(0, 60).mean(),
                                    'within_300s_fraction': residual.between(0, 300).mean(),
                                    'residual_q01_seconds': residual.quantile(.01),
                                    'residual_median_seconds': residual.median()})
    pd.DataFrame(daily).to_csv(output / 'daily.csv', index=False)
    pd.DataFrame(comparisons).to_csv(output / 'hypotheses.csv', index=False)
    manifest = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                'windows': [[str(a), str(b)] for a, b in windows],
                'inputs': inputs, 'complete_blocks': len(data),
                'method': 'Original complete ten-row blocks; latest of ten valid trade times; same local calendar date. No latency correction.',
                'limitations': ['Trade timestamp is not book timestamp.',
                                'Residual includes trade age, source delay, clock error and scraping time.',
                                'Clock and latency hypotheses are not uniquely identifiable.',
                                'Regular-hours subset filters trade clock only; not an eligibility calendar.'],
                'code_sha256': {str(p): sha256(p) for p in [Path(__file__), Path('rl_boleta/audit_parquet.py')]},
                'outputs_sha256': {p.name: sha256(p) for p in sorted(output.iterdir())}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(pd.DataFrame(comparisons).to_string(index=False))


if __name__ == '__main__':
    run()
