import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import gymnasium as gym
import numpy as np

from rl_boleta.compute_benchmark import benchmark


class ToyTrainEnv(gym.Env):
    """Cheap fixture; no historical or financial performance claims."""
    def __init__(self, normalizers, scenario):
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (4,), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1, 1, (2,), dtype=np.float32)
        self.economic_options = dict(account_regime='cash_settled', wind_down_points=54,
                                     reward_objective='terminal_cash_utility')
        self.input_hashes = {}; self.completed = []; self.sampling_order = []
        self.verified = False
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed); self.step_number = 0
        self.sampling_order.append('2025-03-03')
        return np.array([1, 2, 3, 1], dtype=np.float32), {}
    def step(self, action):
        self.step_number += 1; done = self.step_number == 8
        observation = np.array([1, 2, 3, 0 if done else 1], dtype=np.float32)
        if done:self.completed.append(dict(session_id='2025-03-03', status='scheduled_end', flat=True))
        return observation, float(action[0]), done, False, {}
    def verify_inputs(self):self.verified = True


class ComputeBenchmarkTests(unittest.TestCase):
    def run_fixture(self, root, algorithm):
        with patch('rl_boleta.historical_env.HistoricalTrainingEnv', ToyTrainEnv), redirect_stdout(io.StringIO()):
            return benchmark('fixture', root/'benchmark', algorithm, width=64,
                             measured_steps=2048, materialize_buffer=True)

    def test_ppo_full_settings_measure_after_warmup_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.run_fixture(Path(temp), 'PPO')
            self.assertEqual(report['status'], 'compute_benchmark_completed')
            self.assertEqual(report['warmup_realized_transitions'], 2048)
            self.assertEqual(report['measured_realized_transitions'], 2048)
            self.assertEqual(report['measured_updates'], 10)
            self.assertEqual(report['effective_settings']['epochs'], 10)
            self.assertEqual(report['effective_settings']['batch_size'], 64)
            self.assertTrue(report['checkpoint_prediction_identical'])
            self.assertGreater(report['rss_peak_process_bytes'], 0)
            self.assertFalse(report['validation_prices_accessed'] or report['test_prices_accessed'])
            self.assertFalse(report['full_budget_selection_authorized'])

    def test_sac_measured_phase_really_updates_full_buffer_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.run_fixture(Path(temp), 'SAC')
            self.assertEqual(report['warmup_realized_transitions'], 10000)
            self.assertEqual(report['warmup_updates'], 0)
            self.assertEqual(report['measured_updates'], 2048)
            self.assertEqual(report['effective_settings']['buffer_size'], 100000)
            self.assertEqual(report['effective_settings']['batch_size'], 256)
            self.assertEqual(report['buffer_total_bytes'], 100000*(2*4+2+3)*4)
            self.assertTrue(report['actor_changed'])
            self.assertTrue(report['materialize_buffer'])

    def test_memory_shortage_is_reported_before_model_allocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch('rl_boleta.historical_env.HistoricalTrainingEnv', ToyTrainEnv), \
                 patch('rl_boleta.compute_benchmark.available_ram_bytes', return_value=1), \
                 patch('rl_boleta.compute_benchmark.build_agent') as builder:
                with self.assertRaisesRegex(RuntimeError, 'RAM'):
                    benchmark('fixture', root/'out', 'SAC')
                builder.assert_not_called()
            report = json.loads((root/'out/report.json').read_text())
            self.assertEqual(report['status'], 'compute_benchmark_failed')

    def test_other_algorithms_measure_updates_without_smoke_overrides(self):
        for algorithm in ('A2C', 'DDPG'):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as temp:
                report = self.run_fixture(Path(temp), algorithm)
                self.assertEqual(report['status'], 'compute_benchmark_completed')
                self.assertGreater(report['measured_updates'], 0)
                self.assertTrue(report['checkpoint_prediction_identical'])
                if algorithm == 'DDPG':
                    self.assertEqual(report['warmup_updates'], 0)
                    self.assertEqual(report['effective_settings']['batch_size'], 256)
                else:
                    self.assertEqual(report['measured_realized_transitions'], 2050)
                    self.assertEqual(report['effective_settings']['rollout_steps'], 5)

    def test_invalid_backend_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'out'
            with self.assertRaises(ValueError):benchmark('fixture', out, 'PPO', device='auto')
            self.assertFalse(out.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out = root/'out'; out.mkdir()
            (out/'sentinel').write_text('preserved')
            with self.assertRaises(FileExistsError):benchmark('fixture', out, 'PPO')
            self.assertEqual((out/'sentinel').read_text(), 'preserved')


if __name__ == '__main__':unittest.main()
