"""Core v3 validation selection. Diagnostic rankings never authorize final refit."""
import argparse
import gc
import itertools
import json
import random
from datetime import date
from decimal import Decimal,localcontext
from pathlib import Path

from .algorithm_builders import ALGORITHMS
from .data_pipeline import digest
from .historical_normalization import load_train_normalizer
from .masked_baselines import BASELINES,BaselinePolicy
from .masked_eligibility import read_eligible_session
from .masked_observations import MaskedEncoder
from .masked_preparation import verify
from .missing_data_replay import MaskedDailyReplay


def result_metrics(result):
    if result.marked_return is None or not result.transitions:
        raise ValueError('missing completed common validation outcome; never zero-fill or drop date')
    with localcontext() as ctx:
        ctx.prec=50;capital=result.transitions[0].before_wealth;peak=capital;drawdown=Decimal(0)
        fees=turnover=Decimal(0);max_age=0
        for t in result.transitions:
            peak=max(peak,t.after_wealth);drawdown=max(drawdown,(peak-t.after_wealth)/peak)
            for event in t.executions:
                fees+=event.fees
                turnover+=sum((f.quantity*f.price for f in event.fills),Decimal(0))
            max_age=max(max_age,max(((t.at-stamp).total_seconds() for h,stamp in
                zip(t.residual_holdings,t.mark_capture_times) if h),default=0))
        final=result.transitions[-1]
        return dict(session_id=str(result.plan.day),status=result.status,marked_return=str(result.marked_return),
            realized_return=None if result.realized_return is None else str(result.realized_return),
            flat=final.flat,maximum_marked_drawdown=str(drawdown),fees=str(fees),turnover_per_capital=str(turnover/capital),
            residual_holdings=list(result.portfolio.holdings),
            residual_marked_exposure_per_capital=str((final.after_wealth-result.portfolio.cash)/capital),
            maximum_held_receipt_age_seconds=max_age,
            capital_stop=any(t.reason.startswith('capital_stop') for t in result.transitions))


def aggregate_candidate(runs,expected_seeds,expected_dates):
    """Full seed/date denominator, retaining economic failures; exact Decimal ties."""
    if len(runs)!=len(expected_seeds) or {r['seed'] for r in runs}!=set(expected_seeds):
        return dict(eligible=False,reason='incomplete_or_duplicate_seed_set')
    rows=[]
    for run in runs:
        outcomes=run.get('validation',[])
        if (run.get('status')!='completed' or len(outcomes)!=len(expected_dates)
                or [r['session_id'] for r in outcomes]!=list(expected_dates)
                or any(r.get('marked_return') is None for r in outcomes)):
            return dict(eligible=False,reason='failed_fit_or_incomplete_common_dates')
        if any(not Decimal(r[k]).is_finite() for r in outcomes for k in ('marked_return','maximum_marked_drawdown','fees','turnover_per_capital','residual_marked_exposure_per_capital')):
            return dict(eligible=False,reason='nonfinite_validation_metric')
        rows.extend(outcomes)
    with localcontext() as ctx:
        ctx.prec=50
        def mean(key):return str(sum((Decimal(r[key]) for r in rows),Decimal(0))/len(rows))
        admission=day_trading_admissibility(rows)
        return dict(eligible=True,day_trading_admissibility=admission,
            mean_marked_return=mean('marked_return'),mean_maximum_marked_drawdown=mean('maximum_marked_drawdown'),
            mean_fees=mean('fees'),mean_turnover_per_capital=mean('turnover_per_capital'),
            mean_residual_marked_exposure_per_capital=mean('residual_marked_exposure_per_capital'),
            flat_completion_rate=str(Decimal(sum(r['flat'] for r in rows))/len(rows)),
            liquidation_failure_count=sum(r['status']=='liquidation_failure' for r in rows),
            capital_stop_count=sum(r['capital_stop'] for r in rows),
            seed_session_outcomes=len(rows),market_sessions=len(expected_dates))


def day_trading_admissibility(rows):
    """Assess observed flat execution, never discard failures or certify future exits."""
    failures=[]
    for index,row in enumerate(rows):
        holdings=row.get('residual_holdings')
        realized=row.get('realized_return')
        cash_outcome=(realized is not None and Decimal(realized).is_finite()
            and Decimal(realized)==Decimal(row['marked_return']))
        if (row.get('flat') is not True or holdings is None or not holdings
                or any(type(h) is not int or h!=0 for h in holdings)
                or row.get('status') not in ('scheduled_end','capital_stop') or not cash_outcome):
            failures.append(dict(outcome_index=index,session_id=row['session_id'],status=row.get('status')))
    return dict(admissible=bool(rows) and not failures,
        rule='flat_all_common_validation_seed_sessions',outcomes=len(rows),
        noncompliant_outcomes=len(failures),failures=failures,
        future_liquidation_guaranteed=False)


def rank_candidates(candidates,*,require_day_trading=False):
    return sorted((c for c in candidates if c['aggregate']['eligible'] and
        (not require_day_trading or c['aggregate'].get('day_trading_admissibility',{}).get('admissible') is True)),key=lambda c:(
        -Decimal(c['aggregate']['mean_marked_return']),Decimal(c['aggregate']['mean_maximum_marked_drawdown']),
        c['width'],Decimal(str(c['learning_rate']))))


def paired_differences(runs,baseline,dates):
    if [r['session_id'] for r in baseline]!=list(dates):raise ValueError('baseline must use exact common validation dates')
    rows=[]
    for run in runs:
        if [r['session_id'] for r in run['validation']]!=list(dates):raise ValueError('model dates differ from baseline')
        for model,control in zip(run['validation'],baseline):
            with localcontext() as ctx:
                ctx.prec=50;difference=Decimal(model['marked_return'])-Decimal(control['marked_return'])
            rows.append(dict(seed=run['seed'],session_id=model['session_id'],marked_return_difference=str(difference),
                model_flat=model['flat'],baseline_flat=control['flat']))
    with localcontext() as ctx:
        ctx.prec=50;mean=sum((Decimal(r['marked_return_difference']) for r in rows),Decimal(0))/len(rows)
    return dict(mean_marked_difference=str(mean),paired_seed_session_outcomes=rows,market_sessions=len(dates))


class ValidationContext:
    def __init__(self,normalizer_dir,scenario):
        from .historical_env import HistoricalTrainingEnv
        self.env=HistoricalTrainingEnv(normalizer_dir,scenario);self.scenario=scenario
        self.directory=self.env.eligibility_dir
        m=json.loads((self.directory/'manifest.json').read_text());self.protocol=json.loads((self.directory/'protocol.json').read_text())
        self.dates=tuple(r['session_id'] for r in json.loads((self.directory/'sessions.json').read_text())
            if r['data_eligible'] and r['partition']=='validation')
        if not self.dates:raise ValueError('nonempty common validation dates required')
        self.anchors=dict(self.env.input_hashes)
        prepared=Path(m['prepared_manifest']['path']);source=json.loads(prepared.read_text())
        for row in source['sessions']:
            if row['session_id'] not in self.dates:continue
            self.anchors.update(row['canonical_inputs'])
            grid=prepared.parent/row['grid_file'];self.anchors[str(grid.resolve())]=source['outputs'][row['grid_file']]
        self.verify_inputs()

    def verify_inputs(self):
        self.env.verify_inputs()
        for p,h in self.anchors.items():verify(p,h)

    def session(self,day):
        if day not in self.dates:raise ValueError('only frozen validation dates admitted; test blocked')
        return read_eligible_session(self.directory,date.fromisoformat(day),partition='validation')

    def replay(self,session,policy):
        return MaskedDailyReplay(self.env.tickers,**self.env.economic_options).run(session.day,session.frames,policy)

    def evaluate_many(self,models,*,on_day_complete=None):
        import numpy as np
        from .cached_observations import CachedMaskedEncoder
        rows={key:[] for key in models}
        for day in self.dates:
            session=self.session(day)
            encoder=CachedMaskedEncoder(self.env.encoder.normalizer,session,self.env.encoder.initial_capital,
                include_account_context=self.env.encoder.include_account_context)
            for key,model in models.items():
                def policy(obs):
                    x=encoder.flatten(obs,session.trades)
                    action,_=model.predict(x,deterministic=True)
                    if not np.all(np.isfinite(action)):raise RuntimeError('nonfinite validation action')
                    return tuple(float(a) for a in np.clip(action,-1,1))
                rows[key].append(result_metrics(self.replay(session,policy)))
            if on_day_complete is not None:
                on_day_complete(day,{key:values[-1] for key,values in rows.items()})
        self.verify_inputs();return rows

    def baselines(self):
        streams={s:random.Random(s) for s in range(100,110)}
        runs={(name,seed):[] for name in BASELINES for seed in (range(100,110) if name=='uniform_random_actions' else (None,))}
        for day in self.dates:
            session=self.session(day)
            for (name,seed),rows in runs.items():
                policy=BaselinePolicy(name,self.env.tickers,rng=streams.get(seed))
                rows.append(result_metrics(self.replay(session,policy)))
        self.verify_inputs()
        return [dict(baseline=name,seed=seed,validation=rows) for (name,seed),rows in runs.items()]


def make_plan(protocol,mode,algorithms,scenarios,steps=None):
    if mode not in ('diagnostic','protocol'):raise ValueError('explicit selection mode required')
    if not algorithms or any(a not in ALGORITHMS for a in algorithms):raise ValueError('registered core algorithms required')
    if not scenarios or any(s not in ('all_gaps','short_gaps') for s in scenarios):raise ValueError('registered scenarios required')
    configs=list(itertools.product(protocol['models']['hidden_width_candidates'],protocol['models']['learning_rate_candidates']))
    if mode=='diagnostic':
        steps=384 if steps is None else steps
        if type(steps) is not int or not 368<=steps<=4096:raise ValueError('diagnostic budget must be 368..4096')
        configs=[configs[0],configs[-1]]
    else:
        if steps is not None:raise ValueError('protocol budget cannot be overridden')
        review=protocol.get('day_trading_review',{})
        if (review.get('status')!='frozen_and_verified'
                or review.get('admissibility_rule')!='flat_all_common_validation_seed_sessions'):
            raise ValueError('protocol selection blocked: exit preparation, learning objective and account assumptions must be frozen and verified')
        if protocol['environment'].get('account_regime') not in ('cash_settled','intraday_buying_power'):
            raise ValueError('protocol selection requires an explicit frozen account regime')
        steps=protocol['training']['tuning_steps_per_fit']
    seeds=protocol['training']['tuning_seeds']
    jobs=[dict(scenario=s,algorithm=a,width=w,learning_rate=lr,seed=seed) for s,a,(w,lr),seed in
        itertools.product(scenarios,algorithms,configs,seeds)]
    return dict(mode=mode,steps_per_fit=steps,seeds=seeds,configs=[dict(width=w,learning_rate=lr) for w,lr in configs],
        scenarios=list(scenarios),algorithms=list(algorithms),jobs=jobs,planned_fits=len(jobs),
        requested_transitions=len(jobs)*steps,test_prices_accessed=False,eligible_for_final_refit=mode=='protocol',
        scope='core algorithms; discount/observation variant selection remains a separate stage',
        replay_array_bytes_per_off_policy_fit=(1024 if mode=='diagnostic' else 100000)*(
            2*(15502+3*(protocol['environment'].get('account_regime','legacy_reinvest')!='legacy_reinvest'))+18+3)*4)


def train_job(context,job,steps,diagnostic,destination):
    import torch,numpy as np
    from .algorithm_builders import build_agent,describe_agent
    from .historical_env import HistoricalTrainingEnv
    from .historical_normalization import HistoricalMaskedNormalizer
    from stable_baselines3.common.callbacks import BaseCallback
    destination.mkdir(parents=True,exist_ok=False);env=HistoricalTrainingEnv(context.env.normalizer_dir,job['scenario'])
    device=job.get('device','cpu')
    model=build_agent(job['algorithm'],env,job['seed'],job['width'],job['learning_rate'],smoke=diagnostic,device=device)
    actor=model.actor if job['algorithm'] in ('SAC','DDPG') else model.policy.mlp_extractor.policy_net
    initial=torch.cat([p.detach().flatten() for p in actor.parameters()]).clone()
    class TerminalAudit(BaseCallback):
        def _on_step(self):
            for info in self.locals['infos']:
                if 'episode_result' in info and (info.get('TimeLimit.truncated') or info['terminal_observation'][-1]!=0):
                    raise RuntimeError('invalid financial terminal observation')
            return True
    model.learn(total_timesteps=steps,callback=TerminalAudit())
    limit=model.n_steps-1 if job['algorithm'] in ('PPO','A2C') else 0
    if not steps<=model.num_timesteps<=steps+limit:raise RuntimeError('rollout budget violation')
    final=torch.cat([p.detach().flatten() for p in actor.parameters()])
    if torch.equal(initial,final) or any(not torch.isfinite(p).all() for p in model.policy.parameters()) or not env.completed:
        raise RuntimeError('actor did not update, nonfinite weights or no complete episode')
    model.save(destination/'model.zip');env.encoder.normalizer.save(destination/'normalizer.json')
    restored=type(model).load(destination/'model.zip',device=device,custom_objects={'buffer_size':1})
    if HistoricalMaskedNormalizer.load(destination/'normalizer.json')!=env.encoder.normalizer:
        raise RuntimeError('normalizer checkpoint mismatch')
    sampling=list(env.sampling_order);probe,_=env.reset(seed=job['seed'])
    if not np.array_equal(model.predict(probe,deterministic=True)[0],restored.predict(probe,deterministic=True)[0]):
        raise RuntimeError('checkpoint prediction mismatch')
    env.verify_inputs()
    report=dict(status='trained_awaiting_validation',**job,requested_transitions=steps,realized_transitions=model.num_timesteps,
        diagnostic=diagnostic,eligible_for_final_refit=False,sampling_order=sampling,
        actor_updated=True,checkpoint_prediction_identical=True,settings=describe_agent(model),
        artifacts_sha256={p.name:digest(p) for p in destination.iterdir() if p.is_file()})
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report


def execute(normalizer_dir,output,*,mode='diagnostic',algorithms=('PPO',),scenarios=('all_gaps','short_gaps'),steps=None,resume=False,device='cpu'):
    import torch
    from .algorithm_builders import resolve_device
    device=resolve_device(device)
    normalizer_dir,output=map(Path,(normalizer_dir,output));torch.set_num_threads(1)
    contexts={s:ValidationContext(normalizer_dir,s) for s in scenarios}
    protocol=next(iter(contexts.values())).protocol;plan=make_plan(protocol,mode,algorithms,scenarios,steps)
    plan['device']=device
    for job in plan['jobs']:job['device']=device
    plan['inputs_sha256']={p:h for c in contexts.values() for p,h in c.anchors.items()}
    plan['source_sha256']={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('algorithm_builders.py'),
        Path(__file__).with_name('historical_env.py'),Path(__file__).with_name('masked_observations.py'),Path(__file__).with_name('masked_baselines.py'),Path(__file__).with_name('missing_data_replay.py'),Path(__file__).with_name('cached_observations.py'))}
    if output.exists():
        if not resume:raise FileExistsError(output)
        if json.loads((output/'plan.json').read_text())!=plan:raise ValueError('resume requires identical code, inputs and plan')
        previous=json.loads((output/'manifest.json').read_text())
        for p,h in previous.get('committed_json_sha256',{}).items():verify(output/p,h)
    else:
        output.mkdir(parents=True);(output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    state=dict(status='in_progress',mode=mode,test_prices_accessed=False,eligible_for_final_refit=False,completed_jobs=0,failed_jobs=0,committed_json_sha256={})
    def save(): (output/'manifest.json').write_text(json.dumps(state,indent=2)+'\n')
    save();reports={};controls={}
    try:
        for scenario,context in contexts.items():
            path=output/scenario/'baselines.json';path.parent.mkdir(exist_ok=True)
            if not path.exists():path.write_text(json.dumps(context.baselines(),indent=2)+'\n')
            baseline_runs=json.loads(path.read_text())
            controls[scenario]=next(r['validation'] for r in baseline_runs if r['baseline']=='equal_allocation_single_entry')
            state['committed_json_sha256'][str(path.relative_to(output))]=digest(path);save()
        for job in plan['jobs']:
            key=(job['scenario'],job['algorithm'],job['width'],job['learning_rate'])
            name=f"{job['algorithm']}_w{job['width']}_lr{job['learning_rate']}_seed{job['seed']}"
            destination=output/job['scenario']/name;path=destination/'report.json'
            if path.exists():
                report=json.loads(path.read_text())
                for n,h in report.get('artifacts_sha256',{}).items():verify(destination/n,h)
            elif destination.exists():raise ValueError('partial job without report; preserve it and start a new run directory')
            else:
                try:report=train_job(contexts[job['scenario']],job,plan['steps_per_fit'],mode=='diagnostic',destination)
                except Exception as exc:
                    destination.mkdir(parents=True,exist_ok=True);report=dict(status='failed',**job,error=str(exc))
                    path.write_text(json.dumps(report,indent=2)+'\n')
            if any(report[k]!=job[k] for k in job):raise ValueError('cached job identity differs from plan')
            reports.setdefault(key,[]).append(report)
            state['committed_json_sha256'][str(path.relative_to(output))]=digest(path)
            state['completed_jobs']+=report['status'] in ('completed','trained_awaiting_validation');state['failed_jobs']+=report['status']=='failed';save()
            print(json.dumps(dict(**job,status=report['status'])),flush=True);gc.collect()
        # Stream one market session across all checkpoints of an algorithm/scenario.
        # Loading for prediction uses a one-slot unused replay buffer, not the training allocation.
        import stable_baselines3 as sb3
        for scenario,algorithm in itertools.product(scenarios,algorithms):
            pending=[];models={}
            for key,runs in reports.items():
                if key[:2]!=(scenario,algorithm):continue
                for report in runs:
                    if report['status']!='trained_awaiting_validation':continue
                    name=f"{algorithm}_w{report['width']}_lr{report['learning_rate']}_seed{report['seed']}"
                    folder=output/scenario/name
                    models[name]=getattr(sb3,algorithm).load(folder/'model.zip',device=device,custom_objects={'buffer_size':1})
                    pending.append((name,folder,report))
            if models:
                evaluated=contexts[scenario].evaluate_many(models)
                for name,folder,report in pending:
                    report.update(status='completed',validation=evaluated[name],eligible_for_final_refit=False)
                    path=folder/'report.json';path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
                    state['committed_json_sha256'][str(path.relative_to(output))]=digest(path);save()
                print(json.dumps(dict(scenario=scenario,algorithm=algorithm,validation_dates=len(contexts[scenario].dates),checkpoints=len(models))),flush=True)
            models.clear();gc.collect()
        candidates=[]
        for (scenario,algorithm,width,lr),runs in reports.items():
            aggregate=aggregate_candidate(runs,plan['seeds'],contexts[scenario].dates)
            candidate=dict(scenario=scenario,algorithm=algorithm,width=width,learning_rate=lr,aggregate=aggregate)
            if aggregate['eligible']:candidate['versus_equal_entry']=paired_differences(runs,controls[scenario],contexts[scenario].dates)
            candidates.append(candidate)
        selected=[]
        for scenario,algorithm in itertools.product(scenarios,algorithms):
            ranked=rank_candidates([c for c in candidates if c['scenario']==scenario and c['algorithm']==algorithm],
                require_day_trading=mode=='protocol')
            if ranked:selected.append(ranked[0])
        artifact=dict(mode=mode,eligible_for_final_refit=mode=='protocol' and len(selected)==len(scenarios)*len(algorithms),
            candidates=candidates,selected=selected,selection_scope=plan['scope'],test_prices_accessed=False)
        filename='selected_configurations.json' if mode=='protocol' else 'diagnostic_ranking.json'
        (output/filename).write_text(json.dumps(artifact,indent=2,allow_nan=False)+'\n')
        for c in contexts.values():c.verify_inputs()
        for p,h in plan['source_sha256'].items():verify(p,h)
        state.update(status=('diagnostic_selection_completed' if mode=='diagnostic' else 'protocol_selection_completed') if len(selected)==len(scenarios)*len(algorithms) else 'selection_incomplete',
            eligible_for_final_refit=artifact['eligible_for_final_refit'],selection_sha256=digest(output/filename),
            outputs_sha256={str(p.relative_to(output)):digest(p) for p in output.rglob('*.json') if p!=output/'manifest.json'})
        save();return artifact
    except Exception as exc:
        state.update(status='failed',error=str(exc));save();raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--normalizer-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=('diagnostic','protocol'),default='diagnostic')
    p.add_argument('--algorithm',choices=(*ALGORITHMS,'ALL'),default='PPO');p.add_argument('--scenario',choices=('all_gaps','short_gaps','ALL'),default='ALL')
    p.add_argument('--steps',type=int);p.add_argument('--resume',action='store_true')
    p.add_argument('--device',choices=('cpu','cuda'),default='cpu');a=p.parse_args()
    execute(a.normalizer_dir,a.output,mode=a.mode,algorithms=ALGORITHMS if a.algorithm=='ALL' else (a.algorithm,),
        scenarios=('all_gaps','short_gaps') if a.scenario=='ALL' else (a.scenario,),steps=a.steps,resume=a.resume,device=a.device)


if __name__=='__main__':main()
