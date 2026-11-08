"""One fixed preprocessing/Ridge specification; no target transformation."""

from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def make_pipeline() -> Pipeline:
    preprocessing = ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ("categorical", OneHotEncoder(drop=None, handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ], remainder="drop", sparse_threshold=0.0)
    return Pipeline([
        ("preprocessing", preprocessing),
        ("ridge", Ridge(alpha=1.0, solver="cholesky", fit_intercept=True)),
    ])
