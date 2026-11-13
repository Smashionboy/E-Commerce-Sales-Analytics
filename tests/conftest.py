"""Small synthetic fixture, used exclusively for tests. Monetary inputs are cents."""

import pandas as pd
import pytest

from src.contracts import COLUMNS, DATES, FILES


@pytest.fixture
def tables():
    def frame(name, rows):
        d = pd.DataFrame(rows, columns=COLUMNS[name])
        for c in DATES.get(name, []):
            d[c] = pd.to_datetime(d[c], format="ISO8601")
        return d

    return {
        "customers": frame(
            "customers",
            [
                ["a", "u1", "00001", "city", "SP"],
                ["b", "u1", "00001", "city", "SP"],
                ["c", "u2", "00002", "city", "RJ"],
                ["d", "u3", "00003", "city", "MG"],
            ],
        ),
        "sellers": frame("sellers", [["s1", "00001", "city", "SP"]]),
        "products": frame("products", [["p1", "cat", 10, 20, 1, 10, 10, 10, 10]]),
        "category_translation": frame("category_translation", [["cat", "category"]]),
        "orders": frame(
            "orders",
            [
                [
                    "o1",
                    "a",
                    "delivered",
                    "2018-01-02",
                    "2018-01-02",
                    "2018-01-03",
                    "2018-01-05 20:00",
                    "2018-01-05",
                ],
                [
                    "o2",
                    "b",
                    "delivered",
                    "2018-03-02",
                    "2018-03-02",
                    "2018-03-03",
                    "2018-03-10",
                    "2018-03-08",
                ],
                [
                    "o3",
                    "c",
                    "delivered",
                    "2018-03-03",
                    "2018-03-03",
                    "2018-03-04",
                    None,
                    "2018-03-10",
                ],
                ["o4", "d", "canceled", "2018-03-04", None, None, None, "2018-03-10"],
            ],
        ),
        "order_items": frame(
            "order_items",
            [
                ["o1", 1, "p1", "s1", "2018-01-03", 1000, 100],
                ["o1", 2, "p1", "s1", "2018-01-03", 2000, 200],
                ["o2", 1, "p1", "s1", "2018-03-03", 5000, 500],
                ["o3", 1, "p1", "s1", "2018-03-04", 4000, 400],
                ["o4", 1, "p1", "s1", "2018-03-05", 90000, 900],
            ],
        ),
        "order_payments": frame(
            "order_payments",
            [
                ["o1", 1, "credit_card", 1, 2000],
                ["o1", 2, "voucher", 1, 1300],
                ["o2", 1, "credit_card", 1, 5500],
                ["o4", 1, "credit_card", 1, 90900],
            ],
        ),
        "order_reviews": frame(
            "order_reviews",
            [
                ["r1", "o1", 2, None, None, "2018-01-06", "2018-01-06"],
                ["r2", "o1", 5, None, None, "2018-01-07", "2018-01-07"],
                ["r1", "o2", 1, None, None, "2018-03-11", "2018-03-11"],
            ],
        ),
    }


@pytest.fixture
def raw_dir(tables, tmp_path):
    for t, d in tables.items():
        d = d.copy()
        for c in ["price", "freight_value", "payment_value"]:
            if c in d:
                d[c] = d[c] / 100
        for c in DATES.get(t, []):
            d[c] = d[c].dt.strftime("%Y-%m-%d %H:%M:%S")
        d.to_csv(tmp_path / FILES[t], index=False)
    return tmp_path
