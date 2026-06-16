import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


# -----------------------------
# CONNECTION
# -----------------------------
def get_connection():
    # credentials come from the .env file - never hard-coded
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT", "5432")
    )


# -----------------------------
# LOOKUP HELPERS
# -----------------------------
def get_size_id(cur, size_name):
    # look up the UUID for a size name e.g. "Large" → some UUID
    # returns None if the size isn't in the lookup table
    cur.execute("SELECT id FROM sizes WHERE name = %s", (size_name,))
    result = cur.fetchone()
    return result[0] if result else None


def get_flavour_id(cur, flavour_name):
    # look up the UUID for a flavour name e.g. "Hazelnut" → some UUID
    # returns None for unflavoured drinks (flavour_name will be None)
    if not flavour_name:
        return None
    cur.execute("SELECT id FROM flavours WHERE name = %s", (flavour_name,))
    result = cur.fetchone()
    return result[0] if result else None


# -----------------------------
# LOAD ORDERS
# -----------------------------
def load_orders(cur, orders):
    # insert one row per customer visit into the orders table
    # ON CONFLICT DO NOTHING means re-running the pipeline won't duplicate data
    for order in orders:
        cur.execute("""
            INSERT INTO orders (id, branch_name, customer_id, order_time, payment_method, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            order["id"],
            order["branch_name"],
            order["customer_id"],
            order["order_time"],
            order["payment_method"],
            order["total_amount"]
        ))

    print(f"Loaded {len(orders)} orders")


# -----------------------------
# LOAD ORDER ITEMS
# -----------------------------
def load_order_items(cur, order_items):
    # insert one row per distinct item
    # look up the size and flavour UUIDs from the lookup tables before inserting
    for item in order_items:
        size_id = get_size_id(cur, item["size"])
        flavour_id = get_flavour_id(cur, item["flavour"])

        cur.execute("""
            INSERT INTO order_items (id, order_id, item_name, size_id, flavour_id, price, quantity)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            item["id"],
            item["order_id"],
            item["item_name"],
            size_id,
            flavour_id,
            item["price"],
            item["quantity"]
        ))

    print(f"Loaded {len(order_items)} order items")


# -----------------------------
# MAIN LOAD FUNCTION
# -----------------------------
def load_to_database(orders, order_items):
    conn = get_connection()
    cur = conn.cursor()

    # load orders first, then items (items reference orders)
    load_orders(cur, orders)
    load_order_items(cur, order_items)

    conn.commit()
    cur.close()
    conn.close()

    print("Database load complete")