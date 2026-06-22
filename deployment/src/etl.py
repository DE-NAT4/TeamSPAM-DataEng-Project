import csv
import uuid
import hashlib
import logging
from datetime import datetime
from collections import defaultdict

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def extract(body_text):
    """
    Parses raw CSV text into a list of dictionaries.

    Args:
        body_text: CSV file content as a list of strings (one per line),
                   as returned by s3_utils.load_file().

    Returns:
        List of dictionaries, one per row. Column names are stripped of
        leading/trailing whitespace (skipinitialspace=True).
        Columns: date, time, location, customer_name, items_total,
                 amount_paid, payment_method, card_number
    """
    LOGGER.info('extract: starting')

    reader = csv.DictReader(body_text, skipinitialspace=True)
    data = [row for row in reader]

    LOGGER.info(f'extract: done: rows={len(data)}')
    return data


def _hash_customer(name):
    # SHA-256 hash of the customer name → deterministic UUID.
    # Same person always maps to the same UUID so we can still spot regulars,
    # but the real name cannot be recovered from the hash (GDPR-friendly).
    hashed = hashlib.sha256(name.strip().lower().encode()).digest()
    return str(uuid.UUID(bytes=hashed[:16]))


def _parse_item(raw_item):
    # Price is always the rightmost ' - ' segment.
    # e.g. 'Large Speciality Tea - English breakfast - 1.60'
    #   → name='Large Speciality Tea - English breakfast', price=1.60
    name, price_str = raw_item.strip().rsplit(' - ', 1)
    name = name.strip()
    size = name.split(' ', 1)[0]  # first word is always the size

    # Flavour only exists when 'Flavoured' appears AND there's a ' - ' separator
    # e.g. 'Regular Flavoured iced latte - Hazelnut' → flavour='Hazelnut'
    flavour = None
    if 'Flavoured' in name and ' - ' in name:
        flavour = name.rsplit(' - ', 1)[1].strip()

    return {
        'item_name': name,
        'size': size,
        'flavour': flavour,
        'price': float(price_str.strip()),
    }


def transform(data):
    """
    Cleans and reshapes raw CSV rows into orders and order_items ready for Redshift.

    Transformations applied:
        - card_number is dropped (PCI compliance - never stored)
        - customer_name is replaced with a SHA-256 UUID hash (GDPR)
        - date + time columns are merged into a single TIMESTAMP
        - items_total string is split into individual order_item rows
        - duplicate items within one order are collapsed into quantity > 1

    Args:
        data: List of row dictionaries from extract().

    Returns:
        Tuple of (orders, order_items):
            orders      - list of dicts with id, branch_name, customer_id,
                          order_time, payment_method, total_amount
            order_items - list of dicts with id, order_id, item_name, size,
                          flavour, price, quantity
    """
    LOGGER.info(f'transform: starting: rows={len(data)}')
    orders = []
    order_items = []

    for row in data:
        order_id = str(uuid.uuid4())

        date_str = row['date'].strip()
        time_str = row['time'].strip()
        order_time = datetime.strptime(f'{date_str} {time_str}', '%d/%m/%Y %H:%M')

        orders.append({
            'id': order_id,
            'branch_name': row['location'].strip(),
            'customer_id': _hash_customer(row['customer_name']),
            'order_time': order_time.strftime('%Y-%m-%d %H:%M:%S'),
            'payment_method': row['payment_method'].strip(),
            'total_amount': float(row['amount_paid'].strip()),
        })

        raw_items = row.get('items_total', '').strip()
        if not raw_items:
            continue

        # Collapse duplicate items in the same order into a single row with quantity > 1
        item_counts = defaultdict(int)
        item_details = {}

        for raw_item in raw_items.split(','):
            raw_item = raw_item.strip()
            if ' - ' not in raw_item:
                continue

            parsed = _parse_item(raw_item)
            key = (parsed['item_name'], parsed['size'], parsed['flavour'], parsed['price'])
            item_counts[key] += 1
            item_details[key] = parsed

        for key, quantity in item_counts.items():
            details = item_details[key]
            order_items.append({
                'id': str(uuid.uuid4()),
                'order_id': order_id,
                'item_name': details['item_name'],
                'size': details['size'],
                'flavour': details['flavour'],
                'price': details['price'],
                'quantity': quantity,
            })

    LOGGER.info(f'transform: done: orders={len(orders)}, order_items={len(order_items)}')
    return orders, order_items
