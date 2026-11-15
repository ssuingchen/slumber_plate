"""Central configuration for scoring weights, GI thresholds, and dataset mapping."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_NUTRITION_PATH = DATA_DIR / "nutrition.csv"
DEFAULT_GI_PATH = DATA_DIR / "GI.numbers"
DEFAULT_DB_PATH = PROJECT_ROOT / "slumber_plate.db"

DISCLAIMER_TEXT = (
    "Educational & personal tracking only — not medical advice. "
    "Consult a qualified healthcare professional before making significant dietary or sleep-related changes."
)

LNAA_FIELDS: Tuple[str, ...] = (
    "valine_mg",
    "leucine_mg",
    "isoleucine_mg",
    "tyrosine_mg",
    "phenylalanine_mg",
    "methionine_mg",
)

LNAA_DISPLAY_NAMES: Dict[str, str] = {
    "valine_mg": "Valine (Val)",
    "leucine_mg": "Leucine (Leu)",
    "isoleucine_mg": "Isoleucine (Ile)",
    "tyrosine_mg": "Tyrosine (Tyr)",
    "phenylalanine_mg": "Phenylalanine (Phe)",
    "methionine_mg": "Methionine (Met)",
}


@dataclass(frozen=True)
class ScoringConfig:
    """Configurable weights and thresholds for the Sleep Score (0-100) engine."""

    # Component weights (must sum to 1.0)
    trp_lnaa_weight: float = 0.60
    gi_suitability_weight: float = 0.30
    meal_balance_weight: float = 0.10

    # Trp:LNAA ratio normalization range
    trp_lnaa_min_ref: float = 0.03
    trp_lnaa_max_ref: float = 0.12

    # GI category thresholds
    gi_low_max: float = 55.0
    gi_medium_max: float = 69.0

    # GI suitability scoring anchors (0-100 sub-score)
    gi_ideal_score: float = 100.0
    gi_medium_base_score: float = 55.0
    gi_high_floor_score: float = 15.0
    gi_unknown_neutral_score: float = 50.0

    # Meal balance / practicality thresholds
    min_trp_mg_for_full_balance: float = 100.0
    min_carb_g_for_insulin_response: float = 15.0
    ideal_carb_g_upper: float = 75.0

    # Recommender thresholds
    trp_rich_min_mg_per_100g: float = 150.0
    low_gi_carb_min_g_per_100g: float = 10.0


DEFAULT_SCORING_CONFIG = ScoringConfig()
