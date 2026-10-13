"""One fresh-process, train-only hardware benchmark with full algorithm settings."""
import argparse
import importlib.metadata
import json
import platform
import resource
import time
from pathlib import Path

from .algorithm_builders import ALGORITHMS, build_agent, describe_agent, resolve_device
from .data_pipeline import digest


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == 'Darwin' else value * 1024)


def available_ram_bytes():
    path = Path('/proc/meminfo')
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    return None


def buffer_arrays(model):
    import numpy as np
    buffer = model.replay_buffer if hasattr(model, 'replay_buffer') else model.rollout_buffer
    return {name: value for name, value in vars(buffer).items() if isinstance(value, np.ndarray)}


def benchmark(normalizer_dir, output, algorithm, *, device='cpu', scenario='all_gaps',
              width=128, learning_rate=1e-4, seed=0, measured_steps=2048,
              torch_threads=1, materialize_buffer=False):
    import numpy as np
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    from .historical_env import HistoricalTrainingEnv

    if algorithm not in ALGORITHMS or scenario not in ('all_gaps', 'short_gaps'):
        raise ValueError('registered algorithm and scenario required')
    if type(measured_steps) is not int or not 2048 <= measured_steps <= 20000:
        raise ValueError('measure 2048 to 20000 transitions after warmup')
    if type(torch_threads) is not int or torch_threads < 1:
        raise ValueError('positive CPU thread count required')
    if width not in (64, 128) or learning_rate not in (1e-4, 3e-4):
        raise ValueError('configuration outside frozen grid')
    device = resolve_device(device)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='compute_benchmark_in_progress', algorithm=algorithm, scenario=scenario,
                  requested_device=device, seed=seed, width=width, learning_rate=learning_rate,
                  partition='train', validation_prices_accessed=False, test_prices_accessed=False,
                  full_budget_selection_authorized=False, eligible_for_final_refit=False,
                  materialize_buffer=materialize_buffer, torch_threads=torch_threads)
    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    def sync():
        if device == 'cuda':
            torch.cuda.synchronize()
    def gpu_memory():
        return None if device == 'cpu' else dict(
            allocated_peak_bytes=torch.cuda.max_memory_allocated(),
            reserved_peak_bytes=torch.cuda.max_memory_reserved())
    save()
    started = time.monotonic()
    env = None
    try:
        torch.set_num_threads(torch_threads)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        if device == 'cuda':
            torch.cuda.reset_peak_memory_stats()
        setup = time.monotonic()
        env = HistoricalTrainingEnv(normalizer_dir, scenario)
        if env.economic_options['account_regime'] not in ('cash_settled', 'intraday_buying_power'):
            raise ValueError('explicit research account profile required')
        if (env.economic_options.get('wind_down_points') != 54
                or env.economic_options.get('reward_objective') != 'terminal_cash_utility'):
            raise ValueError('reviewed wind-down and cash utility profile required')
        report.update(account_regime=env.economic_options['account_regime'],
                      economic_options={k: str(v) for k, v in env.economic_options.items()},
                      observation_dimension=int(np.prod(env.observation_space.shape)),
                      inputs_sha256=dict(env.input_hashes))
        # SB3's replay arrays are in RAM even for a CUDA model. Check before allocation.
        estimate = 100000 * (2 * int(np.prod(env.observation_space.shape))
                            + int(np.prod(env.action_space.shape)) + 3) * 4
        available = available_ram_bytes()
        if algorithm in ('SAC', 'DDPG') and available is not None and available < estimate * 1.25 + 1024**3:
            raise RuntimeError('insufficient available RAM for full replay buffer plus working memory')
        report['available_ram_before_model_bytes'] = available
        model = build_agent(algorithm, env, seed, width, learning_rate, smoke=False, device=device)
        arrays = buffer_arrays(model)
        report.update(effective_settings=describe_agent(model), device=str(model.device),
                      buffer_array_bytes={k: a.nbytes for k, a in arrays.items()},
                      buffer_total_bytes=sum(a.nbytes for a in arrays.values()))
        if materialize_buffer:
            for a in arrays.values():
                a.fill(0)
        sync()
        report.update(setup_seconds=time.monotonic() - setup,
                      rss_peak_after_setup_bytes=peak_rss_bytes())
        actor = model.actor if algorithm in ('SAC', 'DDPG') else model.policy.mlp_extractor.policy_net

        class Progress(BaseCallback):
            def __init__(self, phase):
                super().__init__(); self.phase = phase
            def _on_step(self):
                if self.n_calls % 500 == 0:
                    print(json.dumps(dict(phase=self.phase, transitions=self.model.num_timesteps,
                                          updates=self.model._n_updates)), flush=True)
                for info in self.locals['infos']:
                    if 'episode_result' in info and (info.get('TimeLimit.truncated')
                            or info['terminal_observation'][-1] != 0):
                        raise RuntimeError('invalid financial terminal during benchmark')
                return True

        warmup_steps = model.learning_starts if algorithm in ('SAC', 'DDPG') else model.n_steps
        sync(); warmup_started = time.monotonic()
        model.learn(total_timesteps=warmup_steps, callback=Progress('warmup'))
        sync()
        report.update(warmup_seconds=time.monotonic() - warmup_started,
                      warmup_realized_transitions=model.num_timesteps, warmup_updates=model._n_updates,
                      gpu_setup_warmup_memory=gpu_memory())
        save()
        before_steps, before_updates = model.num_timesteps, model._n_updates
        before_actor = torch.cat([p.detach().flatten() for p in actor.parameters()]).clone()
        if device == 'cuda':
            torch.cuda.reset_peak_memory_stats()
        sync(); measured_started = time.monotonic()
        model.learn(total_timesteps=measured_steps, reset_num_timesteps=False, callback=Progress('measured'))
        sync(); seconds = time.monotonic() - measured_started
        realized = model.num_timesteps - before_steps
        limit = model.n_steps - 1 if algorithm in ('PPO', 'A2C') else 0
        if not measured_steps <= realized <= measured_steps + limit or model._n_updates <= before_updates:
            raise RuntimeError('benchmark did not execute requested learning and updates')
        after_actor = torch.cat([p.detach().flatten() for p in actor.parameters()])
        if torch.equal(before_actor, after_actor) or not all(torch.isfinite(p).all().item() for p in model.policy.parameters()):
            raise RuntimeError('actor unchanged or weights nonfinite')
        report.update(measured_requested_transitions=measured_steps, measured_realized_transitions=realized,
                      measured_updates=model._n_updates - before_updates, measured_seconds=seconds,
                      measured_transitions_per_second=realized / seconds,
                      gpu_measured_memory=gpu_memory(), rss_peak_after_learning_bytes=peak_rss_bytes(),
                      actor_changed=True, weights_finite=True,
                      completed_training_sessions=list(env.completed), sampling_order=list(env.sampling_order))
        # Confirm a complete-policy checkpoint on the same backend, without allocating a second full buffer.
        model.save(output / 'model.zip')
        restored = type(model).load(output / 'model.zip', device=device, custom_objects={'buffer_size': 1})
        probe, _ = env.reset(seed=seed)
        np.testing.assert_array_equal(model.predict(probe, deterministic=True)[0],
                                      restored.predict(probe, deterministic=True)[0])
        env.verify_inputs()
        report.update(status='compute_benchmark_completed', checkpoint_prediction_identical=True,
                      checkpoint_sha256=digest(output / 'model.zip'),
                      gpu_name=None if device == 'cpu' else torch.cuda.get_device_name(0),
                      gpu_compute_capability=None if device == 'cpu' else list(torch.cuda.get_device_capability(0)),
                      dependencies={n: importlib.metadata.version(n) for n in
                                    ('numpy', 'torch', 'gymnasium', 'stable-baselines3')},
                      python=platform.python_version(), platform=platform.platform(),
                      tf32_enabled=False, rss_peak_process_bytes=peak_rss_bytes(),
                      source_sha256={name: digest(Path(__file__).with_name(name)) for name in
                                     ('compute_benchmark.py', 'algorithm_builders.py', 'historical_env.py',
                                      'historical_normalization.py', 'cached_observations.py', 'missing_data_replay.py',
                                      'masked_env.py', 'masked_observations.py', 'economic_kernel.py',
                                      'session_replay.py', 'market_calendar.py')},
                      elapsed_seconds=time.monotonic() - started,
                      limitations=['Train-only technical run, no model selection or test evaluation.',
                                   'Timing includes historical session IO and preprocessing during learn.',
                                   'RSS is process high-water memory, not an incremental per-phase peak.',
                                   'Torch CUDA peaks exclude driver and other processes.',
                                   'Unmaterialized buffers can underestimate fully populated resident RAM.',
                                   'Short measurement excludes late-date workload and cache variation.'])
        save(); return report
    except Exception as exc:
        report.update(status='compute_benchmark_failed', error=str(exc), elapsed_seconds=time.monotonic() - started)
        save(); raise
    finally:
        if env is not None:
            env.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--normalizer-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--algorithm', choices=ALGORITHMS, required=True)
    p.add_argument('--device', choices=('cpu', 'cuda'), required=True)
    p.add_argument('--scenario', choices=('all_gaps', 'short_gaps'), default='all_gaps')
    p.add_argument('--width', type=int, choices=(64, 128), default=128)
    p.add_argument('--learning-rate', type=float, choices=(1e-4, 3e-4), default=1e-4)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--measured-steps', type=int, default=2048)
    p.add_argument('--torch-threads', type=int, default=1)
    p.add_argument('--materialize-buffer', action='store_true')
    a = p.parse_args()
    r = benchmark(a.normalizer_dir, a.output, a.algorithm, device=a.device, scenario=a.scenario,
                  width=a.width, learning_rate=a.learning_rate, seed=a.seed,
                  measured_steps=a.measured_steps, torch_threads=a.torch_threads,
                  materialize_buffer=a.materialize_buffer)
    print(json.dumps({k: r[k] for k in ('status', 'algorithm', 'device', 'measured_realized_transitions',
                      'measured_seconds', 'measured_updates', 'buffer_total_bytes',
                      'rss_peak_process_bytes', 'gpu_measured_memory')}, indent=2))


if __name__ == '__main__':
    main()
