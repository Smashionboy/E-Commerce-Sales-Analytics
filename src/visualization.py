"""Consistent presentation; plots use BRL and disclose tail clipping/boundaries."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from .statistics import delivery_review_sample

GENERATED_FIGURES = [
    "monthly_revenue.png",
    "monthly_orders.png",
    "order_value.png",
    "top_categories.png",
    "customer_segments.png",
    "delivery_distribution.png",
    "delivery_reviews.png",
]

PALETTE = ["#426B82", "#86A8A0", "#B89A76", "#817C9B", "#AC7878", "#A5ADB4"]


def make_figures(
    sales: pd.DataFrame,
    monthly: pd.DataFrame,
    categories: pd.DataFrame,
    segments: pd.DataFrame,
    output: Path,
) -> list[str]:
    """Return seven figure names; empty datasets produce no misleading plots."""
    output.mkdir(parents=True, exist_ok=True)
    if sales.empty:
        for name in GENERATED_FIGURES:
            (output / name).unlink(missing_ok=True)
        return []
    sns.set_theme(
        style="whitegrid",
        palette=PALETTE,
        font_scale=1.05,
        rc={"axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 120},
    )
    names = []

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(output / name, dpi=160, bbox_inches="tight")
        plt.close(fig)
        names.append(name)

    for col, name, title, ylabel in [
        (
            "revenue",
            "monthly_revenue.png",
            "Delivered product GMV by purchase month",
            "Product GMV (BRL)",
        ),
        (
            "orders",
            "monthly_orders.png",
            "Delivered orders by purchase month",
            "Orders",
        ),
    ]:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(monthly.month, monthly[col], marker="o", markersize=3, color=PALETTE[0])
        ax.set(
            title=title,
            xlabel="Purchase month (boundary months may be incomplete)",
            ylabel=ylabel,
        )
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
        fig.autofmt_xdate()
        save(fig, name)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    cap = sales.revenue.quantile(0.99)
    ax.hist(sales.loc[sales.revenue <= cap, "revenue"], bins=55, color=PALETTE[0])
    ax.axvline(
        sales.revenue.median(),
        color=PALETTE[2],
        label=f"Median: {sales.revenue.median():.2f} BRL",
    )
    ax.set(
        title=f"Order product value (display <= P99: {cap:,.0f} BRL)",
        xlabel="Product value (BRL); full sample used in KPIs",
        ylabel="Orders",
    )
    ax.legend()
    save(fig, "order_value.png")
    fig, ax = plt.subplots(figsize=(9, 5))
    top = categories.head(10).sort_values("revenue")
    ax.barh(top.category, top.revenue, color=PALETTE[0])
    ax.set(
        title="Top 10 categories by product GMV", xlabel="Product GMV (BRL)", ylabel=""
    )
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
    save(fig, "top_categories.png")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    s = segments.sort_values("customers")
    ax.barh(s.segment, s.customers, color=PALETTE[1])
    ax.set(
        title="Customers by descriptive RFM segment",
        xlabel="Unique customers",
        ylabel="",
    )
    save(fig, "customer_segments.png")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    valid = sales.loc[sales.delivery_days >= 0, "delivery_days"]
    cap = valid.quantile(0.99)
    ax.hist(valid[valid <= cap], bins=50, color=PALETTE[0])
    ax.set(
        title=f"Delivery time (display <= P99: {cap:.1f} days)",
        xlabel="Days from purchase to receipt",
        ylabel="Delivered orders with valid timestamps",
    )
    save(fig, "delivery_distribution.png")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    d = delivery_review_sample(sales)
    bands = pd.cut(
        d.delivery_days,
        [0, 7, 14, 21, 30, float("inf")],
        right=False,
        labels=["<7", "7–14", "14–21", "21–30", "30+"],
    )
    g = d.groupby(bands, observed=True).agg(
        mean=("review_score", "mean"), n=("order_id", "size")
    )
    axes[0].bar(g.index.astype(str), g["mean"], color=PALETTE[0])
    axes[0].set(
        title="Score by delivery duration",
        xlabel="Delivery duration (days)",
        ylabel="Mean review score",
        ylim=(0, 5),
    )
    for j, row in enumerate(g.itertuples()):
        axes[0].text(
            j, 0.18, f"n={row.n:,}", ha="center", fontsize=8, color="white", rotation=90
        )
    cross = (
        pd.crosstab(d.is_late, d.review_score, normalize="index").reindex(
            index=[False, True], columns=[1, 2, 3, 4, 5], fill_value=0
        )
        * 100
    )
    cross.index = ["On time", "Late"]
    cross.plot.bar(stacked=True, ax=axes[1], color=PALETTE, rot=0)
    axes[1].set(
        title="Review score distribution by delay", xlabel="", ylabel="Orders (%)"
    )
    axes[1].legend(title="Score", ncol=5, fontsize=8)
    fig.suptitle(
        "Association only · earliest eligible order per customer · review after receipt",
        fontsize=10,
    )
    save(fig, "delivery_reviews.png")
    return names
