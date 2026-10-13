import contextlib
import csv
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path

import test_masked_preparation as fixtures
from rl_boleta.data_pipeline import digest
from rl_boleta.gap_policy_audit import run
from rl_boleta.masked_preparation import prepare
from rl_boleta.scenario_manifests import budget,build


class ScenarioTests(unittest.TestCase):
    def test_budget_counts_fits_seeds_and_transitions(self):
        p=fixtures.protocol();r=budget(p)
        self.assertEqual((r['all_gaps']['tuning'],r['all_gaps']['final']),(108,90))
        self.assertEqual((r['short_gaps']['tuning'],r['short_gaps']['final']),(48,40))
        self.assertEqual(r['total'],286)
        self.assertEqual(r['requested_environment_transitions'],208000000)

    def fixture(self,root):
        a,p,g=fixtures.PreparationTests().fixture(root)
        mp=a/'manifest.json';m=json.loads(mp.read_text());name=next(iter(m['outputs']))
        with gzip.open(a/name,'rt') as handle:rows=[json.loads(line) for line in handle]
        # Accepted receipt at q=29 remains usable at q=30. Absence is q31..33.
        rows=[r for r in rows if not (r['ticker']=='A' and r['snapshot_id'].rsplit('-',1)[-1] in ('30','31','32','33'))]
        with gzip.open(a/name,'wt') as handle:
            for r in rows:handle.write(json.dumps(r)+'\n')
        m['outputs'][name]=digest(a/name);mp.write_text(json.dumps(m))
        gp=g/'asset_grid.csv.gz'
        with gzip.open(gp,'rt') as handle:grid=list(csv.DictReader(handle))
        from datetime import date,timedelta
        from rl_boleta.data_pipeline import iso
        from rl_boleta.session_replay import session_plan
        missing={iso(session_plan(date(2025,3,3)).opening+timedelta(minutes=q)) for q in (31,32,33)}
        for r in grid:
            if r['session_id']=='2025-03-03' and r['ticker']=='A' and r['decision_at'] in missing:r['state']='no_recent_capture'
        with gzip.open(gp,'wt',newline='') as handle:
            w=csv.DictWriter(handle,fieldnames=list(grid[0]));w.writeheader();w.writerows(grid)
        ap=g/'manifest.json';audit=json.loads(ap.read_text());audit['source_manifests'][str(mp)]=digest(mp)
        audit['outputs_sha256'][gp.name]=digest(gp);ap.write_text(json.dumps(audit))
        prep=root/'prepared';train=root/'train_audit'
        with contextlib.redirect_stdout(io.StringIO()):prepare(a,p,g,prep);run(prep,train)
        return prep,train,p

    def test_separate_selection_common_dates_and_bounded_sensitivities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prep,train,p=self.fixture(root);out=root/'design'
            r=build(prep,train,p,out)
            self.assertFalse(r['training_ready']);self.assertFalse(r['financial_scores_accessed'])
            primary=r['scenario_manifests']['all_gaps']['partition_summary']['train']
            short=r['scenario_manifests']['short_gaps']['partition_summary']['train']
            self.assertEqual(primary['data_eligible_sessions'],1)
            self.assertEqual(short['data_eligible_sessions'],0)
            self.assertEqual(r['common_date_counts']['test'],0)
            self.assertEqual(json.loads((out/'common_dates.json').read_text())['train'],[])
            ss=json.loads((out/'short_gaps/sensitivities.json').read_text())
            self.assertTrue(all(not parts['train'] for parts in ss.values()))
            rows=json.loads((out/'short_gaps/sessions.json').read_text())
            self.assertIn('gap_exceeds_frozen_cap',rows[0]['exclusion_reasons'])
            self.assertEqual(json.loads((out/'short_gaps/protocol.json').read_text())['episode']['long_gap_policy']['primary_cap_minutes'],2)
            self.assertIsNone(json.loads((out/'all_gaps/protocol.json').read_text())['episode']['long_gap_policy']['primary_cap_minutes'])
            with self.assertRaises(FileExistsError):build(prep,train,p,out)

    def test_bad_budget_or_algorithm_set_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'protocol.json';data=fixtures.protocol()
            data['planned_fits']['short_gaps']['total']=89;p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'budget'):build(root/'absent',root/'absent',p,root/'out')
            data=fixtures.protocol();data['experimental_scenarios']['scenarios']['short_gaps']['algorithms']=['PPO'];p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'algorithm'):build(root/'absent',root/'absent',p,root/'out')
            self.assertFalse((root/'out').exists())
