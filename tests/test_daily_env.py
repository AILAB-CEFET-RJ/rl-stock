"""Optional Gym/SB3 integration tests, synthetic sessions only."""
import importlib.util
import unittest

AVAILABLE = all(importlib.util.find_spec(n) for n in ('gymnasium', 'stable_baselines3', 'numpy'))


@unittest.skipUnless(AVAILABLE, 'install requirements-training.txt for Gym/SB3 integration')
class DailyEnvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rl_boleta.daily_training import synthetic_sessions
        from rl_boleta.observations import Encoder, fit_normalizer
        cls.sessions = synthetic_sessions()
        cls.encoder = Encoder(fit_normalizer(cls.sessions, ('SYNTA', 'SYNTB')))

    def env(self, **options):
        from rl_boleta.daily_env import DailyTrainingEnv
        return DailyTrainingEnv(self.sessions, self.encoder, **options)

    def test_seeded_uniform_sampling_and_no_normalizer_update(self):
        a, b = self.env(), self.env()
        means = self.encoder.normalizer.means
        a.reset(seed=123); b.reset(seed=123)
        for _ in range(20):
            a.reset(); b.reset()
        self.assertEqual(a.sampling_order, b.sampling_order)
        self.assertEqual(set(a.sampling_order), {str(s.day) for s in self.sessions})
        self.assertEqual(self.encoder.normalizer.means, means)

    def test_step_replay_agree_and_terminal_cash_is_encoded(self):
        from rl_boleta.session_replay import DailySessionReplay
        env = self.env()
        obs, _ = env.reset(seed=0)
        self.assertTrue(env.observation_space.contains(obs))
        done = False; reward = 0; index = 0
        while not done:
            obs, r, done, truncated, info = env.step((1, 0) if index == 0 else (0, 0))
            self.assertFalse(truncated)
            self.assertTrue(env.observation_space.contains(obs))
            reward += r; index += 1
        calls = []
        expected = DailySessionReplay(env.tickers).run(env.session.day, env.session.frames,
            lambda o: calls.append(o) or ((1, 0) if len(calls) == 1 else (0, 0)))
        self.assertAlmostEqual(reward, float(expected.financial_return), places=12)
        self.assertEqual(index, 368)
        self.assertTrue(info['action_ignored_for_liquidation'])
        self.assertEqual(obs[-5:-3].tolist(), [0., 0.])
        self.assertEqual(obs[-1], 0)
        self.assertAlmostEqual(float(obs[-6]), float(expected.portfolio.cash/100000), places=6)
        with self.assertRaises(ValueError):
            env.step((0, 0))

    def test_invalid_action_and_capital_mismatch_fail(self):
        env = self.env(); env.reset(seed=0)
        with self.assertRaises(ValueError):
            env.step((float('nan'), 0))
        with self.assertRaises(ValueError):
            self.env(initial_capital=1000)

    def test_training_excludes_missing_next_observation(self):
        from dataclasses import replace
        from rl_boleta.daily_env import DailyTrainingEnv
        sessions = (replace(self.sessions[0], frames=self.sessions[0].frames[:-1]),)+self.sessions[1:]
        with self.assertRaises(ValueError):
            DailyTrainingEnv(sessions, self.encoder)

    def test_actual_ppo_settings_and_initialization(self):
        import torch
        from rl_boleta.daily_training import build_ppo
        model = build_ppo(self.env(), seed=0)
        self.assertEqual((model.n_steps, model.batch_size, model.n_epochs), (2048, 64, 10))
        self.assertEqual((model.gamma, model.gae_lambda, model.ent_coef), (1, .95, 0))
        self.assertEqual(model.policy.optimizer.defaults['betas'], (.9, .999))
        self.assertEqual(model.policy.optimizer.defaults['eps'], 1e-5)
        self.assertTrue(torch.all(model.policy.log_std == 0))
        self.assertIsNot(model.policy.mlp_extractor.policy_net, model.policy.mlp_extractor.value_net)
        for module in model.policy.modules():
            if isinstance(module, torch.nn.Linear):
                self.assertTrue(torch.all(module.bias == 0))

    def test_frozen_evaluation_retains_missing_scheduled_dates(self):
        from datetime import date
        import numpy as np
        from rl_boleta.daily_training import evaluate_period
        class HoldModel:
            def predict(self, inputs, deterministic):
                self.deterministic = deterministic
                return np.zeros(2), None
        model = HoldModel()
        results = evaluate_period(model, {self.sessions[0].day: self.sessions[0]},
                                  self.encoder, date(2025, 3, 3), date(2025, 3, 4))
        self.assertEqual(len(results), 2)
        self.assertTrue(model.deterministic)
        self.assertEqual(results[0].financial_return, 0)
        self.assertEqual(results[1].status, 'not_startable')
        self.assertIsNone(results[1].financial_return)
