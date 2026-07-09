import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("dashboard_app", ROOT / "app.py")
dashboard_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard_app)


class HolidayFetchThrottlingTests(unittest.TestCase):
    def setUp(self):
        dashboard_app._holiday_fetch_failed_at = None

    def tearDown(self):
        dashboard_app._holiday_fetch_failed_at = None

    @patch.object(dashboard_app, "_load_holiday_cache", return_value=None)
    @patch.object(dashboard_app, "_fetch_holidays", return_value=None)
    def test_failed_fetch_is_not_retried_immediately(self, fetch_holidays, load_holiday_cache):
        self.assertEqual(dashboard_app._get_holidays(), [])
        self.assertEqual(dashboard_app._get_holidays(), [])

        self.assertEqual(fetch_holidays.call_count, 1)

    @patch.object(dashboard_app, "_load_holiday_cache", return_value=None)
    @patch.object(dashboard_app, "_fetch_holidays", return_value=[])
    def test_empty_success_is_cached(self, fetch_holidays, load_holiday_cache):
        self.assertEqual(dashboard_app._get_holidays(), [])

        self.assertIsNone(dashboard_app._holiday_fetch_failed_at)
        fetch_holidays.assert_called_once()

    @patch.object(dashboard_app, "_load_holiday_cache", return_value=None)
    @patch.object(dashboard_app, "_fetch_holidays", return_value=None)
    def test_failed_fetch_retries_after_interval(self, fetch_holidays, load_holiday_cache):
        dashboard_app._holiday_fetch_failed_at = (
            datetime.now(dashboard_app.CST)
            - timedelta(seconds=dashboard_app._HOLIDAY_FETCH_RETRY_INTERVAL + 1)
        )

        self.assertEqual(dashboard_app._get_holidays(), [])

        fetch_holidays.assert_called_once()


if __name__ == "__main__":
    unittest.main()
