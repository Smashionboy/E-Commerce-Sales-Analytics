"""Read raw CSVs and construct one row per order before joining child tables."""

from pathlib import Path

import numpy as np
import pandas as pd

from .config import RAW
from .contracts import COLUMNS, DATES, FILES, MONEY, NUMERIC
from .data_validation import validate_tables
from .provenance import source_manifest


def read_tables(raw_dir: Path = RAW) -> dict[str, pd.DataFrame]:
    """Strict parsing; preserve ZIP prefixes as strings and money as integer cents."""
    source_manifest(raw_dir)
    tables = {}
    for name, filename in FILES.items():
        path = raw_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"{path}: run python -m src.download_data first")
        d = pd.read_csv(path, dtype="string")
        if set(d.columns) != set(COLUMNS[name]):
            raise ValueError(f"{filename}: CSV header does not match the contract")
        for col in DATES.get(name, []):
            d[col] = pd.to_datetime(d[col], format="%Y-%m-%d %H:%M:%S", errors="raise")
        for col in NUMERIC.get(name, []):
            d[col] = pd.to_numeric(d[col], errors="raise")
        for col in MONEY.get(name, []):
            # Reject fractional cents instead of silently rounding source changes.
            values = d[col].to_numpy(dtype=float, na_value=np.nan)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(
                    f"{name}.{col}: missing, non-finite or negative amount"
                )
            scaled = values * 100
            if not np.allclose(scaled, np.round(scaled), rtol=0, atol=1e-7):
                raise ValueError(f"{name}.{col}: fractional cents")
            d[col] = np.round(scaled).astype("int64")
        tables[name] = d
    validate_tables(tables)
    for name, columns in NUMERIC.items():
        for col in columns:
            if col not in MONEY.get(name, []):
                tables[name][col] = tables[name][col].astype("Int64")
    return tables


def build_order_facts(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Input monetary columns are cents. Output has both cents and BRL amounts.

    Latest review response wins per order; review_id is a deterministic tie break.
    Missing payments are retained as NULL, never converted into zero revenue.
    """
    i = tables["order_items"]
    pay = tables["order_payments"]
    rev = tables["order_reviews"]
    items = i.groupby("order_id", as_index=False).agg(
        revenue_cents=("price", "sum"),
        freight_cents=("freight_value", "sum"),
        item_count=("order_item_id", "size"),
    )
    payments = pay.groupby("order_id", as_index=False).agg(
        payment_cents=("payment_value", "sum"),
        payment_rows=("payment_sequential", "size"),
    )
    reviews = rev.sort_values(
        ["order_id", "review_answer_timestamp", "review_creation_date", "review_id"]
    ).drop_duplicates("order_id", keep="last")
    facts = tables["orders"].merge(
        tables["customers"], on="customer_id", validate="many_to_one"
    )
    facts = facts.merge(items, on="order_id", how="left", validate="one_to_one")
    facts = facts.merge(payments, on="order_id", how="left", validate="one_to_one")
    facts = facts.merge(
        reviews[["order_id", "review_score", "review_answer_timestamp"]],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    for src, dst in [
        ("revenue_cents", "revenue"),
        ("freight_cents", "freight"),
        ("payment_cents", "payment_total"),
    ]:
        facts[dst] = facts[src] / 100
    facts["gross_value"] = facts.revenue + facts.freight
    facts["delivery_days"] = (
        facts.order_delivered_customer_date - facts.order_purchase_timestamp
    ).dt.total_seconds() / 86400
    facts["late_days"] = (
        facts.order_delivered_customer_date.dt.normalize()
        - facts.order_estimated_delivery_date.dt.normalize()
    ).dt.days
    # Nullable Boolean: missing delivery time must not be interpreted as on time.
    facts["is_late"] = (
        (facts.late_days > 0).astype("boolean").mask(facts.late_days.isna())
    )
    return facts


def sales_sample(facts: pd.DataFrame) -> pd.DataFrame:
    """Delivered orders with >=1 position; month refers to purchase, not receipt."""
    return facts.loc[
        (facts.order_status == "delivered") & (facts.item_count > 0)
    ].copy()


def category_sales(
    tables: dict[str, pd.DataFrame], sales: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate at item grain; never join item amounts to raw payments or reviews."""
    d = tables["order_items"].merge(
        sales[["order_id"]], validate="many_to_one", on="order_id"
    )
    d = d.merge(
        tables["products"][["product_id", "product_category_name"]],
        on="product_id",
        validate="many_to_one",
    )
    d = d.merge(
        tables["category_translation"],
        on="product_category_name",
        how="left",
        validate="many_to_one",
    )
    d["category"] = d.product_category_name_english.fillna(
        d.product_category_name
    ).fillna("unknown")
    out = d.groupby("category", as_index=False).agg(
        revenue_cents=("price", "sum"),
        items=("order_item_id", "size"),
        orders=("order_id", "nunique"),
    )
    out["revenue"] = out.revenue_cents / 100
    return out.sort_values(
        ["revenue", "category"], ascending=[False, True]
    ).reset_index(drop=True)
