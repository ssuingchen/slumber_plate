import unittest

from src.data.models import FoodItem
from src.recommender.pairings import recommend_carbs_for_trp_food, recommend_trp_foods_for_carb


class TestRecommender(unittest.TestCase):
    def setUp(self) -> None:
        self.seeds = FoodItem(
            food_id="seeds",
            name="Pumpkin Seeds",
            tryptophan_mg=576.0,
            valine_mg=1579.0,
            leucine_mg=2419.0,
            isoleucine_mg=1279.0,
            tyrosine_mg=1093.0,
            phenylalanine_mg=1733.0,
            methionine_mg=603.0,
            carbs_g=10.7,
        )
        self.barley = FoodItem(
            food_id="barley",
            name="Pearled Barley",
            tryptophan_mg=110.0,
            valine_mg=350.0,
            leucine_mg=500.0,
            isoleucine_mg=270.0,
            tyrosine_mg=220.0,
            phenylalanine_mg=340.0,
            methionine_mg=140.0,
            carbs_g=70.0,
            gi_value=23.0,
            gi_category="Low",
        )
        self.high_gi = FoodItem(
            food_id="candy",
            name="Glucose Candy",
            tryptophan_mg=0.0,
            carbs_g=95.0,
            gi_value=95.0,
            gi_category="High",
        )
        self.foods = [self.seeds, self.barley, self.high_gi]

    def test_recommend_carbs_for_trp_food_filters_low_gi(self) -> None:
        recs = recommend_carbs_for_trp_food(self.seeds, self.foods, top_k=5)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].partner_food.food_id, "barley")
        self.assertEqual(recs[0].breakdown.effective_gi_category, "Low")

    def test_recommend_trp_foods_for_carb(self) -> None:
        recs = recommend_trp_foods_for_carb(self.barley, self.foods, top_k=5)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].partner_food.food_id, "seeds")


if __name__ == "__main__":
    unittest.main()

