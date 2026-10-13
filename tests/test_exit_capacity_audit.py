import unittest
from dataclasses import replace
from decimal import Decimal

from rl_boleta.economic_kernel import Config, Level, Portfolio
from rl_boleta.exit_capacity_audit import audit_session, bid_capacity, summarize
from rl_boleta.missing_data_replay import PartialExecutionEngine
from test_masked_baselines import session, TICKERS


class ExitCapacityTests(unittest.TestCase):
    def thin_tail(self):
        s=session();frames=list(s.frames)
        for i in range(len(frames)-3,len(frames)):
            frames[i]=replace(frames[i],books=tuple(replace(b,
                bids=tuple(Level(q.price,'25.9') for q in b.bids)) for b in frames[i].books))
        return replace(s,frames=tuple(frames))

    def test_per_level_integer_capacity_matches_real_execution(self):
        s=self.thin_tail();tail=s.frames[-3:]
        e=PartialExecutionEngine(Config(TICKERS,horizon=3))
        p=Portfolio(0,(100,100));expected=[0,0]
        for frame in tail:
            expected=[v+bid_capacity(frame.book(t),'.1') for v,t in zip(expected,TICKERS)]
            event=e.execute(p,tuple(-h for h in p.holdings),tuple(frame.book(t).midpoint for t in TICKERS),frame,'liquidation')
            p=event.after
        self.assertEqual(expected,[30,30]);self.assertEqual(p.holdings,(70,70))
        self.assertNotEqual(bid_capacity(tail[-1].books[0],'.1'),int(sum(q.size for q in tail[-1].books[0].bids)*Decimal('.1')))

    def test_repeated_capture_not_new_capacity_and_minimum_is_retrospective(self):
        s=self.thin_tail();frames=list(s.frames)
        frames[-1]=replace(frames[-1],books=frames[-2].books)
        s=replace(s,frames=tuple(frames));r=audit_session(s,TICKERS,initial_capital=10000,windows=(1,2,3,4,400))
        for a in r['assets']:
            self.assertEqual(a['windows']['1']['capacity_shares'],10)
            self.assertEqual(a['windows']['2']['capacity_shares'],10)
            self.assertEqual(a['windows']['2']['valid_grid_points'],2)
            self.assertEqual(a['windows']['2']['unique_captures'],1)
            self.assertEqual(a['windows']['3']['capacity_shares'],20)
            self.assertEqual(a['minimum_trailing_grid_points']['equal_capital_reference'],4)
            self.assertIsNone(a['windows']['400'])
        self.assertEqual(r['exit_at'],'2025-07-03T16:59:00Z')

    def test_missing_books_and_subinteger_depth_cannot_sell(self):
        s=self.thin_tail();frames=list(s.frames)
        frames[-2]=replace(frames[-2],books=())
        frames[-1]=replace(frames[-1],books=tuple(replace(b,
            bids=tuple(Level(q.price,1) for q in b.bids)) for b in frames[-1].books))
        r=audit_session(replace(s,frames=tuple(frames)),TICKERS,initial_capital=1000,windows=(1,2,3))
        for a in r['assets']:
            self.assertEqual(a['windows']['2']['capacity_shares'],0)
            self.assertEqual(a['windows']['2']['positive_capacity_captures'],0)
            self.assertEqual(a['minimum_trailing_grid_points']['equal_capital_reference'],3)

    def test_no_window_can_satisfy_reference_and_summary_keeps_denominator(self):
        s=session();frames=tuple(replace(f,books=tuple(replace(b,
            bids=tuple(Level(q.price,1) for q in b.bids)) for b in f.books)) for f in s.frames)
        r=audit_session(replace(s,frames=frames),TICKERS,windows=(1,400))
        self.assertTrue(all(a['minimum_trailing_grid_points']['equal_capital_reference'] is None for a in r['assets']))
        summary=summarize([r],windows=(1,400))
        self.assertEqual(summary['asset_session_observations'],2)
        self.assertEqual(summary['equal_capital_reference']['insufficient_entire_horizon'],2)
        self.assertEqual(summary['windows']['400']['insufficient_horizon_asset_sessions'],2)

    def test_rejects_uncovered_exit_invalid_window_and_participation(self):
        with self.assertRaises(ValueError):audit_session(session(missing_exit=True),TICKERS)
        with self.assertRaises(ValueError):audit_session(session(),TICKERS,windows=(True,))
        with self.assertRaises(ValueError):audit_session(session(),TICKERS,windows=(1,1))
        with self.assertRaises(ValueError):bid_capacity(session().frames[-1].books[0],0)

    def test_runner_rejects_out_of_training_dates_before_loading_prices(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from rl_boleta.data_pipeline import digest
        from rl_boleta.exit_capacity_audit import run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);child=root/'all_gaps';child.mkdir()
            (child/'protocol.json').write_text('{}')
            (child/'sessions.json').write_text(json.dumps([
                dict(session_id='2025-06-02',partition='train',data_eligible=True)]))
            cm=child/'manifest.json';cm.write_text(json.dumps({'outputs_sha256':{}}))
            (root/'manifest.json').write_text(json.dumps(dict(status='frozen_two_scenario_date_design',
                scenario_manifests={'all_gaps':dict(path=str(cm),sha256=digest(cm))})))
            with patch('rl_boleta.exit_capacity_audit.read_eligible_session') as reader:
                with self.assertRaisesRegex(ValueError,'March-May'):
                    run(root,root/'output')
                reader.assert_not_called()
            self.assertFalse((root/'output').exists())


if __name__=='__main__':unittest.main()
