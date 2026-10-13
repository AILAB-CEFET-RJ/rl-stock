"""Causal masked v3 features and per-feature normalization primitives.

References can precede the visible history, but never the current session.
The generic fitting API is synthetic-only; historical fitting uses frozen manifests.
"""
import json
import math
from dataclasses import asdict,dataclass
from datetime import date,timedelta
from pathlib import Path

from .economic_kernel import number
from .missing_data_replay import MaskedDailyReplay,MaskedSessionResult,ReferencePoint
from .observations import PARTITIONS,Trade,feature_names
from .session_replay import session_plan

SCHEMA='masked-market-40-plus-three-availability-fields-v3'
AGE_SECONDS=390*60


@dataclass(frozen=True)
class MaskedRow:
    at: object
    values: tuple  # forty floats per asset, or forty None when absent
    availability: tuple
    receipt_ages: tuple
    reference_ages: tuple

    def validate(self,tickers):
        n=len(tickers)
        if len(self.values)!=40*n or any(len(v)!=n for v in
                (self.availability,self.receipt_ages,self.reference_ages)):
            raise ValueError('masked feature dimension mismatch')
        for i,valid in enumerate(self.availability):
            if type(valid) is not bool:raise ValueError('binary availability required')
            block=self.values[40*i:40*(i+1)]
            if valid and any(v is None or not math.isfinite(v) for v in block):
                raise ValueError('valid asset requires finite market fields')
            if not valid and any(v is not None for v in block):
                raise ValueError('missing asset must have absent fields')
        if any(not math.isfinite(v) or not 0<=v<=1 for v in self.receipt_ages+self.reference_ages):
            raise ValueError('bounded finite ages required')


class FeatureCursor:
    """Stateful forward-only feature transform; all updates committed together."""
    def __init__(self,tickers,lag_reference,reference_state):
        self.tickers=tuple(tickers)
        self.at=lag_reference.at;self.session_id=lag_reference.session_id
        self.opening=session_plan(date.fromisoformat(self.session_id)).opening
        self.references={r.book.ticker:r for r in reference_state}
        if len(reference_state)!=len(self.tickers) or set(self.references)!=set(self.tickers):
            raise ValueError('one causal reference per asset required')
        for r in reference_state:
            if not isinstance(r,ReferencePoint) or not self.opening<=r.grid_at<=self.at or r.book.available_at<self.opening:
                raise ValueError('reference outside observed session past')
            if (r.grid_at-self.opening).total_seconds()%60:
                raise ValueError('reference is off grid')

    def consume(self,frame,trades):
        if frame.at!=self.at+timedelta(minutes=1) or frame.session_id!=self.session_id:
            raise ValueError('consecutive same-session history required')
        if not {b.ticker for b in frame.books}<=set(self.tickers):
            raise ValueError('unknown feature asset')
        books={b.ticker:b for b in frame.books
               if (frame.at-b.available_at).total_seconds()<=60}
        values=[];masks=[];receipt=[];reference=[];updated=dict(self.references)
        for ticker in self.tickers:
            prior=self.references[ticker];book=books.get(ticker)
            valid=book is not None;masks.append(valid)
            if valid:
                if book.available_at<prior.book.available_at or book.available_at<self.opening:
                    raise ValueError('capture chronology or session mismatch')
                if book.available_at==prior.book.available_at and book!=prior.book:
                    raise ValueError('ambiguous or conflicting capture')
                displayed=trades.get((frame.at,ticker),())
                if len(displayed)!=10 or any(not isinstance(t,Trade) for t in displayed):
                    raise ValueError('ten explicit validated trades required')
                if any(t.at>frame.at for t in displayed):raise ValueError('future trade')
                if any(a.at<b.at for a,b in zip(displayed,displayed[1:])):
                    raise ValueError('trades must be ranked by descending time')
                ref=prior.book.midpoint
                for levels in (book.bids,book.asks):
                    values.extend(float(l.price/ref-1) for l in levels)
                    values.extend(math.log1p(float(l.size)) for l in levels)
                values.extend(float(t.price/ref-1) for t in displayed)
                values.extend(math.log1p(float(t.size)) for t in displayed)
                receipt.append(min(1.,(frame.at-book.available_at).total_seconds()/AGE_SECONDS))
                reference.append(min(1.,(frame.at-prior.grid_at).total_seconds()/AGE_SECONDS))
                updated[ticker]=ReferencePoint(book,frame.at)
            else:
                values.extend([None]*40)
                receipt.append(min(1.,(frame.at-prior.book.available_at).total_seconds()/AGE_SECONDS))
                reference.append(0.)
        row=MaskedRow(frame.at,tuple(values),tuple(masks),tuple(receipt),tuple(reference))
        row.validate(self.tickers)
        self.references=updated;self.at=frame.at
        return row


@dataclass(frozen=True)
class MaskedNormalizer:
    tickers: tuple
    means: tuple
    scales: tuple
    counts: tuple
    partition: str
    sessions: tuple
    synthetic_only: bool = True

    def __post_init__(self):
        width=40*len(self.tickers)
        if not self.tickers or len(set(self.tickers))!=len(self.tickers):raise ValueError('unique assets required')
        if any(len(v)!=width for v in (self.means,self.scales,self.counts)):
            raise ValueError('normalizer dimension mismatch')
        if any(not math.isfinite(v) for v in self.means+self.scales) or any(v<=0 for v in self.scales):
            raise ValueError('finite positive scales required')
        if any(type(c) is not int or c<1 for c in self.counts):raise ValueError('positive per-feature counts required')
        if self.partition not in PARTITIONS:raise ValueError('invalid fitting partition')
        self._validate_origin()
        first,last=PARTITIONS[self.partition]
        if not self.sessions or len(set(self.sessions))!=len(self.sessions) or any(
                not first<=date.fromisoformat(d)<=last for d in self.sessions):
            raise ValueError('normalization dates outside fitting partition')

    def _validate_origin(self):
        if self.synthetic_only is not True:raise ValueError('historical fitting is not enabled in generic normalizer')

    def transform(self,row):
        row.validate(self.tickers)
        values=tuple(0. if v is None else max(-10.,min(10.,(v-m)/s))
                     for v,m,s in zip(row.values,self.means,self.scales))
        return values+tuple(float(v) for v in row.availability)+row.receipt_ages+row.reference_ages

    def save(self,path):
        payload=dict(schema=SCHEMA,feature_names=feature_names(self.tickers),clip=[-10,10],
            age_denominator_seconds=AGE_SECONDS,std_ddof=0,masked_sentinel='zero_after_standardization',
            **asdict(self))
        with Path(path).open('x') as handle:json.dump(payload,handle,indent=2,allow_nan=False)

    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text())
        if (data.get('schema')!=SCHEMA or data.get('clip')!=[-10,10] or data.get('std_ddof')!=0
            or data.get('age_denominator_seconds')!=AGE_SECONDS
            or data.get('masked_sentinel')!='zero_after_standardization'
            or tuple(data.get('feature_names',()))!=feature_names(data['tickers'])):
            raise ValueError('incompatible masked normalizer schema')
        return cls(tuple(data['tickers']),tuple(data['means']),tuple(data['scales']),
                   tuple(data['counts']),data['partition'],tuple(data['sessions']),data['synthetic_only'])


@dataclass(frozen=True)
class MaskedMarketSession:
    day: date
    frames: tuple
    trades: dict
    synthetic: bool = False


class MaskedMoments:
    """Streaming population moments; missing fields never count as observations."""
    def __init__(self,tickers):
        self.tickers=tuple(tickers);width=40*len(self.tickers)
        self.counts=[0]*width;self.means=[0.]*width;self.m2=[0.]*width

    def update(self,row):
        row.validate(self.tickers)
        for j,value in enumerate(row.values):
            if value is not None:
                self.counts[j]+=1;delta=value-self.means[j]
                self.means[j]+=delta/self.counts[j];self.m2[j]+=delta*(value-self.means[j])

    @property
    def scales(self):
        return tuple(math.sqrt(max(0.,var/n)) or 1. if n else 1. for var,n in zip(self.m2,self.counts))


def masked_market_rows(session,tickers):
    """Unique feature points from causal warmup through exit; no economic policy."""
    episode=MaskedDailyReplay(tickers).start(session.day,session.frames)
    if isinstance(episode,MaskedSessionResult) or episode._missing_exit:
        raise ValueError('normalization requires causal entry and common exit coverage')
    obs=episode.observation();cursor=FeatureCursor(tickers,obs.lag_reference,obs.reference_state)
    for frame in obs.market_history:yield cursor.consume(frame,session.trades)
    for at in episode.plan.required_times:
        if at>obs.at:yield cursor.consume(episode._indexed[at],session.trades)


def fit_masked_normalizer(sessions,tickers,partition='train'):
    if partition not in PARTITIONS:raise ValueError('cannot fit on validation or test')
    sessions=tuple(sessions);tickers=tuple(tickers)
    if not sessions or any(s.synthetic is not True for s in sessions):
        raise ValueError('historical normalization requires the frozen-manifest fitting API')
    first,last=PARTITIONS[partition];moments=MaskedMoments(tickers);dates=[]
    for session in sorted(sessions,key=lambda s:s.day):
        if not first<=session.day<=last or str(session.day) in dates:
            raise ValueError('duplicate or out-of-partition fitting date')
        for row in masked_market_rows(session,tickers):moments.update(row)
        dates.append(str(session.day))
    return MaskedNormalizer(tickers,tuple(moments.means),moments.scales,tuple(moments.counts),partition,tuple(dates))


class MaskedEncoder:
    def __init__(self,normalizer,initial_capital=100000,*,include_account_context=False):
        if not isinstance(normalizer,MaskedNormalizer):raise ValueError('v3 normalizer required')
        self.normalizer=normalizer;self.tickers=normalizer.tickers
        self.initial_capital=number(initial_capital)
        if type(include_account_context) is not bool:raise ValueError('explicit account context flag required')
        self.include_account_context=include_account_context
        if self.initial_capital<=0:raise ValueError('positive initial capital required')

    def encode(self,observation,trades):
        history=observation.market_history
        if len(history)!=20 or history[-1].at!=observation.at:raise ValueError('20-step window ending now required')
        cursor=FeatureCursor(self.tickers,observation.lag_reference,observation.reference_state)
        rows=[];last=None
        for frame in history:
            last=cursor.consume(frame,trades);rows.append(self.normalizer.transform(last))
        if last.availability!=observation.availability:raise ValueError('availability disagrees with history')
        mids=tuple(cursor.references[t].book.midpoint for t in self.tickers)
        stamps=tuple(cursor.references[t].book.available_at for t in self.tickers)
        if mids!=observation.marked_midpoints or stamps!=observation.mark_capture_times:
            raise ValueError('portfolio marks disagree with causal history')
        p=observation.portfolio;theta=self.initial_capital
        if len(p.holdings)!=len(self.tickers):raise ValueError('portfolio dimension mismatch')
        marked=p.cash+sum(h*mid for h,mid in zip(p.holdings,mids))
        context=self.portfolio_context(observation,mids,cursor.opening)
        if not all(math.isfinite(v) for row in rows for v in row) or not all(math.isfinite(v) for v in context):
            raise ValueError('nonfinite policy input')
        return tuple(rows),context

    def portfolio_context(self,observation,mids,opening):
        p=observation.portfolio;theta=self.initial_capital
        marked=p.cash+sum(h*mid for h,mid in zip(p.holdings,mids))
        extra=()
        if self.include_account_context:
            if observation.account_regime not in ('cash_settled','intraday_buying_power'):
                raise ValueError('explicit account observation required')
            power=number(observation.buying_power);pending=number(observation.pending_sale_proceeds)
            if not 0<=power<=p.cash or pending<0:raise ValueError('invalid account observation')
            extra=(float(power/theta),float(pending/theta),float(observation.account_regime=='intraday_buying_power'))
        elif observation.account_regime!='legacy_reinvest':
            raise ValueError('encoder must expose account buying power')
        return (float(p.cash/theta),)+tuple(float(h*mid/theta) for h,mid in zip(p.holdings,mids))+(
            float(marked/theta),)+extra+((observation.at-opening).total_seconds()/AGE_SECONDS,
            observation.remaining_transitions/390)

    def flatten(self,observation,trades):
        rows,context=self.encode(observation,trades)
        return tuple(v for row in rows for v in row)+context
