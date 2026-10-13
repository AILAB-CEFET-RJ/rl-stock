"""Four-algorithm historical train smoke; no validation/test outcomes or full-budget fits."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import date, timedelta
from pathlib import Path


def run_historical_smoke(output, normalizer_dir, scenario, steps=384, seed=0, algorithm="PPO", *, device='cpu'):
    import numpy as np
    import torch
    from .algorithm_builders import build_agent, describe_agent, resolve_device
    from stable_baselines3.common.env_checker import check_env
    from stable_baselines3.common.callbacks import BaseCallback
    from .historical_env import HistoricalTrainingEnv
    from .historical_normalization import HistoricalMaskedNormalizer

    if type(steps) is not int or not 368 <= steps <= 4096:
        raise ValueError('historical smoke budget must be between 368 and 4096 transitions')
    device = resolve_device(device)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    env = HistoricalTrainingEnv(normalizer_dir, scenario)
    normalizer = env.encoder.normalizer
    check_env(env, warn=True)
    # Keep checker resets/transitions separate from the learning accounting.
    env.sampling_order.clear();env.completed.clear()
    model = build_agent(algorithm, env, seed, smoke=True, device=device)
    effective_settings = describe_agent(model)
    class ClipAudit(BaseCallback):
        def __init__(self):
            super().__init__()
            self.components = self.clipped = 0
            self.valid_counts = set()
            self.terminals = 0

        def _on_step(self):
            proposals = self.locals['actions']
            self.components += proposals.size
            self.clipped += int(np.count_nonzero(np.abs(proposals) > 1))
            for info in self.locals['infos']:
                self.valid_counts.add(sum(info['availability']))
                if 'episode_result' in info:
                    self.terminals += 1
                    if info.get('TimeLimit.truncated') or info['terminal_observation'][-1] != 0:
                        raise RuntimeError('genuine financial end must not bootstrap or retain a horizon')
            return True
    clipping = ClipAudit()
    initial_parameters = torch.cat([p.detach().flatten() for p in model.policy.parameters()]).clone()
    actor = model.actor if algorithm in ('SAC', 'DDPG') else model.policy.mlp_extractor.policy_net
    initial_actor = torch.cat([p.detach().flatten() for p in actor.parameters()]).clone()
    if device == 'cuda': torch.cuda.synchronize()
    started = time.monotonic()
    model.learn(total_timesteps=steps, callback=clipping)
    if device == 'cuda': torch.cuda.synchronize()
    wall = time.monotonic()-started
    final_parameters = torch.cat([p.detach().flatten() for p in model.policy.parameters()])
    final_actor = torch.cat([p.detach().flatten() for p in actor.parameters()])
    if (torch.equal(initial_parameters, final_parameters) or torch.equal(initial_actor, final_actor)
            or not torch.isfinite(final_parameters).all() or not env.completed):
        raise RuntimeError('smoke failed to update policy or complete a session')
    overrun_limit = model.n_steps-1 if algorithm in ('PPO', 'A2C') else 0
    if not steps <= model.num_timesteps <= steps+overrun_limit:
        raise RuntimeError('transition budget exceeded allowed rollout overrun')
    terminal_audit = None
    if algorithm in ('SAC', 'DDPG'):
        buffer = model.replay_buffer
        end = buffer.buffer_size if buffer.full else buffer.pos
        mask = buffer.dones[:end, 0].astype(bool)
        terminal_audit = dict(terminal_count=int(mask.sum()),
                             terminal_horizon_zero=bool(np.all(buffer.next_observations[:end, 0, -1][mask] == 0)),
                             no_time_limit_bootstrap=bool(np.all(buffer.timeouts[:end, 0][mask] == 0)))
        if not mask.any() or not all((terminal_audit['terminal_horizon_zero'], terminal_audit['no_time_limit_bootstrap'])):
            raise RuntimeError('replay terminal-state or bootstrap audit failed')
    model.save(output/'model.zip')
    normalizer.save(output/'normalizer.json')
    learning_sampling_order=list(env.sampling_order)
    learning_unfinished_session=str(env.session.day)
    restored = type(model).load(output/'model.zip', device=device)
    restored_normalizer = HistoricalMaskedNormalizer.load(output/'normalizer.json')
    if restored_normalizer != normalizer:raise RuntimeError('normalizer snapshot mismatch')
    probe, _ = env.reset(seed=seed)
    before, _ = model.predict(probe, deterministic=True)
    after, _ = restored.predict(probe, deterministic=True)
    if not np.array_equal(before, after):
        raise RuntimeError('checkpoint deterministic prediction mismatch')
    # Replay only training dates sampled by this smoke; never consult validation/test prices.
    from .missing_data_replay import MaskedDailyReplay
    from .cached_observations import CachedMaskedEncoder
    evaluation = []
    for day in sorted(set(learning_sampling_order)):
        session = env.session_for_day(date.fromisoformat(day))
        encoder = CachedMaskedEncoder(restored_normalizer, session, env.encoder.initial_capital,
                                      include_account_context=env.encoder.include_account_context)
        def policy(observation):
            inputs = np.asarray(encoder.flatten(observation, session.trades), dtype=np.float32)
            actions, _ = restored.predict(inputs, deterministic=True)
            return tuple(float(a) for a in np.clip(actions, -1, 1))
        result = MaskedDailyReplay(env.tickers, **env.economic_options).run(session.day, session.frames, policy)
        if not result.coverage_candidate or result.status not in ('scheduled_end','capital_stop','liquidation_failure'):
            raise RuntimeError('frozen historical train replay failed')
        evaluation.append(result)
    env.verify_inputs()
    files = [Path(__file__).with_name(n) for n in
             ('algorithm_builders.py', 'historical_training.py', 'historical_env.py', 'historical_normalization.py', 'masked_env.py', 'masked_observations.py', 'missing_data_replay.py', 'session_replay.py',
              'economic_kernel.py', 'market_calendar.py', 'cached_observations.py')]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(status='historical_train_integration_only', historical_data_used=True,
        scenario=scenario,partition='train',validation_prices_accessed=False,test_prices_accessed=False,
        account_regime=env.economic_options['account_regime'],
        reward_objective=env.economic_options['reward_objective'],
        wind_down_execution_points=env.economic_options['wind_down_points'],
        eligible_training_sessions=len(env.dates),inputs_sha256=env.input_hashes,
        algorithm=type(model).__name__, seed=seed, device=str(model.device),
        python=platform.python_version(), dependencies={n: importlib.metadata.version(n)
            for n in ('stable-baselines3', 'gymnasium', 'torch', 'numpy')},
        requested_transitions=steps, realized_transitions=model.num_timesteps,
        effective_settings=effective_settings,
        replay_terminal_audit=terminal_audit,
        terminal_observations_audited=clipping.terminals,
        valid_asset_counts_seen=sorted(clipping.valid_counts),
        normalizer_unchanged_on_evaluation=normalizer == restored_normalizer,
        evaluation_scope='sampled training dates only; integration, not hyperparameter selection or generalization',
        updates=model._n_updates, wall_seconds=wall, torch_threads=torch.get_num_threads(),
        observation_shape=list(env.observation_space.shape), tickers=list(env.tickers),
        parameter_count=sum(p.numel() for p in model.policy.parameters()),
        policy_changed=True, checkpoint_prediction_identical=True,
        actor_changed=True, weights_finite=True,
        frozen_evaluation=[dict(session_id=str(r.plan.day), status=r.status, flat=r.transitions[-1].flat) for r in evaluation],
        audited_action_components=clipping.components, out_of_bounds_components=clipping.clipped,
        action_audit_stage='raw Gaussian proposals' if algorithm in ('PPO', 'A2C') else 'after squashing/noise clipping',
        sampling_order=learning_sampling_order, completed_sessions=env.completed,
        loaded_train_dates=sorted(set(env.loaded_dates)),
        normalizer_sha256=sha(output/'normalizer.json'),
        unfinished_rollout_session=learning_unfinished_session,
        source_hashes={p.name: sha(p) for p in files},
        artifacts={p.name: sha(p) for p in (output/'model.zip', output/'normalizer.json')},
        protocol_deviations=['smoke budget only; no validation selection or final refit'] + (
            ['32-step rollouts', 'batch size 16', 'one optimization epoch'] if algorithm == 'PPO' else
            ['replay size 1024', 'batch size 32', 'learning starts 32'] if algorithm in ('SAC', 'DDPG') else []),
        full_experiment_completed=False)
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-smoke',action='store_true',required=True)
    parser.add_argument('--normalizer-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=384);parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--scenario',choices=('all_gaps','short_gaps','ALL'),default='ALL')
    parser.add_argument('--algorithm',choices=('PPO','A2C','SAC','DDPG','ALL'),default='ALL')
    parser.add_argument('--device',choices=('cpu','cuda'),default='cpu')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    scenarios=('all_gaps','short_gaps') if args.scenario=='ALL' else (args.scenario,)
    algorithms=('PPO','A2C','SAC','DDPG') if args.algorithm=='ALL' else (args.algorithm,)
    summaries=[]
    import gc
    state=dict(status='in_progress',validation_prices_accessed=False,test_prices_accessed=False,completed_runs=[])
    status_path=args.output/'manifest.json'
    def save():status_path.write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        for scenario in scenarios:
            for algorithm in algorithms:
                report=run_historical_smoke(args.output/scenario/algorithm,args.normalizer_dir,scenario,args.steps,args.seed,algorithm,device=args.device)
                summary={k:report[k] for k in ('status','scenario','algorithm','realized_transitions','updates',
                    'actor_changed','checkpoint_prediction_identical','replay_terminal_audit')}
                print(json.dumps(summary),flush=True);summaries.append(summary);gc.collect()
                state['completed_runs']=summaries;save()
        suite=args.output/'suite_report.json';suite.write_text(json.dumps(summaries,indent=2)+'\n')
        state.update(status='historical_train_smoke_completed',full_experiment_completed=False,
            suite_report_sha256=hashlib.sha256(suite.read_bytes()).hexdigest())
        save()
    except Exception as exc:
        state.update(status='failed',error=str(exc));save();raise


if __name__=='__main__':main()
