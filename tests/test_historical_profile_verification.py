import unittest
from rl_boleta.historical_profile_verification import probe_dates


class ProfileProbeTests(unittest.TestCase):
    def rows(self):return [dict(session_id=day,partition='train',data_eligible=True,
        remaining_transitions=horizon,longest_missing_grid_run=gap) for day,horizon,gap in
        [('2025-03-03',300,2),('2025-03-04',100,34),('2025-03-05',23,1),('2025-03-06',10,0)]]

    def test_quality_and_clock_select_examples_without_return_fields(self):
        rows=self.rows();dates=tuple(r['session_id'] for r in rows)
        self.assertEqual(probe_dates(rows,dates,54),('2025-03-03','2025-03-05','2025-03-04'))
        rows.reverse();self.assertEqual(probe_dates(rows,dates,54),('2025-03-03','2025-03-05','2025-03-04'))

    def test_incomplete_or_nontraining_members_are_rejected(self):
        rows=self.rows();dates=tuple(r['session_id'] for r in rows)
        with self.assertRaises(ValueError):probe_dates(rows[:-1],dates,54)
        rows[0]['partition']='test'
        with self.assertRaises(ValueError):probe_dates(rows,dates,54)


if __name__=='__main__':unittest.main()
