"""Native integration test; only an explicit disposable test URL permits writes."""

import os

import pytest
from sqlalchemy import create_engine, text

from src.contracts import FILES
from src.load_data import load
from src.verify_sql import verify

pytestmark = pytest.mark.integration


@pytest.fixture
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    e = create_engine(url)
    try:
        yield e
    finally:
        e.dispose()


def test_native_load_rerun_queries_and_bad_load_preserves_data(engine, raw_dir):
    import pandas as pd

    from src.preprocessing import read_tables

    load(engine, raw_dir)
    load(engine, raw_dir)
    assert verify(engine, read_tables(raw_dir))["status"] == "passed"
    p = raw_dir / FILES["order_items"]
    d = pd.read_csv(p)
    d.loc[0, "price"] = -1
    d.to_csv(p, index=False)
    with pytest.raises(ValueError):
        load(engine, raw_dir)
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM olist.orders")).scalar_one() == 4


def test_native_transaction_rolls_back_after_copy_failure(engine, raw_dir):
    import pandas as pd
    from psycopg.errors import NumericValueOutOfRange

    load(engine, raw_dir)
    path = raw_dir / FILES["order_items"]
    d = pd.read_csv(path)
    d.loc[0, "price"] = 1_000_000_000_000
    d.to_csv(path, index=False)
    # Valid nonnegative integer cents, but deliberately beyond NUMERIC(14,2).
    # Failure happens after TRUNCATE and parent COPY, testing an actual rollback.
    with pytest.raises(NumericValueOutOfRange):
        load(engine, raw_dir)
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM olist.orders")).scalar_one() == 4
        assert (
            c.execute(
                text("SELECT SUM(price) FROM olist.order_items WHERE order_id='o1'")
            ).scalar_one()
            == 30
        )


def test_native_zero_delivered_order_sample(engine, raw_dir):
    import pandas as pd

    from src.preprocessing import read_tables

    path = raw_dir / FILES["orders"]
    d = pd.read_csv(path)
    d["order_status"] = "canceled"
    d.to_csv(path, index=False)
    load(engine, raw_dir)
    assert verify(engine, read_tables(raw_dir))["status"] == "passed"


def test_native_zero_value_category_does_not_divide_by_zero(engine, raw_dir):
    import pandas as pd

    from src.preprocessing import read_tables

    path = raw_dir / FILES["order_items"]
    d = pd.read_csv(path)
    d["price"] = 0
    d.to_csv(path, index=False)
    load(engine, raw_dir)
    assert verify(engine, read_tables(raw_dir))["status"] == "passed"
