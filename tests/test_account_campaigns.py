import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from rl_boleta.account_campaigns import profile,prepare_accounts
from rl_boleta.masked_eligibility import observation_episode_signature


class AccountCampaignTests(unittest.TestCase):
    def template(self):return json.loads(Path('configs/experimental_protocol_v3.json').read_text())

    def test_profiles_register_controls_and_preserve_market_grid_and_template(self):
        original=self.template();before=deepcopy(original)
        for mode in ('cash_settled','intraday_buying_power'):
            p=profile(original,mode)
            self.assertEqual(p['environment']['account_regime'],mode)
            self.assertEqual(p['environment']['reward_objective'],'terminal_cash_utility')
            self.assertEqual(p['episode']['normal']['last_intention_index'],334)
            self.assertEqual(p['episode']['early_close_2025_07_03']['last_regular_fill_index'],155)
            self.assertEqual(observation_episode_signature(p),observation_episode_signature(original))
            self.assertTrue(p['day_trading_review']['full_budget_selection_blocked'])
            self.assertNotIn('train_artifact',p['normalization'])
        self.assertEqual(original,before)
        with self.assertRaises(ValueError):profile(original,'legacy_reinvest')

    def test_grid_change_or_inconsistent_execution_bounds_are_not_silently_accepted(self):
        original=self.template();p=profile(original,'cash_settled')
        p['episode']['normal']['last_intention_index']=387
        with self.assertRaisesRegex(ValueError,'bounds'):observation_episode_signature(p)
        p=profile(original,'cash_settled');p['episode']['normal']['liquidation_index']=388
        with self.assertRaises(ValueError):observation_episode_signature(p)
        p=profile(original,'cash_settled');p['episode']['window_features']=10
        self.assertNotEqual(observation_episode_signature(p),observation_episode_signature(original))
        p=profile(original,'cash_settled');p['episode']['wind_down_execution_points']=True
        with self.assertRaises(ValueError):observation_episode_signature(p)

    def test_outputs_are_new_and_input_template_stays_unchanged(self):
        def build(prep,audit,protocol,out):
            out.mkdir();(out/'common_dates.json').write_text(json.dumps({'train':['2025-03-03']}))
            (out/'manifest.json').write_text('{}')
            return dict(common_date_counts={'train':1},computed_budget={'total':286})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);proto=root/'protocol.json';proto.write_text(json.dumps(self.template()))
            for name in ('prepared','audit'):
                (root/name).mkdir();(root/name/'manifest.json').write_text('{}')
            before=proto.read_bytes();out=root/'profiles'
            with patch('rl_boleta.account_campaigns.build',side_effect=build):
                result=prepare_accounts(root/'prepared',root/'audit',proto,out)
                self.assertEqual(set(result['campaigns']),{'cash_settled','intraday_buying_power'})
                self.assertTrue(result['normalization_pending'])
                self.assertFalse(result['full_budget_selection_authorized'])
                with self.assertRaises(FileExistsError):prepare_accounts(root/'prepared',root/'audit',proto,out)
            self.assertEqual(proto.read_bytes(),before)


if __name__=='__main__':unittest.main()
