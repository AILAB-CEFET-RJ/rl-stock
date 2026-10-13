import importlib.util
import unittest
from dataclasses import replace

AVAILABLE=importlib.util.find_spec('numpy') is not None


@unittest.skipUnless(AVAILABLE,'numpy required for cached float32 observations')
class CachedObservationTests(unittest.TestCase):
    def test_all_steps_match_original_including_long_gaps_and_terminal(self):
        import numpy as np
        from rl_boleta.masked_training import synthetic_sessions,TICKERS
        from rl_boleta.masked_observations import MaskedEncoder,fit_masked_normalizer
        from rl_boleta.cached_observations import CachedMaskedEncoder
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        s=synthetic_sessions()[0];norm=fit_masked_normalizer((s,),TICKERS)
        plain=MaskedEncoder(norm);cache=CachedMaskedEncoder(norm,s)
        e=MaskedDailyReplay(TICKERS).start(s.day,s.frames);count=0
        while True:
            obs=e.observation(allow_terminal=e.kernel.done)
            self.assertTrue(np.array_equal(np.asarray(plain.flatten(obs,s.trades),dtype=np.float32),cache.flatten(obs,s.trades)))
            if e.kernel.done:break
            e.advance((.4,)*18 if count==0 else (0,)*18 if e.discretionary else None);count+=1
        self.assertEqual(count,367)
        self.assertTrue(all(not row.flags.writeable for row in cache.rows.values()))

    def test_future_tail_changes_do_not_affect_cached_past_and_marks_checked(self):
        import numpy as np
        from rl_boleta.masked_training import synthetic_sessions,TICKERS
        from rl_boleta.masked_observations import fit_masked_normalizer
        from rl_boleta.cached_observations import CachedMaskedEncoder
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        from rl_boleta.economic_kernel import Level
        s=synthetic_sessions()[0];norm=fit_masked_normalizer((s,),TICKERS);frames=list(s.frames)
        frames[-1]=replace(frames[-1],books=tuple(replace(b,bids=tuple(Level(l.price+10,l.size) for l in b.bids),
            asks=tuple(Level(l.price+10,l.size) for l in b.asks)) for b in frames[-1].books))
        changed=replace(s,frames=tuple(frames));a=CachedMaskedEncoder(norm,s);b=CachedMaskedEncoder(norm,changed)
        obs=MaskedDailyReplay(TICKERS).start(s.day,s.frames).observation()
        self.assertTrue(np.array_equal(a.flatten(obs,s.trades),b.flatten(obs,changed.trades)))
        with self.assertRaises(ValueError):a.flatten(replace(obs,marked_midpoints=(1,)*18),s.trades)
        with self.assertRaises(ValueError):a.flatten(obs,dict(s.trades))
