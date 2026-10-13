"""Masked Gym integration: gaps, true terminal states and frozen evaluation."""
import importlib.util
import unittest
from dataclasses import replace
from datetime import timedelta

AVAILABLE = all(importlib.util.find_spec(n) for n in ('gymnasium', 'stable_baselines3', 'numpy'))


@unittest.skipUnless(AVAILABLE, 'install requirements-training.txt')
class MaskedEnvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rl_boleta.masked_training import synthetic_sessions, TICKERS
        from rl_boleta.masked_observations import MaskedEncoder, fit_masked_normalizer
        cls.sessions = synthetic_sessions()[:1]
        cls.encoder = MaskedEncoder(fit_masked_normalizer(cls.sessions, TICKERS))

    def env(self, sessions=None, **options):
        from rl_boleta.masked_env import MaskedTrainingEnv
        return MaskedTrainingEnv(sessions or self.sessions, self.encoder, **options)

    def test_gaps_preserve_episode_and_match_direct_replay(self):
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        env = self.env(); obs, _ = env.reset(seed=0)
        self.assertEqual(obs.shape, (15502,))
        self.assertEqual(env.episode.plan.first_decision.minute, 52)
        seen = set(); total = 0.; count = 0
        while not env.episode.kernel.done:
            obs, r, done, truncated, info = env.step((.2,)*18 if count == 0 else (0,)*18)
            self.assertFalse(truncated)
            self.assertTrue(env.observation_space.contains(obs))
            seen.add(sum(info['availability'])); total += r; count += 1
        calls = []
        result = MaskedDailyReplay(env.tickers).run(env.session.day, env.session.frames,
            lambda o: calls.append(o) or ((.2,)*18 if len(calls) == 1 else (0,)*18))
        self.assertEqual(count, 367)
        self.assertEqual(seen, {0, 17, 18})
        self.assertAlmostEqual(total, float(result.marked_return), places=12)
        self.assertEqual(obs[-1], 0)
        self.assertTrue(done and info['flat'])
        self.assertTrue(info['action_ignored_for_liquidation'])
        with self.assertRaises(ValueError):env.step((0,)*18)

    def test_terminal_cash_utility_is_separate_from_marked_return_in_gym(self):
        from rl_boleta.economic_kernel import Level
        from rl_boleta.masked_training import TICKERS
        from rl_boleta.masked_observations import MaskedEncoder,fit_masked_normalizer
        from rl_boleta.masked_env import MaskedTrainingEnv
        s=self.sessions[0];frames=[]
        for f in s.frames:
            frames.append(replace(f,books=tuple(replace(b,bids=tuple(Level(q.price,1) for q in b.bids))
                for b in f.books)) if f.at>=s.frames[-54].at else f)
        s=replace(s,frames=tuple(frames))
        encoder=MaskedEncoder(fit_masked_normalizer((s,),TICKERS))
        env=MaskedTrainingEnv((s,),encoder,wind_down_points=54,reward_objective='terminal_cash_utility')
        env.reset(seed=0);total=0.;steps=0
        while not env.episode.kernel.done:
            _,r,done,truncated,info=env.step((.2,)*18 if steps==0 else (0,)*18)
            total+=r;steps+=1;self.assertFalse(truncated)
        result=env.episode.result()
        self.assertFalse(info['flat']);self.assertIsNone(result.realized_return)
        self.assertGreater(float(info['terminal_inventory_adjustment_usd']),0)
        self.assertAlmostEqual(total,float((result.portfolio.cash-100000)/100000),places=12)
        self.assertAlmostEqual(float(info['episode_result']['learning_return']),total,places=12)
        self.assertNotAlmostEqual(total,float(result.marked_return))

    def test_unavailable_action_mask_and_clipping(self):
        env = self.env(); env.reset(seed=0)
        while env.episode.kernel.frame.at < env.episode.plan.opening+timedelta(minutes=30):
            env.step((0,)*18)
        _, _, done, truncated, info = env.step((2,)*18)
        self.assertEqual(info['applied_actions'][0], 0)
        self.assertEqual(info['applied_actions'][1:], (1.,)*17)
        self.assertTrue(info['action_clipped_at_env'])
        self.assertFalse(done or truncated)

    def test_exit_data_absence_rejected_and_unexpected_absence_aborts(self):
        from rl_boleta.missing_data_replay import PartialFrame
        s = self.sessions[0]
        with self.assertRaises(ValueError):self.env((replace(s, frames=s.frames[:-1]),))
        env = self.env(); env.reset(seed=0)
        exit_at = env.episode.plan.liquidation
        env.episode._indexed[exit_at] = PartialFrame(exit_at, str(s.day))
        while env.episode.kernel.frame.at < exit_at-timedelta(minutes=1):env.step((0,)*18)
        with self.assertRaises(RuntimeError):env.step((0,)*18)
        with self.assertRaises(ValueError):env.episode.observation(allow_terminal=True)

    def test_early_capital_stop_is_terminal_with_zero_horizon(self):
        from rl_boleta.economic_kernel import Level
        from rl_boleta.observations import Trade
        s = self.sessions[0]; frames=[]; trades=dict(s.trades)
        for frame in s.frames:
            q=int((frame.at-s.frames[0].at).total_seconds()/60)+1
            if q >= 24:
                books=tuple(replace(b,
                    bids=tuple(Level(l.price/2,l.size) for l in b.bids),
                    asks=tuple(Level(l.price/2,l.size) for l in b.asks)) for b in frame.books)
                frame=replace(frame,books=books)
                for b in books:trades[frame.at,b.ticker]=tuple(Trade(b.midpoint,10,frame.at) for _ in range(10))
            frames.append(frame)
        env=self.env((replace(s,frames=tuple(frames),trades=trades),));env.reset(seed=0)
        env.step((1,)*18)
        obs, _, done, truncated, info=env.step((0,)*18)
        self.assertTrue(done);self.assertFalse(truncated)
        self.assertEqual(info['reason'],'capital_stop')
        self.assertEqual(obs[-1],0)
        self.assertTrue(info['flat'])

    def test_liquidation_depth_failure_is_terminal_with_residuals(self):
        from rl_boleta.economic_kernel import Level
        s=self.sessions[0]; final=s.frames[-1]
        books=tuple(replace(b,bids=tuple(Level(l.price,1) for l in b.bids)) for b in final.books)
        env=self.env((replace(s,frames=s.frames[:-1]+(replace(final,books=books),)),))
        env.reset(seed=0);env.step((1,)*18)
        while not env.episode.kernel.done:obs,_,done,truncated,info=env.step((0,)*18)
        self.assertTrue(done);self.assertFalse(truncated)
        self.assertEqual(info['reason'],'liquidation_failure')
        self.assertFalse(info['flat']);self.assertEqual(obs[-1],0)
        self.assertEqual(info['episode_result']['realized_return'],'None')
        self.assertTrue(any(obs[-21:-3] > 0))

    def test_historical_invalid_features_and_capital_are_rejected(self):
        s=self.sessions[0]
        with self.assertRaises(ValueError):self.env((replace(s,synthetic=False),))
        with self.assertRaises(ValueError):self.env(initial_capital=1000)
        trades=dict(s.trades);del trades[s.frames[-1].at,self.encoder.tickers[0]]
        with self.assertRaises(ValueError):self.env((replace(s,trades=trades),))
        env=self.env();env.reset(seed=0)
        with self.assertRaises(ValueError):env.step((float('nan'),)*18)

    def test_frozen_evaluation_keeps_missing_dates_and_missing_exit(self):
        import numpy as np
        from rl_boleta.masked_training import evaluate_period
        s=self.sessions[0];normalizer=self.encoder.normalizer
        class Hold:
            def predict(self, inputs, deterministic):
                assert deterministic
                return np.zeros(18),None
        results=evaluate_period(Hold(), {s.day:replace(s,frames=s.frames[:-1])},
            self.encoder,s.day,s.day+timedelta(days=1))
        self.assertEqual([r.status for r in results],['exit_data_missing','not_startable'])
        self.assertTrue(all(r.marked_return is None for r in results))
        self.assertEqual(normalizer,self.encoder.normalizer)

    def test_seeded_resets_do_not_refit_statistics(self):
        a,b=self.env(),self.env();normalizer=self.encoder.normalizer
        obs_a,_=a.reset(seed=7);obs_b,_=b.reset(seed=7)
        self.assertEqual(a.sampling_order,b.sampling_order)
        self.assertEqual(obs_a.tolist(),obs_b.tolist())
        self.assertEqual(normalizer,self.encoder.normalizer)
        with self.assertRaises(ValueError):a.reset(options={'day':'2025-03-03'})

    def test_frozen_short_session_ends_at_calendar_exit(self):
        from datetime import date
        import numpy as np
        from rl_boleta.masked_training import evaluate_period
        from rl_boleta.session_replay import session_plan
        s=self.sessions[0];day=date(2025,7,3)
        delta=session_plan(day).opening-session_plan(s.day).opening
        frames=tuple(replace(f,at=f.at+delta,session_id=str(day),
            books=tuple(replace(b,available_at=b.available_at+delta,
                snapshot_id=f'july-{b.snapshot_id}') for b in f.books)) for f in s.frames[:209])
        trades={(at+delta,t):tuple(replace(trade,at=trade.at+delta) for trade in ts)
            for (at,t),ts in s.trades.items() if at<=s.frames[208].at}
        class Hold:
            def predict(self,inputs,deterministic):return np.zeros(18),None
        result=evaluate_period(Hold(),{day:replace(s,day=day,frames=frames,trades=trades)},
            self.encoder,day,day)[0]
        self.assertEqual(result.status,'scheduled_end')
        self.assertEqual(len(result.transitions),187)
        self.assertEqual(result.transitions[-1].at,session_plan(day).liquidation)
