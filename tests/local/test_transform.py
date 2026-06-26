"""
Tests for pipeline/etl/transform.py  (the local Postgres pipeline version)

Covers three things:
  1. parse_item()      — parses a single item string into a structured dict
  2. hash_customer()   — GDPR-friendly deterministic hashing of customer names
  3. transform_data()  — the full transformation from raw CSV rows to
                         (orders, order_items) ready for the local DB
"""
import pytest
from etl.transform import parse_item, hash_customer, transform_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_row(**overrides):
    """Build a minimal valid CSV row dict, with any field overridable."""
    base = {
        "date": "28/03/2025",
        " time": " 09:00",           # note the leading space — that's how the CSV lands
        " location": " Leeds",
        " customer_name": " Test User",
        " items_total": " Large Chai latte - 2.60",
        " amount_paid": " 2.60",
        " payment_method": " CARD",
        " card_number": " 1234567890",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# parse_item — item string parser
# ---------------------------------------------------------------------------

def test_parse_item_simple():
    # Basic item: "Size Name - price"
    result = parse_item("Large Filter coffee - 1.80")
    assert result["item_name"] == "Large Filter coffee"
    assert result["size"] == "Large"
    assert result["flavour"] is None
    assert result["price"] == 1.80


def test_parse_item_with_dash_in_product_name():
    # Items like "Large Speciality Tea - English breakfast - 1.60" have a dash
    # inside the product name; only the rightmost " - " separates the price
    result = parse_item("Large Speciality Tea - English breakfast - 1.60")
    assert result["item_name"] == "Large Speciality Tea - English breakfast"
    assert result["price"] == 1.60
    assert result["flavour"] is None   # "Flavoured" keyword is absent


def test_parse_item_flavoured():
    # The word "Flavoured" in the name signals that the text after the last
    # " - " in the name part is the flavour, not part of the base name
    result = parse_item("Regular Flavoured iced latte - Hazelnut - 2.75")
    assert result["flavour"] == "Hazelnut"
    assert result["price"] == 2.75
    assert result["item_name"] == "Regular Flavoured iced latte - Hazelnut"


def test_parse_item_regular_size():
    result = parse_item("Regular Chai latte - 2.30")
    assert result["size"] == "Regular"


def test_parse_item_strips_whitespace():
    # Items from CSV often have leading/trailing spaces after the comma split
    result = parse_item("  Large Chai latte - 2.60  ")
    assert result["size"] == "Large"
    assert result["price"] == 2.60


def test_parse_item_price_is_float():
    # Price must be a float, not a string, so arithmetic can be done later
    result = parse_item("Regular Hot Chocolate - 1.40")
    assert isinstance(result["price"], float)


# ---------------------------------------------------------------------------
# hash_customer — deterministic GDPR hashing
# ---------------------------------------------------------------------------

def test_hash_customer_same_name_same_hash():
    # The same customer name must always produce the same UUID so we can
    # identify returning customers without storing their real name
    assert hash_customer("Alice Smith") == hash_customer("Alice Smith")


def test_hash_customer_case_insensitive():
    # Names are normalised to lowercase before hashing so "ALICE" and "alice"
    # are treated as the same person
    assert hash_customer("Alice Smith") == hash_customer("ALICE SMITH")


def test_hash_customer_strips_whitespace():
    # Leading/trailing whitespace in the CSV should not produce a different hash
    assert hash_customer("  Alice Smith  ") == hash_customer("Alice Smith")


def test_hash_customer_different_names_differ():
    # Two different people must not map to the same UUID
    assert hash_customer("Alice Smith") != hash_customer("Bob Jones")


def test_hash_customer_returns_valid_uuid_string():
    # The return value must be a UUID string (36 chars, dashes in right places)
    # so it fits the VARCHAR(36) customer_id column
    result = hash_customer("Alice Smith")
    assert len(result) == 36
    parts = result.split("-")
    assert len(parts) == 5


# ---------------------------------------------------------------------------
# transform_data — end-to-end row transformation
# ---------------------------------------------------------------------------

def test_transform_produces_one_order_per_row():
    orders, _ = transform_data([make_row(), make_row()])
    assert len(orders) == 2


def test_transform_order_fields_present():
    # These are the columns the database expects
    orders, _ = transform_data([make_row()])
    order = orders[0]
    assert "id" in order
    assert "branch_name" in order
    assert "customer_id" in order
    assert "order_time" in order
    assert "payment_method" in order
    assert "total_amount" in order


def test_transform_does_not_store_customer_name():
    # GDPR: the real name must never appear in the output — only the hash
    orders, _ = transform_data([make_row()])
    assert "customer_name" not in orders[0]


def test_transform_does_not_store_card_number():
    # PCI compliance: card numbers must never be persisted
    orders, _ = transform_data([make_row()])
    assert "card_number" not in orders[0]


def test_transform_order_time_format():
    # order_time must be a string in "YYYY-MM-DD HH:MM:SS" so it's
    # directly insertable into a TIMESTAMP column
    orders, _ = transform_data([make_row()])
    assert orders[0]["order_time"] == "2025-03-28 09:00:00"


def test_transform_total_amount_is_float():
    orders, _ = transform_data([make_row()])
    assert isinstance(orders[0]["total_amount"], float)


def test_transform_duplicate_items_collapsed_into_quantity():
    # When the same item appears more than once in an order we want a single
    # row with quantity > 1, not N duplicate rows
    row = make_row(**{" items_total": " Large Chai latte - 2.60, Large Chai latte - 2.60, Large Chai latte - 2.60"})
    _, items = transform_data([row])
    assert len(items) == 1
    assert items[0]["quantity"] == 3


def test_transform_different_items_are_separate_rows():
    row = make_row(**{" items_total": " Large Chai latte - 2.60, Regular Hot Chocolate - 1.40"})
    _, items = transform_data([row])
    assert len(items) == 2


def test_transform_empty_items_total_produces_no_order_items():
    # An order with no items should still create an order row but zero item rows
    row = make_row(**{" items_total": ""})
    orders, items = transform_data([row])
    assert len(orders) == 1
    assert len(items) == 0


def test_transform_malformed_item_skipped():
    # Items that have no " - " separator (e.g. a parsing artefact) should be
    # silently skipped rather than crashing the whole pipeline
    row = make_row(**{" items_total": " INVALID ITEM, Large Chai latte - 2.60"})
    _, items = transform_data([row])
    assert len(items) == 1   # only the valid item survives


def test_transform_empty_input_returns_empty_lists():
    orders, items = transform_data([])
    assert orders == []
    assert items == []


def test_transform_each_order_has_unique_id():
    # Every order must get its own UUID — no two rows share an id
    rows = [make_row(), make_row(), make_row()]
    orders, _ = transform_data(rows)
    ids = [o["id"] for o in orders]
    assert len(ids) == len(set(ids))


def test_transform_items_reference_correct_order_id():
    # Each order_item's order_id must match the parent order's id
    row = make_row(**{" items_total": " Large Chai latte - 2.60"})
    orders, items = transform_data([row])
    assert items[0]["order_id"] == orders[0]["id"]
