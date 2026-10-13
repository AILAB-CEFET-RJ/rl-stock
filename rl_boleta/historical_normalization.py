"""Manifest-bound train-only v3 normalizers; no neural-network fitting or test prices."""
import argparse
import json
import platform
from dataclasses import dataclass
from datetime import date,datetime,timezone
from pathlib import Path

from .data_pipeline import digest,iso
from .masked_eligibility import read_eligible_session
from .masked_preparation import verify
from .masked_observations import (AGE_SECONDS,SCHEMA,MaskedNormalizer,MaskedMoments,
    masked_market_rows)
from .observations import PARTITIONS,feature_names


@dataclass(frozen=True)
class HistoricalMaskedNormalizer(MaskedNormalizer):
    synthetic_only: bool = False
    scenario: str = ''
    eligibility_sha256: str = ''

    def _validate_origin(self):
        if (self.synthetic_only is not False or self.scenario not in ('all_gaps','short_gaps')
                or len(self.eligibility_sha256)!=64
                or any(c not in '0123456789abcdef' for c in self.eligibility_sha256)):
            raise ValueError('historical normalizer requires explicit scenario and eligibility hash')
        if tuple(sorted(self.sessions))!=self.sessions:raise ValueError('historical dates must be chronological')

    @classmethod
    def load(cls,path):
        d=json.loads(Path(path).read_text())
        if (d.get('schema')!=SCHEMA or d.get('clip')!=[-10,10] or d.get('std_ddof')!=0
            or d.get('age_denominator_seconds')!=AGE_SECONDS
            or d.get('masked_sentinel')!='zero_after_standardization'
            or tuple(d.get('feature_names',()))!=feature_names(d['tickers'])):
            raise ValueError('incompatible historical masked normalizer schema')
        return cls(tickers=tuple(d['tickers']),means=tuple(d['means']),scales=tuple(d['scales']),
            counts=tuple(d['counts']),partition=d['partition'],sessions=tuple(d['sessions']),
            synthetic_only=d['synthetic_only'],scenario=d['scenario'],eligibility_sha256=d['eligibility_sha256'])


def design_inputs(directory):
    directory=Path(directory);mp=directory/'manifest.json';m=json.loads(mp.read_text())
    if m['status']!='frozen_two_scenario_date_design' or m['financial_scores_accessed'] is not False:
        raise ValueError('frozen two-scenario date design required')
    for n,h in m['outputs_sha256'].items():verify(directory/n,h)
    manifests={};records={};tickers=None;profile=None
    for scenario in ('all_gaps','short_gaps'):
        source=m['scenario_manifests'][scenario];path=Path(source['path']);verify(path,source['sha256'])
        child=json.loads(path.read_text())
        if child['status']!='frozen_conditional_eligibility' or not child['normalization_date_selection_ready']:
            raise ValueError('conditional selection must meet minimum operational coverage')
        for n,h in child['outputs_sha256'].items():verify(path.parent/n,h)
        protocol=json.loads((path.parent/'protocol.json').read_text());assets=tuple(protocol['tickers'])
        current_profile=(child['prepared_manifest'],child['preparation_protocol_sha256'],protocol['data'],protocol['normalization'])
        if profile is not None and profile!=current_profile:
            raise ValueError('scenario normalizers must use the same verified preparation and feature rules')
        profile=current_profile
        if tickers is not None and assets!=tickers:raise ValueError('scenario asset universes differ')
        tickers=assets;manifests[scenario]=(path,source['sha256'])
        records[scenario]=json.loads((path.parent/'sessions.json').read_text())
    return m,manifests,records,tickers


def fit_train_normalizers(design_dir,output_dir,*,partition='train'):
    if partition!='train':
        raise ValueError('only train normalization enabled; final refit requires validation-selected models')
    design_dir,output_dir=map(Path,(design_dir,output_dir));source_path=design_dir/'manifest.json';source_sha=digest(source_path)
    design,manifests,records,tickers=design_inputs(design_dir)
    dates={name:tuple(r['session_id'] for r in rows if r['data_eligible'] and r['partition']=='train') for name,rows in records.items()}
    if not dates['all_gaps'] or not dates['short_gaps'] or not set(dates['short_gaps'])<=set(dates['all_gaps']):
        raise ValueError('nonempty nested fitting date sets required')
    first,last=PARTITIONS['train']
    if any(ds!=tuple(sorted(set(ds))) or any(not first<=date.fromisoformat(d)<=last for d in ds) for ds in dates.values()):
        raise ValueError('fitting dates must be unique chronological train dates')
    output_dir.mkdir(parents=True,exist_ok=False)
    moments={name:MaskedMoments(tickers) for name in dates};rows_per_day={name:{} for name in dates}
    written=[]
    try:
        # Read each primary train session once, updating only scenarios that admit it.
        for day in dates['all_gaps']:
            session=read_eligible_session(manifests['all_gaps'][0].parent,date.fromisoformat(day),partition='train')
            if session.synthetic is not False:raise ValueError('historical preparation required')
            recipients=[name for name,ds in dates.items() if day in ds];count=0
            for row in masked_market_rows(session,tickers):
                for name in recipients:moments[name].update(row)
                count+=1
            for name in recipients:rows_per_day[name][day]=count
            print(json.dumps(dict(session_id=day,feature_points=count,scenarios=recipients)),flush=True)
        normalizers={};entries={}
        for name,acc in moments.items():
            norm=HistoricalMaskedNormalizer(tickers=tickers,means=tuple(acc.means),scales=acc.scales,
                counts=tuple(acc.counts),partition='train',sessions=dates[name],scenario=name,
                eligibility_sha256=manifests[name][1])
            path=output_dir/f'normalizer_{name}_train.json';norm.save(path);written.append(path)
            if HistoricalMaskedNormalizer.load(path)!=norm:raise RuntimeError('normalizer roundtrip mismatch')
            normalizers[name]=norm
            entries[name]=dict(file=path.name,sha256=digest(path),eligibility_manifest=dict(path=str(manifests[name][0].resolve()),sha256=manifests[name][1]),
                fitting_sessions=list(dates[name]),rows_per_session=rows_per_day[name],
                unique_feature_points=sum(rows_per_day[name].values()),
                per_feature_count_min=min(norm.counts),per_feature_count_max=max(norm.counts))
        verify(source_path,source_sha)
        for p,h in manifests.values():verify(p,h)
        report=dict(schema='historical-train-normalizer-bundle-v3',status='historical_train_normalization_completed',
            training_ready=False,neural_networks_fitted=False,partition='train',test_prices_accessed=False,
            validation_prices_accessed=False,created_at=iso(datetime.now(timezone.utc)),python=platform.python_version(),
            design_manifest=dict(path=str(source_path.resolve()),sha256=source_sha),normalizers=entries,
            normalizers_numerically_equal=normalizers['all_gaps'].means==normalizers['short_gaps'].means and normalizers['all_gaps'].scales==normalizers['short_gaps'].scales,
            fitting_policy='unique valid market feature points, causal warmup through scheduled exit; missing sentinels excluded; population std; constants scale=1; clip at transform only',
            final_refit='not generated; requires validation-selected models and a new fit on each scenario train+validation dates',
            code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('masked_observations.py'),
                Path(__file__).with_name('masked_eligibility.py'),Path(__file__).with_name('masked_preparation.py'),
                Path(__file__).with_name('missing_data_replay.py'))},
            outputs_sha256={p.name:digest(p) for p in written})
        (output_dir/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        return report
    except Exception as exc:
        (output_dir/'manifest.json').write_text(json.dumps(dict(status='failed',training_ready=False,error=str(exc)),indent=2)+'\n')
        raise


def load_train_normalizer(directory,scenario):
    directory=Path(directory);m=json.loads((directory/'manifest.json').read_text())
    if (m['schema']!='historical-train-normalizer-bundle-v3'
            or m['status']!='historical_train_normalization_completed' or m['partition']!='train'):
        raise ValueError('completed historical train normalization required')
    if scenario not in ('all_gaps','short_gaps'):raise ValueError('explicit scenario required')
    for n,h in m['outputs_sha256'].items():verify(directory/n,h)
    verify(m['design_manifest']['path'],m['design_manifest']['sha256'])
    entry=m['normalizers'][scenario];e=entry['eligibility_manifest'];verify(e['path'],e['sha256'])
    norm=HistoricalMaskedNormalizer.load(directory/entry['file'])
    if (norm.scenario!=scenario or norm.partition!='train' or norm.eligibility_sha256!=e['sha256']
            or list(norm.sessions)!=entry['fitting_sessions']):raise ValueError('normalizer binding mismatch')
    child_path=Path(e['path']);child=json.loads(child_path.read_text())
    for n,h in child['outputs_sha256'].items():verify(child_path.parent/n,h)
    dates=tuple(r['session_id'] for r in json.loads((child_path.parent/'sessions.json').read_text()) if r['data_eligible'] and r['partition']=='train')
    if norm.sessions!=dates:raise ValueError('normalizer must cover exactly frozen train dates')
    return norm


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--design-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--partition',choices=('train','final_refit'),default='train')
    a=p.parse_args();r=fit_train_normalizers(a.design_dir,a.output_dir,partition=a.partition)
    print(json.dumps({name:{k:e[k] for k in ('unique_feature_points','per_feature_count_min','per_feature_count_max')}
        for name,e in r['normalizers'].items()},indent=2))


if __name__=='__main__':main()
