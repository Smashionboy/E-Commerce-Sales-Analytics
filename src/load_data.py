"""Transactional bulk CSV -> PostgreSQL loader. Reruns replace only the olist schema's data."""

import argparse
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import RAW, ROOT, database_url
from .contracts import COLUMNS, MONEY
from .preprocessing import read_tables

# Foreign-key parents before children.
LOAD_ORDER = [
    "customers",
    "sellers",
    "category_translation",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
]


def db_row(row: tuple, columns: list[str], money: list[str]) -> tuple:
    """Convert pandas scalars to COPY-compatible Python objects, cents -> NUMERIC BRL."""
    result = []
    for col, v in zip(columns, row):
        if pd.isna(v):
            v = None
        elif col in money:
            v = Decimal(int(v)) / 100
        elif isinstance(v, pd.Timestamp):
            v = v.to_pydatetime()
        elif hasattr(v, "item"):
            v = v.item()
        result.append(v)
    return tuple(result)


def load(engine: Engine, raw_dir: Path = RAW) -> dict[str, int]:
    """Validate all inputs before mutation; atomic TRUNCATE + COPY + constraint checks.

    A failed load rolls back the previous dataset, DDL included. No CASCADE outside
    the named eight tables. Serializes concurrent loaders via an advisory lock.
    """
    tables = read_tables(raw_dir)
    counts = {name: len(d) for name, d in tables.items()}
    with engine.begin() as conn:
        driver = conn.connection.driver_connection
        with driver.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(734128)")
            cursor.execute((ROOT / "sql/01_schema.sql").read_text(encoding="utf-8"))
            cursor.execute("TRUNCATE " + ", ".join("olist." + t for t in LOAD_ORDER))
            for table in LOAD_ORDER:
                cols = COLUMNS[table]
                with cursor.copy(
                    f"COPY olist.{table} ({','.join(cols)}) FROM STDIN"
                ) as copy:
                    for row in tables[table][cols].itertuples(index=False, name=None):
                        copy.write_row(db_row(row, cols, MONEY.get(table, [])))
                cursor.execute(f"SELECT COUNT(*) FROM olist.{table}")
                if cursor.fetchone()[0] != counts[table]:
                    raise ValueError(f"Row count mismatch after COPY: {table}")
            for table in LOAD_ORDER:
                cursor.execute(f"ANALYZE olist.{table}")
    return counts


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    engine = create_engine(database_url())
    try:
        print(load(engine))
    except (ValueError, FileNotFoundError) as exc:
        raise RuntimeError(f"Input validation failed before commit: {exc}") from None
    except Exception as exc:
        # Do not echo connection strings or entire COPY rows into user logs.
        raise RuntimeError(
            f"Load failed ({type(exc).__name__}) and was rolled back. Check PostgreSQL availability and column types."
        ) from None
    finally:
        engine.dispose()
