"""Hand-calculated economics and invariants; synthetic books only."""
import random
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from rl_boleta.economic_kernel import (
    Book, Config, ExecutionEngine, Frame, Level, Portfolio, ReplayKernel,
    desired_orders, wealth,
)

START = datetime(2025, 3, 3, 14, 30, tzinfo=timezone.utc)


def book(ticker="A", minute=0, mid=100, sizes=(100,)*5, identity=None, spread=2):
    mid, half = D(str(mid)), D(str(spread))/2
    return Book(ticker, identity or f"{ticker}-{minute}", START+timedelta(minutes=minute),
                tuple(Level(mid-half-i, size) for i,size in enumerate(sizes)),
                tuple(Level(mid+half+i, size) for i,size in enumerate(sizes)))


def frame(minute=0, books=None, session="2025-03-03"):
    return Frame(START+timedelta(minutes=minute), session, books or (book(minute=minute),))


def config(tickers=("A",), **kwargs):
    return Config(tickers, initial_capital=1000, fee_rate=0, participation=1,
                  horizon=4, **kwargs)


class ExecutionTests(unittest.TestCase):
    def test_walks_levels_and_vwap_hand_calculation(self):
        b=book(sizes=(3,5,10,10,10))
        event=ExecutionEngine(config()).execute(Portfolio(1000,(0,)),(5,),(100,),frame(books=(b,)))
        self.assertEqual(event.after,Portfolio(493,(5,)))  # 3*101 + 2*102 = 507
        self.assertEqual([f.quantity for f in event.fills],[3,2])
        self.assertEqual(event.outcomes[0].vwap,D('101.4'))
        self.assertEqual(event.outcomes[0].canceled,0)

    def test_user_example_three_at_100_two_at_101(self):
        b=book(mid=99, sizes=(3,5,10,10,10))
        e=ExecutionEngine(config()).execute(Portfolio(1000,(0,)),(5,),(99,),frame(books=(b,)))
        self.assertEqual(e.after,Portfolio(498,(5,)))
        self.assertEqual(e.outcomes[0].vwap,D('100.4'))

    def test_fees_in_budget_prevent_negative_cash(self):
        cfg=replace(config(),fee_rate=D('.01'))
        e=ExecutionEngine(cfg).execute(Portfolio(101,(0,)),(1,),(100,),frame())
        self.assertEqual(e.after,Portfolio(101,(0,)))
        self.assertIn('cash',e.outcomes[0].reasons)
        self.assertIsNone(e.outcomes[0].vwap)

    def test_buy_fees_once_and_holdings_sell_cap(self):
        engine=ExecutionEngine(replace(config(),fee_rate=D('.01')))
        e=engine.execute(Portfolio(1000,(0,)),(5,),(100,),frame())
        self.assertEqual(e.after.cash,D('489.95'))
        self.assertEqual(e.fees,D('5.05'))
        sell=engine.execute(e.after,(-20,),(100,),frame(1))
        self.assertEqual(sell.after,Portfolio('980.00',(0,)))
        self.assertEqual(sell.outcomes[0].filled,-5)
        self.assertEqual(sell.outcomes[0].canceled,15)
        self.assertIn('holdings',sell.outcomes[0].reasons)

    def test_no_short_sale_with_empty_inventory(self):
        e=ExecutionEngine(config()).execute(Portfolio(1000,(0,)),(-5,),(100,),frame())
        self.assertEqual(e.after,Portfolio(1000,(0,)))
        self.assertEqual(e.fills,())

    def test_partial_fills_and_participation_floor(self):
        cfg=replace(config(),participation=D('.1'))
        b=book(sizes=(9,10,19,20,29))
        e=ExecutionEngine(cfg).execute(Portfolio(10000,(0,)),(20,),(100,),frame(books=(b,)))
        self.assertEqual([f.quantity for f in e.fills],[1,1,2,2])
        self.assertEqual(e.outcomes[0].filled,6)
        self.assertEqual(e.outcomes[0].canceled,14)
        self.assertIn('depth',e.outcomes[0].reasons)

    def test_same_capture_cannot_replenish_capacity(self):
        engine=ExecutionEngine(config()); b=book(sizes=(1,1,1,1,1))
        e=engine.execute(Portfolio(10000,(0,)),(5,),(100,),frame(books=(b,)))
        again=engine.execute(e.after,(5,),(100,),frame(1,books=(b,)))
        self.assertEqual(again.fills,())
        new=engine.execute(again.after,(5,),(100,),frame(2,books=(book(minute=2,sizes=(1,)*5),)))
        self.assertEqual(new.outcomes[0].filled,5)

    def test_changed_capture_contents_are_rejected_without_spending(self):
        engine=ExecutionEngine(config());engine.register_frame(frame())
        with self.assertRaisesRegex(ValueError,'conflicting'):
            engine.execute(Portfolio(1000,(0,)),(5,),(100,),frame(books=(book(mid=110,identity='A-0'),)))
        good=engine.execute(Portfolio(1000,(0,)),(5,),(100,),frame())
        self.assertEqual(good.outcomes[0].filled,5)

    def test_sells_finance_buys_with_fixed_shared_budgets(self):
        cfg=config(('A','B')); books=(book('A'),book('B'))
        e=ExecutionEngine(cfg).execute(Portfolio(0,(5,0)),(-5,5),(100,100),frame(books=books))
        self.assertEqual(e.after,Portfolio(91,(0,4))) # 495 sale, 404 purchase
        self.assertEqual([f.side for f in e.fills],['sell','buy'])

    def test_budget_leftover_is_not_redistributed(self):
        cfg=config(('A','B')); books=(book('A',sizes=(1,)*5),book('B'))
        e=ExecutionEngine(cfg).execute(Portfolio(10000,(0,0)),(50,50),(100,100),frame(books=books))
        self.assertEqual(e.after.holdings,(5,49))
        self.assertEqual(e.after.cash,D(4536)) # A costs515, B4949, unused A budget stays cash

    def test_permuting_tickers_does_not_assign_buy_priority(self):
        books=(book('A',mid=100),book('B',mid=200))
        f=frame(books=books)
        a=ExecutionEngine(config(('A','B'))).execute(Portfolio(1000,(0,0)),(5,2),(100,200),f)
        b=ExecutionEngine(config(('B','A'))).execute(Portfolio(1000,(0,0)),(2,5),(200,100),f)
        self.assertEqual(a.after.cash,b.after.cash)
        self.assertEqual(a.after.holdings,tuple(reversed(b.after.holdings)))

    def test_randomized_conservation_and_capacity(self):
        rng=random.Random(7)
        for _ in range(150):
            cfg=replace(config(('A','B')),fee_rate=D('.002'),participation=D('.25'))
            books=tuple(book(t,mid=rng.randrange(20,200),sizes=tuple(rng.randrange(1,50) for _ in range(5))) for t in cfg.tickers)
            f=frame(books=books);before=Portfolio(rng.randrange(0,1000),tuple(rng.randrange(0,20) for _ in books))
            requests=tuple(rng.randrange(-30,31) for _ in books)
            e=ExecutionEngine(cfg).execute(before,requests,tuple(b.midpoint for b in books),f)
            signed_notional=sum(((-1 if x.side=='sell' else 1)*x.quantity*x.price for x in e.fills),D(0))
            fees=sum((x.fee for x in e.fills),D(0))
            self.assertEqual(e.after.cash,before.cash-signed_notional-fees)
            for i,t in enumerate(cfg.tickers):
                position_change=sum((x.quantity if x.side=='buy' else -x.quantity) for x in e.fills if x.ticker==t)
                self.assertEqual(e.after.holdings[i],before.holdings[i]+position_change)
                self.assertLessEqual(abs(e.outcomes[i].filled),abs(requests[i]))
            for fill in e.fills:
                quote=(f.book(fill.ticker).asks if fill.side=='buy' else f.book(fill.ticker).bids)[fill.level-1]
                self.assertLessEqual(fill.quantity,int(quote.size*cfg.participation))
            self.assertGreaterEqual(e.after.cash,0)


class ReplayTests(unittest.TestCase):
    def test_horizon_requires_explicit_choice(self):
        with self.assertRaises(TypeError):
            Config(("A",))

    def test_session_derived_horizons_without_hourly_resets(self):
        from datetime import date
        from rl_boleta.market_calendar import window
        for day,expected in [(date(2025,3,3),368),(date(2025,7,3),188)]:
            opening,closing=window(day)
            start=(opening+timedelta(minutes=21)).astimezone(timezone.utc)
            last=(closing-timedelta(minutes=1)).astimezone(timezone.utc)
            horizon=int((last-start).total_seconds()/60)
            self.assertEqual(horizon,expected)
            def observed(at):
                b=replace(book(identity=str(at)),available_at=at)
                return Frame(at,str(day),(b,))
            k=ReplayKernel(replace(config(),horizon=horizon),observed(start))
            for index in range(1,horizon+1):
                if index<horizon:
                    k.submit((0,))
                result=k.advance(observed(start+timedelta(minutes=index)))
                self.assertEqual(result.terminated,index==horizon)
            self.assertEqual(k.frame.at,last)
            self.assertEqual(k.portfolio.cash,D(1000))
            self.assertEqual(len(k.history),expected)

    def test_missing_reserved_exit_truncates_without_sale(self):
        k=ReplayKernel(replace(config(),horizon=2),frame())
        k.submit((D('.5'),));k.advance(frame(1))
        before=k.portfolio
        result=k.advance(None)
        self.assertTrue(result.truncated);self.assertFalse(result.terminated)
        self.assertEqual(k.portfolio,before)
        self.assertEqual(result.executions,())
        self.assertFalse(result.flat)

    def test_intention_fixed_before_future_book_and_cash_limits_fill(self):
        k=ReplayKernel(config(),frame())
        self.assertEqual(k.submit((1,)),(10,))
        next_book=book(minute=1,mid=200)
        r=k.advance(frame(1,(next_book,)))
        self.assertEqual(r.executions[0].outcomes[0].desired,10)
        self.assertEqual(k.portfolio,Portfolio(196,(4,)))
        self.assertEqual(r.reward,D('-.004')) # no gain for buying after the price rise

    def test_holding_gets_market_gain_and_identity(self):
        k=ReplayKernel(config(),frame());k.submit((D('.5'),));first=k.advance(frame(1))
        self.assertEqual(first.reward,D('-.005'))
        k.submit((0,));r=k.advance(frame(2,(book(minute=2,mid=102),)))
        self.assertEqual(r.after_wealth-r.before_wealth,D(10))
        self.assertEqual(r.reward,D('.01'))
        self.assertEqual(r.executions[0].fills,())

    def test_dead_zone_and_signed_integer_sizing(self):
        cfg=config();p=Portfolio(1000,(0,))
        self.assertEqual(desired_orders((D('.05'),),p,frame(),cfg),(0,))
        self.assertEqual(desired_orders((D('-.19'),),p,frame(),cfg),(-1,))
        self.assertEqual(desired_orders((D('.09'),),Portfolio(1,(0,)),frame(),cfg),(0,))

    def test_terminal_reserves_book_and_charges_real_bid_and_fees(self):
        cfg=replace(config(),horizon=2,fee_rate=D('.01'))
        k=ReplayKernel(cfg,frame());k.submit((D('.5'),));k.advance(frame(1))
        with self.assertRaises(ValueError):k.submit((1,))
        r=k.advance(frame(2))
        self.assertTrue(r.terminated);self.assertTrue(r.flat)
        self.assertEqual(r.reason,'scheduled_end')
        self.assertEqual(k.portfolio.cash,D('980.00'))
        self.assertEqual(sum(t.reward for t in k.history),D('-.02'))
        self.assertEqual(r.executions[0].kind,'liquidation')
        with self.assertRaises(ValueError):k.advance(frame(3))

    def test_terminal_insufficient_depth_retains_marked_residuals(self):
        k=ReplayKernel(replace(config(),horizon=2),frame());k.submit((D('.9'),));k.advance(frame(1))
        r=k.advance(frame(2,(book(minute=2,sizes=(1,)*5),)))
        self.assertTrue(r.terminated);self.assertFalse(r.flat)
        self.assertEqual(r.residual_holdings,(4,))
        self.assertEqual(r.after_wealth,k.portfolio.cash+400)

    def test_stop_has_separate_fills_and_round_trip_costs(self):
        k=ReplayKernel(replace(config(),fee_rate=D('.01')),frame())
        k.submit((D('.9'),));k.advance(frame(1))
        k.submit((D('.5'),));r=k.advance(frame(2,(book(minute=2,mid=50),)))
        self.assertEqual(r.reason,'capital_stop');self.assertTrue(r.terminated)
        self.assertEqual([e.kind for e in r.executions],['regular','capital_stop'])
        self.assertTrue(any(f.side=='buy' for f in r.executions[0].fills))
        self.assertTrue(all(f.side=='sell' for f in r.executions[1].fills))
        self.assertEqual(sum(t.reward for t in k.history),(r.after_wealth-1000)/1000)
        all_fees=sum(e.fees for t in k.history for e in t.executions)
        self.assertGreater(all_fees,D(9))
        self.assertTrue(r.flat)

    def test_stop_reuses_remaining_same_capture_bid_capacity(self):
        cfg=replace(config(('A','B')),initial_capital=D(3000),capital_floor=D('.95'))
        k=ReplayKernel(cfg,frame(books=(book('A'),book('B'))))
        k.submit((1,1));k.advance(frame(1,(book('A',1),book('B',1))))
        k.submit((-1,0));r=k.advance(frame(2,(book('A',2,mid=20,sizes=(1,)*5),book('B',2,mid=20,sizes=(1,)*5))))
        a_sales=sum(f.quantity for e in r.executions for f in e.fills if f.ticker=='A' and f.side=='sell')
        self.assertLessEqual(a_sales,5)
        self.assertEqual(r.reason,'capital_stop')
        self.assertFalse(r.flat)

    def test_gap_cancels_pending_without_retrospective_exit(self):
        k=ReplayKernel(config(),frame());k.submit((D('.5'),));k.advance(frame(1))
        before=k.portfolio;k.submit((-1,));r=k.advance(frame(3,(book(minute=3,mid=500),)))
        self.assertTrue(r.truncated);self.assertFalse(r.terminated)
        self.assertEqual(r.reason,'nonconsecutive_observation')
        self.assertEqual(r.executions,());self.assertEqual(r.reward,0)
        self.assertEqual(k.portfolio,before);self.assertEqual(r.after_wealth,995)
        self.assertNotEqual(r.canceled_pending,())
        self.assertEqual(r.at,START+timedelta(minutes=3))
        self.assertEqual(r.valuation_at,START+timedelta(minutes=1))

    def test_missing_and_session_change_truncate(self):
        for future,reason in [(None,'missing_observation'),(frame(1,session='other'),'session_interruption')]:
            k=ReplayKernel(config(),frame());k.submit((1,));r=k.advance(future)
            self.assertEqual(r.reason,reason);self.assertTrue(r.truncated)
            self.assertEqual(k.portfolio,Portfolio(1000,(0,)))

    def test_orders_do_not_persist_after_partial_execution(self):
        k=ReplayKernel(config(),frame());k.submit((1,));k.advance(frame(1,(book(minute=1,sizes=(1,)*5),)))
        self.assertEqual(k.portfolio.holdings,(5,))
        self.assertIsNone(k.pending)
        k.submit((0,));r=k.advance(frame(2))
        self.assertEqual(r.executions[0].fills,())
        self.assertEqual(k.portfolio.holdings,(5,))

    def test_rejects_future_stale_regressing_or_conflicting_frames(self):
        with self.assertRaises(ValueError):frame(books=(book(minute=1),))
        k=ReplayKernel(config(),frame());k.submit((1,))
        with self.assertRaises(ValueError):k.advance(frame(0))
        with self.assertRaises(ValueError):k.advance(frame(1,(book(mid=110,identity='A-0'),)))
        self.assertEqual(k.portfolio,Portfolio(1000,(0,)))
        k.advance(frame(1));k.submit((0,))
        r=k.advance(frame(2,(book(),)))
        self.assertEqual(r.reason,'stale_observation');self.assertTrue(r.truncated)

    def test_floor_is_strict_and_relative_to_initial_capital(self):
        k=ReplayKernel(config(),frame());k.submit((D('.5'),));k.advance(frame(1))
        k.submit((0,));r=k.advance(frame(2,(book(minute=2,mid=61),)))
        self.assertEqual(r.after_wealth,D(800))
        self.assertFalse(r.terminated)  # equals floor, not strictly below

    def test_capture_regression_rejected_and_pending_intention_preserved(self):
        cfg=replace(config(),max_receipt_age_seconds=200)
        k=ReplayKernel(cfg,frame());k.submit((D('.5'),));k.advance(frame(1))
        k.submit((0,));before=k.portfolio
        with self.assertRaisesRegex(ValueError,'regressed'):
            k.advance(frame(2,(book(),)))
        self.assertEqual(k.portfolio,before)
        self.assertIsNotNone(k.pending)

    def test_missing_asset_truncates_without_fills(self):
        k=ReplayKernel(config(('A','B')),frame(books=(book('A'),book('B'))))
        k.submit((1,1));r=k.advance(frame(1))
        self.assertEqual(r.reason,'incomplete_universe')
        self.assertTrue(r.truncated);self.assertEqual(r.executions,())

    def test_all_invalid_inputs_rejected(self):
        for action in [(True,),(float('nan'),),(float('inf'),),(2,),(),(0,0)]:
            with self.assertRaises(ValueError):desired_orders(action,Portfolio(1000,(0,)),frame(),config())
        for cash,holdings in [(-1,(0,)),(1,(-1,)),(1,(1.0,)),(1,(True,))]:
            with self.assertRaises(ValueError):Portfolio(cash,holdings)
        for change in [dict(participation=0),dict(fee_rate=-1),dict(horizon=0),dict(initial_capital=0)]:
            with self.assertRaises(ValueError):replace(config(),**change)
        with self.assertRaises(ValueError):Level(float('nan'),1)
        with self.assertRaises(ValueError):replace(book(),available_at=START.replace(tzinfo=None))
        with self.assertRaises(ValueError):replace(book(),bids=book().asks)
        with self.assertRaises(ValueError):replace(book(),asks=(Level(101,1),)*5)

    def test_randomized_episode_wealth_identity_and_reward_telescoping(self):
        for seed in range(20):
            rng=random.Random(seed)
            cfg=replace(config(('A','B')),initial_capital=D(10000),horizon=8,
                        fee_rate=D('.001'),capital_floor=D('.1'))
            current=frame(books=(book('A'),book('B',mid=80)))
            k=ReplayKernel(cfg,current)
            for minute in range(1,9):
                previous,old_frame=k.portfolio,k.frame
                if minute<8:
                    k.submit(tuple(D(rng.randrange(-10,11))/10 for _ in cfg.tickers))
                future=frame(minute,tuple(book(t,minute,mid=rng.randrange(90,110) if t=='A' else rng.randrange(70,90)) for t in cfg.tickers))
                r=k.advance(future)
                market=sum(previous.holdings[i]*(future.book(t).midpoint-old_frame.book(t).midpoint) for i,t in enumerate(cfg.tickers))
                fill_pnl=sum(((1 if f.side=='buy' else -1)*f.quantity*(future.book(f.ticker).midpoint-f.price)-f.fee for e in r.executions for f in e.fills),D(0))
                self.assertEqual(r.after_wealth-r.before_wealth,market+fill_pnl)
                self.assertGreaterEqual(k.portfolio.cash,0)
            self.assertTrue(k.done)
            self.assertEqual(sum(r.reward for r in k.history),(wealth(k.portfolio,k.frame,cfg.tickers)-cfg.initial_capital)/cfg.initial_capital)

    def test_wealth_change_identity_for_market_move_and_trade(self):
        k=ReplayKernel(replace(config(),fee_rate=D('.001')),frame())
        k.submit((D('.4'),));k.advance(frame(1));old=k.portfolio;old_frame=k.frame
        k.submit((D('.3'),));r=k.advance(frame(2,(book(minute=2,mid=110),)))
        event=r.executions[0]
        market_gain=old.holdings[0]*(k.frame.book('A').midpoint-old_frame.book('A').midpoint)
        execution_gain=sum((f.quantity*(k.frame.book('A').midpoint-f.price) for f in event.fills),D(0))
        self.assertEqual(r.after_wealth-r.before_wealth,market_gain+execution_gain-event.fees)


if __name__=='__main__':unittest.main()
