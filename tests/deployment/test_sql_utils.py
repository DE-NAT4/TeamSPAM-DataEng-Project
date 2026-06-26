"""
Tests for deployment/src/utils/sql_utils.py

sql_utils handles all Redshift interactions:
  - create_db_tables()     — CREATE TABLE IF NOT EXISTS for all four tables
  - seed_lookup_tables()   — insert sizes and flavours if not already present
  - save_data_in_db()      — bulk-insert orders and order_items

We use MagicMock for the cursor and connection so no real Redshift (or even
psycopg2) is needed.  The tests verify that the correct SQL is executed and
that edge cases (unknown size, unflavoured item, empty batch) are handled.
"""
import pytest
from unittest.mock import MagicMock, call, patch
from utils import sql_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cursor(size_rows=None, flavour_rows=None, count_return=0):
    """
    Return a mock cursor pre-configured to handle the SELECT queries that
    seed_lookup_tables and save_data_in_db make for lookups.

    size_rows / flavour_rows: list of (name, id) tuples for _load_*_lookup
    count_return: what COUNT(*) returns (0 → not present, 1 → already seeded)
    """
    cursor = MagicMock()

    # Default: nothing seeded yet (COUNT returns 0)
    cursor.fetchone.return_value = (count_return,)

    # _load_size_lookup and _load_flavour_lookup call fetchall()
    size_rows = size_rows or [("Large", "uuid-large"), ("Regular", "uuid-regular")]
    flavour_rows = flavour_rows or [
        ("Hazelnut", "uuid-hazelnut"), ("Caramel", "uuid-caramel"),
        ("Vanilla", "uuid-vanilla"), ("Gingerbread", "uuid-ginger"),
        ("Peppermint", "uuid-pep"), ("Cinnamon", "uuid-cin"),
    ]
    cursor.fetchall.side_effect = [size_rows, flavour_rows]

    return cursor


def make_connection():
    return MagicMock()


def make_order(**overrides):
    base = {
        "id": "order-uuid-1",
        "branch_name": "Leeds",
        "customer_id": "customer-hash",
        "order_time": "2025-03-28 09:00:00",
        "payment_method": "CARD",
        "total_amount": 5.50,
    }
    base.update(overrides)
    return base


def make_item(**overrides):
    base = {
        "id": "item-uuid-1",
        "order_id": "order-uuid-1",
        "item_name": "Large Chai latte",
        "size": "Large",
        "flavour": None,
        "price": 2.60,
        "quantity": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# create_db_tables
# ---------------------------------------------------------------------------

def test_create_db_tables_executes_four_create_statements():
    # There are four tables: sizes, flavours, orders, order_items
    conn = make_connection()
    cursor = MagicMock()
    sql_utils.create_db_tables(conn, cursor)
    assert cursor.execute.call_count == 4


def test_create_db_tables_commits():
    # Changes must be committed so they persist if Lambda is reused
    conn = make_connection()
    cursor = MagicMock()
    sql_utils.create_db_tables(conn, cursor)
    conn.commit.assert_called_once()


def test_create_db_tables_raises_on_cursor_error():
    # If Redshift rejects a CREATE statement the error must propagate,
    # not be swallowed — so the Lambda can log it and fail visibly
    conn = make_connection()
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("Redshift error")
    with pytest.raises(Exception, match="Redshift error"):
        sql_utils.create_db_tables(conn, cursor)


# ---------------------------------------------------------------------------
# seed_lookup_tables
# ---------------------------------------------------------------------------

def test_seed_inserts_all_sizes_when_table_empty():
    # When COUNT(*) returns 0 for each size, we expect two INSERT calls
    conn = make_connection()
    cursor = MagicMock()
    # Return 0 for every COUNT query (nothing seeded yet)
    cursor.fetchone.return_value = (0,)

    sql_utils.seed_lookup_tables(conn, cursor)

    insert_calls = [c for c in cursor.execute.call_args_list
                    if "INSERT INTO sizes" in str(c)]
    assert len(insert_calls) == len(sql_utils.SIZES)


def test_seed_inserts_all_flavours_when_table_empty():
    conn = make_connection()
    cursor = MagicMock()
    cursor.fetchone.return_value = (0,)

    sql_utils.seed_lookup_tables(conn, cursor)

    insert_calls = [c for c in cursor.execute.call_args_list
                    if "INSERT INTO flavours" in str(c)]
    assert len(insert_calls) == len(sql_utils.FLAVOURS)


def test_seed_skips_inserts_when_already_seeded():
    # When COUNT(*) returns 1 for every entry, no INSERTs should run
    # This simulates a warm Lambda invocation where tables are already populated
    conn = make_connection()
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)   # already exists

    sql_utils.seed_lookup_tables(conn, cursor)

    insert_calls = [c for c in cursor.execute.call_args_list
                    if "INSERT INTO" in str(c)]
    assert len(insert_calls) == 0


def test_seed_commits():
    conn = make_connection()
    cursor = MagicMock()
    cursor.fetchone.return_value = (0,)
    sql_utils.seed_lookup_tables(conn, cursor)
    conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# save_data_in_db
# ---------------------------------------------------------------------------

def test_save_inserts_correct_number_of_orders():
    conn = make_connection()
    cursor = make_cursor()
    orders = [make_order(id=f"order-{i}") for i in range(3)]
    items = []

    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)

    order_inserts = [c for c in cursor.execute.call_args_list
                     if "INSERT INTO orders" in str(c)]
    assert len(order_inserts) == 3


def test_save_inserts_correct_number_of_order_items():
    conn = make_connection()
    cursor = make_cursor()
    orders = [make_order()]
    items = [make_item(id=f"item-{i}", size="Large", flavour=None) for i in range(4)]

    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)

    item_inserts = [c for c in cursor.execute.call_args_list
                    if "INSERT INTO order_items" in str(c)]
    assert len(item_inserts) == 4


def test_save_resolves_size_id_from_lookup():
    # save_data_in_db loads sizes once then resolves item["size"] → UUID
    # We verify the UUID from our mock lookup is what gets inserted
    conn = make_connection()
    cursor = make_cursor(size_rows=[("Large", "large-uuid"), ("Regular", "regular-uuid")])
    orders = [make_order()]
    items = [make_item(size="Large", flavour=None)]

    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)

    item_insert = next(c for c in cursor.execute.call_args_list
                       if "INSERT INTO order_items" in str(c))
    # The third positional arg in the VALUES tuple is size_id
    args = item_insert[0][1]   # second element of positional args is the params tuple
    assert "large-uuid" in args


def test_save_uses_none_for_unflavoured_item():
    # Items with no flavour must pass NULL (None) for flavour_id, not a string
    conn = make_connection()
    cursor = make_cursor()
    orders = [make_order()]
    items = [make_item(flavour=None)]

    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)

    item_insert = next(c for c in cursor.execute.call_args_list
                       if "INSERT INTO order_items" in str(c))
    args = item_insert[0][1]
    # flavour_id is the 5th param (index 4) — must be None for unflavoured drinks
    assert args[4] is None


def test_save_resolves_flavour_id_for_flavoured_item():
    # For a flavoured item, flavour_id should resolve to the UUID from the lookup
    conn = make_connection()
    cursor = make_cursor(
        flavour_rows=[("Hazelnut", "hazelnut-uuid"), ("Caramel", "caramel-uuid")]
    )
    orders = [make_order()]
    items = [make_item(flavour="Hazelnut")]

    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)

    item_insert = next(c for c in cursor.execute.call_args_list
                       if "INSERT INTO order_items" in str(c))
    args = item_insert[0][1]
    assert args[4] == "hazelnut-uuid"


def test_save_handles_unknown_size_gracefully():
    # If a new size appears that isn't in the lookup table the result is None,
    # not a KeyError crash — the row is still inserted (with a NULL size_id)
    conn = make_connection()
    cursor = make_cursor(size_rows=[("Large", "large-uuid")])  # "Regular" not in lookup
    orders = [make_order()]
    items = [make_item(size="ExtraLarge", flavour=None)]   # unknown size

    # Should not raise
    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", orders, items)


def test_save_empty_orders_and_items():
    # An empty batch must not crash — just commit with no inserts
    conn = make_connection()
    cursor = make_cursor()
    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", [], [])
    conn.commit.assert_called_once()


def test_save_commits():
    conn = make_connection()
    cursor = make_cursor()
    sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", [make_order()], [])
    conn.commit.assert_called_once()


def test_save_raises_on_db_error():
    # A Redshift error during INSERT must propagate so the Lambda can log and retry
    conn = make_connection()
    cursor = make_cursor()

    # Make the INSERT fail after the lookups succeed
    call_count = [0]
    original_execute = cursor.execute

    def execute_side_effect(sql, params=None):
        call_count[0] += 1
        if "INSERT INTO orders" in sql:
            raise Exception("Redshift INSERT error")

    cursor.execute.side_effect = execute_side_effect

    with pytest.raises(Exception, match="Redshift INSERT error"):
        sql_utils.save_data_in_db(conn, cursor, "bucket", "file.csv", [make_order()], [])
