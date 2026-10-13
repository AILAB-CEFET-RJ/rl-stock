"""Synthetic 18-asset v3 normalization and online encoding, no agent fitting."""
import argparse
import json
import math
from datetime import date,timedelta
from pathlib import Path

from rl_boleta.data_pipeline import digest
from rl_boleta.economic_kernel import Book,Level
from rl_boleta.masked_observations import (MaskedEncoder,MaskedMarketSession,
    MaskedNormalizer,fit_masked_normalizer)
from rl_boleta.missing_data_replay import MaskedDailyReplay,PartialFrame
from rl_boleta.observations import Trade
from rl_boleta.session_replay import session_plan

TICKERS=tuple(f'SYN{i:02d}' for i in range(18))


def session(day):
    plan=session_plan(day);frames=[];trades={}
    last=int((plan.liquidation-plan.opening).total_seconds()//60)
    for q in range(1,last+1):
        at=plan.opening+timedelta(minutes=q);books=[]
        for i,ticker in enumerate(TICKERS):
            if (q==1 and i==17) or (30<=q<=65 and i==0) or 90<=q<=94:continue
            mid=100+i+(2 if q>=66 and i==0 else 0)
            book=Book(ticker,f'{day}-{ticker}-{q}',at,
                tuple(Level(mid-1-j*.01,10000) for j in range(5)),
                tuple(Level(mid+1+j*.01,10000) for j in range(5)))
            books.append(book)
            trades[at,ticker]=tuple(Trade(mid,10,at) for _ in range(10))
        frames.append(PartialFrame(at,str(day),tuple(books)))
    return MaskedMarketSession(day,tuple(frames),trades,synthetic=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('results/v3_masked_observations_2026-10-12'))
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=False)
    training=(session(date(2025,3,3)),session(date(2025,3,4)))
    normalizer=fit_masked_normalizer(training,TICKERS)
    path=args.output_dir/'normalizer.json';normalizer.save(path)
    loaded=MaskedNormalizer.load(path);assert loaded==normalizer
    encoder=MaskedEncoder(loaded)
    test=session(date(2025,7,3))
    episode=MaskedDailyReplay(TICKERS).start(test.day,test.frames)
    masks_seen=set();observations=0;maximum=0.
    with (args.output_dir/'encoding_trace.jsonl').open('w') as handle:
        while not episode.kernel.done:
            obs=episode.observation()
            rows,context=encoder.encode(obs,test.trades)
            flat=tuple(x for row in rows for x in row)+context
            assert len(flat)==15502 and all(math.isfinite(x) for x in flat)
            observations+=1;maximum=max(maximum,max(abs(x) for x in flat))
            valid=sum(obs.availability);masks_seen.add(valid)
            handle.write(json.dumps(dict(at=obs.at.isoformat(),width=len(flat),valid_assets=valid,
                final_row_receipt_ages=rows[-1][40*18+18:40*18+36],
                final_row_reference_ages=rows[-1][-18:],context=context,
                reference_checkpoint_grid=[r.grid_at.isoformat() for r in obs.reference_state]))+'\n')
            episode.advance((.5,)*18 if episode.discretionary and observations==1 else
                            (0,)*18 if episode.discretionary else None)
    result=episode.result()
    assert masks_seen=={0,17,18}
    assert normalizer==loaded
    report=dict(status='passed',synthetic=True,training_ready=False,assets=18,
        input_shape=[20,774],context_width=22,flattened_width=15502,
        fitting_sessions=normalizer.sessions,fitting_partition=normalizer.partition,
        per_feature_valid_count_range=[min(normalizer.counts),max(normalizer.counts)],
        encoded_observations=observations,valid_asset_counts_seen=sorted(masks_seen),
        maximum_absolute_encoded_value=maximum,normalizer_roundtrip_equal=True,
        normalizer_unchanged_on_test=True,replay_status=result.status,
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path('rl_boleta/masked_observations.py'),Path('rl_boleta/missing_data_replay.py'))},
        outputs_sha256={p.name:digest(p) for p in args.output_dir.iterdir()},
        limitations=['Synthetic only; no algorithm fitting or frozen historical eligibility.'])
    (args.output_dir/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
