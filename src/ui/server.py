"""Zero-dependency HTTP server and JSON API for Slumber Plate."""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from src.config.settings import (
    DEFAULT_DB_PATH,
    DEFAULT_GI_PATH,
    DEFAULT_NUTRITION_PATH,
    DISCLAIMER_TEXT,
)
from src.data.loader import load_food_dataset, load_gi_dataset
from src.data.matcher import attach_gi_to_foods
from src.data.models import FoodItem, MealItem
from src.recommender.pairings import (
    find_top_pairings,
    recommend_carbs_for_trp_food,
    recommend_trp_foods_for_carb,
)
from src.scoring.engine import evaluate_meal
from src.tracking.storage import SleepTrackerDB

STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppContext:
    """Shared in-memory dataset index and SQLite tracker."""

    def __init__(
        self,
        nutrition_path: Path = DEFAULT_NUTRITION_PATH,
        gi_path: Path = DEFAULT_GI_PATH,
        db_path: Path = DEFAULT_DB_PATH,
    ) -> None:
        self.foods, self.food_report = load_food_dataset(nutrition_path)
        self.gi_entries, self.gi_report = load_gi_dataset(gi_path)
        self.gi_matched_count = attach_gi_to_foods(self.foods, self.gi_entries)
        self.foods_by_id: Dict[str, FoodItem] = {f.food_id: f for f in self.foods}
        self.db = SleepTrackerDB(db_path)

    def search_foods(self, query: str, limit: int = 25, gi_only: bool = False) -> List[Dict[str, Any]]:
        q = query.strip().lower()
        matches: List[FoodItem] = []
        for f in self.foods:
            if gi_only and f.gi_value is None:
                continue
            if not q or q in f.name.lower():
                matches.append(f)
        # Prioritize foods with GI match and higher Trp if searching
        matches.sort(
            key=lambda f: (
                f.name.lower().startswith(q) if q else False,
                f.gi_value is not None,
                f.tryptophan_mg,
            ),
            reverse=True,
        )
        return [self._food_summary(f) for f in matches[:limit]]

    @staticmethod
    def _food_summary(f: FoodItem) -> Dict[str, Any]:
        return {
            "food_id": f.food_id,
            "name": f.name,
            "serving_size_g": f.serving_size_g,
            "tryptophan_mg": round(f.tryptophan_mg, 2),
            "total_lnaa_mg": round(f.total_lnaa_per_100g(), 2),
            "trp_lnaa_ratio": round(f.trp_lnaa_ratio(), 4) if f.trp_lnaa_ratio() is not None else None,
            "carbs_g": round(f.carbs_g, 2),
            "protein_g": round(f.protein_g, 2),
            "fat_g": round(f.fat_g, 2),
            "calories_kcal": round(f.calories_kcal, 1),
            "gi_value": f.gi_value,
            "gi_category": f.gi_category,
            "gi_match_source": f.gi_match_source,
        }


def make_handler(ctx: AppContext):
    """Create a request handler bound to AppContext."""

    class SlumberPlateHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return  # Keep server output quiet

        def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/" or path == "/index.html":
                html_path = STATIC_DIR / "index.html"
                content = html_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path == "/api/meta":
                self._send_json(
                    {
                        "disclaimer": DISCLAIMER_TEXT,
                        "foods_loaded": self.server_ctx().food_report.loaded_count,
                        "gi_entries_loaded": self.server_ctx().gi_report.loaded_count,
                        "gi_matched_foods": self.server_ctx().gi_matched_count,
                    }
                )
                return

            if path == "/api/foods":
                q = qs.get("q", [""])[0]
                limit = int(qs.get("limit", ["25"])[0])
                gi_only = qs.get("gi_only", ["false"])[0].lower() == "true"
                self._send_json({"foods": self.server_ctx().search_foods(q, limit=limit, gi_only=gi_only)})
                return

            if path == "/api/recommend":
                mode = qs.get("mode", ["top"])[0]
                food_id = qs.get("food_id", [""])[0]
                top_k = int(qs.get("top_k", ["8"])[0])
                if mode == "top" or not food_id:
                    recs = find_top_pairings(self.server_ctx().foods, top_k=top_k)
                elif mode == "for_trp":
                    food = self.server_ctx().foods_by_id.get(food_id)
                    if not food:
                        self._send_json({"error": "Food not found"}, HTTPStatus.NOT_FOUND)
                        return
                    recs = recommend_carbs_for_trp_food(food, self.server_ctx().foods, top_k=top_k)
                else:
                    food = self.server_ctx().foods_by_id.get(food_id)
                    if not food:
                        self._send_json({"error": "Food not found"}, HTTPStatus.NOT_FOUND)
                        return
                    recs = recommend_trp_foods_for_carb(food, self.server_ctx().foods, top_k=top_k)
                self._send_json({"recommendations": [r.to_dict() for r in recs]})
                return

            if path == "/api/meals":
                self._send_json({"meals": self.server_ctx().db.get_meal_logs()})
                return

            if path == "/api/sleep":
                self._send_json({"sleep_logs": self.server_ctx().db.get_sleep_feedback()})
                return

            if path == "/api/analytics":
                self._send_json(self.server_ctx().db.get_analytics())
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/score":
                items = self._resolve_meal_items(body.get("items", []))
                breakdown = evaluate_meal(items)
                self._send_json({"score": breakdown.to_dict()})
                return

            if path == "/api/meals":
                raw_items = body.get("items", [])
                items = self._resolve_meal_items(raw_items)
                if not items:
                    self._send_json({"error": "At least one valid food item is required."}, HTTPStatus.BAD_REQUEST)
                    return
                breakdown = evaluate_meal(items)
                foods_payload = [
                    {"food_id": it.food.food_id, "name": it.food.name, "weight_g": it.weight_g}
                    for it in items
                ]
                meal_id = self.server_ctx().db.log_meal(
                    meal_date=body["meal_date"],
                    meal_time=body.get("meal_time", "20:00"),
                    foods=foods_payload,
                    total_trp_mg=breakdown.total_trp_mg,
                    total_lnaa_mg=breakdown.total_lnaa_mg,
                    trp_lnaa_ratio=breakdown.trp_lnaa_ratio,
                    effective_gi=breakdown.effective_gi,
                    effective_gi_category=breakdown.effective_gi_category,
                    sleep_score=breakdown.sleep_score,
                    planned_bedtime=body.get("planned_bedtime") or None,
                    hours_before_bed=body.get("hours_before_bed"),
                    notes=body.get("notes", ""),
                )
                self._send_json({"id": meal_id, "score": breakdown.to_dict()}, HTTPStatus.CREATED)
                return

            if path == "/api/sleep":
                if "sleep_date" not in body or "overall_quality" not in body:
                    self._send_json({"error": "sleep_date and overall_quality are required."}, HTTPStatus.BAD_REQUEST)
                    return
                fb_id = self.server_ctx().db.log_sleep_feedback(
                    sleep_date=body["sleep_date"],
                    overall_quality=float(body["overall_quality"]),
                    meal_log_id=body.get("meal_log_id") or None,
                    sleep_onset_latency_min=body.get("sleep_onset_latency_min"),
                    night_awakenings=body.get("night_awakenings"),
                    morning_alertness=body.get("morning_alertness"),
                    notes=body.get("notes", ""),
                )
                self._send_json({"id": fb_id}, HTTPStatus.CREATED)
                return

            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def _resolve_meal_items(self, raw_items: List[Dict[str, Any]]) -> List[MealItem]:
            resolved: List[MealItem] = []
            for entry in raw_items:
                fid = str(entry.get("food_id", ""))
                weight = float(entry.get("weight_g", 100.0))
                food = self.server_ctx().foods_by_id.get(fid)
                if food and weight > 0:
                    resolved.append(MealItem(food=food, weight_g=weight))
            return resolved

        @staticmethod
        def server_ctx() -> AppContext:
            return ctx

    return SlumberPlateHandler


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    nutrition_path: Path = DEFAULT_NUTRITION_PATH,
    gi_path: Path = DEFAULT_GI_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Start the local Slumber Plate web server."""
    ctx = AppContext(nutrition_path=nutrition_path, gi_path=gi_path, db_path=db_path)
    server = ThreadingHTTPServer((host, port), make_handler(ctx))
    print(f"Slumber Plate running at http://{host}:{port}")
    print(f"Loaded {ctx.food_report.loaded_count} foods and {ctx.gi_report.loaded_count} GI entries ({ctx.gi_matched_count} matched).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Slumber Plate server.")
    finally:
        server.server_close()

