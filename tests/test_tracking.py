import tempfile
import unittest
from pathlib import Path

from src.tracking.storage import SleepTrackerDB


class TestTracking(unittest.TestCase):
    def test_meal_and_sleep_crud_and_analytics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = SleepTrackerDB(Path(tmpdir) / "test.db")
            m1 = db.log_meal(
                meal_date="2026-11-14",
                meal_time="19:30",
                foods=[{"food_id": "1", "name": "Turkey + Barley", "weight_g": 200}],
                total_trp_mg=320.0,
                total_lnaa_mg=4000.0,
                trp_lnaa_ratio=0.08,
                effective_gi=28.0,
                effective_gi_category="Low",
                sleep_score=86.5,
                planned_bedtime="23:00",
                hours_before_bed=3.5,
            )
            m2 = db.log_meal(
                meal_date="2026-11-15",
                meal_time="22:00",
                foods=[{"food_id": "2", "name": "White Bread", "weight_g": 100}],
                total_trp_mg=50.0,
                total_lnaa_mg=2000.0,
                trp_lnaa_ratio=0.025,
                effective_gi=80.0,
                effective_gi_category="High",
                sleep_score=32.0,
                planned_bedtime="23:00",
                hours_before_bed=1.0,
            )
            db.log_sleep_feedback(
                sleep_date="2026-11-15",
                overall_quality=4.5,
                meal_log_id=m1,
                sleep_onset_latency_min=12.0,
                night_awakenings=0,
                morning_alertness=4.5,
            )
            db.log_sleep_feedback(
                sleep_date="2026-11-16",
                overall_quality=2.5,
                meal_log_id=m2,
                sleep_onset_latency_min=35.0,
                night_awakenings=2,
                morning_alertness=2.5,
            )

            analytics = db.get_analytics()
            self.assertEqual(analytics["linked_nights"], 2)
            self.assertEqual(analytics["avg_quality_low_gi_high_trp"], 4.5)
            self.assertEqual(analytics["avg_quality_other_nights"], 2.5)
            self.assertTrue(db.delete_meal_log(m2))
            self.assertEqual(len(db.get_meal_logs()), 1)


if __name__ == "__main__":
    unittest.main()

