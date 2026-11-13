"""Metrics use an explicitly prepared delivered order sample, one row per order."""

import numpy as np
import pandas as pd


def assert_order_grain(sales: pd.DataFrame) -> None:
    """Fail loudly on multiplication of orders after a JOIN."""
    required = [
        "order_id",
        "customer_unique_id",
        "order_purchase_timestamp",
        "revenue",
        "item_count",
    ]
    if not set(required).issubset(sales.columns):
        raise ValueError("Missing analytical order columns")
    if sales.order_id.isna().any() or sales.order_id.duplicated().any():
        raise ValueError("Expected one row per non-null order_id")
    if sales[required].isna().any().any():
        raise ValueError("Missing analytical order values")
    if not pd.api.types.is_datetime64_any_dtype(sales.order_purchase_timestamp):
        raise ValueError("Purchase timestamps must have datetime dtype")
    for col in ["revenue", "item_count"]:
        if not pd.api.types.is_numeric_dtype(sales[col]):
            raise ValueError(f"{col} must be numeric")
        if not np.isfinite(sales[col].to_numpy(dtype=float)).all():
            raise ValueError(f"{col} must be finite")
    if (sales.revenue < 0).any():
        raise ValueError("Negative revenue")
    if ((sales.item_count < 1) | (sales.item_count % 1 != 0)).any():
        raise ValueError("item_count must be a positive integer")


def sales_kpis(sales: pd.DataFrame) -> dict:
    """Product GMV excludes freight; an empty sample has undefined average ticket."""
    assert_order_grain(sales)
    n = len(sales)
    revenue = float(sales.revenue.sum())
    return {
        "orders": n,
        "product_gmv_brl": round(revenue, 2),
        "aov_brl": revenue / n if n else None,
        "mean_items_per_order": float(sales.item_count.mean()) if n else None,
        "customers": int(sales.customer_unique_id.nunique()),
    }


def monthly_sales(sales: pd.DataFrame) -> pd.DataFrame:
    """Fill internal zero-order months. No claim that boundary months are complete."""
    assert_order_grain(sales)
    columns = [
        "month",
        "revenue",
        "orders",
        "aov",
        "items_per_order",
        "revenue_mom_pct",
        "orders_mom_pct",
    ]
    if sales.empty:
        return pd.DataFrame(columns=columns)
    d = sales.assign(
        month=sales.order_purchase_timestamp.dt.to_period("M").dt.to_timestamp()
    )
    g = d.groupby("month").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "size"),
        items=("item_count", "sum"),
    )
    g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="MS"), fill_value=0)
    g.index.name = "month"
    g["aov"] = g.revenue / g.orders.replace(0, np.nan)
    g["items_per_order"] = g["items"] / g.orders.replace(0, np.nan)
    for col in ["revenue", "orders"]:
        prev = g[col].shift()
        g[col + "_mom_pct"] = (g[col] / prev.where(prev != 0) - 1) * 100
    return g.reset_index()[columns]


def customer_metrics(sales: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    """Recency in calendar days. Frequency counts distinct orders for unique IDs."""
    assert_order_grain(sales)
    if sales.customer_unique_id.isna().any():
        raise ValueError("Missing customer_unique_id")
    if not isinstance(snapshot, pd.Timestamp) or pd.isna(snapshot):
        raise ValueError("Snapshot must be a valid pandas Timestamp")
    if (
        not sales.empty
        and snapshot.normalize() <= sales.order_purchase_timestamp.max().normalize()
    ):
        raise ValueError("Snapshot must be after the final purchase date")
    g = sales.groupby("customer_unique_id").agg(
        frequency=("order_id", "size"),
        monetary=("revenue", "sum"),
        first_purchase=("order_purchase_timestamp", "min"),
        last_purchase=("order_purchase_timestamp", "max"),
    )
    g["recency"] = (snapshot.normalize() - g.last_purchase.dt.normalize()).dt.days
    # Percentile-based R/M avoids qcut errors on ties. Frequency is explicit: 1/2/3+.
    g["r_score"] = (
        np.ceil(g.recency.rank(pct=True, ascending=False) * 3).clip(1, 3).astype(int)
    )
    g["m_score"] = np.ceil(g.monetary.rank(pct=True) * 3).clip(1, 3).astype(int)
    g["f_score"] = g.frequency.clip(upper=3).astype(int)
    g["segment"] = np.select(
        [
            (g.frequency >= 2) & (g.r_score >= 2) & (g.m_score >= 2),
            (g.frequency >= 2) & (g.r_score == 1),
            g.frequency >= 2,
            (g.r_score == 3) & (g.m_score == 3),
            g.r_score == 1,
        ],
        [
            "Active repeat",
            "Lapsed repeat",
            "Other repeat",
            "Recent high value",
            "Older one-time",
        ],
        default="Other one-time",
    )
    return g.reset_index()


def purchase_sequence(sales: pd.DataFrame) -> pd.DataFrame:
    """New/repeat is the order's position in observable customer history."""
    assert_order_grain(sales)
    d = sales.sort_values(
        ["customer_unique_id", "order_purchase_timestamp", "order_id"]
    ).copy()
    d["purchase_number"] = d.groupby("customer_unique_id").cumcount() + 1
    d["buyer_type"] = np.where(
        d.purchase_number == 1, "First observed order", "Repeat order"
    )
    return d


def segment_summary(customers: pd.DataFrame) -> pd.DataFrame:
    """Comparable aggregates; mean customer monetary is distinct from AOV."""
    out = customers.groupby("segment", as_index=False).agg(
        customers=("customer_unique_id", "size"),
        orders=("frequency", "sum"),
        revenue=("monetary", "sum"),
        median_recency=("recency", "median"),
    )
    out["aov"] = out.revenue / out.orders
    out["revenue_share_pct"] = out.revenue / out.revenue.sum() * 100
    return out.sort_values("customers", ascending=False)
