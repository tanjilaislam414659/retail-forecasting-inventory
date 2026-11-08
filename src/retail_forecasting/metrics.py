"""Explicit-denominator forecast metrics, with no epsilon or silent SKU removal."""

import numpy as np
import pandas as pd


def summarize(forecasts: pd.DataFrame, scales: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Macro MASE gives equal weight to each SKU present in each metric group."""
    data = forecasts.copy()
    data["absolute_error"] = (data.predicted_sales - data.actual_sales).abs()
    data["signed_error"] = data.predicted_sales - data.actual_sales
    base = data.groupby(dimensions, sort=True, dropna=False).agg(
        row_count=("actual_sales", "size"), actual_units=("actual_sales", "sum"),
        forecast_units=("predicted_sales", "sum"), absolute_error_units=("absolute_error", "sum"),
        signed_error_units=("signed_error", "sum"), sku_count=("sku", "nunique"),
    ).reset_index()
    base["mae"] = base.absolute_error_units / base.row_count
    base["mean_bias_units"] = base.signed_error_units / base.row_count
    denominator = base.actual_units.where(base.actual_units.ne(0))
    base["wape_pct"] = 100 * base.absolute_error_units / denominator
    base["bias_pct"] = 100 * base.signed_error_units / denominator
    base["wape_status"] = np.where(base.actual_units.eq(0), "undefined_zero_actual_total", "defined")
    sku_dimensions = list(dict.fromkeys(dimensions + ["sku"]))
    individual = data.groupby(sku_dimensions, dropna=False).absolute_error.mean().reset_index(name="sku_mae")
    individual = individual.merge(scales[["sku", "mase_scale"]], on="sku", validate="many_to_one")
    if len(individual) != data[sku_dimensions].drop_duplicates().shape[0] or individual.mase_scale.isna().any():
        raise ValueError("Missing training scale for an evaluated SKU.")
    individual["sku_mase"] = individual.sku_mae / individual.mase_scale.where(individual.mase_scale.ne(0))
    individual["undefined_scale"] = individual.mase_scale.eq(0).astype(int)
    macro = individual.groupby(dimensions, dropna=False).agg(
        macro_mase=("sku_mase", lambda values: np.nan if values.isna().any() else values.mean()),
        undefined_mase_skus=("undefined_scale", "sum"),
    ).reset_index()
    result = base.merge(macro, on=dimensions, validate="one_to_one")
    result["mase_status"] = np.where(result.undefined_mase_skus.gt(0), "undefined_contains_zero_scale_sku", "defined")
    return result
