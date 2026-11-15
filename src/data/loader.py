"""Dataset loaders with schema validation, column alias mapping, and unit normalization."""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.data.models import FoodItem, GIEntry, IngestionReport, derive_gi_category


_NUM_UNIT_RE = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*$")

FOOD_COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "food_id": ("food_id", "id", ""),
    "name": ("name", "food_name", "description", "food"),
    "category": ("category", "food_group", "group"),
    "serving_size": ("serving_size_g", "serving_size", "serving"),
    "tryptophan": ("tryptophan_mg", "tryptophan", "trp_mg", "trp"),
    "valine": ("valine_mg", "valine", "val_mg", "val"),
    "leucine": ("leucine_mg", "leucine", "leu_mg", "leu"),
    "isoleucine": ("isoleucine_mg", "isoleucine", "ile_mg", "ile"),
    "tyrosine": ("tyrosine_mg", "tyrosine", "tyr_mg", "tyr"),
    "phenylalanine": ("phenylalanine_mg", "phenylalanine", "phe_mg", "phe"),
    "methionine": ("methionine_mg", "methionine", "met_mg", "met"),
    "protein": ("protein_g", "protein"),
    "carbs": ("carbs_g", "carbohydrate", "carbohydrates", "carbohydrate_g"),
    "fat": ("fat_g", "fat", "total_fat"),
    "fiber": ("fiber_g", "fiber", "dietary_fiber"),
    "calories": ("calories_kcal", "calories", "energy_kcal", "kcal"),
}

GI_COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "food_id": ("food_id", "id"),
    "name": ("name", "food_name", "food", "description"),
    "gi_value": ("gi_value", "gi", "glycemic_index"),
    "gi_category": ("gi_category", "category"),
    "serving_size_g": ("serving_size_g", "serving size (g)", "serving_size"),
    "carb_portion_g": ("average carbohydrate portion (g)", "carb_portion_g", "carbs_g"),
    "glycemic_load": ("glycemic_load", "gl"),
}


def parse_numeric_with_unit(
    raw: Any,
    target_unit: str = "mg",
    default_unit_if_bare: str = "mg",
) -> Optional[float]:
    """Parse a numeric string with optional unit ('g', 'mg', 'mcg', 'ug', 'kcal') into target_unit."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        unit = default_unit_if_bare.lower()
    else:
        text = str(raw).strip()
        if not text or text.lower() in {"na", "n/a", "null", "none", "-"}:
            return None
        match = _NUM_UNIT_RE.match(text)
        if not match:
            return None
        val = float(match.group(1))
        unit = match.group(2).lower() or default_unit_if_bare.lower()

    if target_unit == "mg":
        if unit == "g":
            return val * 1000.0
        if unit in {"mg", ""}:
            return val
        if unit in {"mcg", "ug"}:
            return val / 1000.0
    elif target_unit == "g":
        if unit in {"g", ""}:
            return val
        if unit == "mg":
            return val / 1000.0
        if unit in {"mcg", "ug"}:
            return val / 1_000_000.0
    return val


def _resolve_column_map(headers: Sequence[str], aliases: Dict[str, Tuple[str, ...]]) -> Dict[str, str]:
    """Map canonical keys to actual header names in a dataset."""
    lower_to_actual = {h.strip().lower(): h for h in headers if h is not None}
    resolved: Dict[str, str] = {}
    for canonical, candidates in aliases.items():
        for cand in candidates:
            if cand in lower_to_actual:
                resolved[canonical] = lower_to_actual[cand]
                break
    return resolved


def _default_unit_for_column(col_name: str, fallback: str) -> str:
    lower = col_name.lower()
    if lower.endswith("_mg"):
        return "mg"
    if lower.endswith("_g"):
        return "g"
    return fallback


def _row_to_food_item(
    row: Dict[str, Any],
    col_map: Dict[str, str],
    row_idx: int,
    report: IngestionReport,
) -> Optional[FoodItem]:
    name_col = col_map.get("name")
    name = str(row.get(name_col, "") if name_col else "").strip()
    if not name:
        report.skipped_count += 1
        report.warnings.append(f"Row {row_idx}: missing food name; skipped.")
        return None

    id_col = col_map.get("food_id")
    raw_id = str(row.get(id_col, "") if id_col is not None else "").strip()
    food_id = raw_id if raw_id else f"food_{row_idx}"

    cat_col = col_map.get("category")
    category = str(row.get(cat_col, "") if cat_col else "").strip()

    serving_col = col_map.get("serving_size")
    serving_g = 100.0
    if serving_col:
        parsed_serving = parse_numeric_with_unit(
            row.get(serving_col), target_unit="g", default_unit_if_bare="g"
        )
        if parsed_serving and parsed_serving > 0:
            serving_g = parsed_serving
        else:
            report.warnings.append(f"Row {row_idx} ({name}): invalid serving_size; defaulted to 100g.")

    scale = 100.0 / serving_g

    def get_mg(key: str, required_zero: bool = True) -> Optional[float]:
        col = col_map.get(key)
        if not col:
            return 0.0 if required_zero else None
        # In nutrition.csv, bare amino acid columns like 'tryptophan' are in grams
        default_u = _default_unit_for_column(col, "g")
        val = parse_numeric_with_unit(row.get(col), target_unit="mg", default_unit_if_bare=default_u)
        if val is None:
            return 0.0 if required_zero else None
        return max(0.0, val * scale)

    def get_g(key: str) -> float:
        col = col_map.get(key)
        if not col:
            return 0.0
        val = parse_numeric_with_unit(row.get(col), target_unit="g", default_unit_if_bare="g")
        return max(0.0, val * scale) if val is not None else 0.0

    cal_col = col_map.get("calories")
    calories = 0.0
    if cal_col:
        parsed_cal = parse_numeric_with_unit(row.get(cal_col), target_unit="kcal", default_unit_if_bare="kcal")
        if parsed_cal is not None:
            calories = max(0.0, parsed_cal * scale)

    return FoodItem(
        food_id=food_id,
        name=name,
        category=category,
        serving_size_g=serving_g,
        tryptophan_mg=get_mg("tryptophan", required_zero=True) or 0.0,
        valine_mg=get_mg("valine", required_zero=True) or 0.0,
        leucine_mg=get_mg("leucine", required_zero=True) or 0.0,
        isoleucine_mg=get_mg("isoleucine", required_zero=True) or 0.0,
        tyrosine_mg=get_mg("tyrosine", required_zero=True) or 0.0,
        phenylalanine_mg=get_mg("phenylalanine", required_zero=True) or 0.0,
        methionine_mg=get_mg("methionine", required_zero=False),
        protein_g=get_g("protein"),
        carbs_g=get_g("carbs"),
        fat_g=get_g("fat"),
        fiber_g=get_g("fiber"),
        calories_kcal=calories,
    )


def load_food_dataset(path: Path) -> Tuple[List[FoodItem], IngestionReport]:
    """Load food & amino-acid dataset from CSV or JSON with validation and normalization."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Food dataset not found: {path}")

    report = IngestionReport()
    items: List[FoodItem] = []

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
        if not isinstance(raw_data, list):
            raise ValueError(f"Expected JSON array in {path}")
        headers = list(raw_data[0].keys()) if raw_data else []
        col_map = _resolve_column_map(headers, FOOD_COLUMN_ALIASES)
        _validate_food_columns(col_map, path)
        report.total_rows = len(raw_data)
        for idx, row in enumerate(raw_data, start=1):
            item = _row_to_food_item(row, col_map, idx, report)
            if item:
                items.append(item)
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            col_map = _resolve_column_map(headers, FOOD_COLUMN_ALIASES)
            _validate_food_columns(col_map, path)
            for idx, row in enumerate(reader, start=1):
                report.total_rows += 1
                item = _row_to_food_item(row, col_map, idx, report)
                if item:
                    items.append(item)
    else:
        raise ValueError(f"Unsupported food dataset format: {path.suffix}")

    report.loaded_count = len(items)
    return items, report


def _validate_food_columns(col_map: Dict[str, str], path: Path) -> None:
    if "name" not in col_map:
        raise ValueError(f"Food dataset {path} is missing a required 'name' column.")
    if "tryptophan" not in col_map:
        raise ValueError(f"Food dataset {path} is missing a required 'tryptophan' column.")


def _rows_from_numbers(path: Path) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        from numbers_parser import Document
    except ImportError as exc:
        raise ImportError(
            "Reading .numbers files requires 'numbers-parser'. Install via: pip install numbers-parser"
        ) from exc

    doc = Document(str(path))
    for sheet in doc.sheets:
        for table in sheet.tables:
            raw_rows = table.rows(values_only=True)
            if not raw_rows:
                continue
            headers = [str(h).strip() if h is not None else "" for h in raw_rows[0]]
            dict_rows: List[Dict[str, Any]] = []
            for row in raw_rows[1:]:
                if all(cell is None or str(cell).strip() == "" for cell in row):
                    continue
                row_dict = {
                    headers[i]: row[i] if i < len(row) else None
                    for i in range(len(headers))
                    if headers[i]
                }
                dict_rows.append(row_dict)
            if dict_rows:
                return [h for h in headers if h], dict_rows
    return [], []


def load_gi_dataset(path: Path) -> Tuple[List[GIEntry], IngestionReport]:
    """Load Glycemic Index dataset from .numbers, .csv, or .json."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GI dataset not found: {path}")

    report = IngestionReport()
    entries: List[GIEntry] = []
    suffix = path.suffix.lower()

    if suffix == ".numbers":
        headers, raw_rows = _rows_from_numbers(path)
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            raw_rows = list(reader)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            raw_rows = json.load(f)
        headers = list(raw_rows[0].keys()) if raw_rows else []
    else:
        raise ValueError(f"Unsupported GI dataset format: {suffix}")

    col_map = _resolve_column_map(headers, GI_COLUMN_ALIASES)
    if "name" not in col_map or "gi_value" not in col_map:
        raise ValueError(f"GI dataset {path} must contain food name and GI value columns.")

    report.total_rows = len(raw_rows)
    for idx, row in enumerate(raw_rows, start=1):
        name = str(row.get(col_map["name"], "") or "").strip()
        gi_raw = row.get(col_map["gi_value"])
        gi_val = parse_numeric_with_unit(gi_raw, target_unit="", default_unit_if_bare="")
        if not name or gi_val is None:
            report.skipped_count += 1
            report.warnings.append(f"GI row {idx}: missing name or numeric GI value; skipped.")
            continue

        cat_col = col_map.get("gi_category")
        gi_cat = str(row.get(cat_col, "") or "").strip() if cat_col else ""
        if not gi_cat:
            gi_cat = derive_gi_category(gi_val)

        serving_val = None
        if "serving_size_g" in col_map:
            serving_val = parse_numeric_with_unit(
                row.get(col_map["serving_size_g"]), target_unit="g", default_unit_if_bare="g"
            )

        carb_portion = None
        if "carb_portion_g" in col_map:
            carb_portion = parse_numeric_with_unit(
                row.get(col_map["carb_portion_g"]), target_unit="g", default_unit_if_bare="g"
            )

        gl_val = None
        if "glycemic_load" in col_map:
            gl_val = parse_numeric_with_unit(
                row.get(col_map["glycemic_load"]), target_unit="", default_unit_if_bare=""
            )

        id_col = col_map.get("food_id")
        food_id = str(row.get(id_col, "") or "").strip() or None if id_col else None

        entries.append(
            GIEntry(
                name=name,
                gi_value=gi_val,
                gi_category=gi_cat,
                serving_size_g=serving_val,
                carb_portion_g=carb_portion,
                glycemic_load=gl_val,
                food_id=food_id,
            )
        )

    report.loaded_count = len(entries)
    return entries, report

