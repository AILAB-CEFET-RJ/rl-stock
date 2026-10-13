import random
import unittest
from dataclasses import replace
from datetime import date,timedelta

from rl_boleta.economic_kernel import Book,Level
from rl_boleta.masked_baselines import BaselinePolicy,run_synthetic_suite
from rl_boleta.masked_observations import MaskedMarketSession
from rl_boleta.missing_data_replay import MaskedDailyReplay,PartialFrame
from rl_boleta.session_replay import session_plan

TICKERS=('A','B')


def session(day=date(2025,7,3), *, missing_exit=False, shallow=False):
    plan=session_plan(day);frames=[]
    for q,at in enumerate(plan.required_times,1):
        books=[]
        for j,t in enumerate(TICKERS):
            if t=='A' and (q==22 or 40<=q<=80 or missing_exit and at==plan.liquidation):continue
            mid=100+j*20
            books.append(Book(t,f'{day}-{t}-{q}',at,
                tuple(Level(mid-.01-i*.01,1 if shallow and at==plan.liquidation else 10000) for i in range(5)),
                tuple(Level(mid+.01+i*.01,10000) for i in range(5))))
        frames.append(PartialFrame(at,str(day),tuple(books)))
    return MaskedMarketSession(day,tuple(frames),{},synthetic=True)


class BaselineTests(unittest.TestCase):
    def observation(self):
        s=session();e=MaskedDailyReplay(TICKERS).start(s.day,s.frames)
        return e.observation()

    def test_equal_entry_once_no_retry_after_missing_fill(self):
        s=session();e=MaskedDailyReplay(TICKERS).start(s.day,s.frames)
        p=BaselinePolicy('equal_allocation_single_entry',TICKERS)
        e.advance(p(e.observation()))
        self.assertEqual(e.kernel.portfolio.holdings[0],0)
        self.assertGreater(e.kernel.portfolio.holdings[1],0)
        e.advance(p(e.observation()))
        self.assertEqual(e.kernel.portfolio.holdings[0],0)
        self.assertEqual(p(e.observation()),(0,0))

    def test_momentum_reversal_exact_endpoints_and_absence(self):
        obs=self.observation();history=list(obs.market_history);current=history[-1]
        def move(book,delta):
            return replace(book,bids=tuple(Level(l.price+delta,l.size) for l in book.bids),
                asks=tuple(Level(l.price+delta,l.size) for l in book.asks))
        history[-1]=replace(current,books=(move(current.books[0],1),move(current.books[1],-1)))
        changed=replace(obs,market_history=tuple(history))
        self.assertEqual(BaselinePolicy('ten_interval_momentum',TICKERS)(changed),(1,-1))
        self.assertEqual(BaselinePolicy('ten_interval_reversal',TICKERS)(changed),(-1,1))
        self.assertEqual(BaselinePolicy('ten_interval_momentum',TICKERS)(obs),(0,0))
        history[-11]=replace(history[-11],books=(history[-11].books[1],))
        changed=replace(changed,market_history=tuple(history))
        self.assertEqual(BaselinePolicy('ten_interval_momentum',TICKERS)(changed),(0,-1))
        history[-1]=replace(history[-1],books=())
        self.assertEqual(BaselinePolicy('ten_interval_momentum',TICKERS)(replace(changed,market_history=tuple(history))),(0,0))

    def test_random_reproducible_stream_persists_across_episode_policies(self):
        obs=self.observation();rng=random.Random(100);reference=random.Random(100)
        first=BaselinePolicy('uniform_random_actions',TICKERS,rng=rng)(obs)
        second=BaselinePolicy('uniform_random_actions',TICKERS,rng=rng)(obs)
        self.assertEqual(first,tuple(reference.uniform(-1,1) for _ in TICKERS))
        self.assertEqual(second,tuple(reference.uniform(-1,1) for _ in TICKERS))
        self.assertNotEqual(first,second)
        with self.assertRaises(ValueError):BaselinePolicy('uniform_random_actions',TICKERS)

    def test_suite_common_denominator_and_no_historical_scoring(self):
        s=session(missing_exit=True);runs=run_synthetic_suite((s,),TICKERS)
        self.assertEqual(len(runs),14)
        self.assertEqual([r['seed'] for r in runs[4:]],list(range(100,110)))
        for run in runs:
            r=run['sessions'][0]
            self.assertEqual(r['status'],'exit_data_missing')
            self.assertFalse(r['coverage_candidate'])
            self.assertIsNone(r['marked_return'])
        with self.assertRaises(ValueError):run_synthetic_suite((replace(s,synthetic=False),),TICKERS)

    def test_cash_and_residual_failure_retained(self):
        s=session(shallow=True);runs=run_synthetic_suite((s,),TICKERS)
        cash=runs[0]['sessions'][0];equal=runs[1]['sessions'][0]
        self.assertEqual(cash['marked_return'],'0');self.assertTrue(cash['flat'])
        self.assertEqual(equal['status'],'liquidation_failure')
        self.assertFalse(equal['flat']);self.assertIsNone(equal['realized_return'])
        self.assertTrue(equal['coverage_candidate']);self.assertGreater(equal['residual_holdings'][1],0)

    def test_missing_scheduled_date_kept_for_every_method(self):
        sessions=(session(date(2025,3,3)),session(date(2025,3,5)))
        runs=run_synthetic_suite(sessions,TICKERS)
        for run in runs:
            self.assertEqual(len(run['sessions']),3)
            self.assertEqual(run['sessions'][1]['status'],'not_startable')
            self.assertIsNone(run['sessions'][1]['marked_return'])
