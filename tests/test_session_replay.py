"""Calendar, causality and daily accounting integration, synthetic books only."""
import ast
import csv
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from rl_boleta.economic_kernel import Book, Frame, Level
from rl_boleta.session_replay import DailySessionReplay, read_market_csv, session_plan

DAY = date(2025, 3, 3)


def frames(day=DAY):
    plan = session_plan(day)
    return [Frame(at, day.isoformat(), (Book(
        'A', at.isoformat(), at,
        tuple(Level(99-i, 10000) for i in range(5)),
        tuple(Level(101+i, 10000) for i in range(5))),))
        for at in plan.required_times]


def replay(**kwargs):
    return DailySessionReplay(('A',), initial_capital=1000, **kwargs)


class SessionTests(unittest.TestCase):
    def test_calendar_normal_short_and_dst(self):
        normal, short = session_plan(DAY), session_plan(date(2025, 7, 3))
        self.assertEqual((normal.horizon, short.horizon), (368, 188))
        self.assertEqual((len(normal.required_times), len(short.required_times)), (389, 209))
        self.assertEqual(normal.first_decision.hour, 14)
        self.assertEqual(session_plan(date(2025, 3, 10)).first_decision.hour, 13)
        self.assertEqual((short.liquidation.hour, short.liquidation.minute), (16, 59))

    def test_reject_holiday_outside_scope_and_invalid_horizon(self):
        for day in (date(2025, 7, 4), date(2025, 8, 1)):
            with self.assertRaises(ValueError):
                session_plan(day)
        with self.assertRaises(ValueError):
            session_plan(DAY, 389)
        with self.assertRaises(ValueError):
            replay(horizon=60)

    def test_one_portfolio_through_hours_and_costed_exit(self):
        seen = []
        def policy(obs):
            seen.append(obs)
            return (1 if len(seen) == 1 else 0,)
        result = replay().run(DAY, frames(), policy)
        self.assertEqual(result.status, 'scheduled_end')
        self.assertTrue(result.evaluable and result.startable and result.flat)
        self.assertEqual(len(result.transitions), 368)
        self.assertEqual(len(seen), 367)
        self.assertTrue(all(o.portfolio.holdings == (9,) for o in seen[1:]))
        self.assertEqual(result.portfolio.cash, Decimal('981.8200'))
        self.assertEqual(result.financial_return, Decimal('-0.01818'))
        self.assertEqual(seen[-1].at, result.plan.liquidation-timedelta(minutes=2))
        self.assertEqual(result.transitions[-1].executions[0].kind, 'liquidation')

    def test_causal_window_and_remaining_time(self):
        seen = []
        result = replay().run(DAY, frames(), lambda o: seen.append(o) or (0,))
        for i, obs in enumerate(seen):
            self.assertEqual(len(obs.market_history), 20)
            self.assertEqual(obs.market_history[-1].at, obs.at)
            self.assertEqual(obs.lag_reference.at, obs.at-timedelta(minutes=20))
            self.assertTrue(all(f.at <= obs.at for f in obs.market_history))
            self.assertEqual(obs.remaining_transitions, 368-i)
        self.assertEqual(result.financial_return, 0)

    def test_short_session_exits_at_reserved_minute(self):
        day = date(2025, 7, 3)
        result = replay().run(day, frames(day), lambda o: (0,))
        self.assertEqual(len(result.transitions), 188)
        self.assertEqual(result.transitions[-1].at, result.plan.liquidation)

    def test_missing_warmup_never_shifts_start(self):
        for index in (0, 10, 20):
            data = frames(); del data[index]
            result = replay().run(DAY, data, lambda o: self.fail('policy called'))
            self.assertEqual(result.status, 'not_startable')
            self.assertFalse(result.evaluable or result.startable)
            self.assertEqual(result.transitions, ())

    def test_gap_cancels_intention_and_does_not_resume(self):
        data = frames(); missing = data.pop(40).at
        controller = replay()
        result = controller.run(DAY, data, lambda o: (1,))
        self.assertEqual(result.status, 'data_truncated')
        self.assertEqual(result.transitions[-1].at, missing)
        self.assertEqual(result.transitions[-1].valuation_at, missing-timedelta(minutes=1))
        self.assertFalse(result.flat or result.evaluable)
        self.assertIsNone(result.financial_return)
        self.assertEqual(result.transitions[-1].executions, ())
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            controller.run(DAY, frames(), lambda o: (0,))

    def test_missing_liquidation_keeps_inventory(self):
        result = replay().run(DAY, frames()[:-1], lambda o: (1,))
        self.assertEqual(result.status, 'data_truncated')
        self.assertFalse(result.flat)
        self.assertIsNone(result.financial_return)
        self.assertEqual(result.transitions[-1].executions, ())

    def test_future_gap_still_excludes_early_economic_stop(self):
        result = replay(capital_floor=Decimal('.999')).run(DAY, frames()[:-1], lambda o: (1,))
        self.assertEqual(result.status, 'capital_stop')
        self.assertEqual(len(result.transitions), 1)
        self.assertFalse(result.evaluable)
        self.assertIsNone(result.financial_return)

    def test_stale_and_incomplete_frames_truncate(self):
        for mode in ('stale', 'incomplete'):
            data = frames(); f = data[40]
            data[40] = replace(f, books=(replace(f.books[0], ticker='B'),) if mode == 'incomplete' else (
                replace(f.books[0], available_at=f.at-timedelta(seconds=61)),))
            result = replay().run(DAY, data, lambda o: (0,))
            self.assertEqual(result.status, 'data_truncated')
            self.assertEqual(result.transitions[-1].reason,
                             'stale_observation' if mode == 'stale' else 'incomplete_universe')

    def test_reject_mixed_duplicate_offgrid_and_preopening(self):
        data = frames()
        invalid = (replace(data[0], session_id='2025-03-04'),
                   replace(data[0], at=data[0].at+timedelta(seconds=1)),
                   replace(data[0], books=(replace(data[0].books[0],
                       available_at=session_plan(DAY).opening-timedelta(seconds=1)),)))
        for f in invalid:
            with self.assertRaises(ValueError):
                replay().run(DAY, [f], lambda o: (0,))
        with self.assertRaises(ValueError):
            replay().run(DAY, data+[data[0]], lambda o: (0,))

    def test_next_date_starts_in_cash(self):
        controller = replay()
        controller.run(DAY, frames()[:-1], lambda o: (1,))
        seen = []
        day = date(2025, 3, 4)
        controller.run(day, frames(day), lambda o: seen.append(o) or (0,))
        self.assertEqual(seen[0].portfolio.cash, 1000)
        self.assertEqual(seen[0].portfolio.holdings, (0,))

    def test_csv_contract_roundtrip_and_legacy_rejection(self):
        rows = []
        for f in frames():
            b = f.books[0]
            row = dict(decision_at=f.at.isoformat(), session_id=f.session_id,
                       A_snapshot_id=b.snapshot_id, A_available_at=b.available_at.isoformat())
            for side, levels in (('bid', b.bids), ('ask', b.asks)):
                for i, level in enumerate(levels, 1):
                    row[f'A_{side}_price_{i}'] = str(level.price)
                    row[f'A_{side}_size_{i}'] = str(level.size)
            rows.append(row)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'market.csv'
            with path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            result = replay().run(DAY, read_market_csv(path, ('A',)), lambda o: (0,))
            self.assertEqual(result.status, 'scheduled_end')
            path.write_text('FileDate,A_price\n2025-03-03,100\n')
            with self.assertRaisesRegex(ValueError, 'revised market.csv'):
                list(read_market_csv(path, ('A',)))

    def test_legacy_constructor_fails_before_dependencies_or_data(self):
        path = Path(__file__).resolve().parents[1]/'rl_boleta/rl_model.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        scope = {}
        exec(compile(ast.Module(body=[init], type_ignores=[]), str(path), 'exec'), scope)
        with self.assertRaisesRegex(RuntimeError, 'Legacy row-partition environment retired'):
            scope['__init__'](object(), None, None, None)

    def test_preparer_output_feeds_daily_replay(self):
        from rl_boleta.data_pipeline import Config, prepare
        records = []
        for f in frames():
            b = f.books[0]
            records.append(dict(schema_version=1, snapshot_id=b.snapshot_id,
                ticker='A', source='synthetic', available_at=b.available_at.isoformat(),
                book_at=None,
                bids=[dict(price=float(l.price), size=float(l.size)) for l in b.bids],
                asks=[dict(price=float(l.price), size=float(l.size)) for l in b.asks],
                trades=[dict(at=f.at.isoformat(), price=100, size=1) for _ in range(10)]))
        with tempfile.TemporaryDirectory() as folder:
            raw, output = Path(folder)/'raw.jsonl', Path(folder)/'prepared'
            raw.write_text(''.join(json.dumps(r)+'\n' for r in records))
            config = Config(('A',), max_spread_bps=500, max_depth_distance_bps=1000,
                            calendar='us-equities-paper-2025',
                            session_first_date=str(DAY), session_last_date=str(DAY))
            prepare([raw], output, config)
            result = replay().run(DAY, read_market_csv(output/'market.csv', ('A',)), lambda o: (0,))
            self.assertTrue(result.evaluable)
            self.assertEqual(result.status, 'scheduled_end')
