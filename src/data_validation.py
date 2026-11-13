"""Hard contract failures stop loading; soft anomalies remain visible in the audit."""

import numpy as np
import pandas as pd

from .contracts import COLUMNS, KEYS, NUMERIC, RELATIONS, REQUIRED, STATUSES


def validate_tables(tables: dict[str, pd.DataFrame]) -> None:
    """Reject missing columns, null/duplicate keys, invalid numbers and broken FKs."""
    for name, columns in COLUMNS.items():
        if name not in tables:
            raise ValueError(f"Missing table: {name}")
        d = tables[name]
        if set(d.columns) != set(columns):
            raise ValueError(
                f"{name}: unexpected columns: {set(d.columns) ^ set(columns)}"
            )
        if d[list(REQUIRED[name])].isna().any().any():
            raise ValueError(f"{name}: NULL in required fields")
        if d.duplicated(KEYS[name]).any():
            raise ValueError(f"{name}: duplicate primary key {KEYS[name]}")
        for col in NUMERIC.get(name, []):
            values = d[col].dropna().to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"{name}.{col}: non-finite or negative value")
            if (values % 1 != 0).any():
                raise ValueError(f"{name}.{col}: expected integer")
    if not set(tables["orders"].order_status).issubset(STATUSES):
        raise ValueError("orders: unknown status")
    if not tables["order_reviews"].review_score.between(1, 5).all():
        raise ValueError("review_score must be 1..5")
    for t, col, parent, key in RELATIONS:
        if not tables[t][col].isin(tables[parent][key]).all():
            raise ValueError(f"{t}.{col}: orphan reference to {parent}.{key}")
    for t, col in [
        ("order_items", "order_item_id"),
        ("order_payments", "payment_sequential"),
    ]:
        if (tables[t][col] < 1).any():
            raise ValueError(f"{t}.{col}: expected positive sequence")


def profile_tables(tables: dict[str, pd.DataFrame]) -> dict:
    """Serializable EDA inventory, including missing values and observed date ranges."""
    result = {}
    for name, d in tables.items():
        numeric = d.select_dtypes(include="number")
        result[name] = {
            "rows": len(d),
            "columns": len(d.columns),
            "dtypes": d.dtypes.astype(str).to_dict(),
            "nulls": d.isna().sum().to_dict(),
            "exact_duplicates": int(d.duplicated().sum()),
            "duplicate_keys": int(d.duplicated(KEYS[name]).sum()),
            "date_ranges": {
                c: {"min": str(d[c].min()), "max": str(d[c].max())}
                for c in d.select_dtypes(include=["datetime"]).columns
            },
            "numeric_summary": numeric.describe().fillna(0).to_dict()
            if len(numeric.columns)
            else {},
        }
    return result


def quality_audit(tables: dict[str, pd.DataFrame], facts: pd.DataFrame) -> pd.DataFrame:
    """Do not silently impute delivery timestamps, payments, reviews or category names."""
    o = tables["orders"]
    p = tables["products"]
    r = tables["order_reviews"]
    rows = [
        (
            "delivered_missing_timestamp",
            (
                (o.order_status == "delivered") & o.order_delivered_customer_date.isna()
            ).sum(),
        ),
        (
            "delivery_before_purchase",
            (o.order_delivered_customer_date < o.order_purchase_timestamp).sum(),
        ),
        (
            "carrier_before_purchase",
            (o.order_delivered_carrier_date < o.order_purchase_timestamp).sum(),
        ),
        (
            "approval_before_purchase",
            (o.order_approved_at < o.order_purchase_timestamp).sum(),
        ),
        ("orders_without_items", facts.item_count.isna().sum()),
        ("orders_without_payments", facts.payment_total.isna().sum()),
        (
            "payment_total_mismatch_gt_1_cent",
            ((facts.payment_total - facts.gross_value).abs() > 0.01000001).sum(),
        ),
        ("orders_multiple_review_rows", (r.groupby("order_id").size() > 1).sum()),
        ("review_id_reused", r.review_id.duplicated().sum()),
        ("products_missing_category", p.product_category_name.isna().sum()),
        (
            "categories_without_translation",
            p.loc[
                p.product_category_name.notna()
                & ~p.product_category_name.isin(
                    tables["category_translation"].product_category_name
                ),
                "product_category_name",
            ].nunique(),
        ),
        (
            "selected_review_before_receipt",
            (facts.review_answer_timestamp < facts.order_delivered_customer_date).sum(),
        ),
        ("zero_price_items", (tables["order_items"].price == 0).sum()),
        ("zero_payment_rows", (tables["order_payments"].payment_value == 0).sum()),
    ]
    return pd.DataFrame(rows, columns=["check", "count"])
