"""Execute every SQL analysis and compare SQL/Python at the same analytical grain."""

import json

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from .config import REPORTS, ROOT, database_url
from .metrics import customer_metrics, monthly_sales, sales_kpis
from .preprocessing import build_order_facts, category_sales, read_tables, sales_sample
from .statistics import delivery_review_sample


def require(condition: bool, message: str) -> None:
    """Explicit checks remain active under python -O."""
    if not condition:
        raise ValueError(message)


def compare_results(results: dict, tables: dict) -> list[str]:
    """Compare source-aligned SQL results, including a zero-delivered-order sample."""
    facts = build_order_facts(tables)
    sales = sales_sample(facts)
    expected = sales_kpis(sales)
    require(len(results["kpis"]) == 1, "Expected one SQL KPI row")
    actual = results["kpis"][0]
    for key, value in expected.items():
        if value is None:
            require(actual[key] is None, f"KPI mismatch: {key}")
        else:
            require(
                actual[key] is not None
                and np.isclose(float(actual[key]), float(value), rtol=0, atol=1e-7),
                f"KPI mismatch: {key}",
            )
    checks = ["orders, GMV, AOV, mean item count, unique customers"]
    py = monthly_sales(sales).set_index("month").sort_index()
    py.index = pd.DatetimeIndex(py.index, name="month")
    sql = pd.DataFrame(results["monthly"], columns=["month", *py.columns])
    sql["month"] = pd.to_datetime(sql.month)
    if sql["month"].dt.tz is not None:
        sql["month"] = sql["month"].dt.tz_localize(None)
    sql = sql.set_index("month").sort_index()
    pd.testing.assert_index_equal(py.index, sql.index, check_names=False)
    for col in py:
        a = pd.to_numeric(sql[col]).to_numpy(dtype=float)
        b = py[col].to_numpy(dtype=float)
        require(
            np.allclose(a, b, rtol=0, atol=1e-7, equal_nan=True),
            f"Monthly mismatch: {col}",
        )
    checks.append("all monthly metrics including calendar gaps and MoM")
    py = category_sales(tables, sales).set_index("category").sort_index()
    sql = (
        pd.DataFrame(
            results["categories"], columns=["category", "revenue", "items", "orders"]
        )
        .set_index("category")
        .sort_index()
    )
    require(list(py.index) == list(sql.index), "Category index mismatch")
    for col in ["revenue", "items", "orders"]:
        require(
            np.allclose(
                py[col].astype(float), sql[col].astype(float), rtol=0, atol=1e-7
            ),
            f"Category mismatch: {col}",
        )
    checks.append("category GMV, item and order counts")
    snapshot = tables[
        "orders"
    ].order_purchase_timestamp.max().normalize() + pd.Timedelta(days=1)
    py = customer_metrics(sales, snapshot).set_index("customer_unique_id").sort_index()
    sql = (
        pd.DataFrame(
            results["customers"],
            columns=["customer_unique_id", "frequency", "monetary", "recency"],
        )
        .set_index("customer_unique_id")
        .sort_index()
    )
    require(list(py.index) == list(sql.index), "Customer index mismatch")
    for col in ["frequency", "monetary", "recency"]:
        require(
            np.allclose(
                py[col].astype(float), sql[col].astype(float), rtol=0, atol=1e-7
            ),
            f"Customer mismatch: {col}",
        )
    checks.append("all customer frequencies, monetary values and recencies")
    py = (
        delivery_review_sample(sales)
        .groupby("is_late")
        .agg(n=("order_id", "size"), mean_score=("review_score", "mean"))
        .sort_index()
    )
    sql = (
        pd.DataFrame(results["delivery"], columns=["is_late", "n", "mean_score"])
        .set_index("is_late")
        .sort_index()
    )
    require(list(py.index) == list(sql.index), "Delivery groups mismatch")
    for col in ["n", "mean_score"]:
        require(
            np.allclose(
                py[col].astype(float), sql[col].astype(float), rtol=0, atol=1e-10
            ),
            f"Delivery mismatch: {col}",
        )
    require(
        results["grain"][0]["raw_orders"]
        == results["grain"][0]["facts_rows"]
        == results["grain"][0]["unique_orders"]
        == len(facts),
        "Order facts grain mismatch",
    )
    checks.extend(
        [
            "delivery review sample sizes and mean scores",
            "order facts preserve one row per source order",
        ]
    )
    return checks


def verify(engine, tables=None) -> dict:
    """Run all SQL files with native psycopg, preserving multiple result sets."""
    if tables is None:
        tables = read_tables()
    all_results = {}
    summaries = []
    with engine.connect() as conn:
        cursor = conn.connection.driver_connection.cursor()
        try:
            version = conn.execute(text("SELECT version()")).scalar_one()
            for file in sorted((ROOT / "sql").glob("0[2-5]_*.sql")):
                cursor.execute(file.read_text(encoding="utf-8"))
                sets = []
                while True:
                    if cursor.description:
                        cols = [c.name for c in cursor.description]
                        sets.append([dict(zip(cols, row)) for row in cursor.fetchall()])
                    if not cursor.nextset():
                        break
                all_results[file.name] = sets
                summaries.append(
                    {
                        "file": file.name,
                        "result_sets": len(sets),
                        "rows": [len(s) for s in sets],
                    }
                )
        finally:
            cursor.close()
    sales = all_results["03_sales_analysis.sql"]
    customer = all_results["04_customer_analysis.sql"]
    selected = {
        "kpis": sales[0],
        "monthly": sales[1],
        "categories": sales[2],
        "customers": customer[0],
        "delivery": all_results["05_advanced_queries.sql"][1],
        "grain": all_results["02_data_quality.sql"][4],
    }
    checks = compare_results(selected, tables)
    return {
        "status": "passed",
        "engine": version,
        "sql_files": summaries,
        "parity_checks": checks,
    }


if __name__ == "__main__":
    engine = create_engine(database_url())
    try:
        result = verify(engine)
        (REPORTS / "sql_verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()
