"""Separate v3 fitting date manifests and common-date evaluation; no model fits."""
import argparse
import json
from pathlib import Path

from .data_pipeline import digest
from .masked_eligibility import GapRule,freeze
from .masked_preparation import verify


def budget(protocol):
    m=protocol['models'];t=protocol['training'];v=protocol['variants']
    configs=len(m['hidden_width_candidates'])*len(m['learning_rate_candidates'])
    core=len(m['algorithms']);variants=len(v['discount']['gammas'])+len(v['observation']['remove_groups'])
    def count(extra):
        tuning=(core+extra)*configs*len(t['tuning_seeds']);final=(core+extra)*len(t['final_seeds'])
        return dict(tuning=tuning,final=final,total=tuning+final,
            requested_environment_transitions=tuning*t['tuning_steps_per_fit']+final*t['final_steps_per_fit'])
    primary=count(variants);secondary=count(0)
    return dict(all_gaps=primary,short_gaps=secondary,total=primary['total']+secondary['total'],
        requested_environment_transitions=primary['requested_environment_transitions']+secondary['requested_environment_transitions'])


def build(prepared_dir,train_audit_dir,protocol_path,output_dir):
    protocol_path,output_dir=map(Path,(protocol_path,output_dir));protocol_hash=digest(protocol_path)
    protocol=json.loads(protocol_path.read_text());design=protocol['experimental_scenarios']
    if design['status']!='frozen_design_historical_fitting_pending':raise ValueError('resolved scenario design required')
    primary=design['scenarios']['all_gaps'];secondary=design['scenarios']['short_gaps']
    GapRule(primary['primary_mode'],primary['cap_grid_points']);GapRule(secondary['primary_mode'],secondary['cap_grid_points'])
    if primary['primary_mode']!='masked_all_gaps' or secondary['primary_mode']!='bounded_grid_gap':
        raise ValueError('all-gaps primary and bounded secondary required')
    if any(s['algorithms']!=protocol['models']['algorithms'] for s in (primary,secondary)):
        raise ValueError('same algorithm set required in both scenarios')
    computed=budget(protocol)
    for name in ('all_gaps','short_gaps'):
        for key in ('total','requested_environment_transitions'):
            if computed[name][key]!=protocol['planned_fits'][name][key]:
                raise ValueError('declared per-scenario fit budget mismatch')
    for key in ('total','requested_environment_transitions'):
        if computed[key]!=protocol['planned_fits'][key]:raise ValueError('declared fit budget mismatch')
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'protocol.json').write_bytes(protocol_path.read_bytes())
    manifests={};records={}
    for name in ('all_gaps','short_gaps'):
        local=json.loads(json.dumps(protocol));rule=design['scenarios'][name]
        local['episode']['long_gap_policy'].update(primary_mode=rule['primary_mode'],primary_cap_minutes=rule['cap_grid_points'])
        # This copy resolves only scenario selection; original preparation remains immutable.
        path=output_dir/f'protocol_{name}.json';path.write_text(json.dumps(local,indent=2)+'\n')
        manifests[name]=freeze(prepared_dir,train_audit_dir,path,output_dir/name)
        records[name]=json.loads((output_dir/name/'sessions.json').read_text())
    common={}
    for part in ('train','validation','test','final_refit'):
        def dates(name):return {r['session_id'] for r in records[name] if r['data_eligible'] and
            (r['partition']==part or part=='final_refit' and r['partition'] in ('train','validation'))}
        all_dates=dates('all_gaps');short_dates=dates('short_gaps')
        if not short_dates<=all_dates:raise ValueError('bounded dates must be subset of all-gaps dates')
        common[part]=sorted(all_dates&short_dates)
    common_path=output_dir/'common_dates.json';common_path.write_text(json.dumps(common,indent=2)+'\n')
    verify(protocol_path,protocol_hash)
    report=dict(status='frozen_two_scenario_date_design',training_ready=False,
        financial_scores_accessed=False,protocol_sha256=protocol_hash,computed_budget=computed,
        scenario_manifests={name:dict(path=str((output_dir/name/'manifest.json').resolve()),
            sha256=digest(output_dir/name/'manifest.json'),partition_summary=m['partition_summary']) for name,m in manifests.items()},
        common_date_counts={p:len(ds) for p,ds in common.items()},
        normalizers='separate train and final-refit normalizers for each scenario; each evaluation checkpoint retains its own',
        cross_evaluation='both independently fitted model sets on common test dates; identical seeds, no refit or online updates',
        outputs_sha256={p.name:digest(p) for p in output_dir.iterdir() if p.is_file()},
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('masked_eligibility.py'))})
    (output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared-dir','train-audit-dir','protocol','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=build(a.prepared_dir,a.train_audit_dir,a.protocol,a.output_dir)
    print(json.dumps(dict(budget=r['computed_budget'],common_date_counts=r['common_date_counts']),indent=2))


if __name__=='__main__':main()
