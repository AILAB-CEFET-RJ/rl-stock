"""End-to-end smoke regression: training and frozen replay share account context."""
import importlib.util
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

AVAILABLE=all(importlib.util.find_spec(n) for n in ('gymnasium','stable_baselines3','torch','numpy'))


@unittest.skipUnless(AVAILABLE,'training dependencies required')
class HistoricalTrainingTests(unittest.TestCase):
    def test_checkpoint_frozen_replay_exposes_account_context_in_both_modes(self):
        from test_historical_env import HistoricalEnvTests
        from rl_boleta.data_pipeline import digest
        from rl_boleta.historical_normalization import HistoricalMaskedNormalizer
        from rl_boleta.historical_training import run_historical_smoke
        for mode in ('cash_settled','intraday_buying_power'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);normdir,sessions,_=HistoricalEnvTests().fixture(root)
                proto=root/'eligibility/protocol.json';p=json.loads(proto.read_text())
                p['environment'].update(account_regime=mode,reward_objective='terminal_cash_utility')
                p['episode']['wind_down_execution_points']=54;proto.write_text(json.dumps(p))
                mp=root/'eligibility/manifest.json';m=json.loads(mp.read_text())
                m['outputs_sha256']['protocol.json']=digest(proto);mp.write_text(json.dumps(m))
                norm=HistoricalMaskedNormalizer.load(normdir/'normalizer.json')
                np=normdir/'account-normalizer.json';replace(norm,eligibility_sha256=digest(mp)).save(np)
                bundle=normdir/'manifest.json';b=json.loads(bundle.read_text())
                b['outputs_sha256'][np.name]=digest(np)
                b['normalizers']['all_gaps'].update(file=np.name,eligibility_manifest=dict(path=str(mp),sha256=digest(mp)))
                bundle.write_text(json.dumps(b))
                with patch('rl_boleta.historical_env.read_eligible_session',side_effect=lambda directory,day,partition:sessions[day]):
                    report=run_historical_smoke(root/'smoke',normdir,'all_gaps',384,0,'PPO')
                self.assertEqual(report['account_regime'],mode)
                self.assertEqual(report['observation_shape'],[1729])
                self.assertEqual(report['reward_objective'],'terminal_cash_utility')
                self.assertEqual(report['wind_down_execution_points'],54)
                self.assertTrue(report['checkpoint_prediction_identical'])
                self.assertTrue(report['actor_changed'])
                self.assertTrue(report['frozen_evaluation'])
                self.assertFalse(report['validation_prices_accessed'] or report['test_prices_accessed'])
                self.assertLessEqual(set(r['session_id'] for r in report['frozen_evaluation']),set(report['sampling_order']))


if __name__=='__main__':unittest.main()
