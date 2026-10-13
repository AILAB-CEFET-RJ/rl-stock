"""Matched v3 policies; synthetic-only diagnostic runner, no historical scores."""
import argparse
import json
import random
import platform
from datetime import timedelta
from pathlib import Path

from . import market_calendar
from .data_pipeline import digest
from .missing_data_replay import MaskedDailyReplay

BASELINES = ('cash','equal_allocation_single_entry','ten_interval_momentum','ten_interval_reversal','uniform_random_actions')


class BaselinePolicy:
    """One policy per episode; RNG may be shared across a seeded date trajectory."""
    def __init__(self, name, tickers, *, rng=None):
        if name not in BASELINES:raise ValueError('unknown matched baseline')
        self.name=name;self.tickers=tuple(tickers);self.first=True;self.rng=rng
        if not self.tickers or len(set(self.tickers))!=len(self.tickers):raise ValueError('unique assets required')
        if name=='uniform_random_actions' and not isinstance(rng,random.Random):
            raise ValueError('explicit seeded random trajectory required')

    def __call__(self, obs):
        first=self.first;self.first=False;n=len(self.tickers)
        if self.name=='cash':return (0,)*n
        if self.name=='equal_allocation_single_entry':return (1 if first else 0,)*n
        if self.name=='uniform_random_actions':return tuple(self.rng.uniform(-1,1) for _ in self.tickers)
        # Exact grid endpoints only: stale carried marks are never momentum prices.
        endpoints={f.at:f for f in obs.market_history}
        previous=endpoints.get(obs.at-timedelta(minutes=10));current=endpoints.get(obs.at)
        old={} if previous is None else {b.ticker:b for b in previous.books}
        now={} if current is None else {b.ticker:b for b in current.books}
        actions=[]
        for t in self.tickers:
            if t not in old or t not in now:signal=0
            else:
                delta=now[t].midpoint-old[t].midpoint
                signal=(delta>0)-(delta<0)
            actions.append(-signal if self.name=='ten_interval_reversal' else signal)
        return tuple(actions)


def run_synthetic_suite(sessions, tickers):
    """Retain every scheduled date and strategy; never discard residual failures."""
    sessions=tuple(sessions);tickers=tuple(tickers)
    if not sessions or any(s.synthetic is not True for s in sessions):
        raise ValueError('historical baseline scoring blocked until final v3 eligibility')
    mapping={s.day:s for s in sessions}
    if len(mapping)!=len(sessions):raise ValueError('duplicate date')
    runs=[]
    for name in BASELINES:
        for seed in range(100,110) if name=='uniform_random_actions' else (None,):
            rng=None if seed is None else random.Random(seed)
            controller=MaskedDailyReplay(tickers);records=[]
            for day in market_calendar.dates(min(mapping),max(mapping)):
                if market_calendar.window(day) is None:continue
                s=mapping.get(day);policy=BaselinePolicy(name,tickers,rng=rng)
                r=controller.run(day,s.frames if s else (),policy)
                records.append(dict(session_id=str(day),status=r.status,startable=r.startable,
                    coverage_candidate=r.coverage_candidate,
                    flat=None if not r.transitions else r.transitions[-1].flat,
                    steps=len(r.transitions),marked_return=None if r.marked_return is None else str(r.marked_return),
                    realized_return=None if r.realized_return is None else str(r.realized_return),
                    residual_holdings=list(r.portfolio.holdings)))
            runs.append(dict(baseline=name,seed=seed,sessions=records))
    denominators=[[(r['session_id'],r['coverage_candidate']) for r in run['sessions']] for run in runs]
    if any(d!=denominators[0] for d in denominators):raise RuntimeError('baseline data denominators differ')
    return runs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthetic-smoke',action='store_true',required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    from .masked_training import synthetic_sessions,TICKERS
    runs=run_synthetic_suite(synthetic_sessions(),TICKERS)
    a.output_dir.mkdir(parents=True,exist_ok=False)
    path=a.output_dir/'runs.json';path.write_text(json.dumps(runs,indent=2)+'\n')
    files=[Path(__file__),Path(__file__).with_name('missing_data_replay.py'),Path(__file__).with_name('masked_training.py'),Path(__file__).with_name('economic_kernel.py'),Path(__file__).with_name('session_replay.py'),Path(__file__).with_name('market_calendar.py')]
    report=dict(status='synthetic_baselines_passed',historical_data_used=False,training_ready=False,
        runs=len(runs),assets=len(TICKERS),common_data_denominator=True,python_version=platform.python_version(),
        random_seed_scope='one stream per seed across chronologically ordered dates; draw only at discretionary decisions',
        code_sha256={str(p):digest(p) for p in files},outputs_sha256={path.name:digest(path)},
        limitations=['Synthetic integration only; no financial comparison on historical or protected test dates.'])
    (a.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
