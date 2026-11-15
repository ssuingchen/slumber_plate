"""Fuzzy and alias matching between food nutrition records and GI records."""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from src.data.models import FoodItem, GIEntry

_CLEAN_RE = re.compile(r"[^a-z0-9\s]+")
_PAREN_RE = re.compile(r"\([^)]*\)")
_STOPWORDS = {"raw", "cooked", "boiled", "made", "from", "with", "in", "for", "min", "water"}


def normalize_food_name(name: str) -> str:
    """Normalize food names by removing '#', parentheticals, and punctuation."""
    text = name.lower().replace("#", " ")
    text = _PAREN_RE.sub(" ", text)
    text = _CLEAN_RE.sub(" ", text)
    return " ".join(text.split())


def _tokenize(normalized: str) -> set:
    return {tok for tok in normalized.split() if tok and tok not in _STOPWORDS}


def match_gi_entry(
    food_name: str,
    gi_entries: List[GIEntry],
    food_id: Optional[str] = None,
    min_score: float = 0.62,
) -> Optional[Tuple[GIEntry, float]]:
    """Find the best matching GIEntry for a food name (or food_id)."""
    if not gi_entries:
        return None

    if food_id:
        for entry in gi_entries:
            if entry.food_id and entry.food_id == food_id:
                return entry, 1.0

    norm_food = normalize_food_name(food_name)
    if not norm_food:
        return None

    food_tokens = _tokenize(norm_food)
    best_entry: Optional[GIEntry] = None
    best_score = 0.0

    for entry in gi_entries:
        norm_gi = normalize_food_name(entry.name)
        if not norm_gi:
            continue
        if norm_food == norm_gi:
            return entry, 1.0

        gi_tokens = _tokenize(norm_gi)
        seq_ratio = SequenceMatcher(None, norm_food, norm_gi).ratio()
        if food_tokens and gi_tokens:
            overlap = len(food_tokens & gi_tokens) / len(food_tokens | gi_tokens)
            containment = len(food_tokens & gi_tokens) / min(len(food_tokens), len(gi_tokens))
            score = 0.40 * seq_ratio + 0.35 * overlap + 0.25 * containment
        else:
            score = seq_ratio

        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is not None and best_score >= min_score:
        return best_entry, round(best_score, 3)
    return None


def attach_gi_to_foods(
    foods: List[FoodItem],
    gi_entries: List[GIEntry],
    min_score: float = 0.62,
) -> int:
    """Attach matching GI values to FoodItems in place. Returns count of matched foods."""
    matched_count = 0
    # Precompute normalized GI entries for faster matching across 8k+ foods
    precomputed: List[Tuple[GIEntry, str, set]] = [
        (entry, normalize_food_name(entry.name), _tokenize(normalize_food_name(entry.name)))
        for entry in gi_entries
    ]
    by_id: Dict[str, GIEntry] = {e.food_id: e for e in gi_entries if e.food_id}

    for food in foods:
        if food.food_id in by_id:
            entry = by_id[food.food_id]
            food.gi_value = entry.gi_value
            food.gi_category = entry.gi_category
            food.gi_match_source = entry.name
            food.gi_match_score = 1.0
            matched_count += 1
            continue

        norm_food = normalize_food_name(food.name)
        food_tokens = _tokenize(norm_food)
        best_entry: Optional[GIEntry] = None
        best_score = 0.0

        for entry, norm_gi, gi_tokens in precomputed:
            if not norm_gi:
                continue
            if norm_food == norm_gi:
                best_entry = entry
                best_score = 1.0
                break
            # Quick token intersection filter before SequenceMatcher
            if food_tokens and gi_tokens and not (food_tokens & gi_tokens):
                continue
            seq_ratio = SequenceMatcher(None, norm_food, norm_gi).ratio()
            if food_tokens and gi_tokens:
                overlap = len(food_tokens & gi_tokens) / len(food_tokens | gi_tokens)
                containment = len(food_tokens & gi_tokens) / min(len(food_tokens), len(gi_tokens))
                score = 0.40 * seq_ratio + 0.35 * overlap + 0.25 * containment
            else:
                score = seq_ratio
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is not None and best_score >= min_score:
            food.gi_value = best_entry.gi_value
            food.gi_category = best_entry.gi_category
            food.gi_match_source = best_entry.name
            food.gi_match_score = round(best_score, 3)
            matched_count += 1

    return matched_count

