"""Verify actual algorithm classes, optimizers, targets and exploration."""
import importlib.util
import unittest

AVAILABLE = all(importlib.util.find_spec(n) for n in ('gymnasium', 'stable_baselines3', 'numpy'))


@unittest.skipUnless(AVAILABLE, 'install requirements-training.txt')
class AlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from rl_boleta.daily_training import synthetic_sessions
        from rl_boleta.observations import Encoder, fit_normalizer
        torch.set_num_threads(1)
        cls.sessions = synthetic_sessions()
        cls.encoder = Encoder(fit_normalizer(cls.sessions, ('SYNTA', 'SYNTB')))

    def model(self, algorithm, smoke=False):
        from rl_boleta.algorithm_builders import build_agent
        from rl_boleta.daily_env import DailyTrainingEnv
        return build_agent(algorithm, DailyTrainingEnv(self.sessions, self.encoder), 0, smoke=smoke)

    def test_a2c_is_adam_with_reference_parameters(self):
        import torch
        model = self.model('A2C')
        self.assertEqual(type(model).__name__, 'A2C')
        self.assertIsInstance(model.policy.optimizer, torch.optim.Adam)
        self.assertEqual((model.n_steps, model.gae_lambda, model.gamma), (5, 1, 1))
        self.assertFalse(model.normalize_advantage)
        self.assertEqual((model.ent_coef, model.vf_coef, model.max_grad_norm), (0, .5, .5))
        self.assertTrue(torch.all(model.policy.log_std == 0))

    def test_offpolicy_reference_budgets_and_update_frequency(self):
        for name in ('SAC', 'DDPG'):
            with self.subTest(name=name):
                model = self.model(name)
                self.assertEqual(type(model).__name__, name)
                self.assertEqual((model.buffer_size, model.batch_size, model.learning_starts), (100000, 256, 10000))
                self.assertEqual((model.gradient_steps, model.train_freq.frequency, model.tau, model.gamma), (1, 1, .005, 1))
                self.assertEqual(model.train_freq.unit.value, 'step')
                self.assertFalse(model.optimize_memory_usage)

    def test_sac_entropy_and_initial_conditional_log_std(self):
        import torch
        model = self.model('SAC', smoke=True)
        self.assertEqual(model.critic.n_critics, 2)
        self.assertEqual(model.target_entropy, -2)
        self.assertEqual(float(model.log_ent_coef.exp()), 1)
        self.assertEqual(model.target_update_interval, 1)
        _, log_std, _ = model.actor.get_action_dist_params(torch.randn(3, 1646))
        self.assertTrue(torch.all(log_std == 0))
        self.assertEqual(model.ent_coef_optimizer.param_groups[0]['eps'], 1e-5)

    def test_target_networks_match_online_and_do_not_share_storage(self):
        import torch
        for name in ('SAC', 'DDPG'):
            model = self.model(name, smoke=True)
            pairs = [(model.critic, model.critic_target)]
            if name == 'DDPG':
                pairs.append((model.actor, model.actor_target))
            for source, target in pairs:
                for a, b in zip(source.parameters(), target.parameters()):
                    self.assertTrue(torch.equal(a, b))
                    self.assertNotEqual(a.data_ptr(), b.data_ptr())

    def test_all_effective_optimizers_use_protocol_adam_settings(self):
        import torch
        for name in ('PPO', 'A2C', 'SAC', 'DDPG'):
            model = self.model(name, smoke=True)
            optimizers = [model.policy.optimizer] if name in ('PPO', 'A2C') else [model.actor.optimizer, model.critic.optimizer]
            if name == 'SAC':
                optimizers.append(model.ent_coef_optimizer)
            for optimizer in optimizers:
                self.assertIsInstance(optimizer, torch.optim.Adam)
                group = optimizer.param_groups[0]
                self.assertEqual((group['betas'], group['eps'], group['lr']), ((.9, .999), 1e-5, 1e-4))

    def test_ddpg_one_critic_and_independent_gaussian_noise(self):
        import numpy as np
        model = self.model('DDPG', smoke=True)
        self.assertEqual(model.critic.n_critics, 1)
        self.assertEqual((model.policy_delay, model.target_noise_clip), (1, 0))
        np.random.seed(123)
        samples = np.array([model.action_noise() for _ in range(5000)])
        self.assertTrue(np.all(np.abs(samples.mean(axis=0)) < .005))
        self.assertTrue(np.all(np.abs(samples.std(axis=0)-.1) < .005))
        self.assertLess(abs(np.corrcoef(samples.T)[0, 1]), .05)

    def test_all_deterministic_outputs_bounded(self):
        import numpy as np
        for name in ('PPO', 'A2C', 'SAC', 'DDPG'):
            model = self.model(name, smoke=True)
            inputs = np.zeros(1646, dtype=np.float32)
            action, _ = model.predict(inputs, deterministic=True)
            self.assertEqual(action.shape, (2,))
            self.assertTrue(np.all(np.isfinite(action)) and np.all(np.abs(action) <= 1))

    def test_unknown_algorithm_and_unfrozen_configuration_rejected(self):
        from rl_boleta.algorithm_builders import build_agent
        for name, kwargs in [('TD3', {}), ('PPO', {'width': 32}), ('SAC', {'learning_rate': .1})]:
            with self.assertRaises(ValueError):
                build_agent(name, None, 0, **kwargs)
