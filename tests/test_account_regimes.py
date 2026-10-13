import importlib.util
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from rl_boleta.economic_kernel import Portfolio
from rl_boleta.missing_data_replay import MaskedReplayKernel, MaskedDailyReplay
from test_missing_data_replay import config,frame,book,day_frames


class AccountRegimeTests(unittest.TestCase):
    def round_trip(self,mode,fee=0):
        k=MaskedReplayKernel(replace(config(horizon=6),fee_rate=D(str(fee))),frame(1),account_regime=mode)
        k.submit((1,));k.advance(frame(2))
        k.submit((-1,));k.advance(frame(3))
        return k

    def test_cash_sale_does_not_replenish_budget_but_intraday_sale_does(self):
        cash=self.round_trip('cash_settled');intraday=self.round_trip('intraday_buying_power')
        self.assertEqual(cash.portfolio,intraday.portfolio)
        self.assertEqual(cash.portfolio.cash,982)
        self.assertEqual(cash.buying_power,91);self.assertEqual(intraday.buying_power,982)
        for k in (cash,intraday):k.submit((1,));k.advance(frame(4))
        self.assertEqual(cash.portfolio.holdings,(0,))
        self.assertEqual(intraday.portfolio.holdings,(9,))
        self.assertLess(intraday.funding_balance,0)
        self.assertEqual(intraday.funding_balance+intraday.pending_sale_proceeds,intraday.portfolio.cash)
        self.assertIn('cash',cash.history[-1].executions[0].outcomes[0].reasons)

    def test_fees_partial_fills_and_no_intraday_settlement_in_cash(self):
        k=self.round_trip('cash_settled',fee='.001')
        self.assertEqual(k.funding_balance,D('90.091'))
        self.assertEqual(k.pending_sale_proceeds,D('890.109'))
        self.assertEqual(k.portfolio.cash,D('980.200'))
        for q in (4,5):k.submit((1,));k.advance(frame(q))
        self.assertEqual(k.buying_power,D('90.091'))
        k.submit((0,));end=k.advance(frame(6));self.assertFalse(end.terminated)
        end=k.advance(frame(7));self.assertTrue(end.terminated)
        self.assertEqual(k.buying_power,D('90.091'))

    def test_same_frame_sales_cannot_fund_cash_buys(self):
        for mode,expected in (('cash_settled',5),('intraday_buying_power',8)):
            k=MaskedReplayKernel(config(('A','B'),horizon=5),frame(1,(book('A'),book('B'))),account_regime=mode)
            k.submit((1,1));k.advance(frame(2,(book('A',2),book('B',2))))
            k.submit((-1,1));k.advance(frame(3,(book('A',3),book('B',3))))
            self.assertEqual(k.portfolio.holdings[1],expected)
            self.assertGreaterEqual(k.portfolio.cash,0)

    def test_masked_failed_fill_does_not_spend_settled_cash(self):
        k=MaskedReplayKernel(config(),frame(1),account_regime='cash_settled')
        k.submit((1,));k.advance(frame(2,()))
        self.assertEqual(k.funding_balance,1000)
        self.assertEqual(k.pending_sale_proceeds,0)
        self.assertEqual(k.portfolio,Portfolio(1000,(0,)))

    def test_new_episode_starts_with_fresh_funds_and_explicit_observation(self):
        for mode in ('cash_settled','intraday_buying_power'):
            e=MaskedDailyReplay(('A',),account_regime=mode,wind_down_points=54).start(date(2025,3,3),day_frames())
            o=e.observation();self.assertEqual(o.account_regime,mode)
            self.assertEqual(o.buying_power,100000);self.assertEqual(o.pending_sale_proceeds,0)
            e.advance((1,));e.advance((-1,))
            self.assertGreater(e.observation().pending_sale_proceeds,0)

    def test_invalid_account_and_negative_limit_rejected(self):
        with self.assertRaises(ValueError):MaskedDailyReplay(('A',),account_regime='margin_4x')
        from rl_boleta.missing_data_replay import PartialExecutionEngine
        engine=PartialExecutionEngine(config())
        with self.assertRaises(ValueError):engine.execute(Portfolio(1000,(0,)),(1,),(100,),frame(1),buying_cash_limit=-1)

    @unittest.skipUnless(importlib.util.find_spec('gymnasium'),'training dependencies required')
    def test_gym_cash_context_cache_and_shared_rule_for_both_modes(self):
        import numpy as np
        from rl_boleta.masked_training import synthetic_sessions,TICKERS
        from rl_boleta.masked_observations import fit_masked_normalizer,MaskedEncoder
        from rl_boleta.cached_observations import CachedMaskedEncoder
        from rl_boleta.masked_env import MaskedTrainingEnv
        s=synthetic_sessions()[0];norm=fit_masked_normalizer((s,),TICKERS)
        for mode in ('cash_settled','intraday_buying_power'):
            enc=MaskedEncoder(norm,include_account_context=True)
            env=MaskedTrainingEnv((s,),enc,account_regime=mode,wind_down_points=54,reward_objective='terminal_cash_utility')
            x,_=env.reset(seed=0);self.assertEqual(x.shape,(15505,))
            cached=CachedMaskedEncoder(norm,s,include_account_context=True)
            for action in ((.2,)*18,(-1,)*18,(1,)*18):
                self.assertTrue(np.array_equal(x,cached.flatten(env.episode.observation(),s.trades)))
                x,_,_,_,info=env.step(action)
                self.assertEqual(info['account_regime'],mode)
            self.assertAlmostEqual(float(x[-1]),env.episode.observation().remaining_transitions/390,places=6)
            with self.assertRaises(ValueError):MaskedEncoder(norm).flatten(env.episode.observation(),s.trades)
        with self.assertRaises(ValueError):MaskedTrainingEnv((s,),MaskedEncoder(norm),account_regime='cash_settled')

    @unittest.skipUnless(importlib.util.find_spec('gymnasium'),'training dependencies required')
    def test_historical_adapter_reads_regime_from_bound_protocol(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from test_historical_env import HistoricalEnvTests
        from rl_boleta.historical_env import HistoricalTrainingEnv
        from rl_boleta.historical_normalization import HistoricalMaskedNormalizer
        from rl_boleta.data_pipeline import digest
        for mode in ('cash_settled','intraday_buying_power'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);normdir,sessions,_=HistoricalEnvTests().fixture(root)
                proto=root/'eligibility/protocol.json';p=json.loads(proto.read_text())
                p['environment'].update(account_regime=mode,reward_objective='terminal_cash_utility')
                p['episode']['wind_down_execution_points']=54;proto.write_text(json.dumps(p))
                mp=root/'eligibility/manifest.json';m=json.loads(mp.read_text())
                m['outputs_sha256']['protocol.json']=digest(proto);mp.write_text(json.dumps(m))
                np=normdir/'normalizer.json';norm=HistoricalMaskedNormalizer.load(np)
                np=normdir/'account-normalizer.json'
                replace(norm,eligibility_sha256=digest(mp)).save(np)
                bundle=normdir/'manifest.json';b=json.loads(bundle.read_text())
                b['outputs_sha256'][np.name]=digest(np)
                b['normalizers']['all_gaps']['file']=np.name
                b['normalizers']['all_gaps']['eligibility_manifest']['sha256']=digest(mp)
                bundle.write_text(json.dumps(b))
                with patch('rl_boleta.historical_env.read_eligible_session',side_effect=lambda directory,day,partition:sessions[day]):
                    env=HistoricalTrainingEnv(normdir,'all_gaps');x,_=env.reset(seed=0)
                    self.assertEqual(x.shape,(1729,));self.assertEqual(env.episode.kernel.account_regime,mode)
                    self.assertEqual(env.episode.kernel.wind_down_points,54)
                    self.assertEqual(env.episode.kernel.reward_objective,'terminal_cash_utility')
                    env.step((1,1));env.step((-1,-1));_,_,_,_,info=env.step((1,1))
                    self.assertEqual(info['account_regime'],mode)
                    env.verify_inputs()


if __name__=='__main__':unittest.main()
