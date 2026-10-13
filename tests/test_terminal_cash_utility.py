import unittest
from dataclasses import replace
from decimal import Decimal as D

from rl_boleta.economic_kernel import Level
from rl_boleta.missing_data_replay import MaskedReplayKernel
from test_missing_data_replay import config,frame,book


class TerminalCashUtilityTests(unittest.TestCase):
    def replay(self,objective,*,missing=False,mid=100):
        k=MaskedReplayKernel(config(horizon=3),frame(1),wind_down_points=2,reward_objective=objective)
        k.submit((1,));k.advance(frame(2))
        for q in (3,4):
            b=book(minute=q,mid=mid)
            b=replace(b,bids=tuple(Level(l.price,'.1') for l in b.bids))
            k.advance(frame(q,() if missing and q==4 else (b,)))
        return k

    def test_residual_financial_accounting_unchanged_utility_equals_cash_delta(self):
        marked=self.replay('marked_wealth',mid=200)
        cash=self.replay('terminal_cash_utility',mid=200)
        self.assertEqual(cash.portfolio,marked.portfolio)
        self.assertEqual(cash.marked_wealth,marked.marked_wealth)
        self.assertGreater(cash.marked_wealth,1000)
        self.assertEqual(cash.portfolio.holdings,(9,))
        self.assertEqual(cash.history[-1].terminal_inventory_adjustment_usd,D(1800))
        self.assertEqual(sum(t.reward for t in cash.history),(cash.portfolio.cash-1000)/1000)
        self.assertEqual(sum(t.reward for t in marked.history),(marked.marked_wealth-1000)/1000)
        self.assertTrue(all(t.terminal_inventory_adjustment_usd==0 for t in cash.history[:-1]))

    def test_flat_episode_has_identical_rewards_fees_and_wealth(self):
        outcomes=[]
        for mode in ('marked_wealth','terminal_cash_utility'):
            k=MaskedReplayKernel(replace(config(horizon=3),fee_rate=D('.001')),frame(1),wind_down_points=2,reward_objective=mode)
            k.submit((1,));k.advance(frame(2));k.advance(frame(3));k.advance(frame(4))
            outcomes.append(k)
        self.assertEqual(outcomes[0].history,outcomes[1].history)
        self.assertEqual(outcomes[0].portfolio,outcomes[1].portfolio)

    def test_data_truncation_never_gets_terminal_inventory_adjustment(self):
        k=self.replay('terminal_cash_utility',missing=True,mid=200)
        self.assertTrue(k.history[-1].truncated)
        self.assertFalse(k.history[-1].terminated)
        self.assertEqual(k.history[-1].terminal_inventory_adjustment_usd,0)
        self.assertEqual(sum(t.reward for t in k.history),(k.marked_wealth-1000)/1000)

    def test_scaled_rewards_and_zero_holdings_stop(self):
        k=MaskedReplayKernel(replace(config(horizon=3),reward_scale=2),frame(1),wind_down_points=2,reward_objective='terminal_cash_utility')
        k.submit((1,));k.advance(frame(2))
        k.advance(frame(3,(book(minute=3,mid=60),)))
        self.assertTrue(k.done);self.assertTrue(k.history[-1].flat)
        self.assertEqual(k.history[-1].reason,'capital_stop')
        self.assertEqual(sum(t.reward for t in k.history),2*(k.portfolio.cash-1000)/1000)
        self.assertEqual(k.history[-1].terminal_inventory_adjustment_usd,0)

    def test_invalid_objective_rejected(self):
        with self.assertRaises(ValueError):MaskedReplayKernel(config(),frame(1),reward_objective='erase_inventory')


if __name__=='__main__':unittest.main()
