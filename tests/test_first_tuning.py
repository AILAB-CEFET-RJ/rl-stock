import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from rl_boleta.account_campaigns import profile
from rl_boleta.data_pipeline import digest
from rl_boleta.first_tuning import run


class FirstTuningTests(unittest.TestCase):
    def fixture(self, root):
        inputs = root / 'inputs'; inputs.mkdir()
        template = json.loads(Path('configs/experimental_protocol_v3.json').read_text())
        proto = inputs / 'protocol.json'
        proto.write_text(json.dumps(profile(template, 'cash_settled')))
        normalizers = inputs / 'normalizers'; normalizers.mkdir()
        nm = normalizers / 'manifest.json'; nm.write_text('{}')
        campaign = dict(protocol=dict(path=str(proto), sha256=digest(proto)),
                        normalizer_manifest=dict(path=str(nm), sha256=digest(nm)),
                        normalizer_output_dir=str(normalizers))
        (inputs/'manifest.json').write_text(json.dumps(dict(
            status='account_profile_inputs_and_train_probes_verified', profile_inputs_verified=True,
            campaigns=dict(cash_settled=campaign))))
        return inputs

    def test_launch_uses_registered_full_budget_and_never_selects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = self.fixture(root)
            before = digest(inputs/'manifest.json')
            with patch('torch.cuda.is_available', return_value=True), \
                 patch('rl_boleta.first_tuning.train_job', return_value=dict(realized_transitions=501760)) as worker, \
                 redirect_stdout(io.StringIO()):
                state = run(root/'output', inputs)
            context, job, steps, diagnostic, out = worker.call_args.args
            self.assertEqual(job['device'], 'cuda')
            self.assertEqual((job['algorithm'],job['width'],job['learning_rate'],job['seed']), ('PPO',128,1e-4,0))
            self.assertEqual(steps,500000); self.assertFalse(diagnostic)
            self.assertEqual(state['status'],'trained_awaiting_validation')
            self.assertFalse(state['validation_prices_accessed'] or state['test_prices_accessed'])
            self.assertFalse(state['eligible_for_final_refit'])
            self.assertEqual(before,digest(inputs/'manifest.json'))

    def test_failure_is_recorded_and_existing_run_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); inputs=self.fixture(root); out=root/'output'
            with patch('torch.cuda.is_available',return_value=True), \
                 patch('rl_boleta.first_tuning.train_job',side_effect=RuntimeError('fixture failure')), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'fixture failure'):run(out,inputs)
            state=json.loads((out/'launch.json').read_text())
            self.assertEqual(state['status'],'training_failed')
            before=digest(out/'launch.json')
            with self.assertRaises(FileExistsError):run(out,inputs)
            self.assertEqual(before,digest(out/'launch.json'))

    def test_unverified_inputs_never_start_training(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inputs=self.fixture(root)
            mp=inputs/'manifest.json';m=json.loads(mp.read_text());m['profile_inputs_verified']=False
            mp.write_text(json.dumps(m))
            with patch('rl_boleta.first_tuning.train_job') as worker:
                with self.assertRaises(ValueError):run(root/'output',inputs)
                worker.assert_not_called()
            self.assertFalse((root/'output').exists())
