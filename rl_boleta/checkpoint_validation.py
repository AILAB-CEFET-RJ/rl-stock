"""Evaluate a completed tuning checkpoint without fitting, selection or test access."""
import argparse
import json
from decimal import Decimal, localcontext
from pathlib import Path

from .algorithm_builders import ALGORITHMS, resolve_device
from .data_pipeline import digest
from .historical_normalization import HistoricalMaskedNormalizer
from .masked_baselines import BaselinePolicy
from .masked_preparation import verify
from .validation_selection import ValidationContext, day_trading_admissibility, result_metrics


def summarize(rows):
    if not rows:
        raise ValueError('nonempty validation outcomes required')
    admission = day_trading_admissibility(rows)
    with localcontext() as ctx:
        ctx.prec = 50
        def mean(key):
            values = [Decimal(row[key]) for row in rows]
            if any(not v.is_finite() for v in values):
                raise ValueError('nonfinite validation metric')
            return str(sum(values, Decimal(0)) / len(values))
        return dict(sessions=len(rows), admissibility=admission,
                    mean_marked_return=mean('marked_return'),
                    mean_realized_return=mean('realized_return') if admission['admissible'] else None,
                    mean_maximum_marked_drawdown=mean('maximum_marked_drawdown'),
                    mean_fees=mean('fees'), mean_turnover_per_capital=mean('turnover_per_capital'),
                    liquidation_failures=sum(r['status']=='liquidation_failure' for r in rows),
                    nonflat_sessions=sum(not r['flat'] for r in rows))


def evaluate(checkpoint_dir, normalizer_dir, output_dir, *, device='cuda', with_baselines=False):
    import torch
    import stable_baselines3 as sb3

    device = resolve_device(device)
    checkpoint_dir, normalizer_dir, output_dir = map(Path, (checkpoint_dir, normalizer_dir, output_dir))
    if output_dir.exists():
        raise FileExistsError('use a new validation output directory')
    source = checkpoint_dir/'report.json'
    trained = json.loads(source.read_text())
    if (trained['status'] != 'trained_awaiting_validation' or trained['algorithm'] not in ALGORITHMS
            or trained.get('actor_updated') is not True or trained.get('checkpoint_prediction_identical') is not True):
        raise ValueError('verified completed tuning checkpoint required')
    for name, sha in trained['artifacts_sha256'].items():
        if Path(name).name != name:
            raise ValueError('checkpoint artifact must have a local filename')
        verify(checkpoint_dir/name, sha)
    if not {'model.zip','normalizer.json'} <= set(trained['artifacts_sha256']):
        raise ValueError('model and normalizer hashes required')
    context = ValidationContext(normalizer_dir, trained['scenario'])
    snapshot = HistoricalMaskedNormalizer.load(checkpoint_dir/'normalizer.json')
    if snapshot != context.env.encoder.normalizer:
        raise ValueError('checkpoint normalizer differs from the verified scenario bundle')
    period = context.protocol['partitions']['validation']
    if (not context.dates or tuple(sorted(set(context.dates))) != context.dates
            or any(not period['first'] <= d <= period['last'] for d in context.dates)):
        raise ValueError('validation dates must be unique and inside the frozen validation period')
    if trained['seed'] not in context.protocol['training']['tuning_seeds']:
        raise ValueError('checkpoint seed outside frozen tuning design')
    if (trained.get('diagnostic') is not False
            or trained['requested_transitions'] != context.protocol['training']['tuning_steps_per_fit']):
        raise ValueError('full tuning-budget checkpoint required')
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model = getattr(sb3, trained['algorithm']).load(checkpoint_dir/'model.zip', device=device,
                                                 custom_objects={'buffer_size':1})
    if (model.num_timesteps != trained['realized_transitions']
            or model.observation_space.shape != context.env.observation_space.shape
            or model.action_space.shape != context.env.action_space.shape):
        raise ValueError('checkpoint budget or observation/action dimensions differ')
    if not all(torch.isfinite(p).all().item() for p in model.policy.parameters()):
        raise ValueError('nonfinite checkpoint weights')
    weights = [p.detach().clone() for p in model.policy.parameters()]
    anchors = {str(source.resolve()):digest(source),
               str((checkpoint_dir/'model.zip').resolve()):digest(checkpoint_dir/'model.zip'),
               str((checkpoint_dir/'normalizer.json').resolve()):digest(checkpoint_dir/'normalizer.json'),
               **context.anchors}
    output_dir.mkdir(parents=True,exist_ok=False)
    report = dict(status='checkpoint_validation_in_progress', phase='single_seed_validation',
                  job={k:trained[k] for k in ('scenario','algorithm','width','learning_rate','seed')},
                  account_regime=context.env.economic_options['account_regime'], device=str(model.device),
                  validation_dates=list(context.dates), inputs_sha256=anchors,
                  validation_prices_accessed=True, test_prices_accessed=False,
                  model_selection_completed=False, eligible_for_final_refit=False,
                  required_tuning_seeds=context.protocol['training']['tuning_seeds'],
                  evaluated_seeds=[trained['seed']], baselines={},
                  source_sha256={name:digest(Path(__file__).with_name(name)) for name in
                                 ('checkpoint_validation.py','validation_selection.py','historical_env.py',
                                  'masked_observations.py','cached_observations.py','missing_data_replay.py',
                                  'economic_kernel.py','masked_baselines.py')})
    def save():
        (output_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    def progress(day, results):
        row=results['checkpoint']
        print(json.dumps(dict(session_id=day,status=row['status'],flat=row['flat'],
                              marked_return=row['marked_return'],realized_return=row['realized_return'])),flush=True)
    save()
    try:
        with torch.inference_mode():
            rows=context.evaluate_many({'checkpoint':model},on_day_complete=progress)['checkpoint']
        if [r['session_id'] for r in rows] != list(context.dates):
            raise ValueError('missing or reordered validation outcomes')
        report.update(validation=rows, summary=summarize(rows))
        if with_baselines:
            for name in ('cash','equal_allocation_single_entry'):
                outcomes=[]
                for day in context.dates:
                    session=context.session(day)
                    result=context.replay(session,BaselinePolicy(name,context.env.tickers))
                    outcomes.append(result_metrics(result))
                    print(json.dumps(dict(baseline=name,session_id=day,status=result.status)),flush=True)
                report['baselines'][name]=dict(validation=outcomes,summary=summarize(outcomes))
        if (model.num_timesteps != trained['realized_transitions']
                or not all(torch.equal(a,b) for a,b in zip(weights,model.policy.parameters()))):
            raise RuntimeError('checkpoint weights changed during frozen evaluation')
        context.verify_inputs()
        for path,sha in anchors.items():verify(path,sha)
        report.update(status='checkpoint_validation_completed',weights_unchanged=True,
                      normalizer_unchanged=HistoricalMaskedNormalizer.load(checkpoint_dir/'normalizer.json')==snapshot)
        save();return report
    except Exception as exc:
        report.update(status='checkpoint_validation_failed',error=str(exc));save();raise
    finally:
        context.env.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint-dir',type=Path,required=True)
    p.add_argument('--normalizer-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    p.add_argument('--with-baselines',action='store_true')
    a=p.parse_args()
    r=evaluate(a.checkpoint_dir,a.normalizer_dir,a.output_dir,device=a.device,with_baselines=a.with_baselines)
    print(json.dumps(dict(status=r['status'],job=r['job'],summary=r['summary'],
                         baselines={k:v['summary'] for k,v in r['baselines'].items()},
                         test_prices_accessed=False,eligible_for_final_refit=False),indent=2))


if __name__=='__main__':main()
