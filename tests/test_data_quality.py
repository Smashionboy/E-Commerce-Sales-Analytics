import zipfile

import pandas as pd
import pytest

from src.contracts import FILES
from src.data_validation import quality_audit, validate_tables
from src.download_data import extract_archive
from src.load_data import db_row
from src.preprocessing import build_order_facts, read_tables


def test_valid_contract_and_reused_review_id(tables):
    validate_tables(tables)
    assert tables["order_reviews"].review_id.duplicated().sum() == 1
    q = quality_audit(tables, build_order_facts(tables)).set_index("check")["count"]
    assert q["orders_without_payments"] == 1
    assert q["orders_multiple_review_rows"] == 1
    assert q["delivered_missing_timestamp"] == 1


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "missing_column",
        "orphan",
        "negative",
        "infinite",
        "score",
        "null",
        "fractional",
        "status",
    ],
)
def test_bad_data_rejected(tables, kind):
    if kind == "duplicate":
        tables["orders"] = pd.concat([tables["orders"], tables["orders"].iloc[:1]])
    elif kind == "missing_column":
        tables["customers"] = tables["customers"].drop(columns="customer_city")
    elif kind == "orphan":
        tables["order_items"].loc[0, "product_id"] = "missing"
    elif kind == "negative":
        tables["order_items"].loc[0, "price"] = -1
    elif kind == "infinite":
        tables["order_items"] = tables["order_items"].astype({"price": float})
        tables["order_items"].loc[0, "price"] = float("inf")
    elif kind == "score":
        tables["order_reviews"].loc[0, "review_score"] = 6
    elif kind == "null":
        tables["customers"].loc[0, "customer_unique_id"] = None
    elif kind == "fractional":
        tables["order_items"] = tables["order_items"].astype({"order_item_id": float})
        tables["order_items"].loc[0, "order_item_id"] = 1.5
    elif kind == "status":
        tables["orders"].loc[0, "order_status"] = "invented"
    with pytest.raises(ValueError):
        validate_tables(tables)


def test_read_csv_roundtrip_preserves_cents_and_zip(raw_dir):
    t = read_tables(raw_dir)
    assert t["order_items"].iloc[0].price == 1000
    assert t["customers"].iloc[0].customer_zip_code_prefix == "00001"


def test_missing_csv(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_tables(tmp_path)


@pytest.mark.parametrize("value", ["bad", "2018-99-99 00:00:00"])
def test_bad_date(raw_dir, value):
    p = raw_dir / FILES["orders"]
    d = pd.read_csv(p)
    d.loc[0, "order_purchase_timestamp"] = value
    d.to_csv(p, index=False)
    with pytest.raises(ValueError):
        read_tables(raw_dir)


def test_fractional_cent_rejected(raw_dir):
    p = raw_dir / FILES["order_items"]
    d = pd.read_csv(p)
    d.loc[0, "price"] = 1.001
    d.to_csv(p, index=False)
    with pytest.raises(ValueError, match="fractional cents"):
        read_tables(raw_dir)


def test_copy_money_conversion():
    from decimal import Decimal

    assert db_row((123, pd.NA), ["price", "text"], ["price"]) == (Decimal("1.23"), None)


def test_invalid_zip_has_no_partial_csv(tmp_path):
    archive = tmp_path / "bad.zip"
    target = tmp_path / "raw"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../evil.csv", "bad")
    with pytest.raises(ValueError, match="missing files"):
        extract_archive(archive, target, "test fixture")
    assert not list(target.glob("*.csv"))


def test_profile_supports_tables_without_numeric_fields(tables):
    from src.data_validation import profile_tables

    p = profile_tables(tables)
    assert p["customers"]["numeric_summary"] == {}
    assert p["orders"]["date_ranges"]["order_purchase_timestamp"]["min"].startswith(
        "2018-01-02"
    )


def test_archive_import_manifest_and_safe_paths(raw_dir, tmp_path):
    archive = tmp_path / "good.zip"
    target = tmp_path / "extracted"
    with zipfile.ZipFile(archive, "w") as z:
        for f in raw_dir.glob("*.csv"):
            z.write(f, arcname="nested/" + f.name)
        z.writestr("../../evil.txt", "do not extract")
    manifest = extract_archive(archive, target, "synthetic test fixture")
    assert len(manifest["files_sha256"]) == 8
    assert not (tmp_path / "evil.txt").exists()
    read_tables(target)


def test_integer_csv_fields_normalized_for_postgres_copy(raw_dir):
    path = raw_dir / FILES["products"]
    d = pd.read_csv(path, dtype="string")
    d["product_weight_g"] = "10.0"
    d.to_csv(path, index=False)
    tables = read_tables(raw_dir)
    value = tables["products"].iloc[0].product_weight_g
    converted = db_row((value,), ["product_weight_g"], [])
    assert isinstance(converted[0], int) and converted[0] == 10


def test_fractional_cent_in_prepared_tables_rejected(tables):
    tables["order_items"] = tables["order_items"].astype({"price": float})
    tables["order_items"].loc[0, "price"] = 0.5
    with pytest.raises(ValueError, match="expected integer"):
        validate_tables(tables)
