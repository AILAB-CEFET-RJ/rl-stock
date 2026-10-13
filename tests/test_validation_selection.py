import unittest
from copy import deepcopy
from pathlib import Path
import json

from rl_boleta.validation_selection import aggregate_candidate,rank_candidates,make_plan,paired_differences,result_metrics

DATES=('2025-06-02','2025-06-03')


def row(day,score,flat=True):
    return dict(session_id=day,marked_return=str(score),maximum_marked_drawdown='.1',fees='2',turnover_per_capital='1',
        residual_marked_exposure_per_capital='0' if flat else '.2',flat=flat,
        residual_holdings=[0,0] if flat else [1,0],realized_return=str(score) if flat else None,
        status='scheduled_end' if flat else 'liquidation_failure',capital_stop=False)


def runs():return [dict(status='completed',seed=s,validation=[row(DATES[0],'.1'),row(DATES[1],'.3',False)]) for s in (0,1,2)]


class ValidationSelectionTests(unittest.TestCase):
    def test_equal_session_and_seed_weight_retains_liquidation_failures(self):
        a=aggregate_candidate(runs(),(0,1,2),DATES)
        self.assertTrue(a['eligible']);self.assertEqual(a['mean_marked_return'],'0.2')
        self.assertEqual(a['flat_completion_rate'],'0.5');self.assertEqual(a['liquidation_failure_count'],3)
        self.assertEqual(a['market_sessions'],2);self.assertEqual(a['seed_session_outcomes'],6)

    def test_missing_seed_date_duplicate_and_nonfinite_are_ineligible(self):
        self.assertFalse(aggregate_candidate(runs()[:-1],(0,1,2),DATES)['eligible'])
        r=runs();r[2]['seed']=1
        self.assertFalse(aggregate_candidate(r,(0,1,2),DATES)['eligible'])
        for mutation in ('date','missing','failed','nan'):
            r=runs()
            if mutation=='date':r[0]['validation'].reverse()
            if mutation=='missing':r[0]['validation'][0]['marked_return']=None
            if mutation=='failed':r[0]['status']='failed'
            if mutation=='nan':r[0]['validation'][0]['marked_return']='NaN'
            self.assertFalse(aggregate_candidate(r,(0,1,2),DATES)['eligible'])

    def test_registered_tie_breaks_and_no_filter_for_flat_success(self):
        def candidate(score,dd,w,lr):return dict(width=w,learning_rate=lr,aggregate=dict(eligible=True,mean_marked_return=score,mean_maximum_marked_drawdown=dd))
        a=candidate('.3','.5',128,.0003);b=candidate('.2','.01',64,.0001)
        self.assertEqual(rank_candidates([b,a])[0],a)
        c=candidate('.3','.2',128,.0003);d=candidate('.3','.2',64,.0003);e=candidate('.3','.2',64,.0001)
        self.assertEqual(rank_candidates([a,c,d,e]),[e,d,c,a])
        self.assertEqual(rank_candidates([dict(aggregate=dict(eligible=False))]),[])

    def test_paired_control_uses_full_same_dates(self):
        control=[row(DATES[0],'.05'),row(DATES[1],'.05')]
        p=paired_differences(runs(),control,DATES)
        self.assertEqual(p['mean_marked_difference'],'0.15')
        self.assertFalse(p['paired_seed_session_outcomes'][1]['model_flat'])
        self.assertTrue(p['paired_seed_session_outcomes'][1]['baseline_flat'])
        with self.assertRaises(ValueError):paired_differences(runs(),control[:-1],DATES)

    def test_full_core_plan_and_diagnostic_cannot_authorize_refit(self):
        protocol=json.loads(Path('configs/experimental_protocol_v3.json').read_text())
        with self.assertRaisesRegex(ValueError,'exit preparation'):
            make_plan(protocol,'protocol',('PPO',),('all_gaps',))
        protocol['day_trading_review']['status']='frozen_and_verified'  # planning fixture, not actual approval
        with self.assertRaisesRegex(ValueError,'explicit frozen account'):
            make_plan(protocol,'protocol',('PPO',),('all_gaps',))
        protocol['environment']['account_regime']='intraday_buying_power'
        p=make_plan(protocol,'protocol',('PPO','A2C','SAC','DDPG'),('all_gaps','short_gaps'))
        self.assertEqual(p['planned_fits'],96);self.assertEqual(p['requested_transitions'],48000000)
        self.assertEqual(p['replay_array_bytes_per_off_policy_fit'],12412400000)
        q=make_plan(protocol,'diagnostic',('PPO',),('all_gaps','short_gaps'))
        self.assertEqual(q['planned_fits'],12);self.assertEqual(q['requested_transitions'],4608)
        self.assertFalse(q['eligible_for_final_refit'])
        with self.assertRaises(ValueError):make_plan(protocol,'protocol',('PPO',),('all_gaps',),384)
        with self.assertRaises(ValueError):make_plan(protocol,'diagnostic',('PPO',),('all_gaps',),500000)

    def test_day_trading_selection_rejects_profitable_residuals_without_dropping_dates(self):
        failed=aggregate_candidate(runs(),(0,1,2),DATES)
        complete=runs()
        for r in complete:r['validation']=[row(d,'-.01') for d in DATES]
        passed=aggregate_candidate(complete,(0,1,2),DATES)
        self.assertTrue(failed['eligible'])
        self.assertFalse(failed['day_trading_admissibility']['admissible'])
        self.assertEqual(failed['day_trading_admissibility']['noncompliant_outcomes'],3)
        self.assertEqual(failed['seed_session_outcomes'],6)
        a=dict(width=64,learning_rate=.0001,aggregate=failed)
        b=dict(width=128,learning_rate=.0003,aggregate=passed)
        self.assertEqual(rank_candidates([a,b]),[a,b])
        self.assertEqual(rank_candidates([a,b],require_day_trading=True),[b])
        self.assertEqual(rank_candidates([a],require_day_trading=True),[])
        self.assertFalse(passed['day_trading_admissibility']['future_liquidation_guaranteed'])

    def test_false_flat_flag_or_unrealized_score_cannot_pass_admission(self):
        from rl_boleta.validation_selection import day_trading_admissibility
        for changes in ({'residual_holdings':[0,1]}, {'realized_return':None},
                {'realized_return':'.4'}, {'status':'exit_data_missing'}, {'residual_holdings':[]}):
            r=row(DATES[0],'.3');r.update(changes)
            self.assertFalse(day_trading_admissibility([r])['admissible'])
        self.assertFalse(day_trading_admissibility([])['admissible'])
        r=row(DATES[0],'.3');r['status']='capital_stop';r['capital_stop']=True
        self.assertTrue(day_trading_admissibility([r])['admissible'])

    def test_economic_metrics_preserve_residuals_and_realized_none(self):
        from test_masked_baselines import session,TICKERS
        from rl_boleta.masked_baselines import BaselinePolicy
        from rl_boleta.missing_data_replay import MaskedDailyReplay
        s=session(shallow=True);r=MaskedDailyReplay(TICKERS).run(s.day,s.frames,BaselinePolicy('equal_allocation_single_entry',TICKERS))
        m=result_metrics(r)
        self.assertFalse(m['flat']);self.assertIsNone(m['realized_return'])
        self.assertEqual(m['status'],'liquidation_failure');self.assertGreater(float(m['residual_marked_exposure_per_capital']),0)
        self.assertGreater(float(m['fees']),0)
        bad=session(missing_exit=True);r=MaskedDailyReplay(TICKERS).run(bad.day,bad.frames,BaselinePolicy('cash',TICKERS))
        with self.assertRaises(ValueError):result_metrics(r)

    def test_test_dates_are_blocked_before_price_loading(self):
        from rl_boleta.validation_selection import ValidationContext
        from unittest.mock import patch
        context=object.__new__(ValidationContext);context.dates=DATES;context.directory=Path('unused')
        with patch('rl_boleta.validation_selection.read_eligible_session') as reader:
            with self.assertRaises(ValueError):context.session('2025-07-08')
            reader.assert_not_called()

    @unittest.skipUnless(__import__('importlib').util.find_spec('stable_baselines3'),'training dependencies required')
    def test_resume_reuses_completed_jobs_and_rejects_tampered_baselines(self):
        import tempfile
        from unittest.mock import patch
        from rl_boleta.validation_selection import execute
        from rl_boleta.data_pipeline import digest
        class Context:
            def __init__(self,*args):
                self.protocol=json.loads(Path('configs/experimental_protocol_v3.json').read_text());self.dates=DATES;self.anchors={}
            def verify_inputs(self):pass
            def baselines(self):return [dict(baseline='equal_allocation_single_entry',seed=None,validation=[row(d,'.05') for d in DATES])]
            def evaluate_many(self,models):return {k:[row(d,'.2',False) for d in DATES] for k in models}
        def train(context,job,steps,diagnostic,folder):
            folder.mkdir(parents=True);checkpoint=folder/'model.zip';checkpoint.write_bytes(b'fixture checkpoint')
            r=dict(status='trained_awaiting_validation',**job,artifacts_sha256={'model.zip':digest(checkpoint)})
            (folder/'report.json').write_text(json.dumps(r));return r
        with tempfile.TemporaryDirectory() as temp,patch('rl_boleta.validation_selection.ValidationContext',Context),\
                patch('rl_boleta.validation_selection.train_job',side_effect=train) as trainer,\
                patch('stable_baselines3.PPO.load',return_value=object()):
            out=Path(temp)/'selection'
            a=execute('unused',out,scenarios=('all_gaps',))
            self.assertFalse(a['eligible_for_final_refit']);self.assertEqual(trainer.call_count,6)
            b=execute('unused',out,scenarios=('all_gaps',),resume=True)
            self.assertEqual(a,b);self.assertEqual(trainer.call_count,6)
            (out/'all_gaps/baselines.json').write_text('[]')
            with self.assertRaises(ValueError):execute('unused',out,scenarios=('all_gaps',),resume=True)
