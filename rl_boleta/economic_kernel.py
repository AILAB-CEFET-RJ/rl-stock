"""Auditable synthetic replay kernel for the revised paper; no Gym or RL dependency.

Money uses Decimal without cent rounding. Snapshots describe exogenous displayed
liquidity, not exchange execution guarantees. submit() sees only the current
frame; advance() supplies the next scheduled frame after the intention is fixed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
from typing import Optional


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a financial number")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError("invalid financial number") from exc
    if not result.is_finite():
        raise ValueError("financial numbers must be finite")
    return result


def aware(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Level:
    price: Decimal
    size: Decimal

    def __post_init__(self):
        object.__setattr__(self, "price", number(self.price))
        object.__setattr__(self, "size", number(self.size))
        if self.price <= 0 or self.size <= 0:
            raise ValueError("book price and size must be positive")


@dataclass(frozen=True)
class Book:
    ticker: str
    snapshot_id: str
    available_at: datetime
    bids: tuple
    asks: tuple

    def __post_init__(self):
        object.__setattr__(self, "available_at", aware(self.available_at))
        if not self.ticker or not self.snapshot_id:
            raise ValueError("ticker and capture identity are required")
        for side in ("bids", "asks"):
            levels = tuple(getattr(self, side))
            if len(levels) != 5 or not all(isinstance(x, Level) for x in levels):
                raise ValueError("five explicit levels per book side are required")
            levels = tuple(sorted(levels, key=lambda x: x.price, reverse=side == "bids"))
            if len({x.price for x in levels}) != 5:
                raise ValueError("prices must be distinct within each side")
            object.__setattr__(self, side, levels)
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("locked or crossed book")

    @property
    def midpoint(self):
        with localcontext() as ctx:
            ctx.prec = 50
            return (self.bids[0].price + self.asks[0].price) / 2


@dataclass(frozen=True)
class Frame:
    at: datetime
    session_id: str
    books: tuple

    def __post_init__(self):
        object.__setattr__(self, "at", aware(self.at))
        object.__setattr__(self, "books", tuple(self.books))
        if not self.session_id or not self.books:
            raise ValueError("session and books are required")
        if len({b.ticker for b in self.books}) != len(self.books):
            raise ValueError("duplicate ticker")
        if any(b.available_at > self.at for b in self.books):
            raise ValueError("future capture in frame")

    def book(self, ticker):
        return next(b for b in self.books if b.ticker == ticker)


@dataclass(frozen=True)
class Portfolio:
    cash: Decimal
    holdings: tuple

    def __post_init__(self):
        object.__setattr__(self, "cash", number(self.cash))
        object.__setattr__(self, "holdings", tuple(self.holdings))
        if self.cash < 0 or any(type(x) is not int or x < 0 for x in self.holdings):
            raise ValueError("cash and integer long holdings must be nonnegative")


def wealth(portfolio, frame, tickers):
    if len(portfolio.holdings) != len(tickers):
        raise ValueError("portfolio dimension mismatch")
    with localcontext() as ctx:
        ctx.prec = 50
        return portfolio.cash + sum(h * frame.book(t).midpoint for t, h in zip(tickers, portfolio.holdings))


@dataclass(frozen=True)
class Config:
    tickers: tuple
    horizon: int  # explicit: derive from the session close after warm-up
    initial_capital: Decimal = Decimal("100000")
    fee_rate: Decimal = Decimal("0.0001")
    participation: Decimal = Decimal("0.10")
    dead_zone: Decimal = Decimal("0.05")
    reward_scale: Decimal = Decimal("1")
    capital_floor: Decimal = Decimal("0.80")
    interval_seconds: int = 60
    max_receipt_age_seconds: int = 60

    def __post_init__(self):
        object.__setattr__(self, "tickers", tuple(self.tickers))
        if not self.tickers or len(set(self.tickers)) != len(self.tickers) or any(not isinstance(t, str) or not t for t in self.tickers):
            raise ValueError("explicit unique tickers required")
        for name in ("initial_capital", "fee_rate", "participation", "dead_zone", "reward_scale", "capital_floor"):
            object.__setattr__(self, name, number(getattr(self, name)))
        if not (self.initial_capital > 0 and self.reward_scale > 0 and 0 <= self.fee_rate < 1 and 0 < self.participation <= 1 and 0 <= self.dead_zone < 1 and 0 < self.capital_floor < 1):
            raise ValueError("invalid economic parameters")
        if any(type(x) is not int or x < 1 for x in (self.horizon, self.interval_seconds)):
            raise ValueError("positive integer horizon and interval required")
        if type(self.max_receipt_age_seconds) is not int or self.max_receipt_age_seconds < 0:
            raise ValueError("invalid receipt age")


def desired_orders(actions, portfolio, frame, config):
    actions = tuple(number(a) for a in actions)
    if len(actions) != len(config.tickers) or any(abs(a) > 1 for a in actions):
        raise ValueError("one action in [-1,1] per asset required")
    with localcontext() as ctx:
        ctx.prec = 50
        value = wealth(portfolio, frame, config.tickers)
        return tuple(0 if abs(a) <= config.dead_zone else
                     (1 if a > 0 else -1) * int((abs(a) * value / (len(actions) * frame.book(t).midpoint)).to_integral_value(rounding=ROUND_FLOOR))
                     for t, a in zip(config.tickers, actions))


@dataclass(frozen=True)
class Fill:
    ticker: str
    snapshot_id: str
    at: datetime
    side: str
    level: int  # one-based, execution priority within the side
    quantity: int
    price: Decimal
    fee: Decimal


@dataclass(frozen=True)
class Outcome:
    ticker: str
    desired: int
    filled: int  # signed
    canceled: int  # unsigned, includes unavailable holdings
    reasons: tuple
    vwap: Optional[Decimal]


@dataclass(frozen=True)
class Execution:
    kind: str
    before: Portfolio
    after: Portfolio
    frame: Frame
    fills: tuple
    outcomes: tuple

    @property
    def fees(self):
        return sum((f.fee for f in self.fills), Decimal(0))


class ExecutionEngine:
    """Per-agent capacity ledger; callers fix requests before supplying fill books."""

    def __init__(self, config):
        self.config = config
        self._used = {}
        self._captures = {}

    def validate_frame(self, frame):
        if set(b.ticker for b in frame.books) != set(self.config.tickers):
            raise ValueError("frame universe mismatch")
        for b in frame.books:
            if (frame.at - b.available_at).total_seconds() > self.config.max_receipt_age_seconds:
                raise ValueError("stale capture")
            key = (b.ticker, b.snapshot_id)
            if key in self._captures and self._captures[key] != b:
                raise ValueError("conflicting contents for capture identity")

    def register_frame(self, frame):
        self.validate_frame(frame)
        self._captures.update({(b.ticker, b.snapshot_id): b for b in frame.books})

    def execute(self, portfolio, desired, observed_midpoints, frame, kind="regular", *, buying_cash_limit=None):
        self.validate_frame(frame)
        desired = tuple(desired)
        mids = tuple(number(p) for p in observed_midpoints)
        n = len(self.config.tickers)
        if len(desired) != n or len(mids) != n or len(portfolio.holdings) != n or any(type(d) is not int for d in desired) or any(p <= 0 for p in mids):
            raise ValueError("invalid execution request")
        with localcontext() as ctx:
            ctx.prec = 50
            if buying_cash_limit is not None:
                buying_cash_limit=number(buying_cash_limit)
                if buying_cash_limit<0:raise ValueError('negative buying cash limit')
            return self._execute(portfolio, desired, mids, frame, kind, buying_cash_limit)

    def _execute(self, portfolio, desired, mids, frame, kind, buying_cash_limit=None):
        used = dict(self._used)  # commit only after all accounting checks succeed
        cash, holdings = portfolio.cash, list(portfolio.holdings)
        fills, outcomes = [], {}
        cfg = self.config

        def walk(i, buy, budget=None):
            nonlocal cash
            ticker, request = cfg.tickers[i], desired[i]
            b = frame.book(ticker)
            target = abs(request) if buy else min(abs(request), holdings[i])
            remaining, reasons, own_fills = target, [], []
            if not buy and target < abs(request):
                reasons.append("holdings")
            for level, quote in enumerate(b.asks if buy else b.bids, 1):
                if remaining == 0:
                    break
                key = (ticker, b.snapshot_id, "buy" if buy else "sell", level)
                capacity = int((cfg.participation * quote.size).to_integral_value(rounding=ROUND_FLOOR)) - used.get(key, 0)
                quantity = min(remaining, capacity)
                if buy:
                    unit = quote.price * (1 + cfg.fee_rate)
                    affordable = int((budget / unit).to_integral_value(rounding=ROUND_FLOOR))
                    if affordable < quantity and "cash" not in reasons:
                        reasons.append("cash")
                    quantity = min(quantity, affordable)
                    if quantity * unit > budget:  # division rounding at an exact integer boundary
                        quantity -= 1
                if quantity <= 0:
                    continue
                notional = quantity * quote.price
                fee = cfg.fee_rate * notional
                cash += -notional - fee if buy else notional - fee
                holdings[i] += quantity if buy else -quantity
                if buy:
                    budget -= notional + fee
                used[key] = used.get(key, 0) + quantity
                remaining -= quantity
                fill = Fill(ticker, b.snapshot_id, frame.at, "buy" if buy else "sell", level, quantity, quote.price, fee)
                own_fills.append(fill)
                fills.append(fill)
            if remaining:
                capacity_left = sum(max(0, int((cfg.participation * q.size).to_integral_value(rounding=ROUND_FLOOR)) - used.get((ticker, b.snapshot_id, "buy" if buy else "sell", l), 0)) for l, q in enumerate(b.asks if buy else b.bids, 1))
                if capacity_left < remaining:
                    reasons.append("depth")
                if buy and "cash" not in reasons and capacity_left:
                    reasons.append("cash")
            filled = target - remaining
            outcomes[i] = Outcome(ticker, request, filled if buy else -filled,
                                  abs(request) - filled, tuple(dict.fromkeys(reasons)),
                                  sum((f.quantity * f.price for f in own_fills), Decimal(0)) / filled if filled else None)

        for i, d in enumerate(desired):
            if d < 0:
                walk(i, False)
        sale_cash = cash if buying_cash_limit is None else min(cash,buying_cash_limit)
        total = sum((d * p for d, p in zip(desired, mids) if d > 0), Decimal(0))
        for i, d in enumerate(desired):
            if d > 0:
                # Round budgets down so independent asset allocations cannot overspend.
                with localcontext() as budget_ctx:
                    budget_ctx.rounding = ROUND_FLOOR
                    budget = sale_cash * d * mids[i] / total
                walk(i, True, budget)
            elif d == 0:
                outcomes[i] = Outcome(cfg.tickers[i], 0, 0, 0, (), None)
        after = Portfolio(cash, tuple(holdings))
        self._used = used
        self.register_frame(frame)
        return Execution(kind, portfolio, after, frame, tuple(fills), tuple(outcomes[i] for i in range(len(desired))))


@dataclass(frozen=True)
class Transition:
    at: datetime  # execution or interruption-detection time
    valuation_at: datetime  # last actually observed mark, distinct on truncation
    before_wealth: Decimal
    after_wealth: Decimal
    reward: Decimal
    executions: tuple
    terminated: bool
    truncated: bool
    reason: str
    residual_holdings: tuple
    flat: bool
    canceled_pending: tuple = ()


class ReplayKernel:
    """One-step intentions, scheduled liquidation, capital floor and gap truncation.

    Initial frame is the first decision after external warm-up. This class does
    not sample episodes, construct features or claim real-data training readiness.
    """

    def __init__(self, config, initial_frame):
        self.config = config
        self.engine = ExecutionEngine(config)
        self.engine.register_frame(initial_frame)
        self.frame = initial_frame
        self.portfolio = Portfolio(config.initial_capital, (0,) * len(config.tickers))
        self.index = 0
        self.pending = None
        self.done = False
        self.history = []

    def submit(self, actions):
        if self.done or self.pending is not None or self.index >= self.config.horizon - 1:
            raise ValueError("cannot submit: finished, pending, or reserved terminal interval")
        self.pending = (desired_orders(actions, self.portfolio, self.frame, self.config),
                        tuple(self.frame.book(t).midpoint for t in self.config.tickers))
        return self.pending[0]

    def advance(self, next_frame):
        if self.done:
            raise ValueError("episode already finished")
        if self.index + 1 < self.config.horizon and self.pending is None:
            raise ValueError("submit an intention, including hold, before advancing")
        if next_frame is None:
            return self._truncate("missing_observation")
        if next_frame.at <= self.frame.at:
            raise ValueError("replay timestamps must increase")
        if next_frame.session_id != self.frame.session_id:
            return self._truncate("session_interruption", next_frame.at)
        if next_frame.at != self.frame.at + timedelta(seconds=self.config.interval_seconds):
            return self._truncate("nonconsecutive_observation", next_frame.at)
        if set(b.ticker for b in next_frame.books) != set(self.config.tickers):
            return self._truncate("incomplete_universe", next_frame.at)
        if any((next_frame.at - b.available_at).total_seconds() > self.config.max_receipt_age_seconds for b in next_frame.books):
            return self._truncate("stale_observation", next_frame.at)
        self.engine.validate_frame(next_frame)
        for t in self.config.tickers:
            old, new = self.frame.book(t), next_frame.book(t)
            if new.available_at < old.available_at or (new.available_at == old.available_at and new.snapshot_id != old.snapshot_id):
                raise ValueError("capture chronology regressed or availability is ambiguous")
        with localcontext() as ctx:
            ctx.prec = 50
            before = wealth(self.portfolio, self.frame, self.config.tickers)
            terminal = self.index + 1 == self.config.horizon
            if terminal:
                desired = tuple(-h for h in self.portfolio.holdings)
                mids = tuple(next_frame.book(t).midpoint for t in self.config.tickers)
            else:
                desired, mids = self.pending
            event = self.engine.execute(self.portfolio, desired, mids, next_frame, "liquidation" if terminal else "regular")
            events = [event]
            after = wealth(event.after, next_frame, self.config.tickers)
            reason = "scheduled_end" if terminal else "running"
            if not terminal and after < self.config.capital_floor * self.config.initial_capital:
                exit_event = self.engine.execute(event.after, tuple(-h for h in event.after.holdings),
                                                 tuple(next_frame.book(t).midpoint for t in self.config.tickers), next_frame, "capital_stop")
                events.append(exit_event)
                after = wealth(exit_event.after, next_frame, self.config.tickers)
                reason, terminal = "capital_stop", True
            self.portfolio = events[-1].after
            self.frame, self.index = next_frame, self.index + 1
            self.pending, self.done = None, terminal
            transition = Transition(next_frame.at, next_frame.at, before, after, self.config.reward_scale * (after - before) / self.config.initial_capital,
                                    tuple(events), terminal, False, reason, self.portfolio.holdings, not any(self.portfolio.holdings))
            self.history.append(transition)
            return transition

    def _truncate(self, reason, detected_at=None):
        value = wealth(self.portfolio, self.frame, self.config.tickers)
        transition = Transition(detected_at or self.frame.at + timedelta(seconds=self.config.interval_seconds),
                                self.frame.at, value, value, Decimal(0), (), False, True, reason,
                                self.portfolio.holdings, not any(self.portfolio.holdings),
                                self.pending[0] if self.pending else ())
        self.pending, self.done = None, True
        self.history.append(transition)
        return transition
