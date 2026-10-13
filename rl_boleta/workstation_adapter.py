"""Rebuild canonical captures at a new root, checking immutable source semantics."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from .data_pipeline import Config, digest
from .masked_preparation import verify


def local_file(directory, name):
    if Path(name).name != name:
        raise ValueError('expected a local artifact filename')
    return Path(directory) / name


def semantic_hash(path, *, snapshots):
    """Ignore only the source path; preserve its SHA, row IDs and all market data."""
    h = hashlib.sha256()
    count = 0
    opener = gzip.open if snapshots else open
    with opener(path, 'rt') as handle:
        rows = (json.loads(line) for line in handle) if snapshots else csv.DictReader(handle)
        for row in rows:
            source = row['provenance'] if snapshots else row
            source['source_file'] = Path(source['source_file']).name
            h.update(json.dumps(row, sort_keys=True, separators=(',', ':'),
                                allow_nan=False).encode() + b'\n')
            count += 1
    return dict(sha256=h.hexdigest(), records=count)


def signature(directory, manifest):
    outputs = {}
    for name, sha in manifest['outputs'].items():
        path = local_file(directory, name)
        verify(path, sha)
        if name != 'rejections.csv' and not name.endswith('.jsonl.gz'):
            raise ValueError('unexpected canonical output')
        outputs[name] = semantic_hash(path, snapshots=name != 'rejections.csv')
        verify(path, sha)
    return dict(config=json.loads(json.dumps(manifest['config'])), timing=manifest['timing'],
                counts=manifest['counts'], rejection_reasons=manifest['rejection_reasons'],
                inputs=[dict(name=Path(i['path']).name, sha256=i['sha256'], counts=i['counts'])
                        for i in manifest['inputs']], outputs=outputs)


def export_reference(adapter_dir, project_root, output_dir):
    adapter_dir, project_root, output_dir = map(Path, (adapter_dir, project_root, output_dir))
    project_root = project_root.resolve()
    mp = adapter_dir / 'manifest.json'
    original = mp.read_bytes()
    manifest = json.loads(original)
    if manifest['status'] != 'provisional_converted':
        raise ValueError('completed canonical adapter required')
    inputs = {}
    for item in manifest['inputs']:
        path = Path(item['path']).resolve()
        relative = path.relative_to(project_root).as_posix()
        if not relative.startswith('data/') or path.suffix != '.parquet' or relative in inputs:
            raise ValueError('distinct raw Parquet inside project data directory required')
        verify(path, item['sha256'])
        inputs[relative] = item['sha256']
    reference = dict(schema='canonical-relocation-reference-v1', inputs=inputs,
                     signature=signature(adapter_dir, manifest),
                     source_manifest_sha256=hashlib.sha256(original).hexdigest(),
                     producer_code_sha256=manifest['code_sha256'])
    verify(mp, reference['source_manifest_sha256'])
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'source_adapter_manifest.json').write_bytes(original)
    path = output_dir / 'reference.json'
    path.write_text(json.dumps(reference, indent=2, allow_nan=False) + '\n')
    (output_dir / 'manifest.json').write_text(json.dumps(dict(
        status='canonical_relocation_reference_exported', training_ready=False,
        outputs_sha256={p.name: digest(p) for p in output_dir.iterdir()}), indent=2) + '\n')
    return reference


def rebuild(reference_dir, project_root, output_dir):
    from .parquet_adapter import Timing, convert

    reference_dir, project_root, output_dir = map(Path, (reference_dir, project_root, output_dir))
    bundle = json.loads((reference_dir / 'manifest.json').read_text())
    if bundle['status'] != 'canonical_relocation_reference_exported':
        raise ValueError('exported relocation reference required')
    for name, sha in bundle['outputs_sha256'].items():
        verify(local_file(reference_dir, name), sha)
    reference = json.loads((reference_dir / 'reference.json').read_text())
    if reference['schema'] != 'canonical-relocation-reference-v1':
        raise ValueError('unsupported relocation reference')
    source_path = reference_dir / 'source_adapter_manifest.json'
    verify(source_path, reference['source_manifest_sha256'])
    source = json.loads(source_path.read_text())
    if source['code_sha256'] != reference['producer_code_sha256']:
        raise ValueError('producer code declaration differs')
    for key, name in (('adapter', 'parquet_adapter.py'), ('validator', 'data_pipeline.py'),
                      ('audit', 'audit_parquet.py')):
        verify(Path(__file__).with_name(name), reference['producer_code_sha256'][key])
    expected = reference['signature']
    if expected['config'] != source['config'] or expected['timing'] != source['timing']:
        raise ValueError('reference settings differ from archived producer')
    paths = []
    root = project_root.resolve()
    for relative, sha in reference['inputs'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root / 'data') or path.suffix != '.parquet':
            raise ValueError('raw path escapes project data directory')
        verify(path, sha)
        paths.append(path)
    if sorted((p.name, digest(p)) for p in paths) != sorted(
            (i['name'], i['sha256']) for i in expected['inputs']):
        raise ValueError('raw file set differs from source reference')
    settings = dict(expected['config'])
    settings['tickers'] = tuple(settings['tickers'])
    # Validate all settings before creating any derivative output.
    config, timing = Config(**settings), Timing(**expected['timing'])
    if output_dir.exists():
        raise FileExistsError('rebuild requires a new output directory')
    report = dict(status='canonical_rebuild_in_progress', training_ready=False,
                  full_budget_selection_authorized=False,
                  reference_manifest_sha256=digest(reference_dir / 'manifest.json'),
                  code_sha256=digest(Path(__file__)))
    result = None
    try:
        result = convert(paths, output_dir, config, timing)
        if signature(output_dir, result) != expected:
            raise ValueError('rebuilt canonical semantics differ from source reference')
        report.update(status='canonical_rebuild_verified', raw_file_count=len(paths),
                      accepted_snapshots=result['counts']['accepted'],
                      canonical_manifest_sha256=digest(output_dir / 'manifest.json'),
                      equivalence='All snapshot fields and rejection rows; source path reduced to basename only.')
    except Exception as exc:
        report.update(status='canonical_rebuild_failed', error=str(exc))
        if result is not None:
            result.update(status='relocation_verification_failed', error=str(exc))
            (output_dir / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
        # Never alter a pre-existing output if conversion refused to create it.
        if output_dir.exists() and not isinstance(exc, FileExistsError):
            (output_dir / 'relocation_report.json').write_text(json.dumps(report, indent=2) + '\n')
        raise
    (output_dir / 'relocation_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    p = sub.add_parser('export')
    p.add_argument('--adapter-dir', type=Path, required=True)
    p = sub.add_parser('rebuild')
    p.add_argument('--reference-dir', type=Path, required=True)
    for p in sub.choices.values():
        p.add_argument('--project-root', type=Path, required=True)
        p.add_argument('--output-dir', type=Path, required=True)
    a = parser.parse_args()
    if a.operation == 'export':
        r = export_reference(a.adapter_dir, a.project_root, a.output_dir)
        print(json.dumps(dict(raw_file_count=len(r['inputs']), status='reference_exported')))
    else:
        print(json.dumps(rebuild(a.reference_dir, a.project_root, a.output_dir), indent=2))


if __name__ == '__main__':
    main()
