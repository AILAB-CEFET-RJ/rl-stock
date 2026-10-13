"""Immutable historical input profiles per account mode; no fitting of policies."""
import argparse
import json
from pathlib import Path

from .data_pipeline import digest
from .masked_preparation import verify
from .scenario_manifests import build

MODES=('cash_settled','intraday_buying_power')


def profile(template,mode):
    if mode not in MODES:raise ValueError('explicit research account mode required')
    p=json.loads(json.dumps(template))
    review=p['day_trading_review']
    if (review['exit_capacity_audit']['proposed_wind_down_execution_points']!=54
            or review['exit_capacity_audit']['execution_rule_implemented'] is not True
            or review['learning_objective']['reference_objective']!='terminal_cash_utility'):
        raise ValueError('implemented reviewed phase and objective required')
    p['protocol_id']+='-'+mode+'-economic-profile'
    p['status']='frozen_economic_profile_historical_verification_pending'
    p['purpose']='New immutable input profile; conditional replay; full research selection remains blocked.'
    p['environment'].update(account_regime=mode,reward_objective='terminal_cash_utility')
    p['episode']['wind_down_execution_points']=54
    for key in ('normal','early_close_2025_07_03'):
        schedule=p['episode'][key];index=schedule['liquidation_index']
        schedule.update(last_regular_fill_index=index-54,last_intention_index=index-55)
    review['status']='pending_historical_profile_verification'
    review['selected_account_regime']=mode
    review['full_budget_selection_blocked']=True
    # Ancestor reports are not reports for this new profile.
    p['normalization'].pop('train_artifact',None)
    p['training'].pop('historical_integration_artifact',None)
    p['training']['validation_executor'].pop('diagnostic_artifact',None)
    p['training']['validation_executor']['protocol_selection_completed']=False
    return p


def prepare_accounts(prepared_dir,train_audit_dir,template_path,output_dir,*,modes=MODES):
    if not modes or len(set(modes))!=len(modes) or any(m not in MODES for m in modes):
        raise ValueError('nonempty distinct registered account modes required')
    template_path,output_dir=map(Path,(template_path,output_dir))
    template_bytes=template_path.read_bytes();template=json.loads(template_bytes)
    anchors={str(template_path.resolve()):digest(template_path)}
    for folder in (prepared_dir,train_audit_dir):
        path=Path(folder)/'manifest.json';anchors[str(path.resolve())]=digest(path)
    profiles={m:profile(template,m) for m in modes}
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'source_protocol.json').write_bytes(template_bytes)
    state=dict(status='preparing',training_ready=False,full_budget_selection_authorized=False,
        test_policy_outcomes_accessed=False,inputs_sha256=anchors,campaigns={})
    mp=output_dir/'manifest.json'
    def save():mp.write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        counts=None
        for mode,p in profiles.items():
            directory=output_dir/mode;directory.mkdir()
            proto=directory/'protocol.json';proto.write_text(json.dumps(p,indent=2)+'\n')
            design_dir=directory/'design';m=build(prepared_dir,train_audit_dir,proto,design_dir)
            common=json.loads((design_dir/'common_dates.json').read_text())
            if counts is not None and common!=counts:raise ValueError('account mode must not change common market dates')
            counts=common
            state['campaigns'][mode]=dict(protocol=dict(path=str(proto.resolve()),sha256=digest(proto)),
                design_manifest=dict(path=str((design_dir/'manifest.json').resolve()),sha256=digest(design_dir/'manifest.json')),
                normalizer_output_dir=str((directory/'normalizers').resolve()),
                common_date_counts=m['common_date_counts'],budget_if_this_campaign_is_run=m['computed_budget'])
            save()
        for path,h in anchors.items():verify(path,h)
        state.update(status='account_profiles_and_date_manifests_prepared',normalization_pending=True,
            code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('masked_eligibility.py'),Path(__file__).with_name('scenario_manifests.py'))},
            outputs_sha256={'source_protocol.json':digest(output_dir/'source_protocol.json')})
        save();return state
    except Exception as exc:
        state.update(status='failed',error=str(exc));save();raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('prepared-dir','train-audit-dir','protocol','output-dir'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--account-regime',choices=(*MODES,'ALL'),default='ALL')
    a=parser.parse_args()
    result=prepare_accounts(a.prepared_dir,a.train_audit_dir,a.protocol,a.output_dir,
        modes=MODES if a.account_regime=='ALL' else (a.account_regime,))
    print(json.dumps(dict(status=result['status'],campaigns=list(result['campaigns'])),indent=2))


if __name__=='__main__':main()
