"""Training-only observation-gap diagnostics, with no strategies or fitting."""
import argparse
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

from .data_pipeline import digest,iso
from .masked_preparation import read_prepared_session,verify


def gap_events(session, entry_at, tickers):
    """Observed endpoint changes are not intragap extrema or loss bounds."""
    events=[]
    for ticker in tickers:
        previous=None;start=None;length=0
        for f in session.frames:
            if f.at < entry_at:continue
            book=next((b for b in f.books if b.ticker==ticker),None)
            if book is None:
                if start is None:start=f.at
                length+=1;continue
            if length:
                events.append(dict(ticker=ticker,start=iso(start),missing_grid_points=length,
                    resumed_at=iso(f.at),reference_grid_at=None if previous is None else iso(previous[0]),
                    endpoint_interval_seconds=None if previous is None else (f.at-previous[0]).total_seconds(),
                    receipt_interval_seconds=None if previous is None else (book.available_at-previous[1].available_at).total_seconds(),
                    observed_midpoint_change=None if previous is None else float(book.midpoint/previous[1].midpoint-1)))
            previous=f.at,book;start=None;length=0
        if length:
            events.append(dict(ticker=ticker,start=iso(start),missing_grid_points=length,
                resumed_at=None,reference_grid_at=None if previous is None else iso(previous[0]),
                endpoint_interval_seconds=None,receipt_interval_seconds=None,observed_midpoint_change=None))
    return events


def run(prepared_dir,output_dir,*,protocol_snapshot=None):
    prepared_dir,output_dir=map(Path,(prepared_dir,output_dir));mp=prepared_dir/'manifest.json'
    m=json.loads(mp.read_text())
    if m['status']!='provisional_partial_grid' or m['training_ready'] is not False:
        raise ValueError('verified provisional grid required')
    protocol=Path(protocol_snapshot) if protocol_snapshot is not None else Path(m['protocol_path'])
    for p,h in m['inputs'].items():verify(protocol if p==m['protocol_path'] else p,h)
    protocol_bytes=protocol.read_bytes();protocol_sha=digest(protocol);prepared_sha=digest(mp)
    output_dir.mkdir(parents=True,exist_ok=False);sessions=[];events=[]
    for row in m['sessions']:
        if row['partition']!='train':continue
        detail=dict(session_id=row['session_id'],coverage_candidate=row['masked_coverage_candidate'],
            startable=row['causal_entry_available'],entry_at=row['entry_at'],max_gap_grid_points=None,gap_events=0)
        if row['causal_entry_available']:
            day=datetime.fromisoformat(row['session_id']).date()
            s=read_prepared_session(prepared_dir,day,protocol_snapshot=protocol)
            gs=gap_events(s,datetime.fromisoformat(row['entry_at'].replace('Z','+00:00')),m['tickers'])
            maximum=max((g['missing_grid_points'] for g in gs),default=0)
            if maximum!=max(row['asset_longest_gap_minutes'].values(),default=0):
                raise ValueError('gap reconstruction differs from preparation')
            detail.update(max_gap_grid_points=maximum,gap_events=len(gs))
            events.extend(dict(session_id=row['session_id'],coverage_candidate=row['masked_coverage_candidate'],**g) for g in gs)
        sessions.append(detail)
        print(json.dumps(detail),flush=True)
    candidates=[r for r in sessions if r['coverage_candidate']]
    bridges=[e for e in events if e['coverage_candidate'] and e['observed_midpoint_change'] is not None]
    changes=sorted(abs(e['observed_midpoint_change']) for e in bridges)
    report=dict(status='train_only_gap_diagnostics',training_ready=False,strategies_run=False,
        partition='train',scheduled_sessions=len(sessions),coverage_candidates=len(candidates),
        maximum_candidate_gap_grid_points=max((r['max_gap_grid_points'] for r in candidates),default=0),
        candidate_session_max_gap_histogram=dict(sorted(Counter(r['max_gap_grid_points'] for r in candidates).items())),
        candidate_sessions_retained_by_grid_cap={str(cap):sum(r['max_gap_grid_points']<=cap for r in candidates)
            for cap in (1,2,5,15,30)},candidate_bridged_gaps=len(bridges),
        maximum_absolute_observed_endpoint_change=max(changes,default=0),
        long_candidate_gaps=[e for e in bridges if e['missing_grid_points']>5],
        sessions=sessions,
        limitations=['Endpoint changes exclude unobserved intragap extrema; no loss or stop-delay bound.',
            'No liquidation, reward, policy, validation prices or test prices used.',
            'Grid absence is a scraper observation gap, not an exchange halt.',
            'Receipt age remains limited to 60 seconds for any executable book.'])
    (output_dir/'preparation_protocol.json').write_bytes(protocol_bytes)
    with (output_dir/'gap_events.jsonl').open('w') as handle:
        for e in events:handle.write(json.dumps(e,allow_nan=False)+'\n')
    (output_dir/'diagnostics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    manifest=dict(status=report['status'],training_ready=False,created_at=iso(datetime.now(timezone.utc)),
        prepared_manifest=dict(path=str(mp.resolve()),sha256=prepared_sha),
        preparation_protocol_sha256=protocol_sha,scope='train only; no validation/test prices',
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('masked_preparation.py'))},
        outputs_sha256={p.name:digest(p) for p in output_dir.iterdir()})
    verify(protocol,protocol_sha);verify(mp,prepared_sha)
    (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--protocol-snapshot',type=Path,help='byte-identical immutable producer protocol')
    a=p.parse_args();r=run(a.prepared_dir,a.output_dir,protocol_snapshot=a.protocol_snapshot)
    print(json.dumps({k:r[k] for k in ('coverage_candidates','maximum_candidate_gap_grid_points',
        'candidate_sessions_retained_by_grid_cap','maximum_absolute_observed_endpoint_change')},indent=2))


if __name__=='__main__':main()
