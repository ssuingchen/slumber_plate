"""Core Trp:LNAA and Sleep Score (0-100) calculation engine."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.config.settings import DEFAULT_SCORING_CONFIG, LNAA_DISPLAY_NAMES, ScoringConfig
from src.data.models import MealItem, derive_gi_category


@dataclass
class ScoreBreakdown:
    """Transparent breakdown of Sleep Score and biochemical metrics."""

    total_trp_mg: float
    total_lnaa_mg: float
    trp_lnaa_ratio: Optional[float]
    total_carbs_g: float
    total_protein_g: float
    total_fat_g: float
    total_fiber_g: float
    total_calories_kcal: float
    effective_gi: Optional[float]
    effective_gi_category: str
    trp_lnaa_subscore: float
    gi_subscore: float
    balance_subscore: float
    sleep_score: float
    included_lnaas: List[str] = field(default_factory=list)
    missing_methionine_foods: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_trp_mg": round(self.total_trp_mg, 2),
            "total_lnaa_mg": round(self.total_lnaa_mg, 2),
            "trp_lnaa_ratio": round(self.trp_lnaa_ratio, 5) if self.trp_lnaa_ratio is not None else None,
            "total_carbs_g": round(self.total_carbs_g, 2),
            "total_protein_g": round(self.total_protein_g, 2),
            "total_fat_g": round(self.total_fat_g, 2),
            "total_fiber_g": round(self.total_fiber_g, 2),
            "total_calories_kcal": round(self.total_calories_kcal, 1),
            "effective_gi": round(self.effective_gi, 1) if self.effective_gi is not None else None,
            "effective_gi_category": self.effective_gi_category,
            "trp_lnaa_subscore": round(self.trp_lnaa_subscore, 1),
            "gi_subscore": round(self.gi_subscore, 1),
            "balance_subscore": round(self.balance_subscore, 1),
            "sleep_score": round(self.sleep_score, 1),
            "included_lnaas": [LNAA_DISPLAY_NAMES.get(f, f) for f in self.included_lnaas],
            "missing_methionine_foods": self.missing_methionine_foods,
            "explanations": self.explanations,
        }


def _score_trp_lnaa(ratio: Optional[float], total_trp_mg: float, cfg: ScoringConfig) -> float:
    if ratio is None or total_trp_mg <= 0.0:
        return 0.0
    if ratio <= 0.0:
        return 0.0
    if ratio < cfg.trp_lnaa_min_ref:
        return 25.0 * (ratio / cfg.trp_lnaa_min_ref)
    if ratio >= cfg.trp_lnaa_max_ref:
        return 100.0
    span = cfg.trp_lnaa_max_ref - cfg.trp_lnaa_min_ref
    if span <= 0:
        return 100.0
    return 25.0 + 75.0 * ((ratio - cfg.trp_lnaa_min_ref) / span)


def _score_gi(effective_gi: Optional[float], cfg: ScoringConfig) -> float:
    if effective_gi is None:
        return cfg.gi_unknown_neutral_score
    if effective_gi <= cfg.gi_low_max:
        return cfg.gi_ideal_score
    if effective_gi <= cfg.gi_medium_max:
        # Smoothly penalize Medium GI from 70 down to 40
        span = max(1.0, cfg.gi_medium_max - cfg.gi_low_max)
        frac = (effective_gi - cfg.gi_low_max) / span
        return 70.0 - 30.0 * frac
    # High GI (>= 70): penalize down to floor
    frac = min(1.0, (effective_gi - cfg.gi_medium_max) / 31.0)
    return max(cfg.gi_high_floor_score, 35.0 - (35.0 - cfg.gi_high_floor_score) * frac)


def _score_balance(total_trp_mg: float, total_carbs_g: float, cfg: ScoringConfig) -> float:
    trp_part = 50.0 * min(1.0, total_trp_mg / max(1.0, cfg.min_trp_mg_for_full_balance))
    carb_part = 50.0 * min(1.0, total_carbs_g / max(1.0, cfg.min_carb_g_for_insulin_response))
    return trp_part + carb_part


def evaluate_meal(
    items: List[MealItem],
    config: ScoringConfig = DEFAULT_SCORING_CONFIG,
) -> ScoreBreakdown:
    """Compute Trp:LNAA ratio, effective GI, and Sleep Score (0-100) for a meal."""
    total_trp = 0.0
    total_val = 0.0
    total_leu = 0.0
    total_ile = 0.0
    total_tyr = 0.0
    total_phe = 0.0
    total_met = 0.0

    total_carbs = 0.0
    total_protein = 0.0
    total_fat = 0.0
    total_fiber = 0.0
    total_calories = 0.0

    gi_carb_weighted_sum = 0.0
    gi_carb_weight_total = 0.0
    gi_gram_weighted_sum = 0.0
    gi_gram_weight_total = 0.0

    missing_met_foods: List[str] = []
    any_met_present = False

    for item in items:
        if item.weight_g <= 0:
            continue
        factor = item.weight_g / 100.0
        f = item.food

        total_trp += f.tryptophan_mg * factor
        total_val += f.valine_mg * factor
        total_leu += f.leucine_mg * factor
        total_ile += f.isoleucine_mg * factor
        total_tyr += f.tyrosine_mg * factor
        total_phe += f.phenylalanine_mg * factor
        if f.methionine_mg is None:
            missing_met_foods.append(f.name)
        else:
            any_met_present = True
            total_met += f.methionine_mg * factor

        item_carbs = f.carbs_g * factor
        total_carbs += item_carbs
        total_protein += f.protein_g * factor
        total_fat += f.fat_g * factor
        total_fiber += f.fiber_g * factor
        total_calories += f.calories_kcal * factor

        if f.gi_value is not None:
            if item_carbs > 0:
                gi_carb_weighted_sum += f.gi_value * item_carbs
                gi_carb_weight_total += item_carbs
            gi_gram_weighted_sum += f.gi_value * item.weight_g
            gi_gram_weight_total += item.weight_g

    total_lnaa = total_val + total_leu + total_ile + total_tyr + total_phe + total_met
    ratio: Optional[float] = (total_trp / total_lnaa) if total_lnaa > 0.0 else None

    if gi_carb_weight_total > 0.0:
        effective_gi: Optional[float] = gi_carb_weighted_sum / gi_carb_weight_total
    elif gi_gram_weight_total > 0.0:
        effective_gi = gi_gram_weighted_sum / gi_gram_weight_total
    else:
        effective_gi = None

    effective_gi_cat = derive_gi_category(effective_gi) if effective_gi is not None else "Unknown"

    trp_sub = _score_trp_lnaa(ratio, total_trp, config)
    gi_sub = _score_gi(effective_gi, config)
    bal_sub = _score_balance(total_trp, total_carbs, config)

    composite = (
        config.trp_lnaa_weight * trp_sub
        + config.gi_suitability_weight * gi_sub
        + config.meal_balance_weight * bal_sub
    )
    composite = max(0.0, min(100.0, composite))

    included_lnaas = ["valine_mg", "leucine_mg", "isoleucine_mg", "tyrosine_mg", "phenylalanine_mg"]
    if any_met_present:
        included_lnaas.append("methionine_mg")

    explanations: List[str] = []
    if ratio is None:
        explanations.append("Total competing LNAAs is 0 mg; Trp:LNAA ratio is undefined (guarded against division by zero).")
    else:
        explanations.append(
            f"Trp:LNAA ratio is {ratio:.4f} ({total_trp:.1f} mg Trp / {total_lnaa:.1f} mg LNAA) -> {trp_sub:.1f}/100 component."
        )

    if effective_gi is None:
        explanations.append(
            f"No matched GI data for carbohydrate items -> neutral GI score ({gi_sub:.1f}/100)."
        )
    else:
        explanations.append(
            f"Effective carb-weighted GI is {effective_gi:.1f} ({effective_gi_cat}) -> {gi_sub:.1f}/100 component."
        )

    if total_carbs < config.min_carb_g_for_insulin_response:
        explanations.append(
            f"Carbohydrates ({total_carbs:.1f}g) are below {config.min_carb_g_for_insulin_response:.0f}g; "
            "pairing with a low-GI carb can help insulin-mediated LNAA clearance."
        )
    else:
        explanations.append(
            f"Meal provides {total_trp:.1f} mg Trp and {total_carbs:.1f}g carbs for insulin-assisted BBB transport."
        )

    if missing_met_foods:
        explanations.append(
            f"Methionine was absent in: {', '.join(missing_met_foods[:3])}"
            + ("..." if len(missing_met_foods) > 3 else "")
        )

    return ScoreBreakdown(
        total_trp_mg=total_trp,
        total_lnaa_mg=total_lnaa,
        trp_lnaa_ratio=ratio,
        total_carbs_g=total_carbs,
        total_protein_g=total_protein,
        total_fat_g=total_fat,
        total_fiber_g=total_fiber,
        total_calories_kcal=total_calories,
        effective_gi=effective_gi,
        effective_gi_category=effective_gi_cat,
        trp_lnaa_subscore=trp_sub,
        gi_subscore=gi_sub,
        balance_subscore=bal_sub,
        sleep_score=composite,
        included_lnaas=included_lnaas,
        missing_methionine_foods=missing_met_foods,
        explanations=explanations,
    )

