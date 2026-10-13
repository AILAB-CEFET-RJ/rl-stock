"""Causal market-feature cache; dynamic portfolio context remains per decision."""
from datetime import timedelta
import numpy as np

from .masked_observations import AGE_SECONDS,FeatureCursor,MaskedEncoder
from .missing_data_replay import MaskedDailyReplay,MaskedSessionResult


class CachedMaskedEncoder(MaskedEncoder):
    def __init__(self,normalizer,session,initial_capital=100000,*,include_account_context=False):
        super().__init__(normalizer,initial_capital,include_account_context=include_account_context)
        self.session=session
        episode=MaskedDailyReplay(self.tickers).start(session.day,session.frames)
        if isinstance(episode,MaskedSessionResult) or episode._missing_exit:raise ValueError('causal entry and common exit required')
        obs=episode.observation();self.opening=episode.plan.opening
        cursor=FeatureCursor(self.tickers,obs.lag_reference,obs.reference_state)
        self.frames=episode._indexed;self.rows={};self.references={}
        for at in episode.plan.required_times:
            if at<=obs.lag_reference.at:continue
            frame=self.frames[at];row=cursor.consume(frame,session.trades)
            values=np.asarray(normalizer.transform(row),dtype=np.float32);values.setflags(write=False)
            self.rows[at]=values
            self.references[at]=(row.availability,tuple(cursor.references[t].book.midpoint for t in self.tickers),
                tuple(cursor.references[t].book.available_at for t in self.tickers))

    def flatten(self,observation,trades):
        if trades is not self.session.trades:raise ValueError('cache bound to the validated session trades')
        if len(observation.market_history)!=20 or observation.market_history[-1].at!=observation.at:
            raise ValueError('20-step causal window ending now required')
        expected=tuple(observation.at-timedelta(minutes=q) for q in range(19,-1,-1))
        if any(frame.at!=at or frame!=self.frames.get(at) for frame,at in zip(observation.market_history,expected)):
            raise ValueError('history differs from cached causal market frames')
        masks,mids,stamps=self.references[observation.at]
        if (masks!=observation.availability or mids!=observation.marked_midpoints or stamps!=observation.mark_capture_times):
            raise ValueError('cached references differ from observed portfolio marks')
        context=self.portfolio_context(observation,mids,self.opening)
        values=np.concatenate([self.rows[at] for at in expected]+[np.asarray(context,dtype=np.float32)])
        if not np.all(np.isfinite(values)):raise ValueError('nonfinite cached policy input')
        return values
