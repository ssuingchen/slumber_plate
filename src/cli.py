"""CLI entrypoint for Slumber Plate."""

import argparse
import json
from pathlib import Path
from typing import List

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
from src.ui.server import run_server


def _find_food(foods: List[FoodItem], query: str) -> FoodItem:
    q = query.strip().lower()
    for f in foods:
        if f.food_id.lower() == q or f.name.lower() == q:
            return f
    for f in foods:
        if q in f.name.lower():
            return f
    raise SystemExit(f"Food not found matching: {query!r}")


def _parse_item_arg(raw: str) -> tuple:
    if ":" in raw:
        name, weight_str = raw.rsplit(":", 1)
        return name.strip(), float(weight_str)
    return raw.strip(), 100.0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="slumber-plate",
        description=f"Slumber Plate — Sleep Nutrition & Trp:LNAA Recommender\n\n{DISCLAIMER_TEXT}",
    )
    parser.add_argument("--nutrition", type=Path, default=DEFAULT_NUTRITION_PATH)
    parser.add_argument("--gi", type=Path, default=DEFAULT_GI_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate a meal combination")
    p_eval.add_argument("items", nargs="+", help="Food name or ID, optionally with :grams (e.g. 'Barley:100')")

    p_rec = sub.add_parser("recommend", help="Recommend tryptophan-rich + low-GI carb pairings")
    p_rec.add_argument("--food", default="", help="Seed food name or ID")
    p_rec.add_argument("--mode", choices=["top", "for_trp", "for_carb"], default="top")
    p_rec.add_argument("--top-k", type=int, default=5)

    p_log_meal = sub.add_parser("log-meal", help="Log an evening meal")
    p_log_meal.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_log_meal.add_argument("--time", default="19:30", help="HH:MM")
    p_log_meal.add_argument("--bedtime", default=None, help="Planned bedtime HH:MM")
    p_log_meal.add_argument("--hours-before-bed", type=float, default=None)
    p_log_meal.add_argument("--notes", default="")
    p_log_meal.add_argument("items", nargs="+")

    p_log_sleep = sub.add_parser("log-sleep", help="Log next-morning subjective sleep quality")
    p_log_sleep.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_log_sleep.add_argument("--quality", type=float, required=True, help="Overall quality (1-5)")
    p_log_sleep.add_argument("--meal-id", type=int, default=None)
    p_log_sleep.add_argument("--latency", type=float, default=None, help="Sleep onset latency (minutes)")
    p_log_sleep.add_argument("--awakenings", type=int, default=None)
    p_log_sleep.add_argument("--alertness", type=float, default=None, help="Morning alertness (1-5)")
    p_log_sleep.add_argument("--notes", default="")

    sub.add_parser("analytics", help="Show sleep & nutrition correlation analytics")

    p_serve = sub.add_parser("serve", help="Start the local Web UI")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            nutrition_path=args.nutrition,
            gi_path=args.gi,
            db_path=args.db,
        )
        return

    if args.command == "analytics":
        db = SleepTrackerDB(args.db)
        print(json.dumps(db.get_analytics(), indent=2))
        return

    if args.command == "log-sleep":
        db = SleepTrackerDB(args.db)
        fb_id = db.log_sleep_feedback(
            sleep_date=args.date,
            overall_quality=args.quality,
            meal_log_id=args.meal_id,
            sleep_onset_latency_min=args.latency,
            night_awakenings=args.awakenings,
            morning_alertness=args.alertness,
            notes=args.notes,
        )
        print(json.dumps({"sleep_feedback_id": fb_id}, indent=2))
        return

    foods, _ = load_food_dataset(args.nutrition)
    gi_entries, _ = load_gi_dataset(args.gi)
    attach_gi_to_foods(foods, gi_entries)

    if args.command == "evaluate":
        meal_items = []
        for raw in args.items:
            q, w = _parse_item_arg(raw)
            meal_items.append(MealItem(food=_find_food(foods, q), weight_g=w))
        breakdown = evaluate_meal(meal_items)
        print(json.dumps(breakdown.to_dict(), indent=2))
        return

    if args.command == "log-meal":
        meal_items = []
        for raw in args.items:
            q, w = _parse_item_arg(raw)
            meal_items.append(MealItem(food=_find_food(foods, q), weight_g=w))
        breakdown = evaluate_meal(meal_items)
        db = SleepTrackerDB(args.db)
        meal_id = db.log_meal(
            meal_date=args.date,
            meal_time=args.time,
            foods=[{"food_id": m.food.food_id, "name": m.food.name, "weight_g": m.weight_g} for m in meal_items],
            total_trp_mg=breakdown.total_trp_mg,
            total_lnaa_mg=breakdown.total_lnaa_mg,
            trp_lnaa_ratio=breakdown.trp_lnaa_ratio,
            effective_gi=breakdown.effective_gi,
            effective_gi_category=breakdown.effective_gi_category,
            sleep_score=breakdown.sleep_score,
            planned_bedtime=args.bedtime,
            hours_before_bed=args.hours_before_bed,
            notes=args.notes,
        )
        print(json.dumps({"meal_log_id": meal_id, "score": breakdown.to_dict()}, indent=2))
        return

    if args.command == "recommend":
        if args.mode == "top" or not args.food:
            recs = find_top_pairings(foods, top_k=args.top_k)
        elif args.mode == "for_trp":
            seed = _find_food(foods, args.food)
            recs = recommend_carbs_for_trp_food(seed, foods, top_k=args.top_k)
        else:
            seed = _find_food(foods, args.food)
            recs = recommend_trp_foods_for_carb(seed, foods, top_k=args.top_k)
        print(json.dumps([r.to_dict() for r in recs], indent=2))


if __name__ == "__main__":
    main()

