import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from rl_boleta.historical_normalization import (HistoricalMaskedNormalizer,fit_train_normalizers,
    load_train_normalizer)
from rl_boleta.masked_observations import (MaskedNormalizer,MaskedEncoder,MaskedMoments,
    MaskedRow,fit_masked_normalizer,masked_market_rows)
from rl_boleta.masked_training import synthetic_sessions,TICKERS
from rl_boleta.data_pipeline import digest


class HistoricalNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Two accepted fitting dates, one primary-only date: no validation prices needed.
        cls.sessions=synthetic_sessions()[:2]

    def fixture(self,root):
        from test_masked_preparation import protocol
        def child(name,days):
            folder=root/name;folder.mkdir();p=protocol();p['tickers']=list(TICKERS)
            p['episode']['long_gap_policy']['primary_mode']='masked_all_gaps' if name=='all_gaps' else 'bounded_grid_gap'
            p['episode']['long_gap_policy']['primary_cap_minutes']=None if name=='all_gaps' else 2
            (folder/'protocol.json').write_text(json.dumps(p))
            rows=[dict(session_id=str(s.day),partition='train',data_eligible=str(s.day) in days) for s in self.sessions]
            rows.append(dict(session_id='2025-06-02',partition='validation',data_eligible=True))
            rows.append(dict(session_id='2025-07-08',partition='test',data_eligible=True))
            (folder/'sessions.json').write_text(json.dumps(rows))
            m=dict(status='frozen_conditional_eligibility',normalization_date_selection_ready=True,
                prepared_manifest=dict(path='same verified preparation',sha256='a'*64),preparation_protocol_sha256='b'*64,
                primary_rule=dict(mode=p['episode']['long_gap_policy']['primary_mode'],cap_grid_points=p['episode']['long_gap_policy']['primary_cap_minutes']),
                outputs_sha256={p.name:digest(p) for p in folder.iterdir()})
            mp=folder/'manifest.json';mp.write_text(json.dumps(m));return dict(path=str(mp),sha256=digest(mp))
        a=child('all_gaps',{str(s.day) for s in self.sessions});b=child('short_gaps',{str(self.sessions[1].day)})
        manifest=dict(status='frozen_two_scenario_date_design',financial_scores_accessed=False,outputs_sha256={},
            scenario_manifests=dict(all_gaps=a,short_gaps=b))
        (root/'manifest.json').write_text(json.dumps(manifest));return root

    def fit(self,root):
        source=self.fixture(root);visited=[]
        def reader(directory,day,*,partition):
            self.assertEqual(partition,'train');visited.append(day)
            return replace(next(s for s in self.sessions if s.day==day),synthetic=False)
        with patch('rl_boleta.historical_normalization.read_eligible_session',side_effect=reader),contextlib.redirect_stdout(io.StringIO()):
            r=fit_train_normalizers(source,root/'normalizers')
        return r,visited

    def test_streaming_moments_real_zero_and_absence_hand_computation(self):
        acc=MaskedMoments(('A','B'))
        def row(a,b):return MaskedRow(None,(a,)*40+(b,)*40,(a is not None,b is not None),(0.,0.),(0.,0.))
        acc.update(row(0.,2.));acc.update(row(None,4.));acc.update(row(2.,None))
        self.assertEqual(acc.counts,[2]*80);self.assertEqual(acc.means,[1.]*40+[3.]*40)
        self.assertEqual(acc.scales,(1.,)*80)

    def test_separate_exact_dates_population_moments_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r,visited=self.fit(root)
            self.assertEqual(visited,[s.day for s in self.sessions])
            self.assertFalse(r['test_prices_accessed'] or r['validation_prices_accessed'] or r['neural_networks_fitted'])
            a=load_train_normalizer(root/'normalizers','all_gaps');b=load_train_normalizer(root/'normalizers','short_gaps')
            self.assertFalse(a.synthetic_only);self.assertEqual(a.sessions,tuple(str(s.day) for s in self.sessions))
            self.assertEqual(b.sessions,(str(self.sessions[1].day),))
            reference=fit_masked_normalizer((self.sessions[1],),TICKERS)
            self.assertEqual((b.means,b.scales,b.counts),(reference.means,reference.scales,reference.counts))
            self.assertNotEqual(a.eligibility_sha256,b.eligibility_sha256)
            self.assertEqual(a.counts,tuple(2*c for c in b.counts))
            self.assertEqual(r['normalizers']['short_gaps']['unique_feature_points'],387)
            self.assertEqual(r['normalizers']['all_gaps']['unique_feature_points'],774)
            with self.assertRaises(ValueError):MaskedNormalizer.load(root/'normalizers'/r['normalizers']['all_gaps']['file'])
            with self.assertRaises(FileExistsError):a.save(root/'normalizers'/r['normalizers']['all_gaps']['file'])

    def test_frozen_encoding_uses_historical_subclass_and_does_not_mutate(self):
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fit(root);norm=load_train_normalizer(root/'normalizers','all_gaps')
            saved=norm;enc=MaskedEncoder(norm);s=self.sessions[0]
            e=MaskedDailyReplay(TICKERS).start(s.day,s.frames)
            self.assertEqual(len(enc.flatten(e.observation(),s.trades)),15502)
            self.assertEqual(norm,saved)

    def test_partition_gates_and_generic_historical_fit_stay_blocked(self):
        for phase in ('validation','test','final_refit'):
            with self.assertRaises(ValueError):fit_train_normalizers('absent','absent',partition=phase)
        with self.assertRaises(ValueError):fit_masked_normalizer((replace(self.sessions[0],synthetic=False),),TICKERS)
        with self.assertRaises(ValueError):HistoricalMaskedNormalizer(TICKERS,(0.,)*720,(1.,)*720,(1,)*720,'train',('2025-03-03',))

    def test_tampered_artifact_rejected_and_failure_is_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r,_=self.fit(root);path=root/'normalizers'/r['normalizers']['all_gaps']['file'];path.write_text('{}')
            with self.assertRaises(ValueError):load_train_normalizer(root/'normalizers','all_gaps')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with patch('rl_boleta.historical_normalization.read_eligible_session',side_effect=ValueError('bad source')):
                with self.assertRaises(ValueError):fit_train_normalizers(root,root/'failed')
            self.assertEqual(json.loads((root/'failed/manifest.json').read_text())['status'],'failed')

    def test_missing_trades_rejected_even_in_unused_tail(self):
        s=self.sessions[0];trades=dict(s.trades);del trades[s.frames[-1].at,TICKERS[0]]
        with self.assertRaises(ValueError):list(masked_market_rows(replace(s,trades=trades),TICKERS))

    def test_different_preparation_or_feature_rules_rejected_before_reading_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);mp=root/'short_gaps/manifest.json'
            child=json.loads(mp.read_text());child['preparation_protocol_sha256']='c'*64;mp.write_text(json.dumps(child))
            parent=root/'manifest.json';m=json.loads(parent.read_text());m['scenario_manifests']['short_gaps']['sha256']=digest(mp);parent.write_text(json.dumps(m))
            with patch('rl_boleta.historical_normalization.read_eligible_session') as reader:
                with self.assertRaisesRegex(ValueError,'same verified preparation'):fit_train_normalizers(root,root/'output')
                reader.assert_not_called()
            self.assertFalse((root/'output').exists())

    def test_swapping_valid_normalizers_does_not_pass_scenario_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r,_=self.fit(root);folder=root/'normalizers';mp=folder/'manifest.json';m=json.loads(mp.read_text())
            target=folder/m['normalizers']['all_gaps']['file'];source=folder/m['normalizers']['short_gaps']['file']
            target.write_bytes(source.read_bytes());m['outputs_sha256'][target.name]=digest(target);mp.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'binding'):load_train_normalizer(folder,'all_gaps')
