import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rl_boleta.data_pipeline import digest
from rl_boleta.finalize_account_inputs import finalize


class FinalizeInputsTests(unittest.TestCase):
    def fixture(self,root):
        def put(path,obj):path.write_text(json.dumps(obj));return dict(path=str(path.resolve()),sha256=digest(path))
        template=root/'source_protocol.json';template.write_text('original immutable template')
        mutable=root/'working.json';mutable.write_text('a later workspace revision')
        directory=root/'cash_settled';directory.mkdir();normdir=directory/'normalizers';normdir.mkdir()
        proto=put(directory/'protocol.json',dict(environment=dict(account_regime='cash_settled',reward_objective='terminal_cash_utility'),episode=dict(wind_down_execution_points=54)))
        design=root/'design';design.mkdir();dm=put(design/'manifest.json',{})
        scenarios={}
        for name in ('all_gaps','short_gaps'):
            child=design/name;child.mkdir();mp=put(child/'manifest.json',{})
            put(child/'sessions.json',[dict(session_id='2025-03-03',partition='train',data_eligible=True,
                remaining_transitions=300,longest_missing_grid_run=1)])
            scenarios[name]=dict(eligibility_manifest=mp)
        put(normdir/'manifest.json',dict(design_manifest=dm,outputs_sha256={},normalizers=scenarios))
        probes=directory/'train_probes';probes.mkdir()
        put(probes/'report.json',dict(status='historical_training_profile_probes_completed',account_regime='cash_settled',
            models_trained=False,validation_prices_accessed=False,test_prices_accessed=False,full_budget_selection_authorized=False,
            observation_dimension=15505,inputs_sha256={},source_sha256={},
            sessions=[dict(scenario=s,session_id='2025-03-03') for s in scenarios]))
        put(root/'manifest.json',dict(status='account_profiles_and_date_manifests_prepared',
            inputs_sha256={str(mutable):digest(template)},outputs_sha256={'source_protocol.json':digest(template)},
            campaigns=dict(cash_settled=dict(protocol=proto,design_manifest=dm,normalizer_output_dir=str(normdir)))))
        return SimpleNamespace(sessions=('2025-03-03',),counts=(1,),means=(0,),scales=(1,))

    def test_archived_template_and_complete_probe_set_finalize_without_unlocking_fits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);norm=self.fixture(root)
            with patch('rl_boleta.finalize_account_inputs.load_train_normalizer',return_value=norm):
                r=finalize(root);self.assertTrue(r['profile_inputs_verified'])
                self.assertFalse(r['full_budget_selection_authorized']);self.assertEqual(r['total_train_probes'],2)
                self.assertEqual(finalize(root)['status'],r['status'])

    def test_missing_probe_refuses_readiness_and_preserves_parent_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);norm=self.fixture(root);p=root/'cash_settled/train_probes/report.json'
            report=json.loads(p.read_text());report['sessions'].pop();p.write_text(json.dumps(report))
            before=(root/'manifest.json').read_bytes()
            with patch('rl_boleta.finalize_account_inputs.load_train_normalizer',return_value=norm):
                with self.assertRaisesRegex(ValueError,'probe dates'):finalize(root)
            self.assertEqual((root/'manifest.json').read_bytes(),before)

    def test_validation_access_or_profile_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);norm=self.fixture(root);p=root/'cash_settled/train_probes/report.json'
            report=json.loads(p.read_text());report['validation_prices_accessed']=True;p.write_text(json.dumps(report))
            with patch('rl_boleta.finalize_account_inputs.load_train_normalizer',return_value=norm):
                with self.assertRaisesRegex(ValueError,'train-only'):finalize(root)
            (root/'cash_settled/protocol.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):finalize(root)


if __name__=='__main__':unittest.main()
