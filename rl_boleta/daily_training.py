"""Four-algorithm integration smoke test. Historical experimental fits remain gated."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import date, timedelta
from pathlib import Path


def synthetic_sessions():
    from .economic_kernel import Book, Frame, Level
    from .observations import MarketSession, Trade
    from .session_replay import session_plan
    sessions = []
    for offset in range(3):
        day = date(2025, 3, 3)+timedelta(days=offset)
        fs, trades = [], {}
        for index, at in enumerate(session_plan(day).required_times):
            books = []
            for j, ticker in enumerate(('SYNTA', 'SYNTB')):
                mid = 100+j*20+(index % 7)*0.01
                books.append(Book(ticker, f'{ticker}-{at.isoformat()}', at,
                    tuple(Level(str(round(mid-.01-i*.01, 2)), 1000) for i in range(5)),
                    tuple(Level(str(round(mid+.01+i*.01, 2)), 1000) for i in range(5))))
                trades[at, ticker] = tuple(Trade(str(mid), 10+i, at) for i in range(10))
            fs.append(Frame(at, str(day), tuple(books)))
        sessions.append(MarketSession(day, tuple(fs), trades))
    return tuple(sessions)


def build_ppo(env, seed, width=64, learning_rate=1e-4, smoke=False):
    from .algorithm_builders import build_agent
    return build_agent('PPO', env, seed, width, learning_rate, smoke)


def evaluate_period(model, sessions, encoder, first, last, **economic_options):
    """Frozen deterministic evaluation, retaining every scheduled date."""
    import numpy as np
    from . import market_calendar
    from .session_replay import DailySessionReplay
    controller = DailySessionReplay(encoder.tickers, **economic_options)
    if controller._template.initial_capital != encoder.initial_capital:
        raise ValueError('encoder and evaluation capital scales must match')
    results = []
    for day in market_calendar.dates(first, last):
        if market_calendar.window(day) is None:
            continue
        session = sessions.get(day)
        def policy(observation):
            inputs = np.asarray(encoder.flatten(observation, session.trades), dtype=np.float32)
            actions, _ = model.predict(inputs, deterministic=True)
            return tuple(float(a) for a in np.clip(actions, -1, 1))
        results.append(controller.run(day, session.frames if session else (), policy))
    return tuple(results)


def run_synthetic_smoke(output, steps=384, seed=0, algorithm="PPO"):
    import numpy as np
    import torch
    from .algorithm_builders import build_agent, describe_agent
    from stable_baselines3.common.env_checker import check_env
    from stable_baselines3.common.callbacks import BaseCallback
    from .daily_env import DailyTrainingEnv
    from .observations import Encoder, Normalizer, fit_normalizer

    if type(steps) is not int or steps < 368:
        raise ValueError('smoke must cover at least one normal session')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    sessions = synthetic_sessions()
    normalizer = fit_normalizer(sessions, ('SYNTA', 'SYNTB'))
    encoder = Encoder(normalizer)
    check_env(DailyTrainingEnv(sessions, encoder), warn=True)
    env = DailyTrainingEnv(sessions, encoder)
    model = build_agent(algorithm, env, seed, smoke=True)
    effective_settings = describe_agent(model)
    class ClipAudit(BaseCallback):
        def __init__(self):
            super().__init__()
            self.components = self.clipped = 0

        def _on_step(self):
            proposals = self.locals['actions']
            self.components += proposals.size
            self.clipped += int(np.count_nonzero(np.abs(proposals) > 1))
            return True
    clipping = ClipAudit()
    initial_parameters = torch.cat([p.detach().flatten() for p in model.policy.parameters()]).clone()
    actor = model.actor if algorithm in ('SAC', 'DDPG') else model.policy.mlp_extractor.policy_net
    initial_actor = torch.cat([p.detach().flatten() for p in actor.parameters()]).clone()
    started = time.monotonic()
    model.learn(total_timesteps=steps, callback=clipping)
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
    restored = type(model).load(output/'model.zip', device='cpu')
    restored_normalizer = Normalizer.load(output/'normalizer.json')
    probe, _ = DailyTrainingEnv(sessions, Encoder(restored_normalizer)).reset(seed=seed)
    before, _ = model.predict(probe, deterministic=True)
    after, _ = restored.predict(probe, deterministic=True)
    if not np.array_equal(before, after):
        raise RuntimeError('checkpoint deterministic prediction mismatch')
    evaluation = evaluate_period(restored, {s.day: s for s in sessions}, Encoder(restored_normalizer),
                                 sessions[0].day, sessions[-1].day)
    if not all(r.evaluable and r.status in ('scheduled_end', 'capital_stop') for r in evaluation):
        raise RuntimeError('frozen synthetic evaluation failed')
    files = [Path(__file__).with_name(n) for n in
             ('algorithm_builders.py', 'daily_training.py', 'daily_env.py', 'observations.py', 'session_replay.py',
              'economic_kernel.py', 'market_calendar.py')]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(status='synthetic_integration_only', historical_data_used=False,
        algorithm=type(model).__name__, seed=seed, device=str(model.device),
        python=platform.python_version(), dependencies={n: importlib.metadata.version(n)
            for n in ('stable-baselines3', 'gymnasium', 'torch', 'numpy')},
        requested_transitions=steps, realized_transitions=model.num_timesteps,
        effective_settings=effective_settings,
        replay_terminal_audit=terminal_audit,
        updates=model._n_updates, wall_seconds=wall, torch_threads=torch.get_num_threads(),
        observation_shape=list(env.observation_space.shape), tickers=list(env.tickers),
        parameter_count=sum(p.numel() for p in model.policy.parameters()),
        policy_changed=True, checkpoint_prediction_identical=True,
        actor_changed=True, weights_finite=True,
        frozen_evaluation=[dict(session_id=str(r.plan.day), status=r.status, flat=r.flat) for r in evaluation],
        audited_action_components=clipping.components, out_of_bounds_components=clipping.clipped,
        action_audit_stage='raw Gaussian proposals' if algorithm in ('PPO', 'A2C') else 'after squashing/noise clipping',
        sampling_order=env.sampling_order, completed_sessions=env.completed,
        unfinished_rollout_session=str(env.session.day),
        source_hashes={p.name: sha(p) for p in files},
        artifacts={p.name: sha(p) for p in (output/'model.zip', output/'normalizer.json')},
        protocol_deviations=['synthetic assets and data', 'smoke budget only'] + (
            ['32-step rollouts', 'batch size 16', 'one optimization epoch'] if algorithm == 'PPO' else
            ['replay size 1024', 'batch size 32', 'learning starts 32'] if algorithm in ('SAC', 'DDPG') else []),
        real_training_ready=False)
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-smoke', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=384)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--algorithm', choices=('PPO', 'A2C', 'SAC', 'DDPG', 'ALL'), default='PPO')
    args = parser.parse_args()
    if args.algorithm == 'ALL':
        args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for algorithm in ('PPO', 'A2C', 'SAC', 'DDPG') if args.algorithm == 'ALL' else (args.algorithm,):
        destination = args.output/algorithm if args.algorithm == 'ALL' else args.output
        report = run_synthetic_smoke(destination, args.steps, args.seed, algorithm)
        print(json.dumps({k: report[k] for k in ('status', 'algorithm', 'realized_transitions',
                                               'policy_changed', 'checkpoint_prediction_identical')}), flush=True)
        summaries.append({k: report[k] for k in ('algorithm', 'requested_transitions',
                                               'realized_transitions', 'updates', 'actor_changed',
                                               'checkpoint_prediction_identical', 'replay_terminal_audit')})
    if args.algorithm == 'ALL':
        (args.output/'suite_report.json').write_text(json.dumps(summaries, indent=2)+'\n')


if __name__ == '__main__':
    main()
