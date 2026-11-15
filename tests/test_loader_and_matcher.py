import unittest
from pathlib import Path

from src.config.settings import DEFAULT_GI_PATH, DEFAULT_NUTRITION_PATH
from src.data.loader import load_food_dataset, load_gi_dataset, parse_numeric_with_unit
from src.data.matcher import attach_gi_to_foods, match_gi_entry
from src.data.models import GIEntry


class TestLoaderAndMatcher(unittest.TestCase):
    def test_parse_numeric_with_unit(self) -> None:
        self.assertAlmostEqual(parse_numeric_with_unit("0.093 g", target_unit="mg"), 93.0)
        self.assertAlmostEqual(parse_numeric_with_unit("150 mg", target_unit="mg"), 150.0)
        self.assertAlmostEqual(parse_numeric_with_unit("100 g", target_unit="g"), 100.0)
        self.assertIsNone(parse_numeric_with_unit("", target_unit="mg"))
        self.assertIsNone(parse_numeric_with_unit("N/A", target_unit="mg"))

    def test_load_real_datasets_and_match(self) -> None:
        foods, food_report = load_food_dataset(DEFAULT_NUTRITION_PATH)
        self.assertGreater(food_report.loaded_count, 8000)

        gi_entries, gi_report = load_gi_dataset(DEFAULT_GI_PATH)
        self.assertGreater(gi_report.loaded_count, 10)

        matched = attach_gi_to_foods(foods, gi_entries)
        self.assertGreater(matched, 0)

    def test_fuzzy_gi_match_strips_hash_and_parens(self) -> None:
        entries = [GIEntry(name="Barley, pearled #", gi_value=23.0)]
        match = match_gi_entry("Barley, pearled, raw", entries)
        self.assertIsNotNone(match)
        entry, score = match
        self.assertEqual(entry.gi_value, 23.0)
        self.assertGreaterEqual(score, 0.62)


if __name__ == "__main__":
    unittest.main()

