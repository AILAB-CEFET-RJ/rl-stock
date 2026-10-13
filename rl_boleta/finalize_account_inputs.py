"""Verify completed normalizer/probe bundles and record readiness without enabling fits."""
import argparse
import json
from pathlib import Path

from .account_campaigns import MODES
from .data_pipeline import digest
from .historical_normalization import load_train_normalizer
from .historical_profile_verification import probe_dates
from .masked_preparation import verify


def finalize(directory,*,reference_normalizer_dir=None):
    directory=Path(directory);mp=directory/'manifest.json';state=json.loads(mp.read_text())
    if state['status'] not in ('account_profiles_and_date_manifests_prepared','account_profile_inputs_and_train_probes_verified'):
        raise ValueError('completed account date profiles required')
    for name,h in state['outputs_sha256'].items():verify(directory/name,h)
    template_sha=digest(directory/'source_protocol.json')
    for path,h in state['inputs_sha256'].items():
        # The producing template is archived byte-for-byte; later workspace edits
        # must not reinterpret or invalidate these immutable account profiles.
        verify(directory/'source_protocol.json' if h==template_sha else path,h)
    selected=tuple(state['campaigns'])
    if not selected or not set(selected)<=set(MODES):raise ValueError('registered profiles required')
    stats={};total=0
    for mode,campaign in state['campaigns'].items():
        for key in ('protocol','design_manifest'):
            verify(campaign[key]['path'],campaign[key]['sha256'])
        proto=json.loads(Path(campaign['protocol']['path']).read_text())
        if (proto['environment']['account_regime']!=mode or proto['environment']['reward_objective']!='terminal_cash_utility'
                or proto['episode']['wind_down_execution_points']!=54):raise ValueError('economic profile differs')
        normdir=Path(campaign['normalizer_output_dir']);nm=normdir/'manifest.json';bundle=json.loads(nm.read_text())
        if bundle['design_manifest']!=campaign['design_manifest']:raise ValueError('normalizers belong to a different design')
        for name,h in bundle['outputs_sha256'].items():verify(normdir/name,h)
        stats[mode]={s:load_train_normalizer(normdir,s) for s in ('all_gaps','short_gaps')}
        probe=normdir.parent/'train_probes/report.json';report=json.loads(probe.read_text())
        if (report['status']!='historical_training_profile_probes_completed' or report['account_regime']!=mode
                or report['models_trained'] is not False or report['validation_prices_accessed'] is not False
                or report['test_prices_accessed'] is not False or report['full_budget_selection_authorized'] is not False
                or report['observation_dimension']!=15505):raise ValueError('completed train-only probes required')
        for path,h in report['inputs_sha256'].items():verify(path,h)
        for path,h in report['source_sha256'].items():verify(path,h)
        expected=set()
        for scenario,norm in stats[mode].items():
            entry=bundle['normalizers'][scenario]['eligibility_manifest']
            records=json.loads((Path(entry['path']).parent/'sessions.json').read_text())
            expected.update((scenario,day) for day in probe_dates(records,norm.sessions,54))
        actual=[(r['scenario'],r['session_id']) for r in report['sessions']]
        if len(actual)!=len(set(actual)) or set(actual)!=expected:raise ValueError('missing or duplicate probe dates')
        total+=len(actual)
        campaign.update(normalizer_manifest=dict(path=str(nm.resolve()),sha256=digest(nm)),
            train_probe_report=dict(path=str(probe.resolve()),sha256=digest(probe)),train_probes=len(actual))
    def same(a,b):return (a.sessions,a.counts,a.means,a.scales)==(b.sessions,b.counts,b.means,b.scales)
    first=next(iter(stats.values()))
    if any(not same(norms[s],first[s]) for norms in stats.values() for s in first):
        raise ValueError('account mode changed fitting dates or market normalization')
    reference=None
    if reference_normalizer_dir is not None:
        refdir=Path(reference_normalizer_dir)
        if any(not same(load_train_normalizer(refdir,s),first[s]) for s in first):
            raise ValueError('market statistics differ from the original fitting bundle')
        reference=dict(path=str((refdir/'manifest.json').resolve()),sha256=digest(refdir/'manifest.json'))
    state.update(status='account_profile_inputs_and_train_probes_verified',normalization_pending=False,
        profile_inputs_verified=True,training_ready=False,full_budget_selection_authorized=False,
        total_train_probes=total,market_statistics_equal_across_account_modes=True,
        reference_market_statistics_verified=reference,
        verification_scope='Fixed train integration probes only; no trained model, validation selection or final refit.',
        verification_code_sha256={str(Path(__file__)):digest(Path(__file__))})
    mp.write_text(json.dumps(state,indent=2)+'\n');return state


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--reference-normalizer-dir',type=Path)
    a=p.parse_args();r=finalize(a.directory,reference_normalizer_dir=a.reference_normalizer_dir)
    print(json.dumps(dict(status=r['status'],total_train_probes=r['total_train_probes']),indent=2))


if __name__=='__main__':main()
