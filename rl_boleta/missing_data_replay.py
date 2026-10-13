"""Experimental v3 economic core and daily controller, synthetic inputs only.

An absent book is never executable liquidity. Last observed books supply marks,
not fills. V2 remains unchanged; feature encoding and historical fitting are
not implemented here. Long-gap eligibility is deliberately unresolved.
"""
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR, localcontext

from .economic_kernel import (Book, Config, ExecutionEngine, Frame,
                              Outcome, Portfolio, aware, number)
from .session_replay import session_plan

REWARD_OBJECTIVES=('marked_wealth','terminal_cash_utility')
ACCOUNT_REGIMES=('legacy_reinvest','cash_settled','intraday_buying_power')


@dataclass(frozen=True)
class PartialFrame:
    at: object
    session_id: str
    books: tuple = ()

    def __post_init__(self):
        object.__setattr__(self,'at',aware(self.at))
        object.__setattr__(self,'books',tuple(self.books))
        if not self.session_id or any(not isinstance(b,Book) for b in self.books):
            raise ValueError('session and explicit books required')
        if len({b.ticker for b in self.books})!=len(self.books):
            raise ValueError('duplicate ticker')
        if any(b.available_at>self.at for b in self.books):
            raise ValueError('future capture')

    def book(self,ticker):
        return next(b for b in self.books if b.ticker==ticker)


class PartialExecutionEngine(ExecutionEngine):
    """Reuse per-level accounting; zero unavailable requests before allocation."""
    def validate_frame(self,frame):
        if not {b.ticker for b in frame.books}<=set(self.config.tickers):
            raise ValueError('unknown asset')
        for b in frame.books:
            if (frame.at-b.available_at).total_seconds()>self.config.max_receipt_age_seconds:
                raise ValueError('stale execution book')
            if (b.ticker,b.snapshot_id) in self._captures and self._captures[(b.ticker,b.snapshot_id)]!=b:
                raise ValueError('conflicting capture identity')

    def execute(self,portfolio,desired,observed_midpoints,frame,kind='regular',*,buying_cash_limit=None):
        desired=tuple(desired)
        if len(desired)!=len(self.config.tickers) or any(type(d) is not int for d in desired):
            raise ValueError('invalid order quantities')
        available={b.ticker for b in frame.books}
        effective=tuple(d if t in available else 0 for t,d in zip(self.config.tickers,desired))
        event=super().execute(portfolio,effective,observed_midpoints,frame,kind,buying_cash_limit=buying_cash_limit)
        outcomes=tuple(Outcome(t,d,0,abs(d),('unavailable_book',),None)
                       if t not in available and d else outcome
                       for t,d,outcome in zip(self.config.tickers,desired,event.outcomes))
        return replace(event,outcomes=outcomes)


@dataclass(frozen=True)
class MaskedTransition:
    at: object
    before_wealth: Decimal
    after_wealth: Decimal
    reward: Decimal
    executions: tuple
    availability: tuple
    mark_capture_times: tuple
    applied_actions: tuple
    terminated: bool
    truncated: bool
    reason: str
    residual_holdings: tuple
    flat: bool
    canceled_pending: tuple = ()
    terminal_inventory_adjustment_usd: Decimal = Decimal(0)


class MaskedReplayKernel:
    def __init__(self,config,initial_frame,*,wind_down_points=1,reward_objective='marked_wealth',account_regime='legacy_reinvest'):
        if config.horizon<2:
            raise ValueError('two transitions required for intention, fill and exit')
        if type(wind_down_points) is not int or wind_down_points<1:
            raise ValueError('positive integer wind-down execution points required')
        self.wind_down_points=wind_down_points
        if reward_objective not in REWARD_OBJECTIVES:
            raise ValueError('explicit supported reward objective required')
        self.reward_objective=reward_objective
        if account_regime not in ACCOUNT_REGIMES:raise ValueError('explicit supported account regime required')
        self.account_regime=account_regime
        self.funding_balance=config.initial_capital
        self.pending_sale_proceeds=Decimal(0)
        self.config=config;self.engine=PartialExecutionEngine(config)
        self.frame=self._fresh(initial_frame)
        if {b.ticker for b in self.frame.books}!=set(config.tickers):
            raise ValueError('complete initial market required')
        self.engine.register_frame(self.frame)
        self.marks={b.ticker:b for b in self.frame.books}
        self.portfolio=Portfolio(config.initial_capital,(0,)*len(config.tickers))
        self.pending=None;self.index=0;self.done=False;self.stop_latched=False;self.history=[]

    def _fresh(self,frame):
        if not isinstance(frame,(PartialFrame,Frame)):
            raise ValueError('explicit partial frame required')
        if not {b.ticker for b in frame.books}<=set(self.config.tickers):
            raise ValueError('unknown asset')
        return PartialFrame(frame.at,frame.session_id,tuple(b for b in frame.books
            if (frame.at-b.available_at).total_seconds()<=self.config.max_receipt_age_seconds))

    @property
    def availability(self):
        available={b.ticker for b in self.frame.books}
        return tuple(t in available for t in self.config.tickers)

    @property
    def marked_wealth(self):
        with localcontext() as ctx:
            ctx.prec=50
            return self.portfolio.cash+sum(h*self.marks[t].midpoint
                for t,h in zip(self.config.tickers,self.portfolio.holdings))

    @property
    def buying_power(self):
        return self.funding_balance if self.account_regime=='cash_settled' else self.portfolio.cash

    @property
    def wind_down(self):
        """Next execution belongs to the scheduled exit phase; no future book used."""
        return self.index+1>=max(1,self.config.horizon-self.wind_down_points+1)

    @property
    def discretionary(self):
        return not self.done and not self.stop_latched and not self.wind_down

    def submit(self,actions):
        if not self.discretionary or self.pending is not None:
            raise ValueError('no discretionary intention permitted')
        actions=tuple(number(a) for a in actions)
        if len(actions)!=len(self.config.tickers) or any(abs(a)>1 for a in actions):
            raise ValueError('one bounded action per asset required')
        applied=tuple(a if valid else Decimal(0) for a,valid in zip(actions,self.availability))
        with localcontext() as ctx:
            ctx.prec=50;value=self.marked_wealth
            desired=tuple(0 if abs(a)<=self.config.dead_zone else
                (1 if a>0 else -1)*int((abs(a)*value/(len(applied)*self.marks[t].midpoint)).to_integral_value(rounding=ROUND_FLOOR))
                for t,a in zip(self.config.tickers,applied))
        self.pending=desired,tuple(self.marks[t].midpoint for t in self.config.tickers),applied
        return desired

    def advance(self,next_frame=None):
        if self.done:raise ValueError('episode finished')
        if self.discretionary and self.pending is None:raise ValueError('intention required')
        if next_frame is None:
            next_frame=PartialFrame(self.frame.at+timedelta(seconds=self.config.interval_seconds),self.frame.session_id)
        if next_frame.at!=self.frame.at+timedelta(seconds=self.config.interval_seconds) or next_frame.session_id!=self.frame.session_id:
            raise ValueError('consecutive same-session grid required')
        for book in next_frame.books:
            known=self.engine._captures.get((book.ticker,book.snapshot_id))
            if known is not None and known!=book:raise ValueError('conflicting capture identity')
        fresh=self._fresh(next_frame)
        self.engine.validate_frame(fresh)
        for book in fresh.books:
            old=self.marks[book.ticker]
            if book.available_at<old.available_at or (book.available_at==old.available_at and book.snapshot_id!=old.snapshot_id):
                raise ValueError('capture chronology regressed or ambiguous')
        with localcontext() as ctx:
            ctx.prec=50;before=self.marked_wealth
            updated=dict(self.marks);updated.update({b.ticker:b for b in fresh.books})
            mids=tuple(updated[t].midpoint for t in self.config.tickers)
            terminal=self.index+1==self.config.horizon
            available={b.ticker for b in fresh.books}
            events=[];actions=self.pending[2] if self.pending else (Decimal(0),)*len(mids)
            canceled=();truncated=False;reason='running'
            if terminal and len(available)!=len(self.config.tickers):
                # No retrospective or partial scheduled exit is invented.
                truncated=True;terminal=False;reason='exit_data_missing'
            elif terminal or self.stop_latched or self.wind_down:
                kind='liquidation' if terminal else 'capital_stop' if self.stop_latched else 'wind_down'
                event=self.engine.execute(self.portfolio,tuple(-h for h in self.portfolio.holdings),mids,fresh,kind)
                events.append(event)
                reason='scheduled_end' if terminal else 'capital_stop_pending' if self.stop_latched else 'wind_down'
            else:
                desired,decision_mids,_=self.pending
                canceled=tuple(d if t not in available else 0 for t,d in zip(self.config.tickers,desired))
                limit=self.buying_power if self.account_regime=='cash_settled' else None
                events.append(self.engine.execute(self.portfolio,desired,decision_mids,fresh,buying_cash_limit=limit))
            portfolio=events[-1].after if events else self.portfolio
            after=portfolio.cash+sum(h*p for h,p in zip(portfolio.holdings,mids))
            latch=self.stop_latched
            if not terminal and not truncated and after<self.config.capital_floor*self.config.initial_capital:
                if not latch:
                    latch=True
                    event=self.engine.execute(portfolio,tuple(-h for h in portfolio.holdings),mids,fresh,'capital_stop')
                    events.append(event);portfolio=event.after
                    after=portfolio.cash+sum(h*p for h,p in zip(portfolio.holdings,mids))
                reason='capital_stop_pending'
            flat=not any(portfolio.holdings)
            if latch and flat and not truncated:
                terminal=True;reason='capital_stop'
            elif terminal and not flat:reason='liquidation_failure'
            purchases=sum((f.quantity*f.price+f.fee for e in events for f in e.fills if f.side=='buy'),Decimal(0))
            sales=sum((f.quantity*f.price-f.fee for e in events for f in e.fills if f.side=='sell'),Decimal(0))
            self.funding_balance-=purchases;self.pending_sale_proceeds+=sales
            if (self.account_regime=='cash_settled' and self.funding_balance<0
                    or abs(self.funding_balance+self.pending_sale_proceeds-portfolio.cash)>Decimal('1e-35')):
                raise RuntimeError('account ledger invariant violated')
            self.portfolio=portfolio;self.marks=updated;self.frame=fresh
            self.index+=1;self.pending=None;self.stop_latched=latch;self.done=terminal or truncated
            # Learning utility gives no terminal credit to unsold inventory.
            # It does not remove assets, debit cash, invent sales or book a loss.
            adjustment=(after-portfolio.cash if terminal and
                self.reward_objective=='terminal_cash_utility' else Decimal(0))
            transition=MaskedTransition(fresh.at,before,after,
                self.config.reward_scale*(after-before-adjustment)/self.config.initial_capital,tuple(events),
                tuple(t in available for t in self.config.tickers),tuple(updated[t].available_at for t in self.config.tickers),
                actions,terminal,truncated,reason,portfolio.holdings,flat,canceled,adjustment)
            self.history.append(transition)
            return transition


@dataclass(frozen=True)
class ReferencePoint:
    book: Book
    grid_at: object

    def __post_init__(self):
        object.__setattr__(self,'grid_at',aware(self.grid_at))
        if not isinstance(self.book,Book) or self.book.available_at>self.grid_at:
            raise ValueError('reference must be observed by its grid time')


@dataclass(frozen=True)
class MaskedObservation:
    at: object
    market_history: tuple
    lag_reference: PartialFrame
    portfolio: Portfolio
    availability: tuple
    marked_midpoints: tuple
    mark_capture_times: tuple
    remaining_transitions: int
    scheduled_liquidation: object
    reference_state: tuple = ()  # latest valid points as of lag_reference, not future
    account_regime: str = 'legacy_reinvest'
    buying_power: object = None
    pending_sale_proceeds: object = None


@dataclass(frozen=True)
class MaskedSessionResult:
    plan: object
    status: str
    startable: bool
    coverage_candidate: bool
    transitions: tuple
    portfolio: Portfolio
    missing_exit_assets: tuple
    training_ready: bool = False

    @property
    def marked_return(self):
        if not self.coverage_candidate or not self.transitions or self.transitions[-1].truncated:
            return None
        with localcontext() as ctx:
            ctx.prec=50
            return (self.transitions[-1].after_wealth-self.transitions[0].before_wealth)/self.transitions[0].before_wealth

    @property
    def realized_return(self):
        return self.marked_return if self.transitions and self.transitions[-1].flat else None


class MaskedSessionEpisode:
    def __init__(self,plan,config,indexed,history,missing_exit,*,wind_down_points=1,reward_objective='marked_wealth',account_regime='legacy_reinvest'):
        self.plan=plan;self._indexed=indexed;self._history=list(history)
        self._missing_exit=missing_exit
        self.kernel=MaskedReplayKernel(config,history[-1],wind_down_points=wind_down_points,
                                      reward_objective=reward_objective,account_regime=account_regime)
        for frame in history[:-1]:self.kernel.engine.register_frame(frame)
        references={};self._reference_history=[]
        for frame in history:
            references.update({b.ticker:ReferencePoint(b,frame.at) for b in frame.books})
            self._reference_history.append(tuple(references[t] for t in config.tickers))

    @property
    def discretionary(self):return self.kernel.discretionary

    def observation(self,allow_terminal=False):
        if self.kernel.done and not allow_terminal:raise ValueError('episode finished')
        if self.kernel.done and self.kernel.history[-1].truncated:
            raise ValueError('data interruption has no training terminal observation')
        tickers=self.kernel.config.tickers
        return MaskedObservation(self.kernel.frame.at,tuple(self._history[-self.plan.window_features:]),
            self._history[-self.plan.window_features-1],self.kernel.portfolio,self.kernel.availability,
            tuple(self.kernel.marks[t].midpoint for t in tickers),
            tuple(self.kernel.marks[t].available_at for t in tickers),
            0 if self.kernel.done else self.plan.horizon-self.kernel.index,self.plan.liquidation,
            self._reference_history[-self.plan.window_features-1],self.kernel.account_regime,
            None if self.kernel.account_regime=='legacy_reinvest' else self.kernel.buying_power,
            None if self.kernel.account_regime=='legacy_reinvest' else self.kernel.pending_sale_proceeds)

    def advance(self,actions=None):
        if self.discretionary:
            if actions is None:raise ValueError('intention required')
            self.kernel.submit(actions)
        elif actions is not None:raise ValueError('reserved or stop interval accepts no action')
        at=self.kernel.frame.at+timedelta(minutes=1)
        transition=self.kernel.advance(self._indexed[at])
        self._history.append(self.kernel.frame)
        self._history=self._history[-self.plan.window_features-1:]
        references={r.book.ticker:r for r in self._reference_history[-1]}
        references.update({b.ticker:ReferencePoint(b,self.kernel.frame.at) for b in self.kernel.frame.books})
        self._reference_history.append(tuple(references[t] for t in self.kernel.config.tickers))
        self._reference_history=self._reference_history[-self.plan.window_features-1:]
        return transition

    def result(self):
        if not self.kernel.done:raise ValueError('episode running')
        return MaskedSessionResult(self.plan,self.kernel.history[-1].reason,True,not self._missing_exit,
            tuple(self.kernel.history),self.kernel.portfolio,self._missing_exit)


class MaskedDailyReplay:
    """Calendar-bound causal start; future exit coverage is never a policy input."""
    def __init__(self,tickers,window_features=20,*,wind_down_points=1,reward_objective='marked_wealth',account_regime='legacy_reinvest',**economic_options):
        if 'horizon' in economic_options or 'interval_seconds' in economic_options:
            raise ValueError('calendar determines horizon and interval')
        if type(window_features) is not int or window_features<1:raise ValueError('positive window required')
        if type(wind_down_points) is not int or wind_down_points<1:
            raise ValueError('positive integer wind-down execution points required')
        self.wind_down_points=wind_down_points
        if reward_objective not in REWARD_OBJECTIVES:
            raise ValueError('explicit supported reward objective required')
        self.reward_objective=reward_objective
        if account_regime not in ACCOUNT_REGIMES:raise ValueError('explicit supported account regime required')
        self.account_regime=account_regime
        self._template=Config(tuple(tickers),horizon=2,**economic_options)
        self.window_features=window_features;self._attempted=set()

    def start(self,day,frames):
        if day in self._attempted:raise ValueError('intraday restart prohibited')
        plan=session_plan(day,self.window_features)
        supplied={};identities={};previous={}
        for frame in sorted(frames,key=lambda f:f.at):
            if not isinstance(frame,(Frame,PartialFrame)):raise ValueError('explicit frame required')
            if frame.session_id!=str(day) or not plan.opening<=frame.at<plan.closing:
                raise ValueError('frame outside session')
            if (frame.at-plan.opening).total_seconds()%60 or frame.at in supplied:
                raise ValueError('duplicate or off-grid timestamp')
            for book in frame.books:
                if book.ticker not in self._template.tickers or book.available_at<plan.opening:
                    raise ValueError('unknown asset or pre-open capture')
                key=book.ticker,book.snapshot_id
                if key in identities and identities[key]!=book:raise ValueError('conflicting capture identity')
                old=previous.get(book.ticker)
                if old and (book.available_at<old.available_at or
                    (book.available_at==old.available_at and book.snapshot_id!=old.snapshot_id)):
                    raise ValueError('capture chronology regressed or ambiguous')
                identities[key]=book;previous[book.ticker]=book
            supplied[frame.at]=frame
        indexed={at:PartialFrame(at,str(day),tuple(b for b in supplied[at].books
            if (at-b.available_at).total_seconds()<=self._template.max_receipt_age_seconds))
            if at in supplied else PartialFrame(at,str(day)) for at in plan.required_times}
        missing_exit=tuple(t for t in self._template.tickers if t not in {b.ticker for b in indexed[plan.liquidation].books})
        history=[];entry=None
        for at in plan.required_times:
            frame=indexed[at]
            if len(frame.books)==len(self._template.tickers):history.append(frame)
            else:history=[]
            if len(history)>=self.window_features+1:
                if (plan.liquidation-at).total_seconds()>=120:entry=at
                break  # Never choose a later warmup based on future coverage.
        self._attempted.add(day)
        if entry is None:
            return MaskedSessionResult(plan,'not_startable',False,False,(),
                Portfolio(self._template.initial_capital,(0,)*len(self._template.tickers)),missing_exit)
        horizon=int((plan.liquidation-entry).total_seconds()//60)
        plan=replace(plan,first_decision=entry,horizon=horizon)
        return MaskedSessionEpisode(plan,replace(self._template,horizon=horizon),indexed,
                                   history[-self.window_features-1:],missing_exit,
                                   wind_down_points=self.wind_down_points,reward_objective=self.reward_objective,
                                   account_regime=self.account_regime)

    def run(self,day,frames,policy):
        episode=self.start(day,frames)
        if isinstance(episode,MaskedSessionResult):return episode
        while not episode.kernel.done:
            episode.advance(policy(episode.observation()) if episode.discretionary else None)
        return episode.result()
