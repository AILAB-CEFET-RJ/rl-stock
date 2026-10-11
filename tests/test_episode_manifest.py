"""Coverage gates and provenance, without historical returns or policies."""
import contextlib
import copy
import gzip
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from rl_boleta.data_pipeline import digest, iso
from rl_boleta.episode_manifest import build_manifest
from rl_boleta.session_replay import session_plan


class EpisodeManifestTests(unittest.TestCase):
    def fixture(self, root, gaps=None, missing_days=(), first=date(2025, 3, 3)):
        root = Path(root)
        adapter = root/'canonical'; adapter.mkdir()
        protocol = json.loads((Path(__file__).resolve().parents[1]/'configs/experimental_protocol_v2.json').read_text())
        protocol['tickers'] = ['AAPL']
        days = [first+timedelta(days=i) for i in range(3)]
        for key, day in zip(('train', 'validation', 'test'), days):
            protocol['partitions'][key] = dict(first=str(day), last=str(day), scheduled_sessions=1, minimum_eligible_sessions=1)
        protocol['partitions']['final_refit'] = dict(first=str(days[0]), last=str(days[1]), scheduled_sessions=2)
        path = root/'protocol.json'; path.write_text(json.dumps(protocol))
        manifest = dict(status='provisional_converted', training_ready=False,
            config=dict(tickers=['AAPL'], max_spread_bps=500, max_depth_distance_bps=500,
                        book_levels=5, recent_trades=10),
            timing=dict(collection_timezone='America/Sao_Paulo', trade_timezone='America/New_York',
                        collection_timezone_status='hypothesis', trade_timezone_status='hypothesis',
                        source_delay_seconds=10800, source_delay_interpretation='unresolved'),
            inputs=[], outputs={}, counts={}, rejection_reasons={})
        for day in days:
            if day in missing_days:
                continue
            raw = root/f'data_scrapping_{day.day}_{day.month}_{day.year}.parquet'
            raw.write_bytes(f'synthetic provenance placeholder {day}'.encode())
            index = len(manifest['inputs'])
            manifest['inputs'].append(dict(path=str(raw), sha256=digest(raw), counts={}))
            name = f'snapshots_{index:04d}_{raw.stem}.jsonl.gz'
            with gzip.open(adapter/name, 'wt') as handle:
                for at in session_plan(day).required_times:
                    if at in (gaps or {}).get(day, ()):
                        continue
                    record = dict(schema_version=1, ticker='AAPL', snapshot_id=iso(at), source='synthetic',
                        available_at=iso(at), book_at=None,
                        bids=[dict(price=99.99-i*.01, size=100) for i in range(5)],
                        asks=[dict(price=100.01+i*.01, size=100) for i in range(5)],
                        trades=[dict(at=iso(at), price=100, size=10) for _ in range(10)])
                    handle.write(json.dumps(record)+'\n')
            manifest['outputs'][name] = digest(adapter/name)
        (adapter/'manifest.json').write_text(json.dumps(manifest))
        return adapter, path, root/'episodes'

    def run_manifest(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return build_manifest(*args)

    def test_complete_sessions_opening_optional_and_partition_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.fixture(folder)
            result = self.run_manifest(args)
            self.assertTrue(result['coverage_feasible'])
            self.assertFalse(result['training_ready'])
            summary = result['partition_summary']
            self.assertEqual(summary['train']['evaluable_sessions'], 1)
            self.assertEqual(summary['train']['valid_grid_points'], 389)
            self.assertEqual(summary['train']['expected_grid_points'], 390)
            self.assertEqual(summary['final_refit']['scheduled_sessions'], 2)
            for name, sha in result['outputs'].items():
                self.assertEqual(digest(args[2]/name), sha)
            with self.assertRaises(FileExistsError):
                self.run_manifest(args)

    def test_gap_preserves_missing_date_denominator_and_trace_causality(self):
        with tempfile.TemporaryDirectory() as folder:
            day, missing = date(2025, 3, 4), date(2025, 3, 5)
            fail = session_plan(day).first_decision+timedelta(minutes=10)
            args = self.fixture(folder, gaps={day:{fail, fail-timedelta(minutes=1)}}, missing_days={missing})
            result = self.run_manifest(args)
            self.assertFalse(result['coverage_feasible'])
            self.assertEqual(result['partition_summary']['validation']['startable_sessions'], 1)
            self.assertEqual(result['partition_summary']['validation']['evaluable_sessions'], 0)
            test = result['partition_summary']['test']
            self.assertEqual((test['scheduled_sessions'], test['sessions_with_raw_files'], test['valid_required_points']), (1, 0, 0))
            validation = json.loads((args[2]/'validation.json').read_text())['sessions'][0]
            self.assertEqual(validation['first_runtime_failure'], iso(fail))
            with gzip.open(args[2]/'alignment_trace.jsonl.gz', 'rt') as handle:
                trace = [json.loads(line) for line in handle]
            self.assertFalse(any(t['session_id']==str(day) and t['decision_at']==iso(fail) for t in trace))
            self.assertTrue(all(t['snapshots']['AAPL']['available_at'] <= t['decision_at'] for t in trace))

    def test_missing_lag_reference_never_shifts_warmup(self):
        with tempfile.TemporaryDirectory() as folder:
            day = date(2025, 3, 3)
            args = self.fixture(folder, gaps={day:{session_plan(day).first_required}})
            result = self.run_manifest(args)
            self.assertEqual(result['partition_summary']['train']['startable_sessions'], 0)
            record = json.loads((args[2]/'train.json').read_text())['sessions'][0]
            self.assertEqual(record['first_decision_at'], iso(session_plan(day).first_decision))

    def test_missing_exit_excludes_complete_session(self):
        with tempfile.TemporaryDirectory() as folder:
            day = date(2025, 3, 3); end = session_plan(day).liquidation
            args = self.fixture(folder, gaps={day:{end, end-timedelta(minutes=1)}})
            result = self.run_manifest(args)
            self.assertEqual(result['partition_summary']['train']['startable_sessions'], 1)
            self.assertEqual(result['partition_summary']['train']['evaluable_sessions'], 0)
            record = json.loads((args[2]/'train.json').read_text())['sessions'][0]
            self.assertFalse(record['liquidation_observation_valid'])

    def test_short_session_has_209_required_points(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_manifest(self.fixture(folder, first=date(2025, 7, 1)))
            self.assertEqual(result['partition_summary']['test']['required_points'], 209)
            self.assertEqual(result['partition_summary']['test']['expected_grid_points'], 210)

    def test_tampered_input_or_manifest_configuration_rejected(self):
        for tamper in ('raw', 'canonical', 'config', 'status'):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as folder:
                args = self.fixture(folder)
                manifest_path = args[0]/'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                if tamper == 'raw':
                    Path(manifest['inputs'][0]['path']).write_bytes(b'changed')
                elif tamper == 'canonical':
                    (args[0]/next(iter(manifest['outputs']))).write_bytes(b'changed')
                else:
                    if tamper == 'config':
                        manifest['config']['tickers'] = ['TSLA']
                    else:
                        manifest['status'] = 'in_progress'
                    manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    self.run_manifest(args)

    def test_overlap_and_calendar_count_mismatch_rejected(self):
        for tamper in ('overlap', 'count'):
            with tempfile.TemporaryDirectory() as folder:
                args = self.fixture(folder)
                protocol = json.loads(args[1].read_text())
                if tamper == 'overlap':
                    protocol['partitions']['validation']['first'] = '2025-03-03'
                else:
                    protocol['partitions']['train']['scheduled_sessions'] = 2
                args[1].write_text(json.dumps(protocol))
                with self.assertRaises(ValueError):
                    self.run_manifest(args)
