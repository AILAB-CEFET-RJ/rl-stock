import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from rl_boleta.checkpoint_validation import evaluate, summarize
from rl_boleta.data_pipeline import digest
from rl_boleta.historical_normalization import HistoricalMaskedNormalizer
from test_validation_selection import row, DATES


class FrozenModel:
    def __init__(self):
        self.policy=torch.nn.Linear(4,2)
        self.observation_space=SimpleNamespace(shape=(4,))
        self.action_space=SimpleNamespace(shape=(2,))
        self.num_timesteps=501760; self.device=torch.device('cpu')


class CheckpointValidationTests(unittest.TestCase):
    def fixture(self,root):
        ckpt=root/'checkpoint';ckpt.mkdir();(ckpt/'model.zip').write_bytes(b'fixture model')
        norm=HistoricalMaskedNormalizer(('A','B'),(0.,)*80,(1.,)*80,(1,)*80,'train',
            ('2025-03-03',),False,'all_gaps','1'*64)
        norm.save(ckpt/'normalizer.json')
        report=dict(status='trained_awaiting_validation',scenario='all_gaps',algorithm='PPO',
                    width=128,learning_rate=1e-4,seed=0,requested_transitions=500000,
                    realized_transitions=501760,diagnostic=False,actor_updated=True,
                    checkpoint_prediction_identical=True,
                    artifacts_sha256={p.name:digest(p) for p in ckpt.iterdir()})
        (ckpt/'report.json').write_text(json.dumps(report))
        class Context:
            def __init__(self,*args):
                self.dates=DATES; self.anchors={}
                self.protocol=json.loads(Path('configs/experimental_protocol_v3.json').read_text())
                self.env=SimpleNamespace(encoder=SimpleNamespace(normalizer=norm),
                    economic_options=dict(account_regime='cash_settled'), tickers=('A','B'),
                    observation_space=SimpleNamespace(shape=(4,)),
                    action_space=SimpleNamespace(shape=(2,)),close=lambda:None)
            def evaluate_many(self,models,*,on_day_complete=None):
                values=[row(DATES[0],'.01'),row(DATES[1],'.02',False)]
                for value in values:
                    if on_day_complete:on_day_complete(value['session_id'],dict(checkpoint=value))
                return dict(checkpoint=values)
            def session(self,day):
                if day not in self.dates:raise ValueError('protected date')
                return SimpleNamespace(day=day)
            def replay(self,session,policy):
                return SimpleNamespace(status='scheduled_end',row=row(session.day,'0' if policy.name=='cash' else '.02'))
            def verify_inputs(self):pass
        return ckpt,Context

    def test_frozen_evaluation_retains_failure_and_cannot_select_one_seed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); ckpt,context=self.fixture(root); before=digest(ckpt/'model.zip')
            with patch('rl_boleta.checkpoint_validation.ValidationContext',context), \
                 patch('stable_baselines3.PPO.load',return_value=FrozenModel()), \
                 patch('rl_boleta.checkpoint_validation.result_metrics',side_effect=lambda result:result.row), \
                 patch('rl_boleta.historical_normalization.fit_train_normalizers') as fitter, \
                 redirect_stdout(io.StringIO()):
                result=evaluate(ckpt,'fixture',root/'evaluation',device='cpu',with_baselines=True)
            fitter.assert_not_called()
            self.assertEqual(result['status'],'checkpoint_validation_completed')
            self.assertEqual(len(result['validation']),2)
            self.assertEqual(result['summary']['liquidation_failures'],1)
            self.assertIsNone(result['summary']['mean_realized_return'])
            self.assertFalse(result['summary']['admissibility']['admissible'])
            self.assertFalse(result['test_prices_accessed'] or result['eligible_for_final_refit'])
            self.assertTrue(result['weights_unchanged'])
            self.assertEqual(set(result['baselines']),{'cash','equal_allocation_single_entry'})
            self.assertEqual(before,digest(ckpt/'model.zip'))

    def test_changed_checkpoint_is_rejected_before_loading_or_price_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ckpt,context=self.fixture(root);(ckpt/'model.zip').write_bytes(b'changed')
            with patch('rl_boleta.checkpoint_validation.ValidationContext') as reader, \
                 patch('stable_baselines3.PPO.load') as loader:
                with self.assertRaisesRegex(ValueError,'hash mismatch'):
                    evaluate(ckpt,'fixture',root/'out',device='cpu')
                reader.assert_not_called();loader.assert_not_called()

    def test_normalizer_binding_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ckpt,context=self.fixture(root)
            p=ckpt/'normalizer.json';n=json.loads(p.read_text());n['eligibility_sha256']='2'*64
            p.write_text(json.dumps(n))
            mp=ckpt/'report.json';m=json.loads(mp.read_text());m['artifacts_sha256'][p.name]=digest(p)
            mp.write_text(json.dumps(m))
            with patch('rl_boleta.checkpoint_validation.ValidationContext',context),patch('stable_baselines3.PPO.load') as loader:
                with self.assertRaisesRegex(ValueError,'normalizer differs'):
                    evaluate(ckpt,'fixture',root/'out',device='cpu')
                loader.assert_not_called()

    def test_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out';out.mkdir();(out/'sentinel').write_text('preserved')
            with self.assertRaises(FileExistsError):evaluate('unused','unused',out,device='cpu')
            self.assertEqual((out/'sentinel').read_text(),'preserved')

    def test_realized_mean_uses_full_denominator_only_when_all_flat(self):
        result=summarize([row(DATES[0],'.01'),row(DATES[1],'-.02')])
        self.assertEqual(result['mean_realized_return'],'-0.005')
        self.assertTrue(result['admissibility']['admissible'])
