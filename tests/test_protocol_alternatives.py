import unittest
from rl_boleta.audit_protocol_alternatives import analyze_day,first_ready,rolling_ready


class AlternativeTests(unittest.TestCase):
    def test_entry_uses_first_ready_window_not_later_convenient_run(self):
        values=[False,True,True,True,False,True,True,True,True]
        self.assertEqual(first_ready(values,3),3)
        report=analyze_day({'A':values},window=3)
        self.assertFalse(report['strict_continuous_from_causal_entry'])
        self.assertTrue(report['masked_coverage_candidate'])

    def test_future_tail_does_not_change_prior_entry(self):
        prefix=[False,True,True,True]
        self.assertEqual(first_ready(prefix,3),first_ready(prefix+[False]*20,3))

    def test_missing_exit_disqualifies_masked_candidate(self):
        report=analyze_day({'A':[True]*8,'B':[True]*7+[False]},window=3)
        self.assertFalse(report['masked_coverage_candidate'])
        self.assertEqual(report['missing_exit_assets'],['B'])

    def test_too_late_entry_cannot_support_intention_fill_exit(self):
        report=analyze_day({'A':[False]*4+[True]*3},window=3)
        self.assertFalse(report['causal_entry_available'])

    def test_full_feature_window_rewarms_after_gap(self):
        self.assertEqual(rolling_ready([True,True,True,False,True,True,True],3),
                         [False,False,True,False,False,False,True])

    def test_gap_preserves_daily_timeline_and_counts_per_asset(self):
        report=analyze_day({'A':[True]*9,'B':[True]*3+[False]*2+[True]*4},window=3)
        self.assertEqual(report['remaining_transitions'],6)
        self.assertEqual(report['asset_gap_runs']['B'],1)
        self.assertEqual(report['asset_longest_gap_minutes']['B'],2)
        self.assertEqual(report['minutes_without_any_current_asset'],0)


if __name__=='__main__':unittest.main()
