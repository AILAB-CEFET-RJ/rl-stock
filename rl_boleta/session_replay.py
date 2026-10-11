"""Calendar-bound day-trading replay for the v2 protocol, independent of Gym.

One session, one portfolio, fixed warm-up, no restart after gaps. Policy inputs
contain only the past market window and current portfolio; coverage is returned
separately after the replay and is never passed to the policy.
"""
import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import market_calendar
from .economic_kernel import Book, Config, ExecutionEngine, Frame, Level, Portfolio, ReplayKernel


@dataclass(frozen=True)
class SessionPlan:
    day: date
    opening: datetime
    closing: datetime
    first_required: datetime
    first_decision: datetime
    liquidation: datetime
    window_features: int
    horizon: int

    @property
    def required_times(self):
        count = int((self.liquidation - self.first_required).total_seconds() // 60) + 1
        return tuple(self.first_required + timedelta(minutes=i) for i in range(count))


def session_plan(day, window_features=20):
    if type(window_features) is not int or window_features < 1:
        raise ValueError("positive integer observation window required")
    bounds = market_calendar.window(day)
    if bounds is None:
        raise ValueError("no regular trading session on this date")
    opening, closing = (t.astimezone(timezone.utc) for t in bounds)
    first_required = opening + timedelta(minutes=1)
    first_decision = opening + timedelta(minutes=window_features + 1)
    liquidation = closing - timedelta(minutes=1)
    horizon = int((liquidation - first_decision).total_seconds() // 60)
    if horizon < 1:
        raise ValueError("window leaves no trading horizon before liquidation")
    return SessionPlan(day, opening, closing, first_required, first_decision,
                       liquidation, window_features, horizon)


@dataclass(frozen=True)
class Observation:
    at: datetime
    lag_reference: Frame
    market_history: tuple
    portfolio: Portfolio
    remaining_transitions: int
    scheduled_liquidation: datetime


@dataclass(frozen=True)
class SessionResult:
    plan: SessionPlan
    status: str
    startable: bool
    evaluable: bool
    data_failures: tuple  # (expected timestamp, reason), independent of strategy
    transitions: tuple
    portfolio: Portfolio

    @property
    def flat(self):
        return not any(self.portfolio.holdings)

    @property
    def financial_return(self):
        """Completed-session estimand; never relabel a truncation as day return."""
        if not self.evaluable or not self.transitions or self.transitions[-1].truncated:
            return None
        first, last = self.transitions[0], self.transitions[-1]
        return (last.after_wealth - first.before_wealth) / first.before_wealth


class SessionEpisode:
    """Step interface shared by scripted replay and the Gym adapter."""
    def __init__(self, plan, config, indexed, failures):
        self.plan, self.failures = plan, failures
        self._indexed = indexed
        self._history = [indexed[plan.first_required + timedelta(minutes=i)]
                         for i in range(plan.window_features + 1)]
        self.kernel = ReplayKernel(config, self._history[-1])
        for frame in self._history[:-1]:
            self.kernel.engine.register_frame(frame)

    @property
    def discretionary(self):
        return not self.kernel.done and self.kernel.index < self.plan.horizon - 1

    def observation(self, allow_terminal=False):
        if self.kernel.done and (not allow_terminal or self.kernel.history[-1].truncated):
            raise ValueError("finished episode has no next decision")
        w = self.plan.window_features
        return Observation(self.kernel.frame.at, self._history[-w-1],
                           tuple(self._history[-w:]), self.kernel.portfolio,
                           self.plan.horizon-self.kernel.index, self.plan.liquidation)

    def advance(self, actions=None):
        if self.kernel.done:
            raise ValueError("episode already finished")
        if self.discretionary:
            if actions is None:
                raise ValueError("discretionary intention required")
            self.kernel.submit(actions)
        elif actions is not None:
            raise ValueError("reserved interval accepts no discretionary action")
        next_frame = self._indexed.get(self.kernel.frame.at + timedelta(minutes=1))
        transition = self.kernel.advance(next_frame)
        if not transition.truncated:
            self._history.append(next_frame)
            self._history = self._history[-self.plan.window_features-1:]
        return transition

    def result(self):
        if not self.kernel.done:
            raise ValueError("episode is still running")
        last = self.kernel.history[-1]
        return SessionResult(self.plan, "data_truncated" if last.truncated else last.reason,
                             True, not self.failures, self.failures,
                             tuple(self.kernel.history), self.kernel.portfolio)


class DailySessionReplay:
    def __init__(self, tickers, window_features=20, **economic_options):
        if "horizon" in economic_options or "interval_seconds" in economic_options:
            raise ValueError("session calendar determines horizon and one-minute interval")
        # Validate options immediately; the placeholder is never used for replay.
        self._template = Config(tuple(tickers), horizon=1, **economic_options)
        if type(window_features) is not int or window_features < 1:
            raise ValueError("positive integer observation window required")
        self.window_features = window_features
        self._attempted = set()

    @property
    def tickers(self):
        return self._template.tickers

    def _index(self, plan, frames):
        indexed = {}
        for frame in frames:
            if frame.session_id != plan.day.isoformat():
                raise ValueError("mixed sessions: provide one calendar date per replay")
            if not plan.opening <= frame.at < plan.closing:
                raise ValueError("frame outside regular session")
            if (frame.at - plan.opening).total_seconds() % 60:
                raise ValueError("frame is not on the session minute grid")
            if frame.at in indexed:
                raise ValueError("duplicate decision timestamp")
            if any(b.available_at < plan.opening for b in frame.books):
                raise ValueError("pre-opening capture cannot fill this session")
            indexed[frame.at] = frame
        return indexed

    def _coverage(self, plan, indexed, config):
        """Independent required-data check; no policy sees this retrospective flag."""
        validator = ExecutionEngine(config)
        previous = {}
        failures = []
        for at in plan.required_times:
            frame = indexed.get(at)
            if frame is None:
                failures.append((at, "missing_observation"))
                continue
            if set(b.ticker for b in frame.books) != set(self.tickers):
                failures.append((at, "incomplete_universe"))
                continue
            if any((at - b.available_at).total_seconds() > config.max_receipt_age_seconds for b in frame.books):
                failures.append((at, "stale_observation"))
                continue
            validator.register_frame(frame)
            for b in frame.books:
                old = previous.get(b.ticker)
                if old and (b.available_at < old.available_at or
                            (b.available_at == old.available_at and b.snapshot_id != old.snapshot_id)):
                    raise ValueError("capture chronology regressed or is ambiguous")
                previous[b.ticker] = b
        return tuple(failures)

    def start(self, day, frames):
        """Attempt a date once per controller. Re-evaluation uses a new controller.

        frames are aligned market frames (not raw captures). Missing grid points
        remain missing. Loaded future data is never included in Observation.
        """
        plan = session_plan(day, self.window_features)
        if day in self._attempted:
            raise ValueError("session already attempted; intraday restart is prohibited")
        indexed = self._index(plan, frames)
        config = replace(self._template, horizon=plan.horizon)
        # Integrity checks can reject contradictory inputs, but no coverage flag
        # is passed to the policy or used to bypass replaying an interrupted day.
        failures = self._coverage(plan, indexed, config)
        self._attempted.add(day)
        initial = Portfolio(config.initial_capital, (0,) * len(self.tickers))
        warmup_failure = any(at <= plan.first_decision for at, _ in failures)
        if warmup_failure:
            return SessionResult(plan, "not_startable", False, False, failures, (), initial)
        return SessionEpisode(plan, config, indexed, failures)

    def run(self, day, frames, policy):
        episode = self.start(day, frames)
        if isinstance(episode, SessionResult):
            return episode
        while not episode.kernel.done:
            episode.advance(policy(episode.observation()) if episode.discretionary else None)
        return episode.result()


def read_market_csv(path, tickers):
    """Read the revised preparer's market.csv; legacy price-only CSV is rejected.

    Produces raw book frames, not encoded/normalized RL observations. Recent
    trades remain in the original market CSV for the future feature encoder.
    """
    tickers = tuple(tickers)
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"decision_at", "session_id"}
        for ticker in tickers:
            required.update(f"{ticker}_{name}" for name in ("snapshot_id", "available_at"))
            for side in ("bid", "ask"):
                for level in range(1, 6):
                    required.update((f"{ticker}_{side}_price_{level}", f"{ticker}_{side}_size_{level}"))
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("expected revised market.csv with explicit books and capture clocks")
        for line, row in enumerate(reader, 2):
            try:
                books = []
                for ticker in tickers:
                    sides = [tuple(Level(row[f"{ticker}_{side}_price_{i}"], row[f"{ticker}_{side}_size_{i}"])
                                   for i in range(1, 6)) for side in ("bid", "ask")]
                    books.append(Book(ticker, row[f"{ticker}_snapshot_id"],
                                      datetime.fromisoformat(row[f"{ticker}_available_at"]), *sides))
                yield Frame(datetime.fromisoformat(row["decision_at"]), row["session_id"], tuple(books))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid market frame at CSV line {line}: {exc}") from exc
