"""Freeze conditional, strategy-independent v3 dates; never fit or score policies."""
import argparse
import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path

from .audit_protocol_alternatives import analyze_day
from .data_pipeline import digest,iso
from .masked_preparation import read_prepared_session,verify
from .session_replay import session_plan


@dataclass(frozen=True)
class GapRule:
    mode: str
    cap_grid_points: object = None

    def __post_init__(self):
        if self.mode=='masked_all_gaps':
            if self.cap_grid_points is not None:raise ValueError('all-gaps rule has no duration cap')
        elif self.mode=='bounded_grid_gap':
            if type(self.cap_grid_points) is not int or self.cap_grid_points<1:
                raise ValueError('bounded rule requires positive integer missing-grid cap')
        else:raise ValueError('explicit resolved primary gap mode required')

    def permits(self,longest):
        return self.mode=='masked_all_gaps' or longest<=self.cap_grid_points


def select_day(row,analysis,rule):
    reasons=[]
    if row['raw_files']==0:reasons.append('no_raw_file')
    if analysis['entry_index'] is None:reasons.append('no_causal_warmup')
    elif not analysis['causal_entry_available']:reasons.append('insufficient_remaining_transitions')
    if not analysis['all_assets_exit_available']:reasons.append('missing_common_exit')
    longest=max(analysis['asset_longest_gap_minutes'].values(),default=0)
    if analysis['causal_entry_available'] and not rule.permits(longest):reasons.append('gap_exceeds_frozen_cap')
    return not reasons,reasons,longest


def observation_episode_signature(protocol):
    """Allow explicit wind-down amendments while preserving the observed grid.

    Ordinary intention/fill bounds must match the declared execution phase;
    the scheduled liquidation, warm-up and causal entry remain unchanged.
    """
    episode=json.loads(json.dumps(protocol['episode']))
    wind=episode.pop('wind_down_execution_points',1)
    if type(wind) is not int or wind<1:raise ValueError('invalid declared wind-down phase')
    for name in ('normal','early_close_2025_07_03'):
        schedule=episode[name];exit_index=schedule['liquidation_index']
        if (wind>=exit_index or schedule['last_regular_fill_index']!=exit_index-wind
                or schedule['last_intention_index']!=exit_index-wind-1):
            raise ValueError('ordinary intention/fill bounds disagree with wind-down phase')
        schedule.pop('last_regular_fill_index');schedule.pop('last_intention_index')
    episode.pop('long_gap_policy',None);episode.pop('eligible_coverage',None)
    return episode


def observation_data_signature(data):
    """Numbered documentation paths retain their original evidence identity.

    Quality thresholds and clock assumptions are compared without alteration.
    Frozen producer files still retain their exact byte/hash validation.
    """
    values=dict(data)
    if 'timing_evidence' in values:
        values['timing_evidence']=re.sub(r'^docs/[0-9]{3}_','docs/',values['timing_evidence'])
    return values


def freeze(prepared_dir,train_audit_dir,protocol_path,output_dir):
    prepared_dir,train_audit_dir,protocol_path,output_dir=map(Path,(prepared_dir,train_audit_dir,protocol_path,output_dir))
    prep_path=prepared_dir/'manifest.json';audit_path=train_audit_dir/'manifest.json'
    initial_hashes={str(p):digest(p) for p in (prep_path,audit_path,protocol_path)}
    prep=json.loads(prep_path.read_text());audit=json.loads(audit_path.read_text());protocol=json.loads(protocol_path.read_text())
    if prep['status']!='provisional_partial_grid' or audit['status']!='train_only_gap_diagnostics':
        raise ValueError('completed partial preparation and training-only diagnostics required')
    verify(prep_path,audit['prepared_manifest']['sha256'])
    for name,h in audit['outputs_sha256'].items():verify(train_audit_dir/name,h)
    old_protocol=train_audit_dir/'preparation_protocol.json';verify(old_protocol,audit['preparation_protocol_sha256'])
    for p,h in prep['inputs'].items():verify(old_protocol if p==prep['protocol_path'] else p,h)
    rule_spec=protocol['episode']['long_gap_policy']
    if rule_spec['status']!='frozen_for_conditional_v3_simulation':raise ValueError('freeze the methodological rule first')
    rule=GapRule(rule_spec['primary_mode'],rule_spec['primary_cap_minutes'])
    caps=tuple(rule_spec['diagnostic_grid_missing_run_caps'])
    if not caps or len(set(caps))!=len(caps):raise ValueError('unique predefined sensitivity caps required')
    for cap in caps:GapRule('bounded_grid_gap',cap)
    # A protocol amendment may resolve gap selection, but never alter the underlying grid.
    original=json.loads(old_protocol.read_text())
    if observation_episode_signature(protocol)!=observation_episode_signature(original):
        raise ValueError('entry or exit semantics changed; rebuild preparation')
    if (protocol['tickers']!=original['tickers'] or observation_data_signature(protocol['data'])!=observation_data_signature(original['data'])
            or protocol['partitions']!=original['partitions']
            or protocol['episode']['window_features']!=original['episode']['window_features']
            or protocol['episode']['minimum_remaining_transitions']!=original['episode']['minimum_remaining_transitions']):
        raise ValueError('grid, quality or chronological partitions changed; rebuild preparation')
    records=[];summary={p:Counter() for p in ('train','validation','test','final_refit')}
    sensitivity={str(cap):{p:[] for p in summary} for cap in caps}
    for row in prep['sessions']:
        name=row['grid_file'];verify(prepared_dir/name,prep['outputs'][name])
        with gzip.open(prepared_dir/name,'rt') as handle:grid=[json.loads(line) for line in handle]
        day=datetime.fromisoformat(row['session_id']).date();plan=session_plan(day)
        if [g['at'] for g in grid]!=[iso(t) for t in plan.required_times]:raise ValueError('grid calendar mismatch')
        if any(not set(g['snapshots'])<=set(protocol['tickers']) for g in grid):raise ValueError('grid universe mismatch')
        a=analyze_day({t:[t in g['snapshots'] for g in grid] for t in protocol['tickers']})
        if a['masked_coverage_candidate']!=row['masked_coverage_candidate']:raise ValueError('coverage diagnostics mismatch')
        selected,reasons,longest=select_day(row,a,rule)
        record=dict(session_id=row['session_id'],partition=row['partition'],data_eligible=selected,
            exclusion_reasons=reasons,entry_at=row['entry_at'],exit_at=row['exit_at'],
            remaining_transitions=a['remaining_transitions'],longest_missing_grid_run=longest,
            missing_exit_assets=a['missing_exit_assets'])
        records.append(record);parts=(row['partition'],'final_refit') if row['partition'] in ('train','validation') else (row['partition'],)
        for part in parts:
            summary[part]['scheduled_sessions']+=1;summary[part]['data_eligible_sessions']+=selected
            for reason in reasons:summary[part][reason]+=1
            for cap in caps:
                if selected and select_day(row,a,GapRule('bounded_grid_gap',cap))[0]:sensitivity[str(cap)][part].append(row['session_id'])
    for part,values in summary.items():
        p=protocol['partitions'][part]
        if values['scheduled_sessions']!=p['scheduled_sessions']:raise ValueError('scheduled denominator mismatch')
        minimum=p.get('minimum_eligible_sessions');values['minimum_eligible_sessions']=minimum
        values['minimum_met']=None if minimum is None else values['data_eligible_sessions']>=minimum
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'preparation_protocol.json').write_bytes(old_protocol.read_bytes())
    (output_dir/'protocol.json').write_bytes(protocol_path.read_bytes())
    (output_dir/'sessions.json').write_text(json.dumps(records,indent=2)+'\n')
    (output_dir/'sensitivities.json').write_text(json.dumps(sensitivity,indent=2)+'\n')
    manifest=dict(schema='conditional-masked-eligibility-v3',status='frozen_conditional_eligibility',training_ready=False,
        created_at=iso(datetime.now(timezone.utc)),primary_rule=dict(mode=rule.mode,cap_grid_points=rule.cap_grid_points),
        scope='conditional capture-time simulation; no certified market-time or live execution claim',
        partition_summary={k:dict(v) for k,v in summary.items()},
        normalization_date_selection_ready=all(summary[p]['minimum_met'] for p in ('train','validation','test')),
        prepared_manifest=dict(path=str(prep_path.resolve()),sha256=initial_hashes[str(prep_path)]),
        train_audit_manifest=dict(path=str(audit_path.resolve()),sha256=initial_hashes[str(audit_path)]),
        frozen_protocol_sha256=initial_hashes[str(protocol_path)],preparation_protocol_sha256=digest(old_protocol),
        outputs_sha256={p.name:digest(p) for p in output_dir.iterdir()},
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('audit_protocol_alternatives.py'))},
        selection_independent_of_strategies=True,financial_scores_accessed=False,
        retained_economic_failures='stop and finite-depth liquidation failures never remove data-eligible dates',
        sensitivities='predefined subsets for frozen-policy paired summaries; no retraining or hyperparameter selection',
        unresolved=['Historical fitting APIs still accept synthetic sessions only.',
            'Per-feature normalizer and actual algorithm fits have not been produced.',
            'Capture-time and single-venue limitations remain; gap length is not a risk bound.'])
    for p,h in initial_hashes.items():verify(p,h)
    (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest


def read_eligible_session(directory,day,*,partition):
    directory=Path(directory);m=json.loads((directory/'manifest.json').read_text())
    if m['schema']!='conditional-masked-eligibility-v3' or m['status']!='frozen_conditional_eligibility':
        raise ValueError('frozen conditional v3 manifest required')
    if partition not in ('train','validation','test','final_refit'):raise ValueError('explicit chronological partition required')
    for name,h in m['outputs_sha256'].items():verify(directory/name,h)
    verify(m['prepared_manifest']['path'],m['prepared_manifest']['sha256'])
    verify(m['train_audit_manifest']['path'],m['train_audit_manifest']['sha256'])
    verify(directory/'protocol.json',m['frozen_protocol_sha256'])
    verify(directory/'preparation_protocol.json',m['preparation_protocol_sha256'])
    records=json.loads((directory/'sessions.json').read_text());row=next((r for r in records if r['session_id']==str(day)),None)
    if row is None or not row['data_eligible']:raise ValueError('date excluded by frozen common data rule')
    if not (row['partition']==partition or partition=='final_refit' and row['partition'] in ('train','validation')):
        raise ValueError('date outside requested partition')
    return read_prepared_session(Path(m['prepared_manifest']['path']).parent,day,
        protocol_snapshot=directory/'preparation_protocol.json')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-dir',type=Path,required=True);p.add_argument('--train-audit-dir',type=Path,required=True)
    p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();m=freeze(a.prepared_dir,a.train_audit_dir,a.protocol,a.output_dir)
    print(json.dumps(m['partition_summary'],indent=2))


if __name__=='__main__':main()
