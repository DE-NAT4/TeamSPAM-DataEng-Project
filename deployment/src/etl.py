from utils import transform
import csv
from datetime import datetime
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

header_fields = [
    "date",
    "time",
    "location",
    "customer_name",
    "items_total",
    "amount_paid",
    "payment_method",
    "card_number"
]

def extract(body_text):
    LOGGER.info('extract: starting')
    reader = csv.DictReader(
        body_text,
        fieldnames=header_fields,
        delimiter=',',
    )

    # skip header row
    next(reader)

    data = [row for row in reader]
    # e.g., data = [{'Name': 'Alice', 'Age': '30', 'Role': 'Engineer'}, {'Name': 'Bob', 'Age': '25', 'Role': 'Designer'}]

    LOGGER.info(f'extract: done: rows={len(data)}')
    return data


def clean_data(rows):
    orders, order_items = transform.transform_data(rows)
    print(f"Transformed into {len(orders)} orders and {len(order_items)} order items")
    return orders, order_items