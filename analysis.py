"""
Olist E-Commerce Analysis - main analysis script.

What this script does, in plain words:
  1. Loads the 8 real Olist tables from data/
  2. Joins them into one order-level table (one row = one order)
  3. Cleans the real-data problems (cancelled orders, missing dates,
     Portuguese category names, orders with more than one review)
  4. Answers the business questions and saves findings.json
  5. Draws the 6 charts into charts/
  6. Builds a small SQLite database (data/olist.sqlite) for the SQL part

Run download_data.py first, then:  python analysis.py
"""

import json
import os
import sqlite3

import matplotlib

try:
    matplotlib.use("Agg")
except Exception:
    # we are inside a Jupyter kernel that already picked its backend -
    # that is fine, the chart functions still work there
    pass
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CHARTS = os.path.join(HERE, "charts")

plt.rcParams.update(
    {
        "figure.figsize": (9, 5),
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
MAIN_COLOR = "#2563eb"
ACCENT = "#f97316"
GREY = "#6b7280"


def load(name):
    return pd.read_csv(os.path.join(DATA, name))


# ----------------------------------------------------------------------
# 1. Load and join
# ----------------------------------------------------------------------
def build_joined():
    orders = load("olist_orders_dataset.csv")
    items = load("olist_order_items_dataset.csv")
    payments = load("olist_order_payments_dataset.csv")
    reviews = load("olist_order_reviews_dataset.csv")
    customers = load("olist_customers_dataset.csv")
    products = load("olist_products_dataset.csv")
    translation = load("product_category_name_translation.csv")
    # the translation file starts with a BOM in the first column name
    translation.columns = [c.strip().lstrip("﻿") for c in translation.columns]

    counts = {
        "orders": len(orders),
        "order_items": len(items),
        "payments": len(payments),
        "reviews": len(reviews),
        "customers": len(customers),
        "products": len(products),
        "sellers": len(load("olist_sellers_dataset.csv")),
    }

    # --- money per order (items table) ---
    money = (
        items.groupby("order_id")
        .agg(
            items_price=("price", "sum"),
            freight=("freight_value", "sum"),
            item_count=("order_item_id", "count"),
        )
        .reset_index()
    )

    # --- category per order: the category of the most costly item ---
    prod = products.merge(translation, on="product_category_name", how="left")
    prod["category"] = prod["product_category_name_english"].fillna(
        prod["product_category_name"]
    )
    items_cat = items.merge(
        prod[["product_id", "category"]], on="product_id", how="left"
    )
    items_cat["category"] = items_cat["category"].fillna("unknown")
    top_item = items_cat.sort_values("price", ascending=False).drop_duplicates(
        "order_id"
    )
    main_cat = top_item[["order_id", "category"]].rename(
        columns={"category": "main_category"}
    )
    # full item-level table with English categories (for SQL later)
    items_full = items_cat.copy()

    # --- payment per order: total + the biggest payment row tells the type ---
    pay_total = (
        payments.groupby("order_id")["payment_value"].sum().rename("paid_value")
    )
    main_pay = (
        payments.sort_values("payment_value", ascending=False)
        .drop_duplicates("order_id")[
            ["order_id", "payment_type", "payment_installments"]
        ]
        .rename(
            columns={
                "payment_type": "main_payment_type",
                "payment_installments": "installments",
            }
        )
    )
    payments_o = pd.concat([pay_total, ], axis=1).reset_index().merge(
        main_pay, on="order_id", how="left"
    )

    # --- one review per order: if an order has two, keep the latest ---
    reviews["review_creation_date"] = pd.to_datetime(reviews["review_creation_date"])
    reviews_o = (
        reviews.sort_values("review_creation_date")
        .drop_duplicates("order_id", keep="last")[["order_id", "review_score"]]
    )

    # --- dates in the orders table ---
    for col in [
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")

    df = (
        orders.merge(money, on="order_id", how="inner")
        .merge(main_cat, on="order_id", how="left")
        .merge(payments_o, on="order_id", how="left")
        .merge(reviews_o, on="order_id", how="left")
        .merge(
            customers[
                [
                    "customer_id",
                    "customer_unique_id",
                    "customer_city",
                    "customer_state",
                ]
            ],
            on="customer_id",
            how="left",
        )
    )

    # --- delivery numbers ---
    df["delivery_days"] = (
        df["order_delivered_customer_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    df["delay_days"] = (
        df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400

    def bucket(d):
        if pd.isna(d):
            return None
        if d <= 0:
            return "Early or on time"
        if d <= 3:
            return "1-3 days late"
        if d <= 7:
            return "4-7 days late"
        return "8+ days late"

    df["delay_bucket"] = df["delay_days"].apply(bucket)
    df["freight_share_pct"] = np.where(
        df["items_price"] > 0, df["freight"] / df["items_price"] * 100, np.nan
    )
    df["purchase_month"] = df["order_purchase_timestamp"].dt.to_period("M").astype(str)

    return df, counts, items_full, reviews, payments


# ----------------------------------------------------------------------
# 2. Findings
# ----------------------------------------------------------------------
def compute_findings(df, counts):
    f = {"table_rows": counts}
    f["joined_rows"] = int(len(df))
    f["date_min"] = str(df["order_purchase_timestamp"].min().date())
    f["date_max"] = str(df["order_purchase_timestamp"].max().date())

    delivered = df[df["order_status"] == "delivered"].copy()
    f["delivered_orders"] = int(len(delivered))

    # ---- delivery vs reviews ----
    d = delivered.dropna(subset=["delay_days", "review_score"])
    f["delivery_sample"] = int(len(d))
    late = d[d["delay_days"] > 0]
    ontime = d[d["delay_days"] <= 0]
    f["pct_delivered_late"] = round(len(late) / len(d) * 100, 1)
    f["avg_review_on_time"] = round(ontime["review_score"].mean(), 2)
    f["avg_review_late"] = round(late["review_score"].mean(), 2)
    f["avg_review_all_delivered"] = round(d["review_score"].mean(), 2)
    f["share_5star_on_time_pct"] = round((ontime["review_score"] == 5).mean() * 100, 1)
    f["share_5star_late_pct"] = round((late["review_score"] == 5).mean() * 100, 1)
    f["share_1star_on_time_pct"] = round((ontime["review_score"] == 1).mean() * 100, 1)
    f["share_1star_late_pct"] = round((late["review_score"] == 1).mean() * 100, 1)

    order_of_buckets = ["Early or on time", "1-3 days late", "4-7 days late", "8+ days late"]
    by_bucket = {}
    for b in order_of_buckets:
        g = d[d["delay_bucket"] == b]
        by_bucket[b] = {
            "orders": int(len(g)),
            "share_pct": round(len(g) / len(d) * 100, 1),
            "avg_review": round(g["review_score"].mean(), 2),
            "share_5star_pct": round((g["review_score"] == 5).mean() * 100, 1),
            "share_1star_pct": round((g["review_score"] == 1).mean() * 100, 1),
        }
    f["review_by_delay_bucket"] = by_bucket
    very_late = by_bucket["8+ days late"]
    f["very_late_avg_review"] = very_late["avg_review"]

    # ---- categories ----
    valid = df[~df["order_status"].isin(["canceled", "unavailable"])]
    cat_rev = valid.groupby("main_category")["items_price"].sum().sort_values(ascending=False)
    f["top_categories_by_revenue"] = {
        k: round(v, 2) for k, v in cat_rev.head(5).items()
    }
    cat_review = (
        delivered.dropna(subset=["review_score"])
        .groupby("main_category")["review_score"]
        .agg(["mean", "count"])
    )
    cat_review = cat_review[cat_review["count"] >= 300].sort_values("mean")
    f["worst_categories_by_review"] = {
        k: {"avg_review": round(v["mean"], 2), "orders": int(v["count"])}
        for k, v in cat_review.head(5).iterrows()
    }
    f["best_categories_by_review"] = {
        k: {"avg_review": round(v["mean"], 2), "orders": int(v["count"])}
        for k, v in cat_review.tail(5).iloc[::-1].iterrows()
    }
    f["total_revenue_brl"] = round(valid["items_price"].sum(), 2)

    # ---- payments ----
    pay = valid.dropna(subset=["main_payment_type"])
    pay = pay[pay["main_payment_type"] != "not_defined"]
    grp = pay.groupby("main_payment_type")
    f["payment_types"] = {
        t: {
            "orders_share_pct": round(len(g) / len(pay) * 100, 1),
            "avg_order_value_brl": round(g["paid_value"].mean(), 2),
            "avg_installments": round(g["installments"].mean(), 1),
        }
        for t, g in grp
    }
    cc = pay[pay["main_payment_type"] == "credit_card"]
    f["credit_card"] = {
        "avg_installments": round(cc["installments"].mean(), 1),
        "pct_paid_in_installments": round((cc["installments"] > 1).mean() * 100, 1),
        "pct_8plus_installments": round((cc["installments"] >= 8).mean() * 100, 1),
        "avg_value_1_installment_brl": round(
            cc[cc["installments"] == 1]["paid_value"].mean(), 2
        ),
        "avg_value_installments_brl": round(
            cc[cc["installments"] > 1]["paid_value"].mean(), 2
        ),
    }
    bl = pay[pay["main_payment_type"] == "boleto"]
    f["boleto_avg_value_brl"] = round(bl["paid_value"].mean(), 2)

    # ---- monthly trend ----
    trend = (
        valid.groupby("purchase_month")
        .agg(orders=("order_id", "count"), revenue=("items_price", "sum"))
        .reset_index()
    )
    trend = trend[
        (trend["purchase_month"] >= "2017-01") & (trend["purchase_month"] <= "2018-08")
    ]
    f["monthly_trend"] = {
        r.purchase_month: {"orders": int(r.orders), "revenue": round(r.revenue, 2)}
        for r in trend.itertuples()
    }
    peak = trend.loc[trend["orders"].idxmax()]
    f["peak_month"] = {
        "month": peak["purchase_month"],
        "orders": int(peak["orders"]),
        "revenue": round(peak["revenue"], 2),
    }
    first_m, last_m = trend.iloc[0], trend.iloc[-1]
    f["trend_first_month"] = {"month": first_m["purchase_month"], "orders": int(first_m["orders"])}
    f["trend_last_month"] = {"month": last_m["purchase_month"], "orders": int(last_m["orders"])}

    # ---- states ----
    st = (
        valid.groupby("customer_state")
        .agg(orders=("order_id", "count"), revenue=("items_price", "sum"))
        .sort_values("revenue", ascending=False)
    )
    f["top_states_by_revenue"] = {
        k: {"orders": int(v["orders"]), "revenue": round(v["revenue"], 2)}
        for k, v in st.head(10).iterrows()
    }
    f["top_state_share_pct"] = round(
        st.iloc[0]["revenue"] / st["revenue"].sum() * 100, 1
    )
    f["top_state"] = st.index[0]

    # ---- repeat customers ----
    per_customer = df.groupby("customer_unique_id")["order_id"].count()
    f["unique_customers"] = int(len(per_customer))
    f["pct_customers_one_order"] = round((per_customer == 1).mean() * 100, 1)
    f["pct_customers_repeat"] = round((per_customer >= 2).mean() * 100, 1)
    f["max_orders_one_customer"] = int(per_customer.max())

    # ---- freight ----
    f["freight_total_share_pct"] = round(
        valid["freight"].sum() / valid["items_price"].sum() * 100, 1
    )
    f["avg_freight_share_per_order_pct"] = round(valid["freight_share_pct"].mean(), 1)
    f["pct_orders_freight_over_30pct"] = round(
        (valid["freight_share_pct"] > 30).mean() * 100, 1
    )
    cat_freight = (
        valid.groupby("main_category")
        .agg(
            freight=("freight", "sum"),
            price=("items_price", "sum"),
            orders=("order_id", "count"),
        )
    )
    cat_freight["share"] = cat_freight["freight"] / cat_freight["price"] * 100
    cat_freight = cat_freight[cat_freight["orders"] >= 300].sort_values("share")
    f["freight_share_lowest_categories"] = {
        k: round(v["share"], 1) for k, v in cat_freight.head(3).iterrows()
    }
    f["freight_share_highest_categories"] = {
        k: round(v["share"], 1) for k, v in cat_freight.tail(3).iloc[::-1].iterrows()
    }

    # ---- review coverage ----
    f["orders_with_review_pct"] = round(df["review_score"].notna().mean() * 100, 1)
    f["avg_delivery_days"] = round(delivered["delivery_days"].mean(), 1)
    return f


# ----------------------------------------------------------------------
# 3. Charts
# ----------------------------------------------------------------------
def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, name), dpi=150)
    plt.close(fig)
    print("chart:", name)


def make_charts(df, f):
    valid = df[~df["order_status"].isin(["canceled", "unavailable"])]

    # 1. monthly orders + revenue
    months = list(f["monthly_trend"].keys())
    orders_m = [f["monthly_trend"][m]["orders"] for m in months]
    rev_m = [f["monthly_trend"][m]["revenue"] / 1e6 for m in months]
    fig, ax1 = plt.subplots()
    ax1.bar(months, orders_m, color=MAIN_COLOR, alpha=0.85, label="Orders")
    ax1.set_ylabel("Orders")
    ax1.tick_params(axis="x", rotation=60)
    for label in ax1.get_xticklabels():
        label.set_ha("left")
    ax2 = ax1.twinx()
    ax2.plot(months, rev_m, color=ACCENT, marker="o", linewidth=2, label="Revenue")
    ax2.set_ylabel("Revenue (million R$)")
    ax1.set_title("Orders and revenue by month (Jan 2017 - Aug 2018)")
    save(fig, "monthly_orders_revenue.png")

    # 2. delivery delay vs review
    buckets = list(f["review_by_delay_bucket"].keys())
    avg_rev = [f["review_by_delay_bucket"][b]["avg_review"] for b in buckets]
    fig, ax = plt.subplots()
    bars = ax.bar(buckets, avg_rev, color=[MAIN_COLOR, "#f59e0b", "#ea580c", "#dc2626"])
    ax.set_ylim(0, 5.4)
    ax.set_ylabel("Average review score (out of 5)")
    ax.set_title("Late delivery kills the review score")
    for bar, v in zip(bars, avg_rev):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.08, f"{v:.2f}",
                ha="center", fontweight="bold")
    save(fig, "delivery_delay_vs_review.png")

    # 3. review by category (best 5 + worst 5, >=300 orders)
    best = f["best_categories_by_review"]
    worst = f["worst_categories_by_review"]
    cats = list(worst.keys())[::-1] + list(best.keys())
    vals = [worst[c]["avg_review"] for c in list(worst.keys())[::-1]] + [
        best[c]["avg_review"] for c in best.keys()
    ]
    colors = ["#dc2626"] * len(worst) + ["#16a34a"] * len(best)
    fig, ax = plt.subplots()
    bars = ax.barh(cats, vals, color=colors)
    ax.set_xlim(0, 5)
    ax.set_xlabel("Average review score (categories with 300+ reviewed orders)")
    ax.set_title("Best and worst categories by review score")
    for bar, v in zip(bars, vals):
        ax.text(v + 0.06, bar.get_y() + bar.get_height() / 2, f"{v:.2f}",
                va="center", fontweight="bold")
    save(fig, "review_by_category.png")

    # 4. payment types: share + avg order value
    pts = f["payment_types"]
    labels = list(pts.keys())
    shares = [pts[t]["orders_share_pct"] for t in labels]
    values = [pts[t]["avg_order_value_brl"] for t in labels]
    fig, ax1 = plt.subplots()
    bars = ax1.bar(labels, shares, color=MAIN_COLOR, alpha=0.85)
    ax1.set_ylabel("Share of orders (%)")
    for bar, v in zip(bars, shares):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.1f}%",
                 ha="center", fontweight="bold")
    ax2 = ax1.twinx()
    ax2.plot(labels, values, color=ACCENT, marker="o", markersize=9, linewidth=2)
    for i, v in enumerate(values):
        ax2.annotate(f"R$ {v:,.0f}", (i, v), textcoords="offset points",
                     xytext=(0, 10), ha="center", color=ACCENT, fontweight="bold")
    ax2.set_ylabel("Average order value (R$)")
    ax1.set_title("How customers pay - share of orders and average order value")
    save(fig, "payment_types.png")

    # 5. top states by revenue
    states = f["top_states_by_revenue"]
    names = list(states.keys())[::-1]
    revs = [states[s]["revenue"] / 1e6 for s in names]
    fig, ax = plt.subplots()
    bars = ax.barh(names, revs, color=MAIN_COLOR)
    ax.set_xlabel("Revenue (million R$)")
    ax.set_title("Top 10 customer states by revenue")
    for bar, v in zip(bars, revs):
        ax.text(v + 0.1, bar.get_y() + bar.get_height() / 2, f"{v:.1f}",
                va="center", fontweight="bold")
    save(fig, "top_states.png")

    # 6. freight share by category (top 8 by orders among >=300)
    cat_freight = (
        valid.groupby("main_category")
        .agg(freight=("freight", "sum"), price=("items_price", "sum"),
             orders=("order_id", "count"))
    )
    cat_freight = cat_freight[cat_freight["orders"] >= 1000]
    cat_freight["share"] = cat_freight["freight"] / cat_freight["price"] * 100
    cat_freight = cat_freight.sort_values("share")
    fig, ax = plt.subplots()
    bars = ax.barh(cat_freight.index, cat_freight["share"], color="#7c3aed")
    ax.set_xlabel("Freight as % of product value")
    ax.set_title("Delivery charge as a share of the basket, by category (1,000+ orders)")
    for bar, v in zip(bars, cat_freight["share"]):
        ax.text(v + 0.3, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%",
                va="center", fontweight="bold")
    save(fig, "freight_share.png")


# ----------------------------------------------------------------------
# 4. SQLite for the SQL part of the notebook
# ----------------------------------------------------------------------
def build_sqlite(items_full, reviews, payments, df):
    db_path = os.path.join(DATA, "olist.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    orders = load("olist_orders_dataset.csv")[
        ["order_id", "customer_id", "order_status",
         "order_purchase_timestamp", "order_delivered_customer_date",
         "order_estimated_delivery_date"]
    ]
    customers = load("olist_customers_dataset.csv")[
        ["customer_id", "customer_unique_id", "customer_city", "customer_state"]
    ]
    orders.to_sql("orders", con, index=False)
    items_full[
        ["order_id", "order_item_id", "product_id", "seller_id", "category",
         "price", "freight_value"]
    ].to_sql("order_items", con, index=False)
    payments.to_sql("payments", con, index=False)
    reviews[["review_id", "order_id", "review_score", "review_creation_date"]].to_sql(
        "reviews", con, index=False
    )
    customers.to_sql("customers", con, index=False)
    df.to_sql("orders_analysis", con, index=False)
    con.close()
    print("sqlite db:", db_path)


def main():
    os.makedirs(CHARTS, exist_ok=True)
    df, counts, items_full, reviews, payments = build_joined()
    f = compute_findings(df, counts)

    out_csv = os.path.join(DATA, "olist_analysis_joined.csv")
    df.to_csv(out_csv, index=False)
    print("joined table:", out_csv, len(df), "rows")

    with open(os.path.join(HERE, "findings.json"), "w") as fh:
        json.dump(f, fh, indent=2)
    print("findings.json written")

    make_charts(df, f)
    build_sqlite(items_full, reviews, payments, df)
    print("\nKey numbers:")
    print("  orders joined:", f["joined_rows"])
    print("  % delivered late:", f["pct_delivered_late"])
    print("  avg review on time vs late:", f["avg_review_on_time"], "vs", f["avg_review_late"])
    print("  repeat customers %:", f["pct_customers_repeat"])


if __name__ == "__main__":
    main()
