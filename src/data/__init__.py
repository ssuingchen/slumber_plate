"""Data ingestion, normalization, and GI matching package."""

from src.data.loader import load_food_dataset, load_gi_dataset, parse_numeric_with_unit
from src.data.matcher import attach_gi_to_foods, match_gi_entry, normalize_food_name
from src.data.models import FoodItem, GIEntry, IngestionReport, MealItem, derive_gi_category

__all__ = [
    "FoodItem",
    "GIEntry",
    "IngestionReport",
    "MealItem",
    "attach_gi_to_foods",
    "derive_gi_category",
    "load_food_dataset",
    "load_gi_dataset",
    "match_gi_entry",
    "normalize_food_name",
    "parse_numeric_with_unit",
]

