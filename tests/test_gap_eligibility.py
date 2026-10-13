import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date,timedelta
from pathlib import Path

import test_masked_preparation as fixtures
from rl_boleta.data_pipeline import digest
from rl_boleta.economic_kernel import Book,Level
from rl_boleta.gap_policy_audit import gap_events,run
from rl_boleta.masked_eligibility import GapRule,freeze,read_eligible_session,select_day
from rl_boleta.masked_preparation import prepare,read_prepared_session
from rl_boleta.masked_observations import MaskedMarketSession,fit_masked_normalizer
from rl_boleta.missing_data_replay import PartialFrame
from rl_boleta.session_replay import session_plan


class GapEligibilityTests(unittest.TestCase):
    def test_explicit_rule_and_no_implicit_null_resolution(self):
        self.assertTrue(GapRule('masked_all_gaps').permits(100))
        self.assertFalse(GapRule('bounded_grid_gap',2).permits(3))
        self.assertTrue(GapRule('bounded_grid_gap',2).permits(2))
        for args in [('pending',None),('bounded_grid_gap',None),('bounded_grid_gap',True),('masked_all_gaps',2)]:
            with self.assertRaises(ValueError):GapRule(*args)

    def test_grid_gap_bridges_are_not_intragap_prices(self):
        day=date(2025,3,3);opening=session_plan(day).opening;fs=[]
        for q in range(21,28):
            at=opening+timedelta(minutes=q)
            mid=100 if q==21 else 90
            books=() if q in (22,23,25,26,27) else (Book('A',str(q),at,
                tuple(Level(mid-.01-i*.01,10) for i in range(5)),
                tuple(Level(mid+.01+i*.01,10) for i in range(5))),)
            fs.append(PartialFrame(at,str(day),books))
        events=gap_events(MaskedMarketSession(day,tuple(fs),{},True),fs[0].at,('A',))
        self.assertEqual([e['missing_grid_points'] for e in events],[2,3])
        self.assertEqual(events[0]['endpoint_interval_seconds'],180)
        self.assertAlmostEqual(events[0]['observed_midpoint_change'],-.1)
        self.assertIsNone(events[1]['observed_midpoint_change'])
        self.assertIsNone(events[1]['resumed_at'])

    def test_common_selection_reasons_include_exit_despite_any_strategy(self):
        analysis=dict(entry_index=21,causal_entry_available=True,all_assets_exit_available=True,
            asset_longest_gap_minutes={'A':34})
        row={'raw_files':1}
        self.assertTrue(select_day(row,analysis,GapRule('masked_all_gaps'))[0])
        self.assertEqual(select_day(row,analysis,GapRule('bounded_grid_gap',5))[1],['gap_exceeds_frozen_cap'])
        analysis['all_assets_exit_available']=False
        self.assertEqual(select_day(row,analysis,GapRule('masked_all_gaps'))[1],['missing_common_exit'])
        analysis.update(entry_index=None,causal_entry_available=False)
        self.assertIn('no_causal_warmup',select_day(row,analysis,GapRule('masked_all_gaps'))[1])

    def fixture(self,root):
        a,p,g=fixtures.PreparationTests().fixture(root);prep=root/'prepared'
        with contextlib.redirect_stdout(io.StringIO()):prepare(a,p,g,prep)
        audit=root/'audit_train'
        with contextlib.redirect_stdout(io.StringIO()):r=run(prep,audit)
        self.assertEqual(r['scheduled_sessions'],1)
        self.assertEqual([s['session_id'] for s in r['sessions']],['2025-03-03'])
        d=json.loads(p.read_text());d['episode']['long_gap_policy'].update(status='frozen_for_conditional_v3_simulation',
            primary_mode='masked_all_gaps',primary_cap_minutes=None)
        # A changed protocol must not silently reinterpret old preparation bytes.
        d['purpose']='Resolved conditional eligibility';p.write_text(json.dumps(d))
        out=root/'eligible';m=freeze(prep,audit,p,out)
        return prep,audit,p,out,m

    def test_frozen_roundtrip_old_protocol_snapshot_and_partition_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prep,audit,p,out,m=self.fixture(root)
            self.assertFalse(m['training_ready'])
            self.assertEqual(m['partition_summary']['train']['data_eligible_sessions'],1)
            self.assertEqual(m['partition_summary']['final_refit']['scheduled_sessions'],2)
            self.assertFalse(m['normalization_date_selection_ready'])
            with self.assertRaises(ValueError):read_prepared_session(prep,date(2025,3,3))
            s=read_eligible_session(out,date(2025,3,3),partition='train')
            self.assertFalse(s.synthetic)
            self.assertEqual(len(s.frames),389)
            with self.assertRaises(ValueError):fit_masked_normalizer((s,),('A','B'))
            with self.assertRaises(ValueError):read_eligible_session(out,date(2025,3,3),partition='test')
            with self.assertRaises(ValueError):read_eligible_session(out,date(2025,3,4),partition='validation')
            self.assertEqual(read_eligible_session(out,date(2025,3,3),partition='final_refit'),s)
            p.write_text('later unrelated working protocol change')
            with contextlib.redirect_stdout(io.StringIO()):
                rerun=run(prep,root/'audit_repeat',protocol_snapshot=out/'preparation_protocol.json')
            self.assertEqual(rerun['scheduled_sessions'],1)
            self.assertEqual(read_eligible_session(out,date(2025,3,3),partition='train'),s)
            snapshot=out/'preparation_protocol.json';snapshot.write_text('{}')
            with self.assertRaises(ValueError):read_eligible_session(out,date(2025,3,3),partition='train')

    def test_pending_rule_or_quality_amendment_requires_new_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prep,audit,p,out,m=self.fixture(root);d=json.loads(p.read_text())
            d['episode']['long_gap_policy']['status']='pending';p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):freeze(prep,audit,p,root/'pending')
            d['episode']['long_gap_policy']['status']='frozen_for_conditional_v3_simulation'
            d['data']['maximum_receipt_age_seconds']=120;p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'rebuild'):freeze(prep,audit,p,root/'changed')

    def test_numbered_evidence_link_keeps_old_grid_compatible_without_relaxing_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prep,audit,p,out,m=self.fixture(root)
            d=json.loads(p.read_text());d['data']['timing_evidence']='docs/clock_transition_audit.md'
            p.write_text(json.dumps(d))
            updated=freeze(prep,audit,p,root/'evidence-link-renamed')
            self.assertEqual(updated['partition_summary'],m['partition_summary'])
            d['data']['timing_evidence']='docs/another_clock_hypothesis.md'
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'rebuild'):
                freeze(prep,audit,p,root/'changed-evidence')

    def test_snapshot_substitution_requires_original_producer_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prep,audit,p,out,m=self.fixture(root);bad=root/'bad.json'
            different=fixtures.protocol();different['data']['maximum_receipt_age_seconds']=120
            bad.write_text(json.dumps(different))
            with self.assertRaises(ValueError):read_prepared_session(prep,date(2025,3,3),protocol_snapshot=bad)
