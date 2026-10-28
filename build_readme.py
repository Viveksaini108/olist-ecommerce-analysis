"""
Build README.md from findings.json so every number in the README
is the real number from the analysis run.

Run:  python build_readme.py
"""

import json
import os

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
TR = F["table_rows"]

top_cat_rows = "\n".join(
    f"| {i+1} | {cat(k)} | {brl(v)} |" for i, (k, v) in enumerate(TOPCAT)
)
worst_rows = "\n".join(
    f"| {cat(k)} | {v['avg_review']} | {v['orders']:,} |" for k, v in WORST
)
best_rows = "\n".join(
    f"| {cat(k)} | {v['avg_review']} | {v['orders']:,} |" for k, v in BEST
)
bucket_rows = "\n".join(
    f"| {b} | {v['orders']:,} | {v['avg_review']} | {v['share_5star_pct']}% | {v['share_1star_pct']}% |"
    for b, v in B.items()
)

README = f"""# Olist E-Commerce Analysis — What Makes Customers Happy or Angry? 🇧🇷

Hi, I'm **Vivek Saini** — a Data Analyst from Meerut, India. This is my
third portfolio project. My first two projects used data I created
myself. This time I wanted the real thing.

So this project uses **real data from Olist, a real marketplace in
Brazil** — {TR['orders']:,} real orders placed between 2016 and 2018,
with what people bought, how they paid, when the parcel reached them,
and the review score they gave after delivery.

> 📓 **Start here:** the full analysis, step by step with charts, SQL
> and commentary, is in **[olist_analysis.ipynb](olist_analysis.ipynb)**.
> The scripts below reproduce everything.

## The question I wanted to answer

> **What makes a customer happy or angry on a marketplace?**

My guess before I touched the data: delivery. A parcel that comes late
should make people angry, and the review score should show it. I tested
that guess, and five more questions:

1. How late are deliveries — and does being late actually hurt the review score?
2. Which product categories earn the most, and which get the best and worst reviews?
3. How do customers pay? Does paying in parts (installments) change how much they spend?
4. How did sales grow month by month, and which states buy the most?
5. Do customers ever come back for a second order?
6. How much of the basket price is eaten by the delivery charge (freight)?

## About the data — it is real

This dataset is **published by Olist itself** on GitHub
([olist/work-at-olist-data](https://github.com/olist/work-at-olist-data))
for public use, under the **CC BY-NC-SA 4.0** licence. The data belongs
to Olist. Only the code in this project is mine.

The `download_data.py` script pulls the tables straight from that page —
no copy-paste, no made-up rows. One honest note: the data was shared by
Olist for a hiring exercise, so customer and seller names are not in it.
The orders, prices, payments, dates and review scores are real.

## The dataset at a glance

| Table | Rows | What it holds |
|---|---|---|
| Orders | {TR['orders']:,} | status, purchase time, promised and real delivery dates |
| Order items | {TR['order_items']:,} | one row per product: price, delivery charge |
| Payments | {TR['payments']:,} | card / boleto / voucher, installments, amount |
| Reviews | {TR['reviews']:,} | the 1–5 star score and comment dates |
| Customers | {TR['customers']:,} | buyer city and state |
| Products | {TR['products']:,} | category (in Portuguese, translated by me) |
| Sellers | {TR['sellers']:,} | seller city and state |

After cleaning and joining: **{F['joined_rows']:,} orders** in one
analysis table ({F['table_rows']['orders'] - F['joined_rows']:,} orders had no items at all and
could not be used). Delivered orders: {F['delivered_orders']:,}. Period:
{F['date_min']} to {F['date_max']} — nearly all sales fall in 2017–2018.

**Cleaning problems I had to fix** (all real): cancelled and
"unavailable" orders mixed in with delivered ones, delivered orders with
no delivery date, a few orders reviewed twice (I kept the latest
review), category names in Portuguese, and orders with items from more
than one category (my rule: the order's category = the category of its
most costly item).

## What I found

### 1. Late delivery is rare — but it kills the review score

Only **{F['pct_delivered_late']}%** of delivered orders arrived after
the promised date. The average delivery took {F['avg_delivery_days']}
days, and {B['Early or on time']['share_pct']}% of orders still beat the
promise. But look at what happens when the promise breaks:

| Delivery | Orders | Avg review | 5-star | 1-star |
|---|---|---|---|---|
{bucket_rows}

On-time orders average **{F['avg_review_on_time']} stars**. Late orders
average **{F['avg_review_late']}**. At 8+ days late, the average is
**{F['very_late_avg_review']}** and {B['8+ days late']['share_1star_pct']}%
of buyers give the worst score. A delay of 1–3 days costs a little.
Past a week, the customer is gone.

**My reading:** the promise matters more than the speed. Olist is slow
but mostly honest — and honest keeps customers happy.

![Delivery delay vs review score](charts/delivery_delay_vs_review.png)

### 2. Categories: money and happiness are different things

Total product sales in the data: **{brl_m(F['total_revenue_brl'])}**.

| # | Top categories by revenue | Sales |
|---|---|---|
{top_cat_rows}

Worst reviews (categories with 300+ reviewed orders):

| Category | Avg review | Orders |
|---|---|---|
{worst_rows}

Best reviews:

| Category | Avg review | Orders |
|---|---|---|
{best_rows}

Two things stood out. **{cat(WORST[0][0])}** is the worst-rated
category ({WORST[0][1]['avg_review']} stars) — heavy furniture is easy
to damage and slow to move. And **{cat(TOPCAT[2][0])}**, the
third-biggest earner at {brl(TOPCAT[2][1])}, scores only
{WORST[3][1]['avg_review']} — a small quality fix there moves a lot of
money. Books make people happiest: **{cat(BEST[0][0])}** at
{BEST[0][1]['avg_review']} stars.

![Reviews by category](charts/review_by_category.png)

### 3. How customers pay — and why installments matter

| Payment type | Share of orders | Avg order value | Avg installments |
|---|---|---|---|
| Credit card | {PAY['credit_card']['orders_share_pct']}% | {brl(PAY['credit_card']['avg_order_value_brl'])} | {PAY['credit_card']['avg_installments']} |
| Boleto (bank slip) | {PAY['boleto']['orders_share_pct']}% | {brl(PAY['boleto']['avg_order_value_brl'])} | {PAY['boleto']['avg_installments']} |
| Voucher | {PAY['voucher']['orders_share_pct']}% | {brl(PAY['voucher']['avg_order_value_brl'])} | {PAY['voucher']['avg_installments']} |
| Debit card | {PAY['debit_card']['orders_share_pct']}% | {brl(PAY['debit_card']['avg_order_value_brl'])} | {PAY['debit_card']['avg_installments']} |

Credit card is king. And most card buyers split the bill:
**{CC['pct_paid_in_installments']}% pay in installments**, and
{CC['pct_8plus_installments']}% split into 8 or more parts. It changes
what they buy — an order paid in parts is worth
**{brl(CC['avg_value_installments_brl'])}** on average, against
**{brl(CC['avg_value_1_installment_brl'])}** paid at once. Almost double.
Easy credit is not a side detail in Brazil; it is a sales tool.

![Payment types](charts/payment_types.png)

### 4. Growth, and the one state that runs the show

In {F['trend_first_month']['month']} the marketplace took
{F['trend_first_month']['orders']} orders. By
**{F['peak_month']['month']}** — the Black Friday month — it took
**{F['peak_month']['orders']:,} orders** and
{brl(F['peak_month']['revenue'])} in product sales. In
{F['trend_last_month']['month']}, the last full month, it held at
{F['trend_last_month']['orders']:,} orders.

![Orders and revenue by month](charts/monthly_orders_revenue.png)

And the map is not even close: **SP (São Paulo) alone brings
{F['top_state_share_pct']}% of all revenue** ({STATES['SP']['orders']:,}
orders, {brl(STATES['SP']['revenue'])}). RJ is second with
{brl(STATES['RJ']['revenue'])}. Protect delivery quality in SP first —
a problem there is a company problem. The rest of the country is the
growth space.

![Top states by revenue](charts/top_states.png)

### 5. Almost nobody comes back

Out of **{F['unique_customers']:,} different customers**, only
**{F['pct_customers_repeat']}% ever placed a second order.**
{F['pct_customers_one_order']}% bought once and never returned. The
most loyal customer in the data placed {F['max_orders_one_customer']}
orders. The marketplace is good at winning new customers. It is not
good at keeping them.

### 6. Freight quietly eats small baskets

Across the whole marketplace, delivery charges add up to
**{F['freight_total_share_pct']}% of the product value**. Per order the
average share is **{F['avg_freight_share_per_order_pct']}%**, because
small orders carry heavy delivery charges. In
**{F['pct_orders_freight_over_30pct']}% of orders, the delivery charge
is more than 30% of what the product itself costs.**

The hardest-hit categories are **{cat(FRE_HI[0][0])}**
({FRE_HI[0][1]}%) and **{cat(FRE_HI[1][0])}** ({FRE_HI[1][1]}%). Note
that {cat(WORST[0][0])} — the worst-rated category — sits in this
high-freight group too ({FRE_HI[2][1]}%): high delivery cost and angry
customers in the same place. At the easy end, **{cat(FRE_LO[0][0])}**
adds only {FRE_LO[0][1]}%, because costly products carry their delivery
charge well.

![Freight share by category](charts/freight_share.png)

## What the business should do

1. **Fix the promise before the speed.** Honest delivery dates at
   checkout — a date you can beat beats a fast date you miss. And warn
   the customer early when a delay is coming; a warned customer is
   less angry than a surprised one.
2. **Save the very late orders first.** The
   {B['8+ days late']['orders']:,} orders that ran 8+ days late are
   where the 1-star reviews are born ({B['8+ days late']['share_1star_pct']}%
   gave 1 star). A fast support reply and a small coupon for this group
   is cheap next to a public bad review.
3. **Look hard at {cat(WORST[0][0])}.** Worst reviews
   ({WORST[0][1]['avg_review']} stars) plus a {FRE_HI[2][1]}% freight
   share points at product quality, packing or the delivery partner for
   large furniture — not at price.
4. **Show the per-month price on product pages.** Buyers who pay in
   parts spend almost double ({brl(CC['avg_value_installments_brl'])}
   vs {brl(CC['avg_value_1_installment_brl'])}). Make the installment
   price as visible as the full price.
5. **Protect SP, grow the rest.** SP is {F['top_state_share_pct']}% of
   revenue. Other states are where the growth is.
6. **Bring buyers back.** With a {F['pct_customers_repeat']}% repeat
   rate, even a small rise is big money. Start with the happiest
   group — on-time buyers, who give 5 stars
   {F['share_5star_on_time_pct']}% of the time — and give them a reason
   to return, like a post-delivery coupon.
7. **Set a free-freight line a little above the average basket.** When
   delivery costs 30%+ of the product price, buyers hesitate. A
   threshold turns that pause into "add one more item".

## Honest limits

- The data **ends in 2018**. It shows how this marketplace behaved
  then, not how it behaves today.
- This is **Brazil, not India**: money is in Brazilian real (R$),
  boleto is a Brazilian bank slip, distances are huge, and the average
  delivery time of {F['avg_delivery_days']} days reflects that.
- {F['orders_with_review_pct']}% of orders in my joined table have a
  review score. The rest could not be used for review questions.
- "The category of an order" is my simple rule (most costly item).
  Orders with items from two categories count once.

## How to run it

```bash
python download_data.py   # 1. pull the real tables from Olist's GitHub
python analysis.py        # 2. join + clean, findings.json, 6 charts, SQLite db
python build_notebook.py  # 3. rebuild and run the notebook
```

Then open `olist_analysis.ipynb` to read the full story. The notebook
also runs the main questions again in **SQL** (SQLite) — 6 queries with
joins across orders, items, payments, reviews and customers.

## Tools used

Python · pandas · SQL (SQLite) · matplotlib · Jupyter

---

*Data: **Olist** — real Brazilian marketplace data, published by Olist
under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/),
source: https://github.com/olist/work-at-olist-data*

*Code: MIT licence, © 2026 Vivek Saini — see [LICENSE](LICENSE).*
"""

with open(os.path.join(HERE, "README.md"), "w") as fh:
    fh.write(README)
print("README.md written,", len(README), "chars")
