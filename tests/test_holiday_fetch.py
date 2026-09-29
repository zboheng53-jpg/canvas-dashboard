from services import academic as academic_service
import web_common
import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))




class HolidayFetchThrottlingTests(unittest.TestCase):
    def setUp(self):
        academic_service._holiday_fetch_failed_at = None

    def tearDown(self):
        academic_service._holiday_fetch_failed_at = None

    @patch.object(academic_service, "_load_holiday_cache", return_value=None)
    @patch.object(academic_service, "_fetch_holidays", return_value=None)
    def test_failed_fetch_is_not_retried_immediately(self, fetch_holidays, load_holiday_cache):
        self.assertEqual(academic_service._get_holidays(), [])
        self.assertEqual(academic_service._get_holidays(), [])

        self.assertEqual(fetch_holidays.call_count, 1)

    @patch.object(academic_service, "_load_holiday_cache", return_value=None)
    @patch.object(academic_service, "_fetch_holidays", return_value=[])
    def test_empty_success_is_cached(self, fetch_holidays, load_holiday_cache):
        self.assertEqual(academic_service._get_holidays(), [])

        self.assertIsNone(academic_service._holiday_fetch_failed_at)
        fetch_holidays.assert_called_once()

    @patch.object(academic_service, "_load_holiday_cache", return_value=None)
    @patch.object(academic_service, "_fetch_holidays", return_value=None)
    def test_failed_fetch_retries_after_interval(self, fetch_holidays, load_holiday_cache):
        academic_service._holiday_fetch_failed_at = (
            datetime.now(web_common.CST)
            - timedelta(seconds=academic_service._HOLIDAY_FETCH_RETRY_INTERVAL + 1)
        )

        self.assertEqual(academic_service._get_holidays(), [])

        fetch_holidays.assert_called_once()


if __name__ == "__main__":
    unittest.main()
