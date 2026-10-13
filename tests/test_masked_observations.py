import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date,timedelta
from pathlib import Path

from rl_boleta.economic_kernel import Book,Level
from rl_boleta.masked_observations import (FeatureCursor,MaskedEncoder,MaskedMarketSession,
    MaskedNormalizer,MaskedRow,fit_masked_normalizer)
from rl_boleta.missing_data_replay import MaskedDailyReplay,PartialFrame,ReferencePoint
from rl_boleta.observations import Trade,market_row
from rl_boleta.session_replay import session_plan

DAY=date(2025,3,3)


def fixture(tickers=('A','B'),missing=None,day=DAY,price=None,trade_size=10):
    plan=session_plan(day);frames=[];trades={}
    n=int((plan.liquidation-plan.opening).total_seconds()//60)
    for q in range(1,n+1):
        at=plan.opening+timedelta(minutes=q);books=[]
        for ticker in tickers:
            if ticker in (missing or {}).get(q,()):continue
            mid=100 if price is None else price(q,ticker)
            b=Book(ticker,f'{day}-{ticker}-{q}',at,
                tuple(Level(mid-1-i*.01,1000) for i in range(5)),
                tuple(Level(mid+1+i*.01,1000) for i in range(5)))
            books.append(b)
            trades[at,ticker]=tuple(Trade(mid,trade_size,at) for _ in range(10))
        frames.append(PartialFrame(at,str(day),tuple(books)))
    return MaskedMarketSession(day,tuple(frames),trades,synthetic=True)


def identity_normalizer(tickers):
    return MaskedNormalizer(tuple(tickers),(0.,)*(40*len(tickers)),(1.,)*(40*len(tickers)),
                            (1,)*(40*len(tickers)),'train',(str(DAY),))


class MaskedObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=fixture(missing={30:('A',)})
        cls.normalizer=fit_masked_normalizer((cls.session,),('A','B'))

    def test_per_feature_counts_exclude_gaps_and_overlapping_windows(self):
        self.assertEqual(self.normalizer.counts[:40],(387,)*40)
        self.assertEqual(self.normalizer.counts[40:],(388,)*40)
        self.assertEqual(self.normalizer.means[5],math.log1p(1000))
        self.assertEqual(self.normalizer.scales[5],1)
        self.assertEqual(self.normalizer.means[30],math.log1p(10))

    def test_absence_zero_is_inserted_after_standardization(self):
        norm=MaskedNormalizer(('A','B'),(1.,)*80,(2.,)*80,(10,)*80,'train',(str(DAY),))
        row=MaskedRow(self.session.frames[1].at,(0.,)*40+(None,)*40,
                      (True,False),(0.,.1),(.01,0.))
        encoded=norm.transform(row)
        self.assertEqual(encoded[:40],(-.5,)*40)
        self.assertEqual(encoded[40:80],(0.,)*40)
        self.assertEqual(encoded[80:82],(1.,0.))
        self.assertEqual(encoded[82:],(0.,.1,.01,0.))

    def test_valid_zero_trade_sizes_are_fitted(self):
        session=fixture(('A',),trade_size=0)
        norm=fit_masked_normalizer((session,),('A',))
        self.assertEqual(norm.counts[30:],(388,)*10)
        self.assertEqual(norm.means[30:],(0.,)*10)
        self.assertEqual(norm.scales[30:],(1.,)*10)

    def test_population_moments_use_valid_count_not_missing_rows(self):
        session=fixture(('A',),missing={30:('A',)},trade_size=0)
        at=session.frames[1].at;trades=dict(session.trades)
        trades[at,'A']=tuple(Trade(100,3,at) for _ in range(10))
        norm=fit_masked_normalizer((replace(session,trades=trades),),('A',))
        self.assertEqual(norm.counts[30],387)
        self.assertAlmostEqual(norm.means[30],math.log(4)/387)
        self.assertAlmostEqual(norm.scales[30],math.log(4)*math.sqrt(386)/387)

    def test_complete_market_values_match_v2_transforms(self):
        obs=MaskedDailyReplay(('A','B')).start(DAY,self.session.frames).observation()
        cursor=FeatureCursor(('A','B'),obs.lag_reference,obs.reference_state)
        current=obs.market_history[0]
        row=cursor.consume(current,self.session.trades)
        self.assertEqual(row.values,market_row(obs.lag_reference,current,self.session.trades,('A','B')))

    def test_long_gap_reference_survives_outside_visible_window(self):
        session=fixture(('A',),missing={q:('A',) for q in range(30,61)},
                        price=lambda q,t:200 if q>=61 else 100)
        episode=MaskedDailyReplay(('A',)).start(DAY,session.frames)
        encoder=MaskedEncoder(identity_normalizer(('A',)))
        while episode.kernel.frame.at<session_plan(DAY).opening+timedelta(minutes=50):
            episode.advance((0,))
        obs=episode.observation();rows,_=encoder.encode(obs,session.trades)
        self.assertTrue(all(not f.books for f in obs.market_history))
        self.assertTrue(all(row[:40]==(0.,)*40 and row[40]==0 for row in rows))
        self.assertAlmostEqual(rows[-1][41],21/390)
        while episode.kernel.frame.at<session_plan(DAY).opening+timedelta(minutes=61):
            episode.advance((0,))
        obs=episode.observation()
        cursor=FeatureCursor(('A',),obs.lag_reference,obs.reference_state)
        for f in obs.market_history:raw=cursor.consume(f,session.trades)
        self.assertEqual(raw.values[20],1.)
        self.assertAlmostEqual(raw.reference_ages[0],32/390)
        self.assertLess(obs.reference_state[0].grid_at,obs.lag_reference.at)

    def test_dimension_for_eighteen_assets(self):
        tickers=tuple(f'SYN{i:02d}' for i in range(18));session=fixture(tickers)
        obs=MaskedDailyReplay(tickers).start(DAY,session.frames).observation()
        encoder=MaskedEncoder(identity_normalizer(tickers))
        rows,context=encoder.encode(obs,session.trades)
        self.assertEqual((len(rows),len(rows[0]),len(context)),(20,774,22))
        self.assertEqual(len(encoder.flatten(obs,session.trades)),15502)

    def test_future_tail_and_future_trade_keys_do_not_change_encoded_past(self):
        session=fixture(('A',))
        changed=fixture(('A',),missing={q:('A',) for q in range(30,390)})
        obs1=MaskedDailyReplay(('A',)).start(DAY,session.frames).observation()
        obs2=MaskedDailyReplay(('A',)).start(DAY,changed.frames).observation()
        future=dict(session.trades)
        at=session_plan(DAY).opening+timedelta(minutes=100)
        future[at,'A']=tuple(Trade(9999,9999,at) for _ in range(10))
        encoder=MaskedEncoder(identity_normalizer(('A',)))
        self.assertEqual(encoder.flatten(obs1,session.trades),encoder.flatten(obs2,future))

    def test_future_reference_and_future_current_trade_rejected(self):
        obs=MaskedDailyReplay(('A','B')).start(DAY,self.session.frames).observation()
        r=ReferencePoint(self.session.frames[20].books[0],self.session.frames[20].at)
        with self.assertRaisesRegex(ValueError,'past'):
            FeatureCursor(('A','B'),obs.lag_reference,(r,obs.reference_state[1]))
        cursor=FeatureCursor(('A','B'),obs.lag_reference,obs.reference_state)
        frame=obs.market_history[0];trades=dict(self.session.trades)
        trades[frame.at,'A']=tuple(Trade(100,10,frame.at+timedelta(seconds=1)) for _ in range(10))
        with self.assertRaisesRegex(ValueError,'future trade'):cursor.consume(frame,trades)
        self.assertEqual(cursor.at,obs.lag_reference.at)
        cursor.consume(frame,self.session.trades) # failure did not mutate state

    def test_missing_trades_cannot_be_imputed(self):
        obs=MaskedDailyReplay(('A','B')).start(DAY,self.session.frames).observation()
        with self.assertRaisesRegex(ValueError,'ten explicit'):
            MaskedEncoder(self.normalizer).encode(obs,{})

    def test_validation_test_and_unfrozen_historical_fitting_rejected(self):
        for partition in ('validation','test'):
            with self.assertRaises(ValueError):fit_masked_normalizer((self.session,),('A','B'),partition)
        with self.assertRaisesRegex(ValueError,'out-of-partition'):
            fit_masked_normalizer((fixture(day=date(2025,6,2)),),('A','B'))
        with self.assertRaisesRegex(ValueError,'historical'):
            fit_masked_normalizer((replace(self.session,synthetic=False),),('A','B'))

    def test_final_refit_accepts_development_dates_but_not_july(self):
        norm=fit_masked_normalizer((fixture(('A',),day=date(2025,6,2)),),('A',),'final_refit')
        self.assertEqual(norm.partition,'final_refit')
        with self.assertRaisesRegex(ValueError,'out-of-partition'):
            fit_masked_normalizer((fixture(('A',),day=date(2025,7,1)),),('A',),'final_refit')

    def test_duplicate_fitting_dates_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            fit_masked_normalizer((self.session,self.session),('A','B'))

    def test_only_actual_late_entry_histories_enter_fit(self):
        session=fixture(('A','B'),missing={2:('B',)})
        norm=fit_masked_normalizer((session,),('A','B'))
        self.assertEqual(norm.counts,(386,)*80)

    def test_missing_exit_is_not_a_fitting_candidate(self):
        session=fixture(('A',),missing={389:('A',)})
        with self.assertRaisesRegex(ValueError,'exit coverage'):
            fit_masked_normalizer((session,),('A',))

    def test_save_load_frozen_normalizer_and_old_schema_rejection(self):
        obs=MaskedDailyReplay(('A','B')).start(DAY,self.session.frames).observation()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'normalizer.json';self.normalizer.save(path)
            loaded=MaskedNormalizer.load(path)
            self.assertEqual(loaded,self.normalizer)
            self.assertEqual(MaskedEncoder(loaded).flatten(obs,self.session.trades),
                             MaskedEncoder(self.normalizer).flatten(obs,self.session.trades))
            with self.assertRaises(FileExistsError):self.normalizer.save(path)
            path.write_text(json.dumps({'schema':'market-40-plus-capture-age-v1'}))
            with self.assertRaisesRegex(ValueError,'schema'):MaskedNormalizer.load(path)

    def test_portfolio_context_uses_held_marks_through_gap(self):
        session=fixture(('A',),missing={23:('A',)},price=lambda q,t:110 if q>=24 else 100)
        episode=MaskedDailyReplay(('A',),initial_capital=1000,fee_rate=0,participation=1).start(DAY,session.frames)
        episode.advance((1,));episode.advance((0,))
        obs=episode.observation();rows,context=MaskedEncoder(identity_normalizer(('A',)),1000).encode(obs,session.trades)
        self.assertEqual(rows[-1][40],0)
        self.assertEqual(context[:3],(.091,.9,.991))
        self.assertAlmostEqual(context[-2],23/390)
        self.assertAlmostEqual(context[-1],366/390)
        episode.advance((0,))
        _,context=MaskedEncoder(identity_normalizer(('A',)),1000).encode(episode.observation(),session.trades)
        self.assertEqual(context[:3],(.091,.99,1.081))

    def test_per_feature_clipping_and_mask_consistency(self):
        norm=identity_normalizer(('A',))
        row=MaskedRow(self.session.frames[1].at,(100.,)*40,(True,),(0.,),(1/390,))
        self.assertEqual(norm.transform(row)[:40],(10.,)*40)
        with self.assertRaisesRegex(ValueError,'absent'):
            norm.transform(replace(row,availability=(False,)))


if __name__=='__main__':unittest.main()
