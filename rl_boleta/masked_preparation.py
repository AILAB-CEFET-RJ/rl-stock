"""Provisional v3 grid from verified canonical snapshots; no fitting or returns."""
import argparse
import bisect
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import data_pipeline, market_calendar
from .audit_protocol_alternatives import analyze_day
from .data_pipeline import Config, digest, iso, load_snapshots, timestamp
from .economic_kernel import Book, Level
from .masked_observations import MaskedMarketSession
from .missing_data_replay import PartialFrame
from .observations import Trade
from .session_replay import session_plan

SCHEMA = 'partial-capture-reference-grid-v3'


def verify(path, expected):
    if digest(Path(path)) != expected:
        raise ValueError(f'provenance hash mismatch: {path}')


def config_for(protocol, day):
    d = protocol['data']
    if (d['calendar'] != market_calendar.NAME or d['grid_seconds'] != 60
            or d['maximum_receipt_age_seconds'] != 60 or d['book_levels_per_side'] != 5
            or d['recent_trades'] != 10 or protocol['episode']['window_features'] != 20
            or protocol['episode']['minimum_remaining_transitions'] != 2):
        raise ValueError('unsupported v3 calendar, grid or observation rules')
    return Config(tuple(protocol['tickers']), d['max_spread_bps'], d['max_depth_distance_bps'],
        max_age_seconds=60, calendar=market_calendar.NAME,
        session_first_date=str(day), session_last_date=str(day))


def align_partial(day, snapshots, config):
    """Latest accepted receipt per asset; no interpolation or carry across opens."""
    assets = defaultdict(list)
    for s in snapshots:
        at = timestamp(s['available_at'], 'available_at')
        if at.astimezone(market_calendar.ZONE).date() != day:
            raise ValueError('capture date differs from source filename')
        if not data_pipeline.snapshot_session_failure(s, config):
            assets[s['ticker']].append((at, s))
    for values in assets.values():values.sort(key=lambda x:x[0])
    times = {t:[at for at,_ in values] for t,values in assets.items()}
    frames, trades, references = [], {}, []
    for at in session_plan(day).required_times:
        books, refs = [], {}
        for ticker in config.tickers:
            j = bisect.bisect_right(times.get(ticker, ()), at)-1
            if j < 0:continue
            receipt, s = assets[ticker][j]
            if (at-receipt).total_seconds() > config.max_age_seconds:continue
            books.append(Book(ticker, s['snapshot_id'], receipt,
                tuple(Level(l['price'], l['size']) for l in s['bids'][:5]),
                tuple(Level(l['price'], l['size']) for l in s['asks'][:5])))
            trades[at,ticker] = tuple(Trade(t['price'],t['size'],timestamp(t['at'],'trade.at'))
                for t in s['trades'][:10])
            refs[ticker] = s['snapshot_id']
        frames.append(PartialFrame(at,str(day),tuple(books)))
        references.append(dict(at=iso(at),snapshots=refs))
    return MaskedMarketSession(day,tuple(frames),trades,synthetic=False), references


def canonical_day(paths, config):
    snapshots, rejected, _, duplicates = load_snapshots(paths,config)
    if rejected or duplicates:
        raise ValueError('canonical snapshots rejected or duplicated on revalidation')
    return snapshots


def prepare(adapter_dir, protocol_path, audit_dir, output_dir):
    adapter_dir,protocol_path,audit_dir,output_dir = map(Path,(adapter_dir,protocol_path,audit_dir,output_dir))
    adapter_path = adapter_dir/'manifest.json';audit_path=audit_dir/'manifest.json'
    adapter,protocol,audit = [json.loads(p.read_text()) for p in (adapter_path,protocol_path,audit_path)]
    if adapter['status'] != 'provisional_converted' or audit['status'] != 'diagnostic_only':
        raise ValueError('completed canonical adapter and gap audit required')
    source_manifests={str(Path(k).resolve()):v for k,v in audit['source_manifests'].items()}
    verify(adapter_path,source_manifests[str(adapter_path.resolve())])
    for path,sha in source_manifests.items():verify(path,sha)
    grid_path=audit_dir/'asset_grid.csv.gz';verify(grid_path,audit['outputs_sha256'][grid_path.name])
    anchors={str(p.resolve()):digest(p) for p in (adapter_path,protocol_path,audit_path,grid_path)}
    partitions=protocol['partitions'];first=date.fromisoformat(partitions['train']['first']);last=date.fromisoformat(partitions['test']['last'])
    train,validation,test,refit=(partitions[k] for k in ('train','validation','test','final_refit'))
    if not (train['first']<=train['last']<validation['first']<=validation['last']<test['first']<=test['last']
            and (refit['first'],refit['last'])==(train['first'],validation['last'])):
        raise ValueError('overlapping or inconsistent chronological partitions')
    config=config_for(protocol,first)
    if (adapter['config']['tickers'] != list(config.tickers) or any(
        adapter['config'][k] != getattr(config,k) for k in
        ('max_spread_bps','max_depth_distance_bps','book_levels','recent_trades'))):
        raise ValueError('canonical quality settings differ from v3')
    if adapter['timing']['collection_timezone'] != 'America/Sao_Paulo' or adapter['timing']['trade_timezone'] != 'America/New_York':
        raise ValueError('canonical clock assumptions differ from audited evidence')
    ref=defaultdict(dict)
    with gzip.open(grid_path,'rt') as handle:
        for r in csv.DictReader(handle):
            key=r['decision_at'];block=ref[r['session_id']].setdefault(key,{})
            if r['ticker'] not in config.tickers or r['ticker'] in block:raise ValueError('invalid reference universe')
            block[r['ticker']]=r['state']=='valid'
    scheduled=[d for d in market_calendar.dates(first,last) if market_calendar.window(d)]
    if set(ref)!={str(d) for d in scheduled}:raise ValueError('reference calendar differs from protocol')
    for part in ('train','validation','test','final_refit'):
        p=partitions[part]
        if sum(p['first']<=str(d)<=p['last'] for d in scheduled)!=p['scheduled_sessions']:
            raise ValueError('partition calendar count mismatch')
    grouped=defaultdict(list);raw=defaultdict(list);raw_paths=set()
    for index,source in enumerate(adapter['inputs']):
        path=Path(source['path']);verify(path,source['sha256'])
        if path.resolve() in raw_paths:raise ValueError('duplicate raw input')
        raw_paths.add(path.resolve())
        m=re.fullmatch(r'data_scrapping_(\d+)_(\d+)_(\d+)\.parquet',path.name)
        if m is None:raise ValueError('dated original filename required')
        day=date(int(m[3]),int(m[2]),int(m[1]))
        if not first<=day<=last:raise ValueError('raw input outside partitions')
        name=f'snapshots_{index:04d}_{path.stem}.jsonl.gz'
        verify(adapter_dir/name,adapter['outputs'][name])
        grouped[day].append(adapter_dir/name);raw[day].append(source)
    output_dir.mkdir(parents=True,exist_ok=False)
    manifest=dict(schema=SCHEMA,status='in_progress',training_ready=False,protocol_id=protocol['protocol_id'],
        inputs=anchors,adapter_manifest=str(adapter_path.resolve()),protocol_path=str(protocol_path.resolve()),
        tickers=list(config.tickers),adapter_timing_metadata=adapter['timing'],
        effective_timing=dict(alignment_clock='available_at',source_delay_seconds=None,
            fixed_source_delay_established=False,source_delay_correction='none',
            collection_timezone=adapter['timing']['collection_timezone'],
            trade_timezone=adapter['timing']['trade_timezone']),
        alignment='available_at only; no source-delay subtraction, including legacy 10800s metadata',
        created_at=iso(datetime.now(timezone.utc)),sessions=[],partition_summary={},outputs={},
        limitations=['Provisional clock assumptions; book market timestamp not certified.',
            'Long-gap rule and final eligibility unresolved; candidates are not training data.',
            'No normalizer, policy, reward or financial returns produced.'])
    def save(): (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    save();summary=defaultdict(Counter)
    try:
        for day in scheduled:
            session,refs=align_partial(day,canonical_day(grouped[day],config_for(protocol,day)),config_for(protocol,day))
            expected=ref[str(day)]
            if set(expected)!={r['at'] for r in refs}:raise ValueError('reference grid differs from calendar')
            for r in refs:
                if set(expected[r['at']])!=set(config.tickers) or any(
                    expected[r['at']][t] != (t in r['snapshots']) for t in config.tickers):
                    raise ValueError(f'grid availability differs from verified audit: {day} {r["at"]}')
            diagnostics=analyze_day({t:[t in r['snapshots'] for r in refs] for t in config.tickers})
            part=next(k for k in ('train','validation','test') if partitions[k]['first']<=str(day)<=partitions[k]['last'])
            name=f'grid_{day}.jsonl.gz'
            with gzip.open(output_dir/name,'wt') as handle:
                for r in refs:handle.write(json.dumps(r,separators=(',',':'))+'\n')
            entry=diagnostics['entry_index']
            row=dict(session_id=str(day),partition=part,grid_file=name,
                canonical_inputs={str(p.resolve()):digest(p) for p in grouped[day]},
                raw_files=len(raw[day]),first_readiness_at=None if entry is None else refs[entry]['at'],
                entry_at=refs[entry]['at'] if diagnostics['causal_entry_available'] else None,
                exit_at=refs[-1]['at'],training_ready=False,**diagnostics)
            manifest['sessions'].append(row);manifest['outputs'][name]=digest(output_dir/name)
            summary[part]['scheduled_sessions']+=1
            for key in ('causal_entry_available','masked_coverage_candidate'):
                summary[part][key]+=diagnostics[key]
            print(json.dumps(dict(session_id=str(day),candidate=diagnostics['masked_coverage_candidate'])),flush=True)
        for path,sha in anchors.items():verify(path,sha)
        for path,sha in source_manifests.items():verify(path,sha)
        for source in adapter['inputs']:verify(source['path'],source['sha256'])
        for paths in grouped.values():
            for p in paths:verify(p,adapter['outputs'][p.name])
        manifest.update(status='provisional_partial_grid',session_count=len(scheduled),
            reference_availability_reproduced=True,partition_summary={k:dict(v) for k,v in summary.items()},
            closed_dates_with_raw_files=[str(d) for d in sorted(grouped) if market_calendar.window(d) is None],
            code_sha256={str(p):digest(p) for p in (Path(__file__),Path(data_pipeline.__file__),
                Path(__file__).with_name('audit_protocol_alternatives.py'),Path(__file__).with_name('session_replay.py'))})
        save()
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));save();raise
    return manifest


def read_prepared_session(directory, day, *, protocol_snapshot=None):
    """Verified raw-feature replay input; synthetic=False keeps fitting blocked."""
    directory=Path(directory);m=json.loads((directory/'manifest.json').read_text())
    if m['schema']!=SCHEMA or m['status']!='provisional_partial_grid' or m['training_ready'] is not False:
        raise ValueError('completed provisional v3 preparation required')
    protocol_file=Path(protocol_snapshot) if protocol_snapshot is not None else Path(m['protocol_path'])
    # An immutable copy is accepted only when byte-identical to the producer protocol.
    for p,sha in m['inputs'].items():
        verify(protocol_file if p==m['protocol_path'] else p,sha)
    row=next((r for r in m['sessions'] if r['session_id']==str(day)),None)
    if row is None:raise ValueError('date outside prepared scheduled sessions')
    name=row['grid_file']
    if Path(name).name!=name:raise ValueError('grid must be a local filename')
    verify(directory/name,m['outputs'][name]);paths=[]
    for p,sha in row['canonical_inputs'].items():verify(p,sha);paths.append(Path(p))
    protocol=json.loads(protocol_file.read_text());config=config_for(protocol,day)
    session,expected=align_partial(day,canonical_day(paths,config),config)
    with gzip.open(directory/name,'rt') as handle:actual=[json.loads(line) for line in handle]
    if actual!=expected:raise ValueError('prepared references differ from causal alignment')
    return session


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter-dir',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--audit-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();m=prepare(a.adapter_dir,a.protocol,a.audit_dir,a.output_dir)
    print(json.dumps(m['partition_summary'],indent=2))


if __name__=='__main__':main()
