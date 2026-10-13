import contextlib
import csv
import gzip
import io
import json
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path

from rl_boleta.data_pipeline import digest,iso
from rl_boleta.masked_preparation import align_partial,config_for,prepare,read_prepared_session
from rl_boleta.masked_observations import fit_masked_normalizer
from rl_boleta.session_replay import session_plan


def snapshot(day,q,ticker='A'):
    at=session_plan(day).opening+timedelta(minutes=q)
    return dict(schema_version=1,snapshot_id=f'{day}-{ticker}-{q}',ticker=ticker,source='synthetic fixture',
        available_at=iso(at),book_at=None,
        bids=[dict(price=99.99-i*.01,size=1000) for i in range(5)],
        asks=[dict(price=100.01+i*.01,size=1000) for i in range(5)],
        trades=[dict(price=100,size=10,at=iso(at)) for _ in range(10)])


def protocol():
    p=json.loads(Path('configs/experimental_protocol_v3.json').read_text());p['tickers']=['A','B']
    for part,first,last,count in [('train','2025-03-03','2025-03-03',1),('validation','2025-03-04','2025-03-04',1),
        ('test','2025-03-05','2025-03-05',1),('final_refit','2025-03-03','2025-03-04',2)]:
        p['partitions'][part].update(first=first,last=last,scheduled_sessions=count)
    return p


class PreparationTests(unittest.TestCase):
    def test_causal_per_asset_alignment_age_cutoff_and_no_preopen(self):
        day=date(2025,3,3);p=protocol();cfg=config_for(p,day)
        s,refs=align_partial(day,[snapshot(day,0),snapshot(day,1,'B'),snapshot(day,4)],cfg)
        self.assertEqual([len(f.books) for f in s.frames[:5]],[2,1,0,1,1])
        self.assertEqual(s.frames[1].books[0].ticker,'B')
        self.assertFalse(s.synthetic)
        changed,_=align_partial(day,[snapshot(day,0),snapshot(day,1,'B'),snapshot(day,4),snapshot(day,100,'B')],cfg)
        self.assertEqual(s.frames[:99],changed.frames[:99])
        pre=snapshot(day,-1);s,_=align_partial(day,[pre],cfg)
        self.assertTrue(all(not f.books for f in s.frames))
        with self.assertRaises(ValueError):align_partial(day,[snapshot(day+timedelta(days=1),1)],cfg)

    def fixture(self,root):
        adapter=root/'adapter';audit=root/'audit';adapter.mkdir();audit.mkdir();p=protocol()
        pp=root/'protocol.json';pp.write_text(json.dumps(p));inputs=[];outputs={};rows=[]
        for day in (date(2025,3,3),date(2025,3,4),date(2025,3,5)):
            snapshots=[]
            if day.day!=4:
                snapshots=[snapshot(day,q,t) for q in range(1,390) for t in ('A','B')
                    if not (day.day==5 and t=='B' and q>=388)]
                raw=root/f'data_scrapping_{day.day}_3_2025.parquet';raw.write_text('fixture')
                name=f'snapshots_{len(inputs):04d}_{raw.stem}.jsonl.gz'
                with gzip.open(adapter/name,'wt') as handle:
                    for s in snapshots:handle.write(json.dumps(s)+'\n')
                inputs.append(dict(path=str(raw),sha256=digest(raw)));outputs[name]=digest(adapter/name)
            _,refs=align_partial(day,snapshots,config_for(p,day))
            for r in refs:
                for t in p['tickers']:rows.append(dict(session_id=str(day),decision_at=r['at'],ticker=t,
                    state='valid' if t in r['snapshots'] else 'no_recent_capture'))
        a=dict(status='provisional_converted',inputs=inputs,outputs=outputs,
            timing=dict(collection_timezone='America/Sao_Paulo',trade_timezone='America/New_York',source_delay_seconds=10800),
            config=dict(tickers=p['tickers'],max_spread_bps=500,max_depth_distance_bps=500,book_levels=5,recent_trades=10))
        (adapter/'manifest.json').write_text(json.dumps(a))
        with gzip.open(audit/'asset_grid.csv.gz','wt',newline='') as handle:
            w=csv.DictWriter(handle,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        m=dict(status='diagnostic_only',source_manifests={str(adapter/'manifest.json'):digest(adapter/'manifest.json')},
            outputs_sha256={'asset_grid.csv.gz':digest(audit/'asset_grid.csv.gz')})
        (audit/'manifest.json').write_text(json.dumps(m));return adapter,pp,audit

    def test_manifest_roundtrip_missing_day_and_exit_fitting_gate_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a,p,g=self.fixture(root);out=root/'output'
            with contextlib.redirect_stdout(io.StringIO()):m=prepare(a,p,g,out)
            self.assertEqual(m['status'],'provisional_partial_grid');self.assertFalse(m['training_ready'])
            self.assertTrue(m['reference_availability_reproduced'])
            self.assertEqual(m['adapter_timing_metadata']['source_delay_seconds'],10800)
            self.assertIsNone(m['effective_timing']['source_delay_seconds'])
            self.assertEqual(m['effective_timing']['source_delay_correction'],'none')
            self.assertEqual([r['masked_coverage_candidate'] for r in m['sessions']],[True,False,False])
            missing=read_prepared_session(out,date(2025,3,4))
            self.assertEqual(len(missing.frames),389);self.assertFalse(any(f.books for f in missing.frames))
            valid=read_prepared_session(out,date(2025,3,3));self.assertFalse(valid.synthetic)
            self.assertEqual(valid.frames[0].books[0].available_at,valid.frames[0].at)
            with self.assertRaises(ValueError):fit_masked_normalizer((valid,),('A','B'))
            with self.assertRaises(FileExistsError):prepare(a,p,g,out)
            target=out/m['sessions'][0]['grid_file'];target.write_bytes(b'tampered')
            with self.assertRaises(ValueError):read_prepared_session(out,date(2025,3,3))

    def test_disagreement_with_verified_grid_fails_without_completed_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a,p,g=self.fixture(root)
            with gzip.open(g/'asset_grid.csv.gz','rt') as handle:rows=list(csv.DictReader(handle))
            rows[0]['state']='no_recent_capture'
            with gzip.open(g/'asset_grid.csv.gz','wt',newline='') as handle:
                w=csv.DictWriter(handle,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            mp=g/'manifest.json';m=json.loads(mp.read_text());m['outputs_sha256']['asset_grid.csv.gz']=digest(g/'asset_grid.csv.gz');mp.write_text(json.dumps(m))
            with self.assertRaises(ValueError):prepare(a,p,g,root/'output')
            self.assertEqual(json.loads((root/'output/manifest.json').read_text())['status'],'failed')

    def test_canonical_or_raw_tampering_rejected(self):
        for kind in ('canonical','raw'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);a,p,g=self.fixture(root)
                m=json.loads((a/'manifest.json').read_text())
                target=a/next(iter(m['outputs'])) if kind=='canonical' else Path(m['inputs'][0]['path'])
                target.write_bytes(b'tampered')
                with self.assertRaises(ValueError):prepare(a,p,g,root/'output')

    def test_quality_failure_not_repaired_or_converted_to_a_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a,p,g=self.fixture(root);mp=a/'manifest.json';m=json.loads(mp.read_text())
            name=next(iter(m['outputs']))
            with gzip.open(a/name,'rt') as handle:rows=[json.loads(line) for line in handle]
            rows[0]['asks'][0]['price']=rows[0]['bids'][0]['price']
            with gzip.open(a/name,'wt') as handle:
                for r in rows:handle.write(json.dumps(r)+'\n')
            m['outputs'][name]=digest(a/name);mp.write_text(json.dumps(m))
            gp=g/'manifest.json';audit=json.loads(gp.read_text());audit['source_manifests'][str(mp)]=digest(mp);gp.write_text(json.dumps(audit))
            with self.assertRaisesRegex(ValueError,'rejected or duplicated'):
                prepare(a,p,g,root/'output')
            self.assertEqual(json.loads((root/'output/manifest.json').read_text())['status'],'failed')

    def test_overlap_and_relaxed_age_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a,p,g=self.fixture(root);data=json.loads(p.read_text())
            data['partitions']['validation']['first']='2025-03-03';p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'chronological'):prepare(a,p,g,root/'output')
        data=protocol();data['data']['maximum_receipt_age_seconds']=120
        with self.assertRaises(ValueError):config_for(data,date(2025,3,3))
