"""
Build olist_analysis.ipynb and execute it end to end.

Markdown numbers come from findings.json (produced by analysis.py),
so the words in the notebook can never drift away from the real results.

Run:  python build_notebook.py
"""

import json
import os

import nbformat as nbf
from nbclient import NotebookClient

HERE = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(HERE, "findings.json")))


def cat(name):
    return name.replace("_", " ")


def brl(v):
    return f"R$ {v:,.0f}"


def brl_m(v):
    return f"R$ {v / 1e6:.2f} million"


B = F["review_by_delay_bucket"]
TOPCAT = list(F["top_categories_by_revenue"].items())
WORST = list(F["worst_categories_by_review"].items())
BEST = list(F["best_categories_by_review"].items())
PAY = F["payment_types"]
CC = F["credit_card"]
STATES = F["top_states_by_revenue"]
FRE_HI = list(F["freight_share_highest_categories"].items())
FRE_LO = list(F["freight_share_lowest_categories"].items())

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


# ---------------------------------------------------------------- intro
md(f"""# Olist E-Commerce Analysis — What Makes Customers Happy or Angry?

Hi, I'm **Vivek Saini**, a Data Analyst from Meerut, India. This is my third
portfolio project. My first two projects used data I created myself. This
time I wanted the real thing, so I worked on **real data from Olist**, a
real marketplace in Brazil.

The data has **{F['table_rows']['orders']:,} orders** from 2016 to 2018 —
what people bought, how they paid, when the parcel reached them, and the
review score they gave after delivery.

I asked one main question in different ways:

> **What makes a customer happy or angry on a marketplace?**

My guess before starting: delivery. If a parcel comes late, the customer
gets angry, and the review shows it. This notebook tests that guess, plus
a few more questions about categories, payments, repeat buyers and
delivery charges.

**Data source and credit:** Olist — published openly on GitHub
(github.com/olist/work-at-olist-data) under the **CC BY-NC-SA 4.0**
licence. The data is real and belongs to Olist. Only the code in this
project is mine.

**Tools:** Python, pandas, SQL (SQLite), matplotlib, Jupyter.""")

# ---------------------------------------------------------------- get data
md("""## Step 1 — Get the data

The `download_data.py` script in this project pulls the 8 tables straight
from Olist's GitHub page. No copy-paste, no fake rows. Let me load them
and see what we have.""")

code("""%matplotlib inline
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
from IPython.display import Image

pd.set_option("display.max_columns", 20)

files = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}
tables = {name: pd.read_csv("data/" + f) for name, f in files.items()}
for name, t in tables.items():
    print(f"{name:12s} {len(t):>8,} rows   {t.shape[1]} columns")""")

md("""## Step 2 — Meet the tables

The tables connect like this:

- **orders** — one row per order: status, purchase time, promised delivery date, real delivery date
- **items** — one row per product in an order: price and delivery charge (freight)
- **payments** — how each order was paid: card, boleto (a Brazilian bank slip), voucher…
- **reviews** — the 1 to 5 star score the customer gave
- **customers** — city and state of the buyer
- **products** — product category (in Portuguese!)
- **sellers** — who sold the item
- **translation** — Portuguese category names changed to English

Here is the orders table, and how many orders sit in each status:""")

code("""tables["orders"].head(3)""")

code("""tables["orders"]["order_status"].value_counts()""")

md(f"""Most orders are **delivered** ({F['delivered_orders']:,}). A few are
cancelled or stuck on the way. For delivery questions, only delivered
orders make sense — a cancelled order never reached anyone.""")

# ---------------------------------------------------------------- cleaning
md("""## Step 3 — Clean and join

Real data is never ready to use. The problems I had to fix:

1. **Cancelled and "unavailable" orders** — kept for sales totals, removed
   from the delivery analysis.
2. **Missing dates** — some delivered orders have no delivery date, so no
   delay can be worked out for them.
3. **Two reviews for one order** — a few orders were reviewed twice. I
   kept the latest review.
4. **Portuguese category names** — changed to English with the
   translation table.
5. **Orders with many items** — for "the category of an order" I used the
   category of its most costly item. A simple rule, and I state it openly.
6. **{F['table_rows']['orders'] - F['joined_rows']:,} orders had no items at all** — no
   products, no price. They cannot be studied, so the joined table drops
   them.

The full cleaning code lives in `analysis.py`. Here I call it and work
with the joined table it builds — one row per order:""")

code("""from analysis import build_joined

df, counts, items_full, reviews_raw, payments_raw = build_joined()
print("joined table:", df.shape)
df[["order_id", "order_status", "main_category", "items_price",
    "freight", "main_payment_type", "review_score",
    "customer_state", "delay_days"]].head()""")

code("""# a look at the cleaning problems, in numbers
delivered = df[df["order_status"] == "delivered"]
print("review rows in raw table      :", f"{len(reviews_raw):,}")
print("orders with a review (joined) :", f"{df['review_score'].notna().sum():,}")
print("delivered orders              :", f"{len(delivered):,}")
print("...but no delivery date       :", f"{delivered['order_delivered_customer_date'].isna().sum():,}")
print("cancelled + unavailable orders:", f"{df['order_status'].isin(['canceled', 'unavailable']).sum():,}")""")

code("""# Portuguese -> English, one small example
tr = tables["translation"].copy()
tr.columns = [c.strip().lstrip("\\ufeff") for c in tr.columns]
tr.head(5)""")

# ---------------------------------------------------------------- Q1 delivery
md(f"""## Question 1 — Does late delivery hurt the review score?

Every order has a **promised** delivery date and a **real** delivery date.
I worked out the gap in days and put each delivered order into a group:
early or on time, 1–3 days late, 4–7 days late, or 8+ days late.

Only **{F['pct_delivered_late']}%** of delivered orders were late at all.
The average delivery took **{F['avg_delivery_days']} days** — Brazil is a
big country. So the real question is not "are they slow?" but "what
happens when they break the promise?\"""")

code("""d = df[df["order_status"] == "delivered"].dropna(subset=["delay_days", "review_score"])
order = ["Early or on time", "1-3 days late", "4-7 days late", "8+ days late"]
d = d.assign(delay_bucket=pd.Categorical(d["delay_bucket"], categories=order, ordered=True))
table = d.groupby("delay_bucket", observed=True).agg(
    orders=("order_id", "count"),
    avg_review=("review_score", "mean"),
    five_star_pct=("review_score", lambda s: (s == 5).mean() * 100),
    one_star_pct=("review_score", lambda s: (s == 1).mean() * 100),
).round(2)
table""")

code("""%matplotlib inline
fig, ax = plt.subplots(figsize=(9, 5))
colors = ["#2563eb", "#f59e0b", "#ea580c", "#dc2626"]
bars = ax.bar(table.index.astype(str), table["avg_review"], color=colors)
ax.set_ylim(0, 5.4)
ax.set_ylabel("Average review score (out of 5)")
ax.set_title("Late delivery kills the review score")
for bar, v in zip(bars, table["avg_review"]):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 0.08, f"{v:.2f}",
            ha="center", fontweight="bold")
plt.tight_layout()
plt.show()""")

md(f"""This is the clearest result in the whole project:

| | On time | Late (any) | 8+ days late |
|---|---|---|---|
| Average review | **{F['avg_review_on_time']}** | **{F['avg_review_late']}** | **{F['very_late_avg_review']}** |
| 5-star reviews | {F['share_5star_on_time_pct']}% | {F['share_5star_late_pct']}% | {B['8+ days late']['share_5star_pct']}% |
| 1-star reviews | {F['share_1star_on_time_pct']}% | {F['share_1star_late_pct']}% | {B['8+ days late']['share_1star_pct']}% |

A small delay of 1–3 days costs a little (average {B['1-3 days late']['avg_review']}).
But past a week, the customer is gone — **{B['8+ days late']['share_1star_pct']}% of
very late orders got the worst score of 1 star.**

So the promise matters more than the speed. Olist is slow but mostly
honest: {B['Early or on time']['share_pct']}% of orders reached on or before the
promised date, and those customers stayed happy.""")

# ---------------------------------------------------------------- Q2 categories
md(f"""## Question 2 — Which categories earn the most, and which make customers happy?

Total product sales in this data: **{brl_m(F['total_revenue_brl'])}**.
The top earner is **{cat(TOPCAT[0][0])}** with {brl(TOPCAT[0][1])}.

But money and happiness are not the same thing, as the review table
shows. (I only ranked categories with 300+ reviewed orders, so a tiny
category with 5 lucky reviews cannot top the list.)""")

code("""valid = df[~df["order_status"].isin(["canceled", "unavailable"])]
revenue_by_cat = (valid.groupby("main_category")["items_price"]
                  .sum().sort_values(ascending=False).head(5))
revenue_by_cat.rename("revenue_R$").round(2)""")

code("""cat_review = (df[df["order_status"] == "delivered"]
              .dropna(subset=["review_score"])
              .groupby("main_category")["review_score"]
              .agg(["mean", "count"]))
cat_review = cat_review[cat_review["count"] >= 300].sort_values("mean")
print("WORST 5 by review:")
display(cat_review.head(5).round(2))
print("BEST 5 by review:")
display(cat_review.tail(5).iloc[::-1].round(2))""")

code("""Image("charts/review_by_category.png")""")

md(f"""Two things stood out for me:

- **{cat(WORST[0][0])}** is the worst-rated category at **{WORST[0][1]['avg_review']}**
  stars ({WORST[0][1]['orders']:,} orders). Big furniture is heavy, easy to
  damage and slow to move — the next section shows its delivery charge is
  also one of the highest.
- **{cat(TOPCAT[2][0])}** is the third-biggest earner ({brl(TOPCAT[2][1])})
  but scores only **{WORST[3][1]['avg_review']}** — below average. A small
  quality fix in a category this big moves a lot of money.
- Books make people happiest: **{cat(BEST[0][0])}** tops the list at
  **{BEST[0][1]['avg_review']}** stars.""")

# ---------------------------------------------------------------- Q3 payments
md(f"""## Question 3 — How do customers pay?

Brazil pays in a way that surprised me. **Credit card is king —
{PAY['credit_card']['orders_share_pct']}% of orders.** And most card
buyers do not pay at once: they split the bill into monthly parts
(installments), which is normal in Brazil.

| Payment type | Share of orders | Average order value |
|---|---|---|
| Credit card | {PAY['credit_card']['orders_share_pct']}% | {brl(PAY['credit_card']['avg_order_value_brl'])} |
| Boleto (bank slip) | {PAY['boleto']['orders_share_pct']}% | {brl(PAY['boleto']['avg_order_value_brl'])} |
| Voucher | {PAY['voucher']['orders_share_pct']}% | {brl(PAY['voucher']['avg_order_value_brl'])} |
| Debit card | {PAY['debit_card']['orders_share_pct']}% | {brl(PAY['debit_card']['avg_order_value_brl'])} |""")

code("""pay = valid.dropna(subset=["main_payment_type"])
pay = pay[pay["main_payment_type"] != "not_defined"]
pay_table = pay.groupby("main_payment_type").agg(
    orders=("order_id", "count"),
    share_pct=("order_id", lambda s: len(s) / len(pay) * 100),
    avg_order_value=("paid_value", "mean"),
    avg_installments=("installments", "mean"),
).round(1).sort_values("orders", ascending=False)
pay_table""")

code("""cc = pay[pay["main_payment_type"] == "credit_card"]
print(f"credit card orders                 : {len(cc):,}")
print(f"paid in installments (>1 part)     : {(cc['installments'] > 1).mean() * 100:.1f}%")
print(f"paid in 8 or more parts            : {(cc['installments'] >= 8).mean() * 100:.1f}%")
print(f"avg value, paid at once            : R$ {cc[cc['installments'] == 1]['paid_value'].mean():,.2f}")
print(f"avg value, paid in installments    : R$ {cc[cc['installments'] > 1]['paid_value'].mean():,.2f}")""")

code("""Image("charts/payment_types.png")""")

md(f"""The lesson is simple and strong: **when people can pay slowly, they
buy bigger.** An order paid in parts is worth **{brl(CC['avg_value_installments_brl'])}**
on average, against **{brl(CC['avg_value_1_installment_brl'])}** for a
one-time card payment — almost double. And {CC['pct_8plus_installments']}%
of card buyers split into 8 or more parts. Credit access is not a side
detail here; it is a sales tool.""")

# ---------------------------------------------------------------- Q4 trend + states
md(f"""## Question 4 — How did sales grow, and where do buyers live?

The marketplace grew fast. In **{F['trend_first_month']['month']}** it took
only **{F['trend_first_month']['orders']} orders**. By
**{F['peak_month']['month']}** — the Black Friday month — it took
**{F['peak_month']['orders']:,} orders** and {brl(F['peak_month']['revenue'])}
in product sales. In {F['trend_last_month']['month']}, the last full month,
it was still at {F['trend_last_month']['orders']:,} orders.""")

code("""trend = (valid.groupby("purchase_month")
         .agg(orders=("order_id", "count"), revenue=("items_price", "sum")))
trend = trend.loc["2017-01":"2018-08"]
trend.head(3)""")

code("""%matplotlib inline
fig, ax1 = plt.subplots(figsize=(10, 5))
ax1.bar(trend.index, trend["orders"], color="#2563eb", alpha=0.85)
ax1.set_ylabel("Orders")
ax1.tick_params(axis="x", rotation=60)
ax2 = ax1.twinx()
ax2.plot(trend.index, trend["revenue"] / 1e6, color="#f97316", marker="o", linewidth=2)
ax2.set_ylabel("Revenue (million R$)")
ax1.set_title("Orders and revenue by month")
plt.tight_layout()
plt.show()""")

code("""states = (valid.groupby("customer_state")
          .agg(orders=("order_id", "count"), revenue=("items_price", "sum"))
          .sort_values("revenue", ascending=False).head(10))
states["revenue"] = states["revenue"].round(2)
states""")

code("""Image("charts/top_states.png")""")

md(f"""One state runs the show: **SP (São Paulo)** brings
**{F['top_state_share_pct']}% of all revenue** with
{STATES['SP']['orders']:,} orders. The next states, RJ and MG, are far
behind. Protecting delivery quality in SP matters more than anywhere
else — and the rest of the country is the growth space.""")

# ---------------------------------------------------------------- Q5 repeat
md(f"""## Question 5 — Do customers come back?

This is the sad number of the project. Out of
**{F['unique_customers']:,} different customers**, only
**{F['pct_customers_repeat']}% ever placed a second order.**
{F['pct_customers_one_order']}% bought once and never returned. The most
loyal customer in the whole data placed {F['max_orders_one_customer']} orders.

The marketplace is good at winning new customers. It is not good at
keeping them.""")

code("""per_customer = df.groupby("customer_unique_id")["order_id"].count()
print(f"unique customers          : {len(per_customer):,}")
print(f"ordered exactly once      : {(per_customer == 1).mean() * 100:.1f}%")
print(f"ordered 2 or more times   : {(per_customer >= 2).mean() * 100:.1f}%")
print(f"most orders by one person : {per_customer.max()}")""")

# ---------------------------------------------------------------- Q6 freight
md(f"""## Question 6 — How much of the basket goes to delivery?

Every order pays freight (delivery charge) on top of the product price.
Across the whole marketplace, freight adds up to
**{F['freight_total_share_pct']}% of the product value**. But averages
hide the pain: per order, the average share is
**{F['avg_freight_share_per_order_pct']}%**, because small orders carry
heavy delivery charges. In **{F['pct_orders_freight_over_30pct']}% of
orders, the delivery charge is more than 30% of what the product itself
costs.**""")

code("""fr = (valid.groupby("main_category")
      .agg(freight=("freight", "sum"), price=("items_price", "sum"),
           orders=("order_id", "count")))
fr = fr[fr["orders"] >= 1000]
fr["freight_share_pct"] = (fr["freight"] / fr["price"] * 100).round(1)
fr.sort_values("freight_share_pct", ascending=False)""")

code("""Image("charts/freight_share.png")""")

md(f"""Heavy and costly-to-move things suffer most:
**{cat(FRE_HI[0][0])}** buyers pay {FRE_HI[0][1]}% extra in delivery,
and **{cat(FRE_HI[1][0])}** {FRE_HI[1][1]}%. Remember the worst-rated
category, {cat(WORST[0][0])}? Its freight share is {FRE_HI[2][1]}% — high
delivery cost and bad reviews in the same place. At the other end,
**{cat(FRE_LO[0][0])}** adds only {FRE_LO[0][1]}% — costly products carry
their delivery charge easily.""")

# ---------------------------------------------------------------- SQL
md("""## The same questions in SQL

Charts are nice, but a data analyst must also speak SQL. `analysis.py`
built a small SQLite database (`data/olist.sqlite`) with the raw tables
plus my joined table. Here are the main questions again as SQL queries
with real joins.""")

code("""con = sqlite3.connect("data/olist.sqlite")
# one index on the reviews table - the "latest review per order"
# query below is painfully slow without it (I timed it: 90+ seconds
# without the index, under 1 second with it)
con.execute("CREATE INDEX IF NOT EXISTS idx_reviews_order ON reviews(order_id)")
con.commit()
pd.read_sql('''
SELECT i.category,
       COUNT(DISTINCT i.order_id) AS orders,
       ROUND(SUM(i.price), 2)     AS revenue
FROM order_items i
JOIN orders o ON o.order_id = i.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY i.category
ORDER BY revenue DESC
LIMIT 5
''', con)""")

code("""pd.read_sql('''
WITH latest AS (
    SELECT r.order_id, r.review_score
    FROM reviews r
    WHERE r.review_creation_date = (
        SELECT MAX(review_creation_date) FROM reviews
        WHERE order_id = r.order_id)
)
SELECT CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date
            THEN 'On time or early' ELSE 'Late' END AS delivery,
       COUNT(*)              AS orders,
       ROUND(AVG(l.review_score), 2) AS avg_review
FROM orders o
JOIN latest l ON l.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY delivery
''', con)""")

code("""pd.read_sql('''
SELECT substr(o.order_purchase_timestamp, 1, 7) AS month,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(SUM(i.price), 2)     AS revenue
FROM orders o
JOIN order_items i ON i.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY month
ORDER BY month
LIMIT 8
''', con)""")

code("""pd.read_sql('''
SELECT c.customer_state,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(SUM(i.price), 2)     AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items i ON i.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY c.customer_state
ORDER BY revenue DESC
LIMIT 5
''', con)""")

code("""pd.read_sql('''
SELECT payment_type,
       COUNT(DISTINCT order_id)   AS orders,
       ROUND(SUM(payment_value), 2) AS total_paid,
       ROUND(AVG(payment_installments), 1) AS avg_installments
FROM payments
GROUP BY payment_type
ORDER BY total_paid DESC
''', con)""")

code("""pd.read_sql('''
SELECT COUNT(*) AS customers_with_2plus_orders
FROM (
    SELECT customer_unique_id
    FROM orders_analysis
    GROUP BY customer_unique_id
    HAVING COUNT(*) >= 2
)
''', con)""")

# ---------------------------------------------------------------- findings + actions
md(f"""## What I found — the short version

1. **Late delivery is rare but deadly.** Only {F['pct_delivered_late']}% of
   orders were late, yet late orders score **{F['avg_review_late']}** stars
   against **{F['avg_review_on_time']}** for on-time ones. At 8+ days
   late, the average falls to **{F['very_late_avg_review']}** and
   {B['8+ days late']['share_1star_pct']}% of buyers give 1 star.
2. **The promise matters more than the speed.** Average delivery takes
   {F['avg_delivery_days']} days, but {B['Early or on time']['share_pct']}% of orders
   still beat the promised date — and those customers give 5 stars
   {F['share_5star_on_time_pct']}% of the time.
3. **Installments sell bigger baskets.** {PAY['credit_card']['orders_share_pct']}%
   of orders are paid by credit card, {CC['pct_paid_in_installments']}% of
   those in parts. An order paid in parts is worth
   {brl(CC['avg_value_installments_brl'])} against
   {brl(CC['avg_value_1_installment_brl'])} paid at once.
4. **One state carries the business.** SP (São Paulo) alone is
   {F['top_state_share_pct']}% of the {brl_m(F['total_revenue_brl'])} in
   product sales.
5. **Almost nobody returns.** Only {F['pct_customers_repeat']}% of
   customers ever ordered twice.
6. **Freight quietly eats small baskets.** In
   {F['pct_orders_freight_over_30pct']}% of orders, delivery costs more
   than 30% of the product price. The worst-rated category
   ({cat(WORST[0][0])}, {WORST[0][1]['avg_review']} stars) is also in the
   highest-freight group at {FRE_HI[2][1]}%.

## What the business should do

1. **Fix the promise before the speed.** Set honest delivery dates at
   checkout — a date you can beat beats a fast date you miss. And tell
   the customer early when a delay is coming; a warned customer is less
   angry than a surprised one.
2. **Save the very late orders first.** The {B['8+ days late']['orders']:,}
   orders that ran 8+ days late are where the 1-star reviews are born.
   A quick support message and a small coupon for this group is cheap
   next to the damage of a public bad review.
3. **Look hard at {cat(WORST[0][0])}.** Worst reviews ({WORST[0][1]['avg_review']})
   plus a {FRE_HI[2][1]}% freight share points at product quality,
   packing or the delivery partner for large furniture — not at price.
4. **Push installments on the product page.** Show the "per month"
   price next to the full price. Buyers who split payments spend
   almost double.
5. **Protect SP, grow the rest.** SP is {F['top_state_share_pct']}% of
   revenue, so a delivery problem there is a company problem. Other
   states are the growth space.
6. **Bring buyers back.** With a {F['pct_customers_repeat']}% repeat
   rate, even a small rise is big money. The happiest group to start
   with: on-time buyers who gave 5 stars ({F['share_5star_on_time_pct']}%
   of on-time orders). A post-delivery coupon for them is an easy first step.
7. **Set a free-freight line a little above the average basket.** When
   delivery costs 30%+ of the product price, buyers hesitate. A
   threshold gives them a reason to add one more item instead of
   leaving.

## Honest limits of this project

- The data **ends in 2018** — it shows how this marketplace behaved
  then, not today.
- This is **Brazil, not India**: money is in Brazilian real (R$),
  boleto is a Brazilian payment method, and delivery distances are huge.
- {F['orders_with_review_pct']}% of the orders in my joined table have a
  review, but {F['table_rows']['orders'] - F['joined_rows']:,} orders had no item rows and
  could not be used at all.
- "The category of an order" is my own simple rule (category of the
  most costly item). An order with items from two categories counts
  once.

## How to run this project

```bash
python download_data.py   # 1. pull the real tables from GitHub
python analysis.py        # 2. join, clean, findings.json, charts, SQLite db
python build_notebook.py  # 3. rebuild and run this notebook
```

*Data: Olist, CC BY-NC-SA 4.0 — https://github.com/olist/work-at-olist-data.
Code: MIT, © 2026 Vivek Saini.*""")

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3"},
}

out = os.path.join(HERE, "olist_analysis.ipynb")
nbf.write(nb, out)
print("notebook written:", out, len(cells), "cells")

client = NotebookClient(nb, timeout=600, kernel_name="python3",
                        resources={"metadata": {"path": HERE}})
client.execute()
nbf.write(nb, out)
errors = [
    o for c in nb.cells if c.cell_type == "code"
    for o in c.get("outputs", []) if o.get("output_type") == "error"
]
print("executed. error outputs:", len(errors))
