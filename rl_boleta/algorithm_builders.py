"""Explicit SB3 2.3.2 configurations for the four reference algorithms."""
ALGORITHMS = ('PPO', 'A2C', 'SAC', 'DDPG')


def resolve_device(device):
    """Explicit backend only; never fall back silently when CUDA was requested."""
    import torch
    if device not in ('cpu', 'cuda'):
        raise ValueError('device must be cpu or cuda')
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    return device


def build_agent(algorithm, env, seed, width=64, learning_rate=1e-4, smoke=False, *, device='cpu'):
    import numpy as np
    import torch
    from stable_baselines3 import PPO, A2C, SAC, DDPG
    from stable_baselines3.common.noise import NormalActionNoise
    from stable_baselines3.common.policies import ActorCriticPolicy
    from stable_baselines3.sac.policies import SACPolicy
    from stable_baselines3.td3.policies import TD3Policy

    if algorithm not in ALGORITHMS:
        raise ValueError('unsupported algorithm')
    if width not in (64, 128) or learning_rate not in (1e-4, 3e-4):
        raise ValueError('configuration outside frozen tuning grid')
    device = resolve_device(device)

    def initialize(policy):
        for module in policy.modules():
            if isinstance(module, torch.nn.Linear):
                torch.nn.init.xavier_uniform_(module.weight, gain=1)
                torch.nn.init.zeros_(module.bias)

    class XavierActorCritic(ActorCriticPolicy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            initialize(self)
            torch.nn.init.zeros_(self.log_std)

    class XavierSAC(SACPolicy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            initialize(self)
            # A state-dependent head cannot output constant zero with Xavier
            # weights. This declared exception gives initial std=1 everywhere.
            torch.nn.init.zeros_(self.actor.log_std.weight)
            torch.nn.init.zeros_(self.actor.log_std.bias)
            self.critic_target.load_state_dict(self.critic.state_dict())

    class XavierDDPG(TD3Policy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            initialize(self)
            self.actor_target.load_state_dict(self.actor.state_dict())
            self.critic_target.load_state_dict(self.critic.state_dict())

    optimizer = dict(optimizer_class=torch.optim.Adam,
                     optimizer_kwargs=dict(betas=(.9, .999), eps=1e-5))
    common = dict(env=env, seed=seed, device=device, learning_rate=learning_rate,
                  gamma=1, verbose=0)
    if algorithm in ('PPO', 'A2C'):
        policy = dict(net_arch=dict(pi=[width, width], vf=[width, width]),
                      activation_fn=torch.nn.ReLU, ortho_init=False,
                      share_features_extractor=False, log_std_init=0, **optimizer)
        settings = dict(policy=XavierActorCritic, policy_kwargs=policy, gae_lambda=.95,
                        ent_coef=0, vf_coef=.5, max_grad_norm=.5, use_sde=False)
        if algorithm == 'PPO':
            return PPO(**common, **settings, n_steps=32 if smoke else 2048,
                       batch_size=16 if smoke else 64, n_epochs=1 if smoke else 10,
                       clip_range=.2, clip_range_vf=None, normalize_advantage=True, target_kl=None)
        settings['gae_lambda'] = 1
        return A2C(**common, **settings, n_steps=5, use_rms_prop=False,
                   normalize_advantage=False)

    settings = dict(buffer_size=1024 if smoke else 100000,
                    batch_size=32 if smoke else 256, learning_starts=32 if smoke else 10000,
                    tau=.005, train_freq=(1, 'step'), gradient_steps=1,
                    optimize_memory_usage=False)
    policy = dict(net_arch=dict(pi=[width, width], qf=[width, width]),
                  activation_fn=torch.nn.ReLU, share_features_extractor=False,
                  n_critics=2 if algorithm == 'SAC' else 1, **optimizer)
    if algorithm == 'SAC':
        model = SAC(XavierSAC, **common, **settings, policy_kwargs=policy,
                    ent_coef='auto_1.0', target_entropy=-env.action_space.shape[0],
                    target_update_interval=1, use_sde=False, use_sde_at_warmup=False,
                    action_noise=None)
        # SB3 builds this optimizer independently of policy_kwargs.
        model.ent_coef_optimizer = torch.optim.Adam(
            [model.log_ent_coef], lr=learning_rate, betas=(.9, .999), eps=1e-5)
        return model
    noise = NormalActionNoise(np.zeros(env.action_space.shape[0]),
                              .1*np.ones(env.action_space.shape[0]))
    return DDPG(XavierDDPG, **common, **settings, policy_kwargs=policy, action_noise=noise)


def describe_agent(model):
    """JSON-safe snapshot of effective settings, including optimizer groups."""
    def adam(optimizer):
        return [dict(lr=g['lr'], betas=list(g['betas']), eps=g['eps'],
                     weight_decay=g['weight_decay']) for g in optimizer.param_groups]
    name = type(model).__name__
    result = dict(algorithm=name, device=str(model.device), policy_class=type(model.policy).__name__, gamma=model.gamma,
                  learning_rate=model.learning_rate, policy_kwargs=repr(model.policy_kwargs),
                  initialization='Xavier uniform gain=1, zero biases; SAC log_std head zero',
                  observation_normalization='frozen external', reward_normalization=False)
    if name in ('PPO', 'A2C'):
        result.update(rollout_steps=model.n_steps, gae_lambda=model.gae_lambda,
                      entropy_weight=model.ent_coef, value_loss_weight=model.vf_coef,
                      max_grad_norm=model.max_grad_norm, normalize_advantage=model.normalize_advantage,
                      optimizer=adam(model.policy.optimizer))
        if name == 'PPO':
            result.update(batch_size=model.batch_size, epochs=model.n_epochs,
                          clip_range=model.clip_range(1), clip_range_vf=None, target_kl=model.target_kl)
    else:
        result.update(buffer_size=model.buffer_size, batch_size=model.batch_size,
                      learning_starts=model.learning_starts, tau=model.tau,
                      train_frequency=[model.train_freq.frequency, model.train_freq.unit.value],
                      gradient_steps=model.gradient_steps, optimize_memory_usage=model.optimize_memory_usage,
                      q_critics=model.critic.n_critics,
                      actor_optimizer=adam(model.actor.optimizer), critic_optimizer=adam(model.critic.optimizer),
                      action_noise='Gaussian std=0.1; clip sum to bounds' if name == 'DDPG' else None)
        if name == 'SAC':
            result.update(entropy_initial_coefficient=1, target_entropy=model.target_entropy,
                          target_update_interval=model.target_update_interval,
                          entropy_optimizer=adam(model.ent_coef_optimizer))
        else:
            result.update(policy_delay=model.policy_delay, target_policy_noise=model.target_policy_noise)
    return result
