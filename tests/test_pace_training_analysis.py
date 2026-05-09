import unittest

import pandas as pd
from pandas.api.types import is_string_dtype

from pipeline.pace_training_analysis_20 import coerce_horse_id_for_merge


class PaceTrainingAnalysisTest(unittest.TestCase):
    def test_coerces_horse_id_columns_to_string_before_merge(self):
        left = pd.DataFrame({"ketto_toroku_bango": [2023104475], "value": [1]})
        right = pd.DataFrame({"ketto_toroku_bango": ["2023104475"], "training_score": [0.3]})

        left2, right2 = coerce_horse_id_for_merge(left, right)
        merged = left2.merge(right2, on="ketto_toroku_bango", how="left")

        self.assertTrue(is_string_dtype(left2["ketto_toroku_bango"]))
        self.assertEqual("2023104475", merged.loc[0, "ketto_toroku_bango"])
        self.assertEqual(0.3, merged.loc[0, "training_score"])


if __name__ == "__main__":
    unittest.main()
