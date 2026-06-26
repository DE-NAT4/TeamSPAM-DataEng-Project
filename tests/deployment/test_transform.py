"""
Tests for deployment/src/transform.py  (the Lambda / Redshift version)

The Lambda transform is slightly different from the local one:
  - extract() takes a list of text lines (from S3) rather than a file path
  - Column names have no leading spaces (they are set explicitly via fieldnames)
  - The time column supports both HH:MM and HH:MM:SS formats
  - Private helpers are prefixed with underscore (_hash_customer, _parse_item)

These tests keep the two versions honest — if you change one, the other
should be updated to match.
"""
import csv
import io
import pytest
import transform   # deployment/src/transform.py, added to path by conftest.py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADER = "date,time,location,customer_name,items_total,amount_paid,payment_method,card_number"

def make_lines(**overrides):
    """Return a two-element list: [header, data_row] with any field overridable.

    Uses csv.writer so fields containing commas (e.g. items_total with multiple
    items) are properly quoted and won't be split into extra columns.
    """
    fields = {
        "date": "28/03/2025",
        "time": "09:00",
        "location": "Leeds",
        "customer_name": "Test User",
        "items_total": "Large Chai latte - 2.60",
        "amount_paid": "2.60",
        "payment_method": "CARD",
        "card_number": "1234567890",
    }
    fields.update(overrides)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "time", "location", "customer_name",
                     "items_total", "amount_paid", "payment_method", "card_number"])
    writer.writerow([
        fields["date"], fields["time"], fields["location"], fields["customer_name"],
        fields["items_total"], fields["amount_paid"], fields["payment_method"], fields["card_number"],
    ])
    return buf.getvalue().splitlines()


# ---------------------------------------------------------------------------
# extract() — CSV text → list of dicts
# ---------------------------------------------------------------------------

def test_extract_skips_header_row():
    # The header line must not appear as a data row
    lines = make_lines()
    rows = transform.extract(lines)
    assert len(rows) == 1


def test_extract_returns_dicts_with_expected_keys():
    rows = transform.extract(make_lines())
    assert "date" in rows[0]
    assert "customer_name" in rows[0]
    assert "items_total" in rows[0]


def test_extract_empty_file_returns_empty_list():
    # A file with only the header should produce no data rows
    rows = transform.extract([HEADER])
    assert rows == []


# ---------------------------------------------------------------------------
# _parse_item — single item string parser
# ---------------------------------------------------------------------------

def test_parse_item_simple():
    result = transform._parse_item("Large Filter coffee - 1.80")
    assert result["item_name"] == "Large Filter coffee"
    assert result["size"] == "Large"
    assert result["flavour"] is None
    assert result["price"] == 1.80


def test_parse_item_dash_in_product_name():
    # The rightmost " - " is always the price separator
    result = transform._parse_item("Large Speciality Tea - English breakfast - 1.60")
    assert result["item_name"] == "Large Speciality Tea - English breakfast"
    assert result["price"] == 1.60
    assert result["flavour"] is None


def test_parse_item_flavoured():
    # "Flavoured" keyword triggers flavour extraction from the name part
    result = transform._parse_item("Regular Flavoured iced latte - Hazelnut - 2.75")
    assert result["flavour"] == "Hazelnut"
    assert result["price"] == 2.75


def test_parse_item_strips_whitespace():
    result = transform._parse_item("  Large Chai latte - 2.60  ")
    assert result["size"] == "Large"
    assert result["price"] == 2.60


# ---------------------------------------------------------------------------
# _hash_customer — deterministic GDPR hashing
# ---------------------------------------------------------------------------

def test_hash_customer_deterministic():
    assert transform._hash_customer("Alice Smith") == transform._hash_customer("Alice Smith")


def test_hash_customer_case_insensitive():
    assert transform._hash_customer("Alice Smith") == transform._hash_customer("alice smith")


def test_hash_customer_strips_whitespace():
    assert transform._hash_customer("  Alice  ") == transform._hash_customer("Alice")


def test_hash_customer_different_names_differ():
    assert transform._hash_customer("Alice") != transform._hash_customer("Bob")


def test_hash_customer_returns_uuid_string():
    result = transform._hash_customer("Alice")
    assert len(result) == 36
    assert result.count("-") == 4


# ---------------------------------------------------------------------------
# transform() — full transformation
# ---------------------------------------------------------------------------

def test_transform_produces_one_order_per_data_row():
    rows = transform.extract(make_lines())
    orders, _ = transform.transform(rows)
    assert len(orders) == 1


def test_transform_does_not_store_card_number():
    # PCI compliance: card numbers must be dropped before Redshift
    rows = transform.extract(make_lines())
    orders, _ = transform.transform(rows)
    assert "card_number" not in orders[0]


def test_transform_does_not_store_customer_name():
    # GDPR: real name replaced by customer_id hash
    rows = transform.extract(make_lines())
    orders, _ = transform.transform(rows)
    assert "customer_name" not in orders[0]


def test_transform_time_format_hhmm():
    # Format without seconds: "HH:MM"
    rows = transform.extract(make_lines(time="09:00"))
    orders, _ = transform.transform(rows)
    assert orders[0]["order_time"] == "2025-03-28 09:00:00"


def test_transform_time_format_hhmmss():
    # Some source files include seconds: "HH:MM:SS" — both must be handled
    rows = transform.extract(make_lines(time="09:00:30"))
    orders, _ = transform.transform(rows)
    assert orders[0]["order_time"] == "2025-03-28 09:00:30"


def test_transform_duplicate_items_collapsed():
    # Three identical items → one row with quantity=3, not three rows
    lines = make_lines(
        items_total="Large Chai latte - 2.60,Large Chai latte - 2.60,Large Chai latte - 2.60"
    )
    rows = transform.extract(lines)
    _, items = transform.transform(rows)
    assert len(items) == 1
    assert items[0]["quantity"] == 3


def test_transform_different_items_produce_separate_rows():
    lines = make_lines(items_total="Large Chai latte - 2.60,Regular Hot Chocolate - 1.40")
    rows = transform.extract(lines)
    _, items = transform.transform(rows)
    assert len(items) == 2


def test_transform_empty_items_total_no_order_items():
    # An order with no items is valid — just no item rows
    lines = make_lines(items_total="")
    rows = transform.extract(lines)
    orders, items = transform.transform(rows)
    assert len(orders) == 1
    assert len(items) == 0


def test_transform_malformed_item_skipped():
    # Items with no " - " price separator should be silently dropped
    lines = make_lines(items_total="BADITEM,Large Chai latte - 2.60")
    rows = transform.extract(lines)
    _, items = transform.transform(rows)
    assert len(items) == 1


def test_transform_empty_input():
    orders, items = transform.transform([])
    assert orders == []
    assert items == []


def test_transform_item_order_id_matches_parent():
    rows = transform.extract(make_lines())
    orders, items = transform.transform(rows)
    assert items[0]["order_id"] == orders[0]["id"]


def test_transform_order_ids_unique_across_rows():
    # Multiple rows in one batch must each get their own UUID
    lines = [HEADER] + [make_lines()[1], make_lines()[1], make_lines()[1]]
    rows = transform.extract(lines)
    orders, _ = transform.transform(rows)
    ids = [o["id"] for o in orders]
    assert len(ids) == len(set(ids))
