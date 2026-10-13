"""Gymnasium adapter for synthetic masked sessions with a common covered exit.

Interior gaps are encoded with masks; missing exit books abort the training fit.
Interrupted evaluation remains the responsibility of MaskedDailyReplay.
"""
import gymnasium as gym
import numpy as np
from decimal import Decimal

from .observations import PARTITIONS
from .missing_data_replay import MaskedDailyReplay, MaskedSessionResult


class MaskedTrainingEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, sessions, encoder, window_features=20, **economic_options):
        super().__init__()
        self.sessions = tuple(sorted(sessions, key=lambda s: s.day))
        self.encoder, self.window_features = encoder, window_features
        self.economic_options = economic_options
        self.tickers = encoder.tickers
        if encoder.normalizer.synthetic_only is not True:
            raise ValueError('historical training adapter is not enabled in this stage')
        first, last = PARTITIONS[encoder.normalizer.partition]
        if (not self.sessions or len({s.day for s in self.sessions}) != len(self.sessions)
                or any(not first <= s.day <= last for s in self.sessions)):
            raise ValueError('unique sessions within fitting partition required')
        if tuple(s.day.isoformat() for s in self.sessions) != encoder.normalizer.sessions:
            raise ValueError('normalizer must be fitted on exactly the training session set')
        controller = self._controller()
        if encoder.include_account_context!=(controller.account_regime!='legacy_reinvest'):
            raise ValueError('encoder account context must match account regime')
        if controller._template.initial_capital != encoder.initial_capital:
            raise ValueError('encoder and environment capital scales must match')
        for s in self.sessions:
            episode = controller.start(s.day, s.frames)
            if isinstance(episode, MaskedSessionResult) or episode._missing_exit:
                raise ValueError('training requires causal entry and common covered exit')
            if s.synthetic is not True:
                raise ValueError('historical training remains gated; synthetic sessions required')
            if window_features != 20:
                raise ValueError('masked encoder requires the frozen 20-row window')
            # Validate the complete feature tail even if a policy stops early.
            from .masked_observations import FeatureCursor
            obs = episode.observation()
            cursor = FeatureCursor(self.tickers, obs.lag_reference, obs.reference_state)
            for frame in obs.market_history:
                encoder.normalizer.transform(cursor.consume(frame, s.trades))
            while not episode.kernel.done:
                episode.advance((0,)*len(self.tickers) if episode.discretionary else None)
                encoder.normalizer.transform(cursor.consume(episode.kernel.frame, s.trades))
        self.action_space = gym.spaces.Box(-1, 1, (len(self.tickers),), dtype=np.float32)
        size = window_features*43*len(self.tickers)+len(self.tickers)+4+3*encoder.include_account_context
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (size,), dtype=np.float32)
        self.episode = None
        self.sampling_order, self.completed = [], []

    def _controller(self):
        return MaskedDailyReplay(self.tickers, self.window_features, **self.economic_options)

    def _encoded(self, terminal=False):
        return np.asarray(self.encoder.flatten(self.episode.observation(allow_terminal=terminal),
                                               self.session.trades), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options:
            raise ValueError('training reset samples dates uniformly; no date override')
        self.session = self.sessions[int(self.np_random.integers(len(self.sessions)))]
        self.sampling_order.append(str(self.session.day))
        self.episode = self._controller().start(self.session.day, self.session.frames)
        return self._encoded(), {'session_id': str(self.session.day)}

    def step(self, action):
        if self.episode is None or self.episode.kernel.done:
            raise ValueError('reset required before step')
        action = np.asarray(action, dtype=np.float64)
        if action.shape != (len(self.tickers),) or not np.all(np.isfinite(action)):
            raise ValueError('finite action per asset required')
        clipped = np.clip(action, -1, 1)
        discretionary = self.episode.discretionary
        transition = self.episode.advance(tuple(float(a) for a in clipped) if discretionary else None)
        if transition.truncated:
            raise RuntimeError('unexpected training data interruption; transition excluded, abort fit')
        info = {'session_id': str(self.session.day), 'reason': transition.reason,
                'action_ignored_for_liquidation': not discretionary,
                'action_clipped_at_env': bool(np.any(action != clipped)),
                'availability': transition.availability,
                'applied_actions': transition.applied_actions,
                'reward_objective': self.episode.kernel.reward_objective,
                'account_regime': self.episode.kernel.account_regime,
                'buying_power_usd': str(self.episode.kernel.buying_power),
                'pending_sale_proceeds_usd': str(self.episode.kernel.pending_sale_proceeds),
                'terminal_inventory_adjustment_usd': str(transition.terminal_inventory_adjustment_usd),
                'marked_wealth_change_usd': str(transition.after_wealth-transition.before_wealth),
                'flat': transition.flat, 'valuation_at': transition.at.isoformat()}
        if transition.terminated:
            result = self.episode.result()
            summary = dict(session_id=str(self.session.day), status=result.status,
                           steps=len(result.transitions), flat=transition.flat,
                           marked_return=str(result.marked_return),
                           realized_return=str(result.realized_return))
            summary['learning_return']=str(sum((t.reward for t in result.transitions),Decimal(0)))
            self.completed.append(summary)
            info['episode_result'] = summary
        return self._encoded(terminal=transition.terminated), float(transition.reward), transition.terminated, False, info
