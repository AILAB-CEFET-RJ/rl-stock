import unittest
from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal as D

from rl_boleta.economic_kernel import Book,Config,Frame,Level,Portfolio,ReplayKernel
from rl_boleta.missing_data_replay import (MaskedDailyReplay,MaskedReplayKernel,
    MaskedSessionResult,PartialExecutionEngine,PartialFrame)
from rl_boleta.session_replay import session_plan

DAY=date(2025,3,3)
OPEN=session_plan(DAY).opening


def book(ticker='A',minute=1,mid=100,size=1000,identity=None,opening=OPEN):
    mid=D(str(mid))
    return Book(ticker,identity or f'{ticker}-{minute}',opening+timedelta(minutes=minute),
        tuple(Level(mid-1-i,size) for i in range(5)),
        tuple(Level(mid+1+i,size) for i in range(5)))


def frame(minute,books=None,day=DAY):
    opening=session_plan(day).opening
    return PartialFrame(opening+timedelta(minutes=minute),str(day),
        (book(minute=minute,opening=opening),) if books is None else books)


def config(tickers=('A',),horizon=4,**options):
    return Config(tickers,horizon=horizon,initial_capital=1000,fee_rate=0,
                  participation=1,**options)


def day_frames(tickers=('A',),missing=None,day=DAY):
    plan=session_plan(day)
    return [frame(q,tuple(book(t,q,opening=plan.opening) for t in tickers
                 if t not in (missing or {}).get(q,())),day)
            for q in range(1,int((plan.liquidation-plan.opening).total_seconds()//60)+1)]


class MaskedKernelTests(unittest.TestCase):
    def test_per_asset_expiration_does_not_cancel_other_fill_or_defer(self):
        k=MaskedReplayKernel(config(('A','B')),
            frame(1,(book('A'),book('B'))))
        self.assertEqual(k.submit((1,1)),(5,5))
        tr=k.advance(frame(2,(book('B',2),)))
        self.assertEqual(k.portfolio,Portfolio(495,(0,5)))
        self.assertEqual(tr.canceled_pending,(5,0))
        self.assertEqual(tr.executions[0].outcomes[0].reasons,('unavailable_book',))
        self.assertEqual(k.submit((1,0)),(0,0))
        tr=k.advance(frame(3,(book('A',3),book('B',3))))
        self.assertEqual(tr.executions[0].fills,())
        self.assertEqual(k.portfolio.holdings,(0,5))

    def test_all_missing_keeps_positions_marks_and_clock_then_recognizes_jump(self):
        k=MaskedReplayKernel(config(horizon=4),frame(1))
        k.submit((1,));k.advance(frame(2))
        self.assertEqual(k.portfolio,Portfolio(91,(9,)))
        k.submit((0,));gap=k.advance(frame(3,()))
        self.assertEqual(gap.reward,0)
        self.assertEqual(k.index,2)
        self.assertEqual(k.availability,(False,))
        self.assertEqual(k.portfolio,Portfolio(91,(9,)))
        self.assertEqual(k.submit((1,)),(0,))
        jump=k.advance(frame(4,(book(minute=4,mid=90),)))
        self.assertEqual(jump.reward,D('-.09'))
        end=k.advance(frame(5,(book(minute=5,mid=90),)))
        self.assertTrue(end.flat)
        self.assertEqual(k.portfolio.cash,892)
        self.assertEqual(sum(t.reward for t in k.history),D('-.108'))

    def test_fee_accounting_and_telescoping_with_scaled_rewards(self):
        cfg=replace(config(horizon=2),fee_rate=D('.001'),reward_scale=2)
        k=MaskedReplayKernel(cfg,frame(1));k.submit((1,));k.advance(frame(2))
        end=k.advance(frame(3))
        self.assertTrue(end.flat)
        self.assertEqual(k.portfolio.cash,D('980.200'))
        self.assertEqual(sum(t.reward for t in k.history),D('-.0396'))
        self.assertEqual(sum(e.fees for t in k.history for e in t.executions),D('1.800'))

    def test_stale_books_are_unavailable_for_fills(self):
        original=book()
        k=MaskedReplayKernel(config(),frame(1,(original,)))
        k.submit((0,));k.advance(frame(2,(original,)))
        k.submit((1,));tr=k.advance(frame(3,(original,)))
        self.assertEqual(tr.availability,(False,))
        self.assertEqual(k.portfolio,Portfolio(1000,(0,)))
        self.assertEqual(tr.executions[0].outcomes[0].canceled,10)

    def test_capital_stop_latches_and_waits_for_missing_inventory(self):
        k=MaskedReplayKernel(config(('A','B'),horizon=5),frame(1,(book('A'),book('B'))))
        k.submit((1,1));k.advance(frame(2,(book('A',2),book('B',2))))
        self.assertEqual(k.portfolio.holdings,(4,4))
        k.submit((0,0));tr=k.advance(frame(3,(book('A',3,mid=40),)))
        self.assertEqual(tr.reason,'capital_stop_pending')
        self.assertEqual(k.portfolio.holdings,(0,4))
        self.assertFalse(k.done);self.assertTrue(k.stop_latched)
        with self.assertRaises(ValueError):k.submit((1,1))
        end=k.advance(frame(4,(book('B',4,mid=40),)))
        self.assertEqual(end.reason,'capital_stop')
        self.assertTrue(end.flat);self.assertTrue(k.done)
        self.assertEqual(k.portfolio.cash,504)

    def test_stop_remains_latched_even_when_missing_asset_returns_at_higher_price(self):
        k=MaskedReplayKernel(config(('A','B'),horizon=5),frame(1,(book('A'),book('B'))))
        k.submit((1,1));k.advance(frame(2,(book('A',2),book('B',2))))
        k.submit((0,0));k.advance(frame(3,(book('A',3,mid=40),)))
        end=k.advance(frame(4,(book('B',4,mid=200),)))
        self.assertEqual(end.reason,'capital_stop')
        self.assertEqual(k.portfolio.cash,1144)

    def test_unavailable_sale_does_not_finance_purchase(self):
        engine=PartialExecutionEngine(config(('A','B')))
        event=engine.execute(Portfolio(100,(10,0)),(-10,10),(100,100),frame(2,(book('B',2),)))
        self.assertEqual(event.after,Portfolio(100,(10,0)))
        self.assertEqual(event.outcomes[0].canceled,10)
        self.assertIn('cash',event.outcomes[1].reasons)

    def test_complete_market_matches_v2_accounting(self):
        cfg=replace(config(('A','B')),fee_rate=D('.001'))
        initial=frame(1,(book('A'),book('B')))
        masked=MaskedReplayKernel(cfg,initial)
        old=ReplayKernel(cfg,Frame(initial.at,initial.session_id,initial.books))
        for q,action in zip((2,3,4),((1,0),(0,1),(-1,0))):
            f=frame(q,(book('A',q,mid=100+q),book('B',q,mid=100-q)))
            masked.submit(action);old.submit(action)
            new_tr=masked.advance(f);old_tr=old.advance(Frame(f.at,f.session_id,f.books))
            self.assertEqual(masked.portfolio,old.portfolio)
            self.assertEqual(new_tr.reward,old_tr.reward)
            self.assertEqual(new_tr.after_wealth,old_tr.after_wealth)
        f=frame(5,(book('A',5),book('B',5)))
        new_tr=masked.advance(f);old_tr=old.advance(Frame(f.at,f.session_id,f.books))
        self.assertEqual(masked.portfolio,old.portfolio)
        self.assertEqual(new_tr.reward,old_tr.reward)

    def test_missing_terminal_book_truncates_without_invented_sale(self):
        k=MaskedReplayKernel(config(horizon=2),frame(1))
        k.submit((1,));k.advance(frame(2))
        end=k.advance(frame(3,()))
        self.assertTrue(end.truncated);self.assertFalse(end.terminated)
        self.assertEqual(end.reason,'exit_data_missing')
        self.assertEqual(k.portfolio,Portfolio(91,(9,)))
        self.assertEqual(end.executions,())

    def test_insufficient_terminal_depth_is_economic_failure_not_data_gap(self):
        k=MaskedReplayKernel(config(horizon=2),frame(1))
        k.submit((1,));k.advance(frame(2))
        end=k.advance(frame(3,(book(minute=3,size='.1'),)))
        self.assertTrue(end.terminated);self.assertFalse(end.truncated)
        self.assertEqual(end.reason,'liquidation_failure')
        self.assertEqual(end.residual_holdings,(9,))

    def test_cached_capture_capacity_does_not_replenish(self):
        engine=PartialExecutionEngine(config())
        b=book(size=1)
        first=engine.execute(Portfolio(10000,(0,)),(5,),(100,),frame(1,(b,)))
        second=engine.execute(first.after,(5,),(100,),frame(2,(b,)))
        self.assertEqual(first.after.holdings,(5,))
        self.assertEqual(second.fills,())

    def test_invalid_identity_does_not_mutate_portfolio_or_marks(self):
        k=MaskedReplayKernel(config(),frame(1));k.submit((1,))
        bad=book(minute=1,mid=110)
        with self.assertRaisesRegex(ValueError,'conflicting'):
            k.advance(frame(2,(bad,)))
        self.assertEqual(k.index,0);self.assertEqual(k.marked_wealth,1000)
        k.advance(frame(2))
        self.assertEqual(k.portfolio.holdings,(9,))

    def test_future_capture_and_timestamp_jump_rejected(self):
        with self.assertRaisesRegex(ValueError,'future'):
            frame(1,(book(minute=2),))
        k=MaskedReplayKernel(config(),frame(1));k.submit((0,))
        with self.assertRaisesRegex(ValueError,'consecutive'):k.advance(frame(3))


class MaskedControllerTests(unittest.TestCase):
    def test_first_causal_entry_is_late_without_future_tail_selection(self):
        controller=MaskedDailyReplay(('A','B'))
        ep=controller.start(DAY,day_frames(('A','B'),{1:('B',),30:('A','B')}))
        self.assertEqual(ep.plan.first_decision,OPEN+timedelta(minutes=22))
        self.assertEqual(ep.plan.horizon,367)
        observation=ep.observation()
        self.assertEqual(len(observation.market_history),20)
        self.assertTrue(all(f.at<=observation.at for f in observation.market_history))
        self.assertFalse(hasattr(observation,'coverage_candidate'))
        with self.assertRaisesRegex(ValueError,'restart'):controller.start(DAY,day_frames(('A','B')))

    def test_future_tail_changes_do_not_change_entry_or_initial_observation(self):
        original=MaskedDailyReplay(('A',)).start(DAY,day_frames())
        altered=MaskedDailyReplay(('A',)).start(DAY,day_frames(missing={q:('A',) for q in range(30,390)}))
        self.assertEqual(original.observation(),altered.observation())
        self.assertEqual(original.plan.first_decision,altered.plan.first_decision)

    def test_daily_grid_continues_through_missing_points_without_restart(self):
        seen=[]
        result=MaskedDailyReplay(('A',)).run(DAY,day_frames(missing={q:('A',) for q in range(30,60)}),
            lambda obs:seen.append(obs) or (0,))
        self.assertEqual(result.status,'scheduled_end')
        self.assertEqual(len(result.transitions),368)
        self.assertEqual(result.marked_return,0)
        self.assertTrue(result.coverage_candidate);self.assertFalse(result.training_ready)
        self.assertTrue(any(not any(o.availability) for o in seen))
        self.assertTrue(any(all(not f.books for f in o.market_history) for o in seen))

    def test_no_initial_complete_window_is_not_startable(self):
        result=MaskedDailyReplay(('A','B')).start(DAY,day_frames(('A','B'),{q:('B',) for q in range(1,390)}))
        self.assertIsInstance(result,MaskedSessionResult)
        self.assertFalse(result.startable);self.assertEqual(result.transitions,())

    def test_exit_missing_excludes_return_even_with_no_trades(self):
        result=MaskedDailyReplay(('A',)).run(DAY,day_frames(missing={389:('A',)}),lambda _: (0,))
        self.assertEqual(result.status,'exit_data_missing')
        self.assertFalse(result.coverage_candidate)
        self.assertIsNone(result.marked_return)
        self.assertIsNone(result.realized_return)

    def test_early_economic_stop_does_not_override_common_exit_coverage(self):
        frames=day_frames(missing={389:('A',)})
        frames[22]=frame(23,(book(minute=23,mid=40),))
        result=MaskedDailyReplay(('A',),initial_capital=1000,fee_rate=0,participation=1).run(
            DAY,frames,lambda obs:(1,) if obs.at==OPEN+timedelta(minutes=21) else (0,))
        self.assertEqual(result.status,'capital_stop')
        self.assertTrue(result.transitions[-1].flat)
        self.assertFalse(result.coverage_candidate)
        self.assertIsNone(result.marked_return)

    def test_marked_return_is_unscaled_and_residual_return_is_not_realized(self):
        frames=day_frames()
        frames[-1]=frame(389,(book(minute=389,size='.1'),))
        result=MaskedDailyReplay(('A',),initial_capital=1000,fee_rate=0,participation=1,reward_scale=2).run(
            DAY,frames,lambda obs:(1,) if obs.at==OPEN+timedelta(minutes=21) else (0,))
        self.assertEqual(result.status,'liquidation_failure')
        self.assertEqual(result.marked_return,D('-.009'))
        self.assertEqual(sum(t.reward for t in result.transitions),D('-.018'))
        self.assertIsNone(result.realized_return)

    def test_short_session_uses_calendar_exit(self):
        day=date(2025,7,3)
        result=MaskedDailyReplay(('A',)).run(day,day_frames(day=day),lambda _: (0,))
        self.assertEqual(len(result.transitions),188)
        self.assertEqual(result.plan.liquidation.hour,16) # 12:59 EDT
        self.assertEqual(result.plan.liquidation.minute,59)

    def test_preopen_and_offgrid_input_rejected(self):
        controller=MaskedDailyReplay(('A',))
        with self.assertRaisesRegex(ValueError,'pre-open'):
            controller.start(DAY,[frame(1,(book(minute=-1),))])
        with self.assertRaisesRegex(ValueError,'off-grid'):
            controller.start(DAY,[PartialFrame(OPEN+timedelta(seconds=75),str(DAY))])
