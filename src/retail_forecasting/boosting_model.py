"""Fixed native-categorical Poisson boosting; no sales-feature recalculation."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, MODEL_FEATURES

MODEL_PARAMETERS = {
    "loss": "poisson", "learning_rate": 0.05, "max_iter": 200,
    "max_leaf_nodes": 15, "min_samples_leaf": 50, "l2_regularization": 1.0,
    "early_stopping": False, "random_state": 42, "categorical_features": "from_dtype",
}


class TrainingCategories(TransformerMixin, BaseEstimator):
    """Learn unordered category labels on training rows; leave numeric values alone."""

    def fit(self, X, y=None):
        if list(X.columns) != MODEL_FEATURES:
            raise ValueError("Expected the unchanged Ridge model-feature columns/order.")
        if X[CATEGORICAL_FEATURES].isna().any().any():
            raise ValueError("Missing categorical label.")
        self.categories_ = {name: sorted(X[name].astype(str).unique().tolist()) for name in CATEGORICAL_FEATURES}
        self.feature_names_in_ = np.array(MODEL_FEATURES, dtype=object)
        self.n_features_in_ = len(MODEL_FEATURES)
        self.n_samples_seen_ = len(X)
        return self

    def transform(self, X):
        check_is_fitted(self, "categories_")
        if list(X.columns) != MODEL_FEATURES:
            raise ValueError("Changed model-feature columns/order.")
        result = X.copy()
        for name in CATEGORICAL_FEATURES:
            labels = X[name].astype(str)
            if X[name].isna().any() or not labels.isin(self.categories_[name]).all():
                raise ValueError(f"Unknown or missing training-defined category: {name}")
            result[name] = pd.Categorical(labels, categories=self.categories_[name], ordered=False)
        return result


def make_pipeline() -> Pipeline:
    return Pipeline([
        ("categories", TrainingCategories()),
        ("estimator", HistGradientBoostingRegressor(**MODEL_PARAMETERS)),
    ])
