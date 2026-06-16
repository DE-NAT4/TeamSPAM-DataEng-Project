import os
import sys
import csv
import json
import uuid
import hashlib
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# where this file lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# CSV lives two levels up in pipeline/ingestion/sources/
CSV_PATH = os.path.normpath(
    os.path.join(BASE_DIR, "..", "ingestion", "sources", "leedsdata.csv")
)

# transformed output goes back into the same sources folder
OUTPUT_PATH = os.path.normpath(
    os.path.join(BASE_DIR, "..", "ingestion", "sources", "leeds_order.json")
)


# -----------------------------
# HELPERS
# -----------------------------
def hash_customer(name):
    # we don't store the real name - hash it so we can still spot regulars
    # the same name always produces the same UUID, but you can't reverse it back to the name
    hashed = hashlib.sha256(name.strip().lower().encode()).digest()
    return str(uuid.UUID(bytes=hashed[:16]))


def parse_item(raw_item):
    # price is always the very last part after " - "
    # e.g. "Large Chai latte - 2.60" → name="Large Chai latte", price=2.60
    # e.g. "Regular Flavoured iced latte - Hazelnut - 2.75" → name="Regular Flavoured iced latte - Hazelnut", price=2.75
    name, price = raw_item.strip().rsplit(" - ", 1)
    name = name.strip()

    # first word is always the size (Large or Regular)
    size = name.split(" ", 1)[0]

    # flavour only exists if the word "Flavoured" appears in the name
    # if it does, the flavour is the bit after the last " - " in the name
    # e.g. "Regular Flavoured iced latte - Hazelnut" → flavour = "Hazelnut"
    flavour = None
    if "Flavoured" in name and " - " in name:
        flavour = name.rsplit(" - ", 1)[1].strip()

    return {
        "item_name": name,
        "size": size,
        "flavour": flavour,
        "price": float(price.strip())
    }


# -----------------------------
# TRANSFORM
# -----------------------------
def transform_data(rows):
    orders = []
    order_items = []

    for row in rows:
        order_id = str(uuid.uuid4())

        # the CSV has separate date and time columns with a leading space on " time"
        # we combine them into a single timestamp for the database
        date_str = row["date"].strip()
        time_str = row[" time"].strip()
        order_time = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")

        # -------------------------
        # BUILD THE ORDER ROW
        # -------------------------
        orders.append({
            "id": order_id,
            "branch_name": row[" location"].strip(),
            # hash the customer name instead of storing it - GDPR friendly
            # same person will always get the same hash so we can still count their visits
            "customer_id": hash_customer(row[" customer_name"].strip()),
            "order_time": order_time.strftime("%Y-%m-%d %H:%M:%S"),
            "payment_method": row[" payment_method"].strip(),
            "total_amount": float(row[" amount_paid"].strip()),
            # card_number deliberately left out - we don't store sensitive financial data
        })

        # -------------------------
        # BUILD THE ORDER ITEMS
        # -------------------------
        raw_items = row.get(" items_total", "")

        if not raw_items:
            continue

        # if the same item appears more than once in an order we want quantity: 3
        # rather than 3 duplicate rows - so we group by item before appending
        item_counts = defaultdict(int)
        item_details = {}

        for raw_item in raw_items.split(","):
            raw_item = raw_item.strip()

            if " - " not in raw_item:
                continue

            parsed = parse_item(raw_item)

            # the key is everything that makes two items the same
            key = (parsed["item_name"], parsed["size"], parsed["flavour"], parsed["price"])
            item_counts[key] += 1
            item_details[key] = parsed

        for key, quantity in item_counts.items():
            details = item_details[key]
            order_items.append({
                "id": str(uuid.uuid4()),
                "order_id": order_id,
                "item_name": details["item_name"],
                "size": details["size"],
                "flavour": details["flavour"],  # None if the drink isn't flavoured
                "price": details["price"],
                "quantity": quantity
            })

    return orders, order_items


# -----------------------------
# SAVE TO JSON
# -----------------------------
def load_json(data, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# -----------------------------
# SAVE TO CSV
# -----------------------------
def save_to_csv(orders, order_items, output_dir):
    # write orders and order_items as separate CSV files
    os.makedirs(output_dir, exist_ok=True)

    orders_path = os.path.join(output_dir, "orders.csv")
    with open(orders_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
        writer.writeheader()
        writer.writerows(orders)

    items_path = os.path.join(output_dir, "order_items.csv")
    with open(items_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=order_items[0].keys())
        writer.writeheader()
        writer.writerows(order_items)

    print(f"CSV files saved to {output_dir}")



