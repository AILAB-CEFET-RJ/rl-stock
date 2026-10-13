"""Historical adapter contracts using fabricated, manifest-bound market sessions."""
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from rl_boleta.data_pipeline import digest

AVAILABLE=all(importlib.util.find_spec(n) for n in ('gymnasium','stable_baselines3','numpy'))


@unittest.skipUnless(AVAILABLE,'install requirements-training.txt')
class HistoricalEnvTests(unittest.TestCase):
    def fixture(self,root):
        from test_masked_baselines import session
        from test_masked_preparation import protocol
        from rl_boleta.observations import Trade
        from dataclasses import replace
        from rl_boleta.historical_normalization import HistoricalMaskedNormalizer
        sessions=[]
        for day in (date(2025,3,3),date(2025,3,4)):
            s=session(day);trades={(f.at,b.ticker):tuple(Trade(b.midpoint,10,f.at) for _ in range(10)) for f in s.frames for b in f.books}
            sessions.append(replace(s,trades=trades,synthetic=False))
        grid=root/'grid.json';grid.write_text('fixture grid source')
        prepared=root/'prepared.json';prepared.write_text(json.dumps(dict(sessions=[dict(session_id=str(s.day),canonical_inputs={},grid_file=grid.name) for s in sessions],outputs={grid.name:digest(grid)})))
        child=root/'eligibility';child.mkdir();p=protocol()
        p['episode']['long_gap_policy'].update(primary_mode='masked_all_gaps',primary_cap_minutes=None)
        (child/'protocol.json').write_text(json.dumps(p))
        (child/'sessions.json').write_text(json.dumps([dict(session_id=str(s.day),partition='train',data_eligible=True) for s in sessions]))
        m=dict(status='frozen_conditional_eligibility',primary_rule=dict(mode='masked_all_gaps',cap_grid_points=None),
            prepared_manifest=dict(path=str(prepared),sha256=digest(prepared)),outputs_sha256={p.name:digest(p) for p in child.iterdir()})
        mp=child/'manifest.json';mp.write_text(json.dumps(m));normdir=root/'normalizers';normdir.mkdir()
        norm=HistoricalMaskedNormalizer(('A','B'),(0.,)*80,(1.,)*80,(1,)*80,'train',tuple(str(s.day) for s in sessions),False,'all_gaps',digest(mp))
        path=normdir/'normalizer.json';norm.save(path);design=root/'design.json';design.write_text('fixture design source')
        entry=dict(file=path.name,eligibility_manifest=dict(path=str(mp),sha256=digest(mp)),fitting_sessions=list(norm.sessions))
        report=dict(schema='historical-train-normalizer-bundle-v3',status='historical_train_normalization_completed',partition='train',
            outputs_sha256={path.name:digest(path)},design_manifest=dict(path=str(design),sha256=digest(design)),normalizers=dict(all_gaps=entry))
        (normdir/'manifest.json').write_text(json.dumps(report));return normdir,{s.day:s for s in sessions},grid

    def test_seeded_uniform_sampling_bounded_cache_and_partition_gate(self):
        from rl_boleta.historical_env import HistoricalTrainingEnv
        with tempfile.TemporaryDirectory() as tmp:
            normdir,sessions,grid=self.fixture(Path(tmp));calls=[]
            def reader(directory,day,*,partition):
                self.assertEqual(partition,'train');calls.append(day);return sessions[day]
            with patch('rl_boleta.historical_env.read_eligible_session',side_effect=reader):
                a=HistoricalTrainingEnv(normdir,'all_gaps',cache_size=1);b=HistoricalTrainingEnv(normdir,'all_gaps',cache_size=1)
                x,_=a.reset(seed=4);y,_=b.reset(seed=4)
                for _ in range(8):a.reset();b.reset()
                self.assertEqual(a.sampling_order,b.sampling_order)
                self.assertEqual(set(a.sampling_order),set(str(d) for d in sessions))
                self.assertEqual(x.tolist(),y.tolist());self.assertLessEqual(len(a._cache),1)
                prior=len(calls)
                with self.assertRaises(ValueError):a.session_for_day(date(2025,7,8))
                self.assertEqual(len(calls),prior)
                with self.assertRaises(ValueError):a.reset(options={'day':'2025-03-03'})
                grid.write_text('tampered')
                with self.assertRaises(ValueError):a.verify_inputs()

    def test_accounting_and_terminal_state_match_direct_replay(self):
        from rl_boleta.historical_env import HistoricalTrainingEnv
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        with tempfile.TemporaryDirectory() as tmp:
            normdir,sessions,_=self.fixture(Path(tmp))
            with patch('rl_boleta.historical_env.read_eligible_session',side_effect=lambda directory,day,partition:sessions[day]):
                env=HistoricalTrainingEnv(normdir,'all_gaps');env.reset(seed=0);count=0;total=0
                while not env.episode.kernel.done:
                    obs,r,done,truncated,info=env.step((1,1) if count==0 else (0,0));count+=1;total+=r
                    self.assertFalse(truncated);self.assertTrue(env.observation_space.contains(obs))
                calls=[];s=env.session
                expected=MaskedDailyReplay(env.tickers,**env.economic_options).run(s.day,s.frames,
                    lambda o:calls.append(o) or ((1,1) if len(calls)==1 else (0,0)))
                self.assertAlmostEqual(total,float(expected.marked_return),places=12)
                self.assertEqual(count,len(expected.transitions));self.assertEqual(obs[-1],0)
                self.assertTrue(done and info['flat'])
                with self.assertRaises(ValueError):env.step((0,0))

    def test_bad_tail_or_source_type_fails_before_policy_steps(self):
        from dataclasses import replace
        from rl_boleta.historical_env import HistoricalTrainingEnv
        with tempfile.TemporaryDirectory() as tmp:
            normdir,sessions,_=self.fixture(Path(tmp));s=next(iter(sessions.values()))
            with patch('rl_boleta.historical_env.read_eligible_session',return_value=replace(s,synthetic=True)):
                env=HistoricalTrainingEnv(normdir,'all_gaps')
                with self.assertRaises(ValueError):env.session_for_day(s.day)
            trades=dict(s.trades);del trades[s.frames[-1].at,'A']
            with patch('rl_boleta.historical_env.read_eligible_session',return_value=replace(s,trades=trades)):
                env=HistoricalTrainingEnv(normdir,'all_gaps')
                with self.assertRaises(ValueError):env.session_for_day(s.day)
            self.assertFalse(env.completed)

    def test_invalid_cache_and_wrong_scenario_fail(self):
        from rl_boleta.historical_env import HistoricalTrainingEnv
        with self.assertRaises(ValueError):HistoricalTrainingEnv('absent','all_gaps',cache_size=0)
        with tempfile.TemporaryDirectory() as tmp:
            normdir,_,_=self.fixture(Path(tmp))
            with self.assertRaises((ValueError,KeyError)):HistoricalTrainingEnv(normdir,'short_gaps')

    def test_smoke_budget_is_bounded_before_opening_data_or_output(self):
        from rl_boleta.historical_training import run_historical_smoke
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'unused'
            for steps in (367,500000,True):
                with self.assertRaises(ValueError):run_historical_smoke(out,'absent','all_gaps',steps=steps)
                self.assertFalse(out.exists())
