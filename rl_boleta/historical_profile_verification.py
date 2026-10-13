"""Fixed training-only integration probes for new economic account profiles."""
import argparse
import json
from datetime import date
from decimal import Decimal,localcontext
from pathlib import Path

from .data_pipeline import digest
from .masked_preparation import verify


def probe_dates(records,dates,wind_points):
    """Select first, late and longest-gap train examples; never select by returns."""
    allowed=set(dates)
    rows=[r for r in records if r['session_id'] in allowed and r['partition']=='train' and r['data_eligible']]
    if {r['session_id'] for r in rows}!=allowed:raise ValueError('probe dates must exactly match frozen training population')
    selected=[min(allowed)]
    late=sorted(r['session_id'] for r in rows if r['remaining_transitions']<=wind_points)
    if late:selected.append(late[0])
    maximum=max(r['longest_missing_grid_run'] for r in rows)
    selected.append(min(r['session_id'] for r in rows if r['longest_missing_grid_run']==maximum))
    return tuple(dict.fromkeys(selected))


def run(normalizer_dir,output_dir):
    import numpy as np
    from .historical_env import HistoricalTrainingEnv
    from .validation_selection import result_metrics
    normalizer_dir,output_dir=map(Path,(normalizer_dir,output_dir))
    contexts={s:HistoricalTrainingEnv(normalizer_dir,s) for s in ('all_gaps','short_gaps')}
    modes={e.economic_options['account_regime'] for e in contexts.values()}
    if len(modes)!=1 or not modes<=set(('cash_settled','intraday_buying_power')):
        raise ValueError('one explicit new account regime per bundle required')
    if any(e.economic_options['wind_down_points']!=54 or e.economic_options['reward_objective']!='terminal_cash_utility' for e in contexts.values()):
        raise ValueError('reviewed 54-point phase and cash utility required')
    output_dir.mkdir(parents=True,exist_ok=False);rows=[];anchors={}
    for scenario,env in contexts.items():
        records=json.loads((env.eligibility_dir/'sessions.json').read_text())
        days=probe_dates(records,tuple(str(d) for d in env.dates),54)
        anchors.update(env.input_hashes)
        for day in days:
            # Explicit integration probe, not an override of uniform training sampling.
            env.session=env.session_for_day(date.fromisoformat(day))
            env.episode=env._controller().start(env.session.day,env.session.frames)
            x=env._encoded();count=0;ignored=0;powers=[]
            if x.shape!=(15505,) or not np.all(np.isfinite(x)):raise RuntimeError('invalid new context input')
            while not env.episode.kernel.done:
                if count==0:action=(.2,)*len(env.tickers)
                elif count==1:action=(-1,)*len(env.tickers)
                elif count==2:action=(1,)*len(env.tickers)
                else:action=(0,)*len(env.tickers)
                x,reward,done,truncated,info=env.step(action)
                if truncated or not np.isfinite(reward) or not np.all(np.isfinite(x)):
                    raise RuntimeError('invalid probe transition')
                ignored+=info['action_ignored_for_liquidation'];count+=1
                if count<=3:powers.append(dict(step=count,buying_power_usd=info['buying_power_usd'],pending_sale_proceeds_usd=info['pending_sale_proceeds_usd']))
            result=env.episode.result();kernel=env.episode.kernel
            with localcontext() as ctx:
                ctx.prec=50
                utility=sum((t.reward for t in result.transitions),Decimal(0))
                expected=kernel.config.reward_scale*(result.portfolio.cash-kernel.config.initial_capital)/kernel.config.initial_capital
                if abs(utility-expected)>Decimal('1e-35'):raise RuntimeError('terminal cash utility mismatch')
                if abs(kernel.funding_balance+kernel.pending_sale_proceeds-result.portfolio.cash)>Decimal('1e-35'):
                    raise RuntimeError('account journal mismatch')
            if not done or x[-1]!=0:raise RuntimeError('nonzero horizon at economic terminal')
            row=dict(scenario=scenario,**result_metrics(result),entry_at=result.plan.first_decision.isoformat(),
                steps=count,automatic_transitions=ignored,learning_return=str(utility),
                final_buying_power_usd=str(kernel.buying_power),funding_balance_usd=str(kernel.funding_balance),
                pending_sale_proceeds_usd=str(kernel.pending_sale_proceeds),first_three_account_states=powers)
            rows.append(row);env.verify_inputs()
            print(json.dumps(dict(scenario=scenario,day=day,status=result.status,flat=row['flat'])),flush=True)
    for p,h in anchors.items():verify(p,h)
    sources=(Path(__file__),Path(__file__).with_name('historical_env.py'),Path(__file__).with_name('cached_observations.py'),
        Path(__file__).with_name('missing_data_replay.py'),Path(__file__).with_name('economic_kernel.py'),Path(__file__).with_name('validation_selection.py'))
    report=dict(status='historical_training_profile_probes_completed',account_regime=next(iter(modes)),
        partition='train',models_trained=False,validation_prices_accessed=False,test_prices_accessed=False,
        full_budget_selection_authorized=False,probe_rule='first train date; first late causal entry; first maximum observation-gap date, deduplicated',
        policy='scripted buy .2, sell -1, buy 1 then hold; forced phase and stops retain precedence',
        observation_dimension=15505,source_sha256={str(p):digest(p) for p in sources},
        inputs_sha256=anchors,sessions=rows,liquidation_failures=sum(r['status']=='liquidation_failure' for r in rows),
        limitations='Selected train integration probes, not all training dates, trained policies or estimates of liquidation reliability.')
    (output_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--normalizer-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();r=run(a.normalizer_dir,a.output_dir)
    print(json.dumps(dict(status=r['status'],probes=len(r['sessions']),liquidation_failures=r['liquidation_failures']),indent=2))


if __name__=='__main__':main()
