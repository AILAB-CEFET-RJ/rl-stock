"""Hand-checked feature transforms, temporal isolation and frozen statistics."""
import csv
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from rl_boleta.daily_training import synthetic_sessions
from rl_boleta.economic_kernel import Portfolio
from rl_boleta.observations import (
    Encoder, MarketSession, Normalizer, Trade, feature_names, fit_normalizer,
    market_row, read_sessions,
)
from rl_boleta.session_replay import DailySessionReplay


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = synthetic_sessions()
        cls.tickers = ('SYNTA', 'SYNTB')
        cls.normalizer = fit_normalizer(cls.sessions, cls.tickers)

    def episode(self):
        session = self.sessions[0]
        return DailySessionReplay(self.tickers).start(session.day, session.frames)

    def test_price_volume_transforms_and_rank(self):
        session = self.sessions[0]
        before, current = session.frames[:2]
        row = market_row(before, current, session.trades, self.tickers)
        self.assertEqual(len(row), 80)
        self.assertEqual(len(feature_names(self.tickers)), 80)
        self.assertAlmostEqual(row[0], float(current.book('SYNTA').bids[0].price/
                                           before.book('SYNTA').midpoint-1))
        self.assertAlmostEqual(row[5], math.log1p(1000))
        self.assertAlmostEqual(row[30], math.log1p(10))
        self.assertAlmostEqual(row[39], math.log1p(19))
        self.assertEqual(feature_names(self.tickers)[20], 'SYNTA.trade_price.1')
        self.assertEqual(feature_names(self.tickers)[40], 'SYNTB.bid_price.1')

    def test_population_statistics_unique_grid_points(self):
        self.assertEqual(self.normalizer.count, 3*388)
        values = []
        for s in self.sessions:
            values.extend(market_row(a, b, s.trades, self.tickers)[0]
                          for a, b in zip(s.frames, s.frames[1:]))
        mean = sum(values)/len(values)
        std = math.sqrt(sum((v-mean)**2 for v in values)/len(values))
        self.assertAlmostEqual(self.normalizer.means[0], mean, places=14)
        self.assertAlmostEqual(self.normalizer.scales[0], std, places=14)
        self.assertEqual(self.normalizer.scales[5], 1)

    def test_shape_and_current_portfolio_separate_from_market_history(self):
        obs = self.episode().observation()
        encoder = Encoder(self.normalizer)
        market, context = encoder.encode(obs, self.sessions[0].trades)
        changed = replace(obs, portfolio=Portfolio(99000, (10, 0)))
        market2, context2 = encoder.encode(changed, self.sessions[0].trades)
        self.assertEqual(market, market2)
        self.assertNotEqual(context, context2)
        self.assertEqual((len(market), len(market[0]), len(context)), (20, 82, 6))
        self.assertEqual(len(encoder.flatten(obs, self.sessions[0].trades)), 1646)
        self.assertEqual(context, (1., 0., 0., 1., 21/390, 368/390))

    def test_future_trade_values_cannot_change_current_input(self):
        obs = self.episode().observation()
        encoder = Encoder(self.normalizer)
        trades = dict(self.sessions[0].trades)
        expected = encoder.flatten(obs, trades)
        future = obs.at+timedelta(minutes=1)
        trades[future, 'SYNTA'] = tuple(Trade(999999, 999999, future) for _ in range(10))
        self.assertEqual(encoder.flatten(obs, trades), expected)

    def test_capture_age_fixed_scale_and_trade_clock_omitted(self):
        obs = self.episode().observation()
        frame = obs.market_history[-1]
        adjusted = replace(frame, books=tuple(replace(b, available_at=b.available_at-timedelta(seconds=30))
                                              for b in frame.books))
        obs = replace(obs, market_history=obs.market_history[:-1]+(adjusted,))
        rows, _ = Encoder(self.normalizer).encode(obs, self.sessions[0].trades)
        self.assertEqual(rows[-1][-2:], (.5, .5))
        trades = {k: tuple(replace(t, at=t.at-timedelta(hours=3)) for t in ts)
                  for k, ts in self.sessions[0].trades.items()}
        self.assertEqual(rows, Encoder(self.normalizer).encode(obs, trades)[0])

    def test_frozen_normalizer_roundtrip_and_clip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'normalizer.json'
            self.normalizer.save(path)
            restored = Normalizer.load(path)
            self.assertEqual(restored, self.normalizer)
            self.assertEqual(restored.transform((1e10,)*80), (10.,)*80)
            self.assertEqual(restored.transform((-1e10,)*80), (-10.,)*80)
            with self.assertRaises(FileExistsError):
                self.normalizer.save(path)
        with self.assertRaises(ValueError):
            self.normalizer.transform((float('nan'),)*80)

    def test_reject_fitting_validation_test_empty_duplicates_and_gaps(self):
        for partition in ('validation', 'test'):
            with self.assertRaises(ValueError):
                fit_normalizer(self.sessions, self.tickers, partition)
        for sessions in ((), (self.sessions[0],)*2,
                         (replace(self.sessions[0], day=date(2025, 6, 2)),),
                         (replace(self.sessions[0], frames=self.sessions[0].frames[:-1]),)):
            with self.assertRaises(ValueError):
                fit_normalizer(sessions, self.tickers)

    def test_reject_missing_trades_and_nonconsecutive_reference(self):
        s = self.sessions[0]
        with self.assertRaises(ValueError):
            market_row(s.frames[0], s.frames[1], {}, self.tickers)
        with self.assertRaises(ValueError):
            market_row(s.frames[0], s.frames[2], s.trades, self.tickers)
        with self.assertRaises(ValueError):
            Trade(-1, 10, s.frames[0].at)

    def test_refit_explicit_partition(self):
        normalizer = fit_normalizer(self.sessions, self.tickers, 'final_refit')
        self.assertEqual(normalizer.partition, 'final_refit')
        self.assertEqual(normalizer.means, self.normalizer.means)

    def test_csv_preserves_all_trades(self):
        s = self.sessions[0]
        rows = []
        for f in s.frames[:2]:
            row = dict(decision_at=f.at.isoformat(), session_id=f.session_id)
            for b in f.books:
                prefix = b.ticker+'_'
                row[prefix+'snapshot_id'] = b.snapshot_id
                row[prefix+'available_at'] = b.available_at.isoformat()
                for side, levels in (('bid', b.bids), ('ask', b.asks)):
                    for i, l in enumerate(levels, 1):
                        row[f'{prefix}{side}_price_{i}'] = str(l.price)
                        row[f'{prefix}{side}_size_{i}'] = str(l.size)
                for i, t in enumerate(s.trades[f.at, b.ticker], 1):
                    row[f'{prefix}trade_price_{i}'] = str(t.price)
                    row[f'{prefix}trade_size_{i}'] = str(t.size)
                    row[f'{prefix}trade_at_{i}'] = t.at.isoformat()
            rows.append(row)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'market.csv'
            with path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            loaded = read_sessions(path, self.tickers)[s.day]
            self.assertEqual(loaded.frames, s.frames[:2])
            self.assertEqual(loaded.trades[s.frames[0].at, 'SYNTA'], s.trades[s.frames[0].at, 'SYNTA'])
