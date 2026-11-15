import unittest

from src.data.models import FoodItem, MealItem
from src.scoring.engine import evaluate_meal


class TestScoringEngine(unittest.TestCase):
    def test_zero_lnaa_guards_division_by_zero(self) -> None:
        sugar = FoodItem(food_id="sugar", name="Pure Sugar", carbs_g=100.0, gi_value=65.0)
        res = evaluate_meal([MealItem(sugar, 50.0)])
        self.assertEqual(res.total_lnaa_mg, 0.0)
        self.assertIsNone(res.trp_lnaa_ratio)
        self.assertEqual(res.trp_lnaa_subscore, 0.0)

    def test_missing_methionine_handled_and_surfaced(self) -> None:
        food = FoodItem(
            food_id="f1",
            name="Test Food",
            tryptophan_mg=200.0,
            valine_mg=400.0,
            leucine_mg=600.0,
            isoleucine_mg=350.0,
            tyrosine_mg=300.0,
            phenylalanine_mg=350.0,
            methionine_mg=None,
            carbs_g=25.0,
            gi_value=40.0,
        )
        res = evaluate_meal([MealItem(food, 100.0)])
        self.assertIn("Test Food", res.missing_methionine_foods)
        self.assertNotIn("methionine_mg", res.included_lnaas)
        self.assertAlmostEqual(res.total_lnaa_mg, 2000.0)
        self.assertAlmostEqual(res.trp_lnaa_ratio, 0.10)

    def test_balanced_trp_low_gi_beats_high_gi_and_low_carb(self) -> None:
        trp_protein = FoodItem(
            food_id="turkey",
            name="Turkey",
            tryptophan_mg=320.0,
            valine_mg=900.0,
            leucine_mg=1400.0,
            isoleucine_mg=850.0,
            tyrosine_mg=650.0,
            phenylalanine_mg=700.0,
            methionine_mg=500.0,
            carbs_g=0.0,
        )
        low_gi_carb = FoodItem(
            food_id="barley",
            name="Pearled Barley",
            tryptophan_mg=120.0,
            valine_mg=300.0,
            leucine_mg=450.0,
            isoleucine_mg=250.0,
            tyrosine_mg=200.0,
            phenylalanine_mg=300.0,
            methionine_mg=120.0,
            carbs_g=70.0,
            gi_value=23.0,
        )
        high_gi_carb = FoodItem(
            food_id="white_bread",
            name="White Bread",
            tryptophan_mg=50.0,
            valine_mg=300.0,
            leucine_mg=450.0,
            isoleucine_mg=250.0,
            tyrosine_mg=200.0,
            phenylalanine_mg=300.0,
            methionine_mg=120.0,
            carbs_g=50.0,
            gi_value=85.0,
        )

        balanced_low_gi = evaluate_meal([MealItem(trp_protein, 100.0), MealItem(low_gi_carb, 100.0)])
        balanced_high_gi = evaluate_meal([MealItem(trp_protein, 100.0), MealItem(high_gi_carb, 100.0)])
        protein_only = evaluate_meal([MealItem(trp_protein, 100.0)])

        self.assertGreater(balanced_low_gi.sleep_score, balanced_high_gi.sleep_score)
        self.assertGreater(balanced_low_gi.sleep_score, protein_only.sleep_score)
        self.assertEqual(balanced_low_gi.effective_gi_category, "Low")


if __name__ == "__main__":
    unittest.main()

