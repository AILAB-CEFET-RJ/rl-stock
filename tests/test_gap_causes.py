import unittest

from rl_boleta.audit_gap_causes import gap_state


class GapCauseTests(unittest.TestCase):
    def test_future_capture_cannot_fill_gap(self):
        self.assertEqual(gap_state([101], [101], 100)[0], 'no_capture_since_open')

    def test_quality_rejection_can_be_covered_by_older_valid_capture(self):
        self.assertEqual(gap_state([70, 95], [70], 100)[0], 'valid')

    def test_recent_rejected_capture_and_stale_valid_capture(self):
        self.assertEqual(gap_state([30, 95], [30], 100)[0], 'recent_capture_rejected')

    def test_no_recent_capture_even_if_last_capture_was_rejected(self):
        self.assertEqual(gap_state([30], [], 100)[0], 'no_recent_capture')

    def test_inclusive_age_limit(self):
        self.assertEqual(gap_state([40], [40], 100)[0], 'valid')
        self.assertEqual(gap_state([39], [39], 100)[0], 'no_recent_capture')

    def test_absent_file_is_distinct_from_empty_session_capture(self):
        self.assertEqual(gap_state([], [], 100, has_file=False)[0], 'no_raw_file')
        self.assertEqual(gap_state([], [], 100)[0], 'no_capture_since_open')


if __name__ == '__main__':
    unittest.main()
