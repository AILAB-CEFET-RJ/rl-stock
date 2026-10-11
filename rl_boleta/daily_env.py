"""Gymnasium adapter for full-coverage training sessions only.

Missing next observations are never turned into bootstrappable training states.
Interrupted evaluation remains the responsibility of DailySessionReplay.
"""
import gymnasium as gym
import numpy as np

from .observations import PARTITIONS
from .session_replay import DailySessionReplay, SessionResult


class DailyTrainingEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, sessions, encoder, window_features=20, **economic_options):
        super().__init__()
        self.sessions = tuple(sorted(sessions, key=lambda s: s.day))
        self.encoder, self.window_features = encoder, window_features
        self.economic_options = economic_options
        self.tickers = encoder.tickers
        first, last = PARTITIONS[encoder.normalizer.partition]
        if (not self.sessions or len({s.day for s in self.sessions}) != len(self.sessions)
                or any(not first <= s.day <= last for s in self.sessions)):
            raise ValueError('unique sessions within fitting partition required')
        if tuple(s.day.isoformat() for s in self.sessions) != encoder.normalizer.sessions:
            raise ValueError('normalizer must be fitted on exactly the training session set')
        controller = self._controller()
        if controller._template.initial_capital != encoder.initial_capital:
            raise ValueError('encoder and environment capital scales must match')
        for s in self.sessions:
            episode = controller.start(s.day, s.frames)
            if isinstance(episode, SessionResult) or episode.failures:
                raise ValueError('training accepts evaluable complete sessions only')
            # Check every feature row before learning, including unused stop tails.
            from .observations import market_row
            indexed = {f.at: f for f in s.frames}
            times = episode.plan.required_times
            for previous, at in zip(times, times[1:]):
                encoder.normalizer.transform(market_row(indexed[previous], indexed[at], s.trades, self.tickers))
        self.action_space = gym.spaces.Box(-1, 1, (len(self.tickers),), dtype=np.float32)
        size = window_features*41*len(self.tickers)+len(self.tickers)+4
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (size,), dtype=np.float32)
        self.episode = None
        self.sampling_order, self.completed = [], []

    def _controller(self):
        return DailySessionReplay(self.tickers, self.window_features, **self.economic_options)

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
                'flat': transition.flat, 'valuation_at': transition.valuation_at.isoformat()}
        if transition.terminated:
            result = self.episode.result()
            summary = dict(session_id=str(self.session.day), status=result.status,
                           steps=len(result.transitions), flat=result.flat,
                           financial_return=str(result.financial_return))
            self.completed.append(summary)
            info['episode_result'] = summary
        return self._encoded(terminal=transition.terminated), float(transition.reward), transition.terminated, False, info
