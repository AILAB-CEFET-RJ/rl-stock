import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rl_boleta.data_pipeline import Config, digest
from rl_boleta.parquet_adapter import Timing, convert
from rl_boleta.workstation_adapter import export_reference, rebuild, semantic_hash


def capture():
    return pd.DataFrame({
        'File_Date': ['2025-06-27 10:30:01'] * 10,
        'Company': ['APPLE INC COM'] * 10, 'Date': ['2025-06-27'] * 10,
        'Time': ['09:30:00'] * 10, 'Shares_Top_of_Book': [100.0] * 10,
        'Prices_Top_of_Book': [100.05, 100.04, 100.03, 100.02, 100.01,
                              99.99, 99.98, 99.97, 99.96, 99.95],
        'Price_of_One_Share': [100.0] * 10, 'Number_of_Shares_Sold': [1.0] * 10,
        'Transaction_type': ['asks'] * 5 + ['bids'] * 5,
    })


class WorkstationAdapterTests(unittest.TestCase):
    def fixture(self, root):
        original = root.resolve() / 'mac'; remote = root.resolve() / 'linux'
        for p in (original, remote):
            (p / 'data').mkdir(parents=True)
        raw = original / 'data/data_scrapping_27_6_2025.parquet'
        bad = capture(); bad['File_Date'] = '2025-06-27 10:31:01'
        bad.loc[0, 'Prices_Top_of_Book'] = float('nan')
        pd.concat([capture(), bad], ignore_index=True).to_parquet(raw)
        source = original / 'canonical'
        convert([raw], source, Config(('AAPL',), 500, 500),
                Timing('America/Sao_Paulo', 'America/New_York'))
        ref = root / 'reference'
        export_reference(source, original, ref)
        shutil.copy2(raw, remote / 'data' / raw.name)
        return source, ref, remote

    def rewrite_reference(self, directory, transform):
        path = directory / 'reference.json'
        data = json.loads(path.read_text()); transform(data)
        path.write_text(json.dumps(data))
        mp = directory / 'manifest.json'; m = json.loads(mp.read_text())
        m['outputs_sha256'][path.name] = digest(path)
        mp.write_text(json.dumps(m))

    def test_rebuild_at_new_root_preserves_all_data_and_rejections(self):
        with tempfile.TemporaryDirectory() as temp:
            source, ref, remote = self.fixture(Path(temp))
            before = {p.name: digest(p) for p in source.iterdir()}
            out = remote / 'canonical'
            report = rebuild(ref, remote, out)
            self.assertEqual(report['status'], 'canonical_rebuild_verified')
            self.assertEqual(report['accepted_snapshots'], 1)
            self.assertFalse(report['full_budget_selection_authorized'])
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['counts']['rejected'], 1)
            self.assertTrue(all(Path(i['path']).is_relative_to(remote) for i in manifest['inputs']))
            self.assertEqual(before, {p.name: digest(p) for p in source.iterdir()})

    def test_changed_raw_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            _, ref, remote = self.fixture(Path(temp))
            next((remote / 'data').iterdir()).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                rebuild(ref, remote, remote / 'out')
            self.assertFalse((remote / 'out').exists())

    def test_changed_reference_semantics_block_success(self):
        with tempfile.TemporaryDirectory() as temp:
            _, ref, remote = self.fixture(Path(temp))
            self.rewrite_reference(ref, lambda r: r['signature']['counts'].update(accepted=2))
            out = remote / 'out'
            with self.assertRaisesRegex(ValueError, 'semantics differ'):
                rebuild(ref, remote, out)
            report = json.loads((out / 'relocation_report.json').read_text())
            self.assertEqual(report['status'], 'canonical_rebuild_failed')
            self.assertEqual(json.loads((out / 'manifest.json').read_text())['status'],
                             'relocation_verification_failed')

    def test_source_path_is_only_ignored_field(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = dict(bids=[dict(price=10, size=3)], available_at='2025-06-27T13:30:01Z',
                          provenance=dict(source_file='/mac/data/a.parquet', source_sha256='abc'))
            def write():
                path = root / 'records.jsonl.gz'
                with gzip.open(path, 'wt') as f:
                    f.write(json.dumps(record) + '\n')
                return semantic_hash(path, snapshots=True)
            before = write()
            record['provenance']['source_file'] = '/linux/data/a.parquet'
            self.assertEqual(before, write())
            record['bids'][0]['size'] = 4
            self.assertNotEqual(before, write())
            record['bids'][0]['size'] = 3
            record['provenance']['source_sha256'] = 'different'
            self.assertNotEqual(before, write())

    def test_no_overwrite_of_previous_output(self):
        with tempfile.TemporaryDirectory() as temp:
            _, ref, remote = self.fixture(Path(temp))
            out = remote / 'out'; out.mkdir()
            (out / 'sentinel').write_text('preserved')
            with self.assertRaises(FileExistsError):
                rebuild(ref, remote, out)
            self.assertEqual(list(out.iterdir()), [out / 'sentinel'])

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, ref, remote = self.fixture(Path(temp))
            def change(r):
                r['inputs'] = {'../other/data_scrapping_27_6_2025.parquet': next(iter(r['inputs'].values()))}
            self.rewrite_reference(ref, change)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                rebuild(ref, remote, remote / 'out')


if __name__ == '__main__':
    unittest.main()
