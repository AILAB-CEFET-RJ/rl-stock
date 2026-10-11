"""Frozen causal policy features. Execution always retains the raw books."""
import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .economic_kernel import number, wealth
from .session_replay import DailySessionReplay, SessionResult, read_market_csv, session_plan

SCHEMA = 'market-40-plus-capture-age-v1'
PARTITIONS = {
    'train': (date(2025, 3, 3), date(2025, 5, 30)),
    'final_refit': (date(2025, 3, 3), date(2025, 6, 30)),
}


@dataclass(frozen=True)
class Trade:
    price: object
    size: object
    at: datetime

    def __post_init__(self):
        from .economic_kernel import aware
        object.__setattr__(self, 'price', number(self.price))
        object.__setattr__(self, 'size', number(self.size))
        object.__setattr__(self, 'at', aware(self.at))
        if self.price <= 0 or self.size < 0:
            raise ValueError('invalid trade price or size')


@dataclass(frozen=True)
class MarketSession:
    day: date
    frames: tuple
    trades: dict  # (frame.at, ticker) -> ten trades in prepared CSV rank order


def read_sessions(path, tickers):
    """No clock-derived trade ages: source-time semantics remain unresolved."""
    tickers = tuple(tickers)
    frames = tuple(read_market_csv(path, tickers))
    groups, trades_by_day = {}, {}
    with Path(path).open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        required = {f'{t}_trade_{field}_{i}' for t in tickers
                    for field in ('at', 'price', 'size') for i in range(1, 11)}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError('ten explicit trades per asset required for policy inputs')
        for frame, row in zip(frames, reader, strict=True):
            day = date.fromisoformat(frame.session_id)
            groups.setdefault(day, []).append(frame)
            trades = trades_by_day.setdefault(day, {})
            for ticker in tickers:
                key = (frame.at, ticker)
                if key in trades:
                    raise ValueError('duplicate trade-frame timestamp')
                trades[key] = tuple(Trade(row[f'{ticker}_trade_price_{i}'],
                                          row[f'{ticker}_trade_size_{i}'],
                                          datetime.fromisoformat(row[f'{ticker}_trade_at_{i}']))
                                    for i in range(1, 11))
    return {day: MarketSession(day, tuple(fs), trades_by_day[day])
            for day, fs in groups.items()}


def feature_names(tickers):
    return tuple(f'{t}.{field}.{i}' for t in tickers
                 for field, count in (('bid_price', 5), ('bid_size', 5),
                                      ('ask_price', 5), ('ask_size', 5),
                                      ('trade_price', 10), ('trade_size', 10))
                 for i in range(1, count+1))


def market_row(previous, current, trades, tickers):
    if (current.session_id != previous.session_id or
            current.at != previous.at + timedelta(minutes=1)):
        raise ValueError('features require consecutive same-session lag reference')
    values = []
    for ticker in tickers:
        book = current.book(ticker)
        reference = previous.book(ticker).midpoint
        displayed = trades.get((current.at, ticker), ())
        if len(displayed) != 10:
            raise ValueError('ten trades required; no zero imputation')
        for levels in (book.bids, book.asks):
            values.extend(float(l.price/reference-1) for l in levels)
            values.extend(math.log1p(float(l.size)) for l in levels)
        values.extend(float(t.price/reference-1) for t in displayed)
        values.extend(math.log1p(float(t.size)) for t in displayed)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('nonfinite transformed market features')
    return tuple(values)


@dataclass(frozen=True)
class Normalizer:
    tickers: tuple
    means: tuple
    scales: tuple
    count: int
    partition: str
    sessions: tuple

    def __post_init__(self):
        width = len(feature_names(self.tickers))
        if (not self.tickers or len(set(self.tickers)) != len(self.tickers) or
                len(self.means) != width or len(self.scales) != width or self.count < 1 or
                not all(math.isfinite(v) for v in self.means+self.scales) or
                not all(v > 0 for v in self.scales)):
            raise ValueError('invalid fitted normalizer')
        if self.partition not in PARTITIONS:
            raise ValueError('normalization must be fitted on train or final_refit')
        first, last = PARTITIONS[self.partition]
        if not self.sessions or len(set(self.sessions)) != len(self.sessions):
            raise ValueError('unique fitting session dates required')
        if any(not first <= date.fromisoformat(d) <= last for d in self.sessions):
            raise ValueError('normalizer contains dates outside fitting partition')

    def transform(self, values):
        if len(values) != len(self.means) or not all(math.isfinite(v) for v in values):
            raise ValueError('normalizer feature mismatch or nonfinite input')
        return tuple(max(-10., min(10., (v-m)/s))
                     for v, m, s in zip(values, self.means, self.scales))

    def save(self, path):
        payload = dict(schema=SCHEMA, tickers=self.tickers, features=feature_names(self.tickers),
                       means=self.means, scales=self.scales, count=self.count,
                       partition=self.partition, sessions=self.sessions, clip=[-10, 10],
                       standard_deviation='population', constant_scale=1)
        with Path(path).open('x', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text())
        if (data['schema'] != SCHEMA or tuple(data['features']) != feature_names(data['tickers'])
                or data['clip'] != [-10, 10] or data['standard_deviation'] != 'population'
                or data['constant_scale'] != 1):
            raise ValueError('normalizer schema mismatch')
        return cls(tuple(data['tickers']), tuple(data['means']), tuple(data['scales']),
                   data['count'], data['partition'], tuple(data['sessions']))


def fit_normalizer(sessions, tickers, partition='train'):
    """Welford population moments, each q2..exit grid point exactly once."""
    if partition not in PARTITIONS:
        raise ValueError('cannot fit on validation or test')
    tickers, sessions = tuple(tickers), tuple(sessions)
    first, last = PARTITIONS[partition]
    count, means, m2, used = 0, [0.]*(40*len(tickers)), [0.]*(40*len(tickers)), []
    for session in sorted(sessions, key=lambda s: s.day):
        if not first <= session.day <= last or session.day.isoformat() in used:
            raise ValueError('duplicate date or date outside normalization partition')
        controller = DailySessionReplay(tickers)
        episode = controller.start(session.day, session.frames)
        if isinstance(episode, SessionResult) or episode.failures:
            raise ValueError('fit accepts only full-coverage evaluable sessions')
        indexed = {f.at: f for f in session.frames}
        times = episode.plan.required_times
        for before, at in zip(times, times[1:]):
            values = market_row(indexed[before], indexed[at], session.trades, tickers)
            count += 1
            for j, v in enumerate(values):
                delta = v-means[j]
                means[j] += delta/count
                m2[j] += delta*(v-means[j])
        used.append(session.day.isoformat())
    scales = tuple(math.sqrt(max(0., v/count)) or 1. for v in m2) if count else ()
    return Normalizer(tickers, tuple(means), scales, count, partition, tuple(used))


class Encoder:
    def __init__(self, normalizer, initial_capital=100000):
        self.normalizer = normalizer
        self.tickers = normalizer.tickers
        self.initial_capital = number(initial_capital)
        if self.initial_capital <= 0:
            raise ValueError('positive initial capital required')

    def encode(self, observation, trades):
        previous, rows = observation.lag_reference, []
        for current in observation.market_history:
            transformed = self.normalizer.transform(market_row(previous, current, trades, self.tickers))
            ages = tuple((current.at-current.book(t).available_at).total_seconds()/60
                         for t in self.tickers)
            rows.append(transformed+ages)
            previous = current
        if not rows or previous.at != observation.at:
            raise ValueError('window must end at current decision')
        plan = session_plan(date.fromisoformat(previous.session_id), len(rows))
        p, theta = observation.portfolio, self.initial_capital
        context = (float(p.cash/theta),) + tuple(
            float(h*previous.book(t).midpoint/theta) for t, h in zip(self.tickers, p.holdings)) + (
            float(wealth(p, previous, self.tickers)/theta),
            (observation.at-plan.opening).total_seconds()/(390*60),
            observation.remaining_transitions/390)
        return tuple(rows), context

    def flatten(self, observation, trades):
        rows, context = self.encode(observation, trades)
        return tuple(v for row in rows for v in row)+context
