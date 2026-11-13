"""Regressions found during the final audit; fixtures are synthetic only."""

import asyncio
import copy
import json
import subprocess
import sys
import zipfile
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from src.contracts import FILES
from src.download_data import extract_archive
from src.execute_notebook import PortableNotebookClient
from src.metrics import customer_metrics, sales_kpis
from src.preprocessing import build_order_facts, read_tables, sales_sample
from src.provenance import source_manifest
from src.verify_sql import compare_results


@pytest.mark.parametrize(
    "column,value",
    [
        ("revenue", np.inf),
        ("revenue", np.nan),
        ("revenue", -1),
        ("item_count", -1),
        ("item_count", 0),
        ("item_count", 1.5),
        ("customer_unique_id", None),
        ("order_purchase_timestamp", pd.NaT),
    ],
)
def test_invalid_analytical_values_rejected(tables, column, value):
    sales = sales_sample(build_order_facts(tables))
    sales[column] = value
    with pytest.raises(ValueError):
        sales_kpis(sales)


def test_missing_rfm_snapshot_rejected(tables):
    sales = sales_sample(build_order_facts(tables))
    with pytest.raises(ValueError, match="Snapshot"):
        customer_metrics(sales, pd.NaT)


def test_changed_imported_csv_fails_integrity_check(raw_dir, tmp_path):
    archive = tmp_path / "original.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in FILES.values():
            z.write(raw_dir / name, arcname=name)
    target = tmp_path / "imported"
    extract_archive(archive, target, "synthetic fixture")
    read_tables(target)
    path = target / FILES["order_items"]
    d = pd.read_csv(path)
    d.loc[0, "price"] = 99
    d.to_csv(path, index=False)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_tables(target)


def test_manual_inputs_are_not_given_old_provenance(raw_dir):
    manifest = source_manifest(raw_dir)
    assert manifest["license"] == "unverified"
    assert len(manifest["files_sha256"]) == 8


def test_ambiguous_zip_rejected_before_csv_publication(raw_dir, tmp_path):
    archive = tmp_path / "ambiguous.zip"
    target = tmp_path / "target"
    with zipfile.ZipFile(archive, "w") as z:
        for name in FILES.values():
            z.write(raw_dir / name, arcname=name)
        z.write(raw_dir / FILES["orders"], arcname="nested/" + FILES["orders"])
    with pytest.raises(ValueError, match="ambiguous"):
        extract_archive(archive, target, "test")
    assert not list(target.glob("*.csv"))


def expected_sql():
    """Known results for conftest's fixture, independent from metric implementation."""
    return {
        "kpis": [
            {
                "orders": 3,
                "product_gmv_brl": 120,
                "aov_brl": 40,
                "mean_items_per_order": 4 / 3,
                "customers": 2,
            }
        ],
        "monthly": [
            {
                "month": "2018-01-01",
                "revenue": 30,
                "orders": 1,
                "aov": 30,
                "items_per_order": 2,
                "revenue_mom_pct": None,
                "orders_mom_pct": None,
            },
            {
                "month": "2018-02-01",
                "revenue": 0,
                "orders": 0,
                "aov": None,
                "items_per_order": None,
                "revenue_mom_pct": -100,
                "orders_mom_pct": -100,
            },
            {
                "month": "2018-03-01",
                "revenue": 90,
                "orders": 2,
                "aov": 45,
                "items_per_order": 1,
                "revenue_mom_pct": None,
                "orders_mom_pct": None,
            },
        ],
        "categories": [
            {"category": "category", "revenue": 120, "items": 4, "orders": 3}
        ],
        "customers": [
            {"customer_unique_id": "u1", "frequency": 2, "monetary": 80, "recency": 3},
            {"customer_unique_id": "u2", "frequency": 1, "monetary": 40, "recency": 2},
        ],
        "delivery": [{"is_late": False, "n": 1, "mean_score": 5}],
        "grain": [{"raw_orders": 4, "facts_rows": 4, "unique_orders": 4}],
    }


def test_sql_comparison_known_fixture_and_corruption(tables):
    good = expected_sql()
    assert len(compare_results(good, tables)) == 6
    for section, column, value in [
        ("kpis", "product_gmv_brl", 121),
        ("customers", "frequency", 99),
        ("delivery", "n", 2),
        ("categories", "revenue", 121),
    ]:
        bad = copy.deepcopy(good)
        bad[section][0][column] = value
        with pytest.raises(ValueError):
            compare_results(bad, tables)


def test_sql_comparison_checks_survive_optimized_python(raw_dir, tmp_path):
    bad = expected_sql()
    bad["kpis"][0]["product_gmv_brl"] = 121
    path = tmp_path / "results.json"
    path.write_text(json.dumps(bad))
    code = "from pathlib import Path; import json,sys; from src.preprocessing import read_tables; from src.verify_sql import compare_results; compare_results(json.loads(Path(sys.argv[1]).read_text()),read_tables(Path(sys.argv[2])))"
    result = subprocess.run(
        [sys.executable, "-O", "-c", code, str(path), str(raw_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "KPI mismatch" in result.stderr


def test_sql_comparison_zero_delivered_orders(tables):
    tables["orders"]["order_status"] = "canceled"
    empty = {
        "kpis": [
            {
                "orders": 0,
                "product_gmv_brl": 0,
                "aov_brl": None,
                "mean_items_per_order": None,
                "customers": 0,
            }
        ],
        "monthly": [],
        "categories": [],
        "customers": [],
        "delivery": [],
        "grain": [{"raw_orders": 4, "facts_rows": 4, "unique_orders": 4}],
    }
    assert len(compare_results(empty, tables)) == 6


def test_notebook_startup_failure_cleans_kernel_without_signal_handlers():
    class Dummy:
        km = type("Manager", (), {"has_kernel": False})()
        kc = None
        async_start_new_kernel = AsyncMock(side_effect=RuntimeError("startup failed"))
        _async_cleanup_kernel = AsyncMock()

    dummy = Dummy()

    async def run():
        async with PortableNotebookClient.async_setup_kernel(dummy):
            raise AssertionError("startup should not succeed")

    with pytest.raises(RuntimeError, match="startup failed"):
        asyncio.run(run())
    dummy._async_cleanup_kernel.assert_awaited_once()


def test_zero_gmv_report_and_stale_figures(tables, tmp_path):
    from src.data_validation import quality_audit
    from src.metrics import monthly_sales, purchase_sequence, segment_summary
    from src.preprocessing import category_sales
    from src.reporting import business_report
    from src.statistics import delivery_hypothesis
    from src.visualization import GENERATED_FIGURES, make_figures

    tables["order_items"]["price"] = 0
    facts = build_order_facts(tables)
    sales = sales_sample(facts)
    monthly = monthly_sales(sales)
    categories = category_sales(tables, sales)
    snapshot = pd.Timestamp("2018-03-05")
    customers = customer_metrics(sales, snapshot)
    segments = segment_summary(customers)
    report = business_report(
        sales_kpis(sales),
        monthly,
        categories,
        customers,
        segments,
        purchase_sequence(sales),
        delivery_hypothesis(sales),
        sales,
        quality_audit(tables, facts),
        snapshot,
    )
    assert "нулевом GMV" in report
    for name in GENERATED_FIGURES:
        (tmp_path / name).write_bytes(b"old generated figure")
    assert make_figures(sales.iloc[:0], monthly, categories, segments, tmp_path) == []
    assert not list(tmp_path.glob("*.png"))


def test_database_password_special_characters(monkeypatch):
    from src.config import database_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    password = "p@ss:${literal}/$# space"
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    assert database_url().password == password
