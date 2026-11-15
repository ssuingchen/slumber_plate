"""Smart Recommender for pairing tryptophan-rich foods with low-GI carbohydrates."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.config.settings import DEFAULT_SCORING_CONFIG, ScoringConfig
from src.data.models import FoodItem, MealItem
from src.scoring.engine import ScoreBreakdown, evaluate_meal


@dataclass
class PairingRecommendation:
    """A recommended pairing of two foods with its Sleep Score breakdown."""

    primary_food: FoodItem
    primary_weight_g: float
    partner_food: FoodItem
    partner_weight_g: float
    breakdown: ScoreBreakdown

    def to_dict(self) -> Dict[str, object]:
        return {
            "primary_food": {
                "food_id": self.primary_food.food_id,
                "name": self.primary_food.name,
                "weight_g": self.primary_weight_g,
                "gi_value": self.primary_food.gi_value,
            },
            "partner_food": {
                "food_id": self.partner_food.food_id,
                "name": self.partner_food.name,
                "weight_g": self.partner_weight_g,
                "gi_value": self.partner_food.gi_value,
                "gi_category": self.partner_food.gi_category,
            },
            "score": self.breakdown.to_dict(),
        }


def is_low_gi_carb(food: FoodItem, config: ScoringConfig = DEFAULT_SCORING_CONFIG) -> bool:
    """Return True if food is a low-GI carbohydrate source."""
    return (
        food.gi_value is not None
        and food.gi_value <= config.gi_low_max
        and food.carbs_g >= config.low_gi_carb_min_g_per_100g
    )


def is_trp_rich(food: FoodItem, config: ScoringConfig = DEFAULT_SCORING_CONFIG) -> bool:
    """Return True if food is rich in tryptophan."""
    return food.tryptophan_mg >= config.trp_rich_min_mg_per_100g


def recommend_carbs_for_trp_food(
    trp_food: FoodItem,
    all_foods: List[FoodItem],
    trp_weight_g: float = 100.0,
    carb_weight_g: float = 100.0,
    top_k: int = 10,
    exclude_terms: Optional[List[str]] = None,
    config: ScoringConfig = DEFAULT_SCORING_CONFIG,
) -> List[PairingRecommendation]:
    """Recommend top low-GI carbohydrate foods to pair with a tryptophan-rich food."""
    excludes = [t.lower() for t in (exclude_terms or []) if t.strip()]
    candidates = [
        f
        for f in all_foods
        if f.food_id != trp_food.food_id
        and is_low_gi_carb(f, config)
        and not any(term in f.name.lower() for term in excludes)
    ]

    results: List[PairingRecommendation] = []
    for carb_food in candidates:
        breakdown = evaluate_meal(
            [MealItem(trp_food, trp_weight_g), MealItem(carb_food, carb_weight_g)],
            config=config,
        )
        results.append(
            PairingRecommendation(
                primary_food=trp_food,
                primary_weight_g=trp_weight_g,
                partner_food=carb_food,
                partner_weight_g=carb_weight_g,
                breakdown=breakdown,
            )
        )

    results.sort(
        key=lambda r: (
            r.breakdown.sleep_score,
            r.breakdown.trp_lnaa_ratio or 0.0,
            r.breakdown.total_trp_mg,
        ),
        reverse=True,
    )
    return results[:top_k]


def recommend_trp_foods_for_carb(
    carb_food: FoodItem,
    all_foods: List[FoodItem],
    carb_weight_g: float = 100.0,
    trp_weight_g: float = 100.0,
    top_k: int = 10,
    exclude_terms: Optional[List[str]] = None,
    candidate_limit: int = 250,
    config: ScoringConfig = DEFAULT_SCORING_CONFIG,
) -> List[PairingRecommendation]:
    """Recommend top tryptophan-rich foods to pair with a carbohydrate food."""
    excludes = [t.lower() for t in (exclude_terms or []) if t.strip()]
    trp_candidates = [
        f
        for f in all_foods
        if f.food_id != carb_food.food_id
        and f.tryptophan_mg > 0
        and not any(term in f.name.lower() for term in excludes)
    ]
    # Pre-rank by Trp:LNAA ratio * log-like Trp presence for fast evaluation on 8k+ datasets
    trp_candidates.sort(
        key=lambda f: ((f.trp_lnaa_ratio() or 0.0), f.tryptophan_mg),
        reverse=True,
    )
    trp_candidates = trp_candidates[:candidate_limit]

    results: List[PairingRecommendation] = []
    for trp_food in trp_candidates:
        breakdown = evaluate_meal(
            [MealItem(carb_food, carb_weight_g), MealItem(trp_food, trp_weight_g)],
            config=config,
        )
        results.append(
            PairingRecommendation(
                primary_food=carb_food,
                primary_weight_g=carb_weight_g,
                partner_food=trp_food,
                partner_weight_g=trp_weight_g,
                breakdown=breakdown,
            )
        )

    results.sort(
        key=lambda r: (
            r.breakdown.sleep_score,
            r.breakdown.trp_lnaa_ratio or 0.0,
            r.breakdown.total_trp_mg,
        ),
        reverse=True,
    )
    return results[:top_k]


def find_top_pairings(
    all_foods: List[FoodItem],
    top_k: int = 10,
    trp_pool_limit: int = 50,
    carb_pool_limit: int = 30,
    config: ScoringConfig = DEFAULT_SCORING_CONFIG,
) -> List[PairingRecommendation]:
    """Discover top overall tryptophan-rich + low-GI carb pairings in the dataset."""
    trp_pool = [f for f in all_foods if is_trp_rich(f, config)]
    if not trp_pool:
        trp_pool = [f for f in all_foods if f.tryptophan_mg > 0]
    trp_pool.sort(key=lambda f: ((f.trp_lnaa_ratio() or 0.0), f.tryptophan_mg), reverse=True)
    trp_pool = trp_pool[:trp_pool_limit]

    carb_pool = [f for f in all_foods if is_low_gi_carb(f, config)]
    carb_pool.sort(key=lambda f: (f.gi_value if f.gi_value is not None else 999.0, -f.carbs_g))
    carb_pool = carb_pool[:carb_pool_limit]

    results: List[PairingRecommendation] = []
    for trp_food in trp_pool:
        for carb_food in carb_pool:
            if trp_food.food_id == carb_food.food_id:
                continue
            breakdown = evaluate_meal(
                [MealItem(trp_food, 100.0), MealItem(carb_food, 100.0)],
                config=config,
            )
            results.append(
                PairingRecommendation(
                    primary_food=trp_food,
                    primary_weight_g=100.0,
                    partner_food=carb_food,
                    partner_weight_g=100.0,
                    breakdown=breakdown,
                )
            )

    results.sort(
        key=lambda r: (
            r.breakdown.sleep_score,
            r.breakdown.trp_lnaa_ratio or 0.0,
            r.breakdown.total_trp_mg,
        ),
        reverse=True,
    )
    return results[:top_k]

