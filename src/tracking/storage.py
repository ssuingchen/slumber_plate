"""SQLite persistence and analytics for meal logs and subjective sleep feedback."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.settings import DEFAULT_DB_PATH


class SleepTrackerDB:
    """CRUD and analytics store for meal logs and next-morning sleep feedback."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meal_date TEXT NOT NULL,
                    meal_time TEXT NOT NULL,
                    planned_bedtime TEXT,
                    hours_before_bed REAL,
                    foods_json TEXT NOT NULL,
                    total_trp_mg REAL NOT NULL,
                    total_lnaa_mg REAL NOT NULL,
                    trp_lnaa_ratio REAL,
                    effective_gi REAL,
                    effective_gi_category TEXT,
                    sleep_score REAL NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sleep_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meal_log_id INTEGER REFERENCES meal_logs(id) ON DELETE SET NULL,
                    sleep_date TEXT NOT NULL,
                    overall_quality REAL NOT NULL,
                    sleep_onset_latency_min REAL,
                    night_awakenings INTEGER,
                    morning_alertness REAL,
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def log_meal(
        self,
        meal_date: str,
        meal_time: str,
        foods: List[Dict[str, Any]],
        total_trp_mg: float,
        total_lnaa_mg: float,
        trp_lnaa_ratio: Optional[float],
        effective_gi: Optional[float],
        effective_gi_category: str,
        sleep_score: float,
        planned_bedtime: Optional[str] = None,
        hours_before_bed: Optional[float] = None,
        notes: str = "",
    ) -> int:
        """Insert a meal log and return its ID."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO meal_logs (
                    meal_date, meal_time, planned_bedtime, hours_before_bed,
                    foods_json, total_trp_mg, total_lnaa_mg, trp_lnaa_ratio,
                    effective_gi, effective_gi_category, sleep_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meal_date,
                    meal_time,
                    planned_bedtime,
                    hours_before_bed,
                    json.dumps(foods),
                    total_trp_mg,
                    total_lnaa_mg,
                    trp_lnaa_ratio,
                    effective_gi,
                    effective_gi_category,
                    sleep_score,
                    notes,
                ),
            )
            return int(cur.lastrowid)

    def get_meal_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent meal logs."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM meal_logs ORDER BY meal_date DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["foods"] = json.loads(item.pop("foods_json"))
            result.append(item)
        return result

    def delete_meal_log(self, meal_id: int) -> bool:
        """Delete a meal log by ID."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM meal_logs WHERE id = ?", (meal_id,))
            return cur.rowcount > 0

    def log_sleep_feedback(
        self,
        sleep_date: str,
        overall_quality: float,
        meal_log_id: Optional[int] = None,
        sleep_onset_latency_min: Optional[float] = None,
        night_awakenings: Optional[int] = None,
        morning_alertness: Optional[float] = None,
        notes: str = "",
    ) -> int:
        """Insert subjective sleep feedback (linked to a meal_log_id or standalone)."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sleep_feedback (
                    meal_log_id, sleep_date, overall_quality,
                    sleep_onset_latency_min, night_awakenings,
                    morning_alertness, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meal_log_id,
                    sleep_date,
                    overall_quality,
                    sleep_onset_latency_min,
                    night_awakenings,
                    morning_alertness,
                    notes,
                ),
            )
            return int(cur.lastrowid)

    def get_sleep_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent sleep feedback entries joined with meal summary if linked."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sf.*, ml.meal_date, ml.sleep_score, ml.trp_lnaa_ratio,
                       ml.effective_gi, ml.effective_gi_category, ml.hours_before_bed,
                       ml.foods_json
                FROM sleep_feedback sf
                LEFT JOIN meal_logs ml ON sf.meal_log_id = ml.id
                ORDER BY sf.sleep_date DESC, sf.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            foods_raw = item.pop("foods_json", None)
            item["foods"] = json.loads(foods_raw) if foods_raw else []
            result.append(item)
        return result

    def delete_sleep_feedback(self, feedback_id: int) -> bool:
        """Delete a sleep feedback record by ID."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sleep_feedback WHERE id = ?", (feedback_id,))
            return cur.rowcount > 0

    def get_analytics(self) -> Dict[str, Any]:
        """Compute time-series and summary insights comparing Low-GI + High-Trp:LNAA nights."""
        with self._connect() as conn:
            linked_rows = conn.execute(
                """
                SELECT sf.sleep_date, sf.overall_quality, sf.sleep_onset_latency_min,
                       sf.night_awakenings, sf.morning_alertness,
                       ml.sleep_score, ml.trp_lnaa_ratio, ml.effective_gi,
                       ml.effective_gi_category, ml.hours_before_bed, ml.foods_json
                FROM sleep_feedback sf
                JOIN meal_logs ml ON sf.meal_log_id = ml.id
                ORDER BY sf.sleep_date ASC, sf.id ASC
                """
            ).fetchall()

        series: List[Dict[str, Any]] = []
        target_qualities: List[float] = []
        other_qualities: List[float] = []
        combo_stats: Dict[str, List[float]] = {}

        for r in linked_rows:
            foods = json.loads(r["foods_json"])
            food_label = " + ".join(f.get("name", "?") for f in foods)
            series.append(
                {
                    "sleep_date": r["sleep_date"],
                    "sleep_score": r["sleep_score"],
                    "trp_lnaa_ratio": r["trp_lnaa_ratio"],
                    "effective_gi": r["effective_gi"],
                    "hours_before_bed": r["hours_before_bed"],
                    "overall_quality": r["overall_quality"],
                    "sleep_onset_latency_min": r["sleep_onset_latency_min"],
                    "morning_alertness": r["morning_alertness"],
                    "foods_label": food_label,
                }
            )
            is_low_gi = r["effective_gi"] is not None and r["effective_gi"] <= 55.0
            is_high_trp = r["trp_lnaa_ratio"] is not None and r["trp_lnaa_ratio"] >= 0.06
            if is_low_gi and is_high_trp:
                target_qualities.append(float(r["overall_quality"]))
            else:
                other_qualities.append(float(r["overall_quality"]))

            if food_label:
                combo_stats.setdefault(food_label, []).append(float(r["overall_quality"]))

        best_combos = [
            {
                "foods_label": label,
                "avg_quality": round(sum(vals) / len(vals), 2),
                "nights": len(vals),
            }
            for label, vals in combo_stats.items()
        ]
        best_combos.sort(key=lambda c: (c["avg_quality"], c["nights"]), reverse=True)

        return {
            "linked_nights": len(series),
            "time_series": series,
            "avg_quality_low_gi_high_trp": (
                round(sum(target_qualities) / len(target_qualities), 2) if target_qualities else None
            ),
            "low_gi_high_trp_nights": len(target_qualities),
            "avg_quality_other_nights": (
                round(sum(other_qualities) / len(other_qualities), 2) if other_qualities else None
            ),
            "other_nights": len(other_qualities),
            "best_combinations": best_combos[:10],
        }

