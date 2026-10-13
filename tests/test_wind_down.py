import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from rl_boleta.economic_kernel import Level, Portfolio
from rl_boleta.missing_data_replay import MaskedDailyReplay, MaskedReplayKernel
from test_missing_data_replay import config, frame, book, day_frames
from rl_boleta.session_replay import session_plan


class WindDownTests(unittest.TestCase):
    def test_partial_sales_multiple_frames_fees_and_flat_waits_until_close(self):
        cfg=replace(config(horizon=5),fee_rate=D('.001'))
        k=MaskedReplayKernel(cfg,frame(1),wind_down_points=4)
        k.submit((1,));k.advance(frame(2))
        self.assertEqual(k.portfolio.holdings,(9,))
        self.assertTrue(k.wind_down);self.assertFalse(k.discretionary)
        with self.assertRaises(ValueError):k.submit((1,))
        for q in (3,4):
            t=k.advance(frame(q,(book(minute=q,size=1),)))
            self.assertEqual(t.executions[0].kind,'wind_down')
            self.assertEqual(t.applied_actions,(0,))
            self.assertFalse(t.terminated)
        self.assertEqual(k.portfolio.holdings,(0,))
        t=k.advance(frame(5));self.assertTrue(t.flat);self.assertFalse(t.terminated)
        t=k.advance(frame(6));self.assertTrue(t.flat);self.assertTrue(t.terminated)
        self.assertEqual(t.reason,'scheduled_end')
        self.assertEqual(sum(t.reward for t in k.history),(k.portfolio.cash-cfg.initial_capital)/cfg.initial_capital)
        self.assertGreater(sum(e.fees for t in k.history for e in t.executions),0)

    def test_capture_reuse_gap_then_resume_does_not_create_capacity(self):
        k=MaskedReplayKernel(config(horizon=5),frame(1),wind_down_points=4)
        k.submit((1,));k.advance(frame(2))
        b=book(minute=3,size=1)
        k.advance(frame(3,(b,)));self.assertEqual(k.portfolio.holdings,(4,))
        k.advance(frame(4,(b,)));self.assertEqual(k.portfolio.holdings,(4,))
        t=k.advance(frame(5,()));self.assertEqual(k.portfolio.holdings,(4,))
        self.assertEqual(t.availability,(False,));self.assertEqual(t.executions[0].fills,())
        t=k.advance(frame(6));self.assertTrue(t.flat)

    def test_terminal_residual_and_missing_exit_remain_distinct(self):
        for missing in (False,True):
            k=MaskedReplayKernel(config(horizon=3),frame(1),wind_down_points=2)
            k.submit((1,));k.advance(frame(2))
            k.advance(frame(3,()))
            b=replace(book(minute=4),bids=tuple(Level(q.price,'.1') for q in book(minute=4).bids))
            t=k.advance(frame(4,() if missing else (b,)))
            self.assertEqual(k.portfolio.holdings,(9,))
            self.assertEqual(t.truncated,missing);self.assertEqual(t.terminated,not missing)
            self.assertEqual(t.reason,'exit_data_missing' if missing else 'liquidation_failure')

    def test_normal_and_shortened_session_frontiers_and_future_invariance(self):
        for day in (date(2025,3,3),date(2025,7,3)):
            frames=day_frames(day=day);e=MaskedDailyReplay(('A',),wind_down_points=54).start(day,frames)
            boundaries=[]
            while not e.kernel.done:
                if e.discretionary:boundaries.append(e.kernel.frame.at)
                e.advance((0,) if e.discretionary else None)
            self.assertEqual(len([t for t in e.kernel.history if any(x.kind in ('wind_down','liquidation') for x in t.executions)]),54)
            self.assertEqual((e.plan.liquidation-boundaries[-1]).total_seconds(),55*60)
            self.assertEqual(e.kernel.history[-54].at,session_plan(day).closing-__import__('datetime').timedelta(minutes=54))
            changed=list(frames);changed[-1]=replace(changed[-1],books=())
            x=MaskedDailyReplay(('A',),wind_down_points=54).start(day,changed)
            y=MaskedDailyReplay(('A',),wind_down_points=54).start(day,frames)
            while x.discretionary:
                self.assertEqual(x.observation(),y.observation())
                x.advance((0,));y.advance((0,))
            self.assertFalse(y.discretionary)
            self.assertEqual(x.kernel.wind_down,y.kernel.wind_down)

    def test_late_causal_entry_is_retained_in_cash_without_policy_calls(self):
        frames=day_frames(missing={q:('A',) for q in range(1,350)})
        def forbidden(obs):raise AssertionError('late entry must not call policy')
        result=MaskedDailyReplay(('A',),wind_down_points=54).run(date(2025,3,3),frames,forbidden)
        self.assertTrue(result.startable);self.assertTrue(result.coverage_candidate)
        self.assertEqual(result.portfolio,Portfolio(100000,(0,)))
        self.assertEqual(result.realized_return,0)
        self.assertEqual(result.status,'scheduled_end')

    def test_stop_retains_precedence_and_legacy_default_is_single_attempt(self):
        k=MaskedReplayKernel(config(horizon=5),frame(1),wind_down_points=4)
        k.submit((1,));k.advance(frame(2));k.stop_latched=True
        t=k.advance(frame(3));self.assertEqual(t.reason,'capital_stop');self.assertTrue(t.terminated)
        e=MaskedDailyReplay(('A',)).start(date(2025,3,3),day_frames())
        while not e.kernel.done:e.advance((0,) if e.discretionary else None)
        self.assertEqual(sum(x.kind=='liquidation' for t in e.kernel.history for x in t.executions),1)
        self.assertFalse(any(x.kind=='wind_down' for t in e.kernel.history for x in t.executions))
        for invalid in (0,-1,True,1.5):
            with self.assertRaises(ValueError):MaskedDailyReplay(('A',),wind_down_points=invalid)


if __name__=='__main__':unittest.main()
