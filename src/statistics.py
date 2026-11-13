"""One predeclared, observational ordinal hypothesis; no causal interpretation."""

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu


def delivery_review_sample(sales: pd.DataFrame) -> pd.DataFrame:
    """Keep nonnegative transit, known score/delay, post-receipt response.

    Select earliest eligible purchase per unique customer to reduce dependence
    from repeated buyers. Seller/region/time clustering can still remain.
    """
    mask = (
        (sales.delivery_days >= 0)
        & sales.is_late.notna()
        & sales.review_score.notna()
        & (sales.review_answer_timestamp >= sales.order_delivered_customer_date)
    )
    return (
        sales.loc[mask]
        .sort_values(["customer_unique_id", "order_purchase_timestamp", "order_id"])
        .drop_duplicates("customer_unique_id")
    )


def delivery_hypothesis(
    sales: pd.DataFrame, bootstrap: int = 1000, seed: int = 42
) -> dict:
    """Two-sided MW U: H0 identical score distributions; H1 different distributions.

    Scores are ordinal with many ties: asymptotic U uses tie correction. U tests
    stochastic ordering/distributions, not a pure median difference. Effect is
    2*U/(n_late*n_on_time)-1 (ties count as half), negative means late is worse.
    Bootstrap CI is for descriptive mean-score difference, late minus on-time.
    """
    d = delivery_review_sample(sales)
    a = d.loc[d.is_late, "review_score"].to_numpy(dtype=float)
    b = d.loc[~d.is_late, "review_score"].to_numpy(dtype=float)
    base = {
        "hypothesis": "H0: score distributions identical; H1: different (two-sided)",
        "method": "Mann-Whitney U, asymptotic, tie-corrected",
        "n_late": len(a),
        "n_on_time": len(b),
        "seed": seed,
        "bootstrap_resamples": bootstrap,
    }
    broad = sales.loc[
        (sales.delivery_days >= 0) & sales.is_late.notna() & sales.review_score.notna()
    ]
    broad = broad.sort_values(
        ["customer_unique_id", "order_purchase_timestamp", "order_id"]
    ).drop_duplicates("customer_unique_id")
    base["sensitivity_including_pre_receipt_reviews"] = [
        {
            "is_late": bool(flag),
            "n": len(group),
            "mean_score": float(group.review_score.mean()),
        }
        for flag, group in broad.groupby("is_late")
    ]
    if min(len(a), len(b)) < 20:
        return {
            **base,
            "status": "insufficient_data",
            "p_value": None,
            "rank_biserial": None,
        }
    test = mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
    rng = np.random.default_rng(seed)
    # Five possible scores: multinomial bootstrap exactly matches resampling of scores.
    ca = np.bincount(a.astype(int), minlength=6)[1:6]
    cb = np.bincount(b.astype(int), minlength=6)[1:6]
    weights = np.arange(1, 6)
    diffs = rng.multinomial(len(a), ca / len(a), size=bootstrap) @ weights / len(
        a
    ) - rng.multinomial(len(b), cb / len(b), size=bootstrap) @ weights / len(b)
    return {
        **base,
        "status": "ok",
        "u_statistic": float(test.statistic),
        "p_value": float(test.pvalue),
        "rank_biserial": float(2 * test.statistic / (len(a) * len(b)) - 1),
        "mean_late": float(a.mean()),
        "mean_on_time": float(b.mean()),
        "median_late": float(np.median(a)),
        "median_on_time": float(np.median(b)),
        "low_score_rate_late": float((a <= 2).mean()),
        "low_score_rate_on_time": float((b <= 2).mean()),
        "mean_difference": float(a.mean() - b.mean()),
        "mean_difference_ci95": np.quantile(diffs, [0.025, 0.975]).tolist(),
    }
