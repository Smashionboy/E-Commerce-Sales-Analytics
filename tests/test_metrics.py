import pandas as pd
import pytest

from src.metrics import customer_metrics, monthly_sales, purchase_sequence, sales_kpis
from src.preprocessing import build_order_facts, category_sales, sales_sample
from src.statistics import delivery_hypothesis, delivery_review_sample


def test_revenue_aov_and_no_double_count(tables):
    facts = build_order_facts(tables)
    s = sales_sample(facts)
    k = sales_kpis(s)
    assert len(facts) == 4 and facts.order_id.is_unique
    assert k == {
        "orders": 3,
        "product_gmv_brl": 120.0,
        "aov_brl": 40.0,
        "mean_items_per_order": 4 / 3,
        "customers": 2,
    }
    first = facts.set_index("order_id").loc["o1"]
    assert first.revenue == 30 and first.payment_total == 33 and first.review_score == 5
    assert category_sales(tables, s).revenue.sum() == 120


def test_empty_metrics(tables):
    s = sales_sample(build_order_facts(tables)).iloc[:0]
    assert sales_kpis(s)["orders"] == 0
    assert sales_kpis(s)["product_gmv_brl"] == 0
    assert sales_kpis(s)["aov_brl"] is None
    assert monthly_sales(s).empty
    assert customer_metrics(s, pd.Timestamp("2018-04-01")).empty
    assert delivery_hypothesis(s)["status"] == "insufficient_data"


def test_order_grain_rejected(tables):
    s = sales_sample(build_order_facts(tables))
    with pytest.raises(ValueError, match="one row"):
        sales_kpis(pd.concat([s, s.iloc[:1]]))


def test_monthly_gap_and_zero_denominator(tables):
    m = monthly_sales(sales_sample(build_order_facts(tables)))
    assert list(m.orders) == [1, 0, 2]
    assert pd.isna(m.iloc[1].aov) and pd.isna(m.iloc[2].revenue_mom_pct)
    assert m.iloc[1].orders_mom_pct == -100


def test_customer_unique_id_frequency_and_sequence(tables):
    s = sales_sample(build_order_facts(tables))
    c = customer_metrics(s, pd.Timestamp("2018-03-05")).set_index("customer_unique_id")
    assert c.loc["u1", "frequency"] == 2 and c.loc["u1", "monetary"] == 80
    assert c.loc["u1", "recency"] == 3 and c.loc["u2", "recency"] == 2
    assert c.f_score.max() == 2 and c.segment.notna().all()
    seq = purchase_sequence(s).set_index("order_id")
    assert (
        seq.loc["o2", "purchase_number"] == 2 and seq.loc["o3", "purchase_number"] == 1
    )
    with pytest.raises(ValueError, match="Snapshot"):
        customer_metrics(s, pd.Timestamp("2018-03-03"))


def test_delivery_deadline_is_calendar_day_and_missing_unknown(tables):
    f = build_order_facts(tables).set_index("order_id")
    assert not f.loc["o1", "is_late"] and f.loc["o2", "is_late"]
    assert pd.isna(f.loc["o3", "is_late"])
    d = delivery_review_sample(sales_sample(f.reset_index()))
    assert (
        len(d) == 1 and d.iloc[0].order_id == "o1"
    )  # same customer, earliest eligible order


def test_pre_receipt_review_excluded(tables):
    s = sales_sample(build_order_facts(tables))
    s.loc[s.order_id == "o1", "review_answer_timestamp"] = pd.Timestamp("2018-01-01")
    d = delivery_review_sample(s)
    assert list(d.order_id) == ["o2"]


def test_statistical_effect_direction_and_seed(tables):
    s = sales_sample(build_order_facts(tables)).iloc[[0]].copy()
    copies = []
    for j in range(60):
        row = s.copy()
        row["order_id"] = str(j)
        row["customer_unique_id"] = str(j)
        row["is_late"] = j < 30
        row["review_score"] = 1 if j < 30 else 5
        copies.append(row)
    d = pd.concat(copies, ignore_index=True)
    a = delivery_hypothesis(d, bootstrap=100)
    b = delivery_hypothesis(d, bootstrap=100)
    assert a == b and a["p_value"] < 0.05 and a["rank_biserial"] == -1
    assert a["mean_difference_ci95"] == [-4.0, -4.0]
