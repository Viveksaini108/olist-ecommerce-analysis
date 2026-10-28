"""
Download the real Olist e-commerce datasets.

The data comes from Olist, a real Brazilian marketplace. Olist published
these tables on GitHub for public use (licence: CC BY-NC-SA 4.0).
This project does NOT create or fake any data - every row is real.

Run:  python download_data.py
The script is safe to run again - files that are already downloaded
are skipped.
"""

import csv
import os
import urllib.request

BASE_URL = (
    "https://raw.githubusercontent.com/olist/work-at-olist-data/"
    "master/datasets/"
)

FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("Downloading real Olist data from GitHub...\n")
    for name in FILES:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            print(f"  already have it, skipping: {name}")
        else:
            url = BASE_URL + name
            print(f"  downloading: {name}")
            urllib.request.urlretrieve(url, path)
        # count real records with the csv module - review comments can
        # contain line breaks, so counting raw lines gives a wrong number
        with open(path, encoding="utf-8") as fh:
            rows = sum(1 for _ in csv.reader(fh)) - 1
        print(f"    -> {rows:,} rows")
    print("\nDone. All files are in the data/ folder.")
    print("Source: Olist (Brazil) - https://github.com/olist/work-at-olist-data")
    print("Licence: CC BY-NC-SA 4.0 (data belongs to Olist)")


if __name__ == "__main__":
    main()
