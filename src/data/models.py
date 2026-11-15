"""Domain models for normalized food, amino-acid, and GI records."""

from dataclasses import dataclass, field
from typing import List, Optional


def derive_gi_category(gi_value: float) -> str:
    """Derive GI category from numeric GI value."""
    if gi_value <= 55.0:
        return "Low"
    if gi_value <= 69.0:
        return "Medium"
    return "High"


@dataclass
class FoodItem:
    """Normalized food record with nutrients scaled per 100g."""

    food_id: str
    name: str
    category: str = ""
    serving_size_g: float = 100.0
    tryptophan_mg: float = 0.0
    valine_mg: float = 0.0
    leucine_mg: float = 0.0
    isoleucine_mg: float = 0.0
    tyrosine_mg: float = 0.0
    phenylalanine_mg: float = 0.0
    methionine_mg: Optional[float] = None
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    calories_kcal: float = 0.0
    gi_value: Optional[float] = None
    gi_category: Optional[str] = None
    gi_match_source: Optional[str] = None
    gi_match_score: float = 0.0

    def included_lnaas(self) -> List[str]:
        """Return list of LNAA fields present on this food item."""
        fields = ["valine_mg", "leucine_mg", "isoleucine_mg", "tyrosine_mg", "phenylalanine_mg"]
        if self.methionine_mg is not None:
            fields.append("methionine_mg")
        return fields

    def total_lnaa_per_100g(self) -> float:
        """Sum of competing LNAAs in mg per 100g."""
        return (
            self.valine_mg
            + self.leucine_mg
            + self.isoleucine_mg
            + self.tyrosine_mg
            + self.phenylalanine_mg
            + (self.methionine_mg or 0.0)
        )

    def trp_lnaa_ratio(self) -> Optional[float]:
        """Return Trp:LNAA ratio per 100g, or None if LNAA is zero."""
        total_lnaa = self.total_lnaa_per_100g()
        if total_lnaa <= 0.0:
            return None
        return self.tryptophan_mg / total_lnaa


@dataclass
class GIEntry:
    """Normalized Glycemic Index record."""

    name: str
    gi_value: float
    gi_category: str = ""
    serving_size_g: Optional[float] = None
    carb_portion_g: Optional[float] = None
    glycemic_load: Optional[float] = None
    food_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.gi_category:
            self.gi_category = derive_gi_category(self.gi_value)


@dataclass
class MealItem:
    """A food item with a chosen serving weight in grams."""

    food: FoodItem
    weight_g: float


@dataclass
class IngestionReport:
    """Summary of dataset loading, validation, and warnings."""

    total_rows: int = 0
    loaded_count: int = 0
    skipped_count: int = 0
    warnings: List[str] = field(default_factory=list)

