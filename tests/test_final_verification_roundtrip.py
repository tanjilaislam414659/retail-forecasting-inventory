"""Post-unblinding checker regression; no real forecasts or outcomes are read."""

from io import StringIO
import unittest

import numpy as np
import pandas as pd


class SavedFloatTests(unittest.TestCase):
    def test_lossless_csv_parser_recovers_evaluator_float_exactly(self):
        values = np.array([np.nextafter(-29., np.inf), 0.1, np.nextafter(48.2, np.inf)])
        encoded = pd.DataFrame({"quantile": values}).to_csv(index=False)
        ordinary = pd.read_csv(StringIO(encoded)).to_numpy().ravel()
        recovered = pd.read_csv(StringIO(encoded), float_precision="round_trip").to_numpy().ravel()
        self.assertFalse(np.array_equal(values, ordinary))
        np.testing.assert_array_equal(values, recovered)


if __name__ == "__main__":
    unittest.main()
