"""Run all analysis without a database: python -m src.run_analysis."""

import argparse
import importlib.metadata
import json
import platform
from datetime import datetime, timezone

import pandas as pd

from .config import PROCESSED, RAW, REPORTS
from .data_validation import profile_tables, quality_audit
from .metrics import (
    customer_metrics,
    monthly_sales,
    purchase_sequence,
    sales_kpis,
    segment_summary,
)
from .preprocessing import build_order_facts, category_sales, read_tables, sales_sample
from .provenance import source_manifest
from .reporting import business_report
from .statistics import delivery_hypothesis, delivery_review_sample
from .visualization import make_figures


def write_json(path, data):
    """Convert NumPy scalars without hiding non-finite JSON numbers."""
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=lambda x: x.item(),
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def run() -> dict:
    """Materialize aggregates, figures, profile and evidence-backed business note."""
    REPORTS.mkdir(exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tables = read_tables()
    facts = build_order_facts(tables)
    sales = sales_sample(facts)
    kpis = sales_kpis(sales)
    monthly = monthly_sales(sales)
    categories = category_sales(tables, sales)
    snapshot = tables[
        "orders"
    ].order_purchase_timestamp.max().normalize() + pd.Timedelta(days=1)
    customers = customer_metrics(sales, snapshot)
    segments = segment_summary(customers)
    sequence = purchase_sequence(sales)
    stats = delivery_hypothesis(sales)
    quality = quality_audit(tables, facts)
    write_json(REPORTS / "data_profile.json", profile_tables(tables))
    write_json(REPORTS / "kpis.json", kpis)
    write_json(REPORTS / "statistics.json", stats)
    write_json(
        REPORTS / "run_metadata.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "rfm_snapshot": str(snapshot.date()),
            "money_input_unit": "integer cents",
            "sample": "delivered orders with items",
            "packages": {
                p: importlib.metadata.version(p)
                for p in [
                    "pandas",
                    "numpy",
                    "scipy",
                    "SQLAlchemy",
                    "matplotlib",
                    "seaborn",
                ]
            },
        },
    )
    for name, d in [
        ("monthly_sales", monthly),
        ("category_sales", categories),
        ("rfm_segments", segments),
        ("data_quality", quality),
        (
            "order_statuses",
            tables["orders"]
            .groupby("order_status")
            .size()
            .rename("orders")
            .reset_index(),
        ),
        (
            "delivery_review_groups",
            delivery_review_sample(sales)
            .groupby("is_late")
            .agg(n=("order_id", "size"), mean_score=("review_score", "mean"))
            .reset_index(),
        ),
    ]:
        d.to_csv(REPORTS / f"{name}.csv", index=False)
    facts.to_csv(PROCESSED / "order_facts.csv", index=False)
    customers.to_csv(PROCESSED / "customer_rfm.csv", index=False)
    figures = make_figures(sales, monthly, categories, segments, REPORTS / "figures")
    write_json(REPORTS / "source_manifest.json", source_manifest(RAW))
    (REPORTS / "business_insights.md").write_text(
        business_report(
            kpis,
            monthly,
            categories,
            customers,
            segments,
            sequence,
            stats,
            sales,
            quality,
            snapshot,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"kpis": kpis, "figures": len(figures)}, ensure_ascii=False, indent=2
        )
    )
    return kpis


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
