"""
Unit tests for signal smoothing and anti-jitter filters (EMA & deadband).
"""
import unittest


class TestFilters(unittest.TestCase):
    def test_ema_smoothing(self):
        # Initial value initializes filter
        alpha = 0.35
        smooth = None
        raw_values = [1500, 1600, 1550, 1500, 1520]

        smoothed = []
        for v in raw_values:
            if smooth is None:
                smooth = float(v)
            else:
                smooth = (alpha * v) + ((1 - alpha) * smooth)
            smoothed.append(int(round(smooth)))

        self.assertEqual(smoothed[0], 1500)
        self.assertEqual(smoothed[1], 1535)
        # Jitter is attenuated
        self.assertTrue(all(1490 <= x <= 1610 for x in smoothed))

    def test_tps_deadband(self):
        # Deadband snaps values below 0.6% to 0.0%
        def clean_tps(raw):
            return 0.0 if raw < 0.6 else raw

        self.assertEqual(clean_tps(0.0), 0.0)
        self.assertEqual(clean_tps(0.3), 0.0)
        self.assertEqual(clean_tps(0.59), 0.0)
        self.assertEqual(clean_tps(0.6), 0.6)
        self.assertEqual(clean_tps(15.2), 15.2)


if __name__ == '__main__':
    unittest.main()
