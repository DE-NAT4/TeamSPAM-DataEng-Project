"""
Data quality tests for pipeline/ingestion/sources/

These tests run the ETL transform against the REAL CSV source files and assert
invariants that must hold for every row of real data. They catch data issues
that unit tests with hand-crafted fixtures cannot — e.g. a new flavour format,
a broken row in a fresh data drop, or a date that doesn't match the pattern.

Leeds data uses the LOCAL pipeline transform (pipeline/etl/transform.py).
Chesterfield data uses the DEPLOYMENT transform (deployment/src/transform.py)
because the Chesterfield CSV has different header spacing ('time' vs ' time')
which the local transform does not handle — the deployment transform ignores
the header row and assigns column names explicitly, so it works for both.

Run these whenever a new source file is added to pipeline/ingestion/sources/.
"""
import os
import sys
import pytest
from ingestion.extract import extract_csv
from etl.transform import transform_data

# Also make the deployment transform available for Chesterfield data
_DEPLOY_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "deployment", "src")
)
if _DEPLOY_SRC not in sys.path:
    sys.path.insert(0, _DEPLOY_SRC)
import transform as deploy_transform

# Resolve absolute paths to the real source files
SOURCES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "pipeline", "ingestion", "sources")
)
LEEDS_CSV = os.path.join(SOURCES_DIR, "leedsdata.csv")
CHESTERFIELD_CSV = os.path.join(SOURCES_DIR, "chesterfielddata.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_and_transform(csv_path):
    """Extract from a CSV and run transform_data; return (orders, items)."""
    rows = extract_csv(csv_path)
    return transform_data(rows)


# ---------------------------------------------------------------------------
# Leeds data
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.exists(LEEDS_CSV), reason="leedsdata.csv not present")
class TestLeedsDataQuality:

    def test_produces_rows(self):
        # The CSV must have at least one data row — if it's empty something went wrong
        orders, items = load_and_transform(LEEDS_CSV)
        assert len(orders) > 0

    def test_no_card_numbers_in_orders(self):
        # PCI compliance: card_number must be stripped during transform
        orders, _ = load_and_transform(LEEDS_CSV)
        for order in orders:
            assert "card_number" not in order

    def test_no_customer_names_in_orders(self):
        # GDPR: real names must be replaced by the customer_id hash
        orders, _ = load_and_transform(LEEDS_CSV)
        for order in orders:
            assert "customer_name" not in order

    def test_all_order_amounts_positive(self):
        # A zero or negative total_amount would indicate a parsing error
        orders, _ = load_and_transform(LEEDS_CSV)
        for order in orders:
            assert order["total_amount"] > 0, f"Non-positive amount in order {order['id']}"

    def test_all_item_prices_positive(self):
        _, items = load_and_transform(LEEDS_CSV)
        for item in items:
            assert item["price"] > 0, f"Non-positive price on item {item['item_name']}"

    def test_all_item_quantities_at_least_one(self):
        _, items = load_and_transform(LEEDS_CSV)
        for item in items:
            assert item["quantity"] >= 1

    def test_order_ids_are_unique(self):
        # Duplicate UUIDs would cause ON CONFLICT to silently drop rows
        orders, _ = load_and_transform(LEEDS_CSV)
        ids = [o["id"] for o in orders]
        assert len(ids) == len(set(ids)), "Duplicate order IDs found"

    def test_order_time_format(self):
        # order_time must be "YYYY-MM-DD HH:MM:SS" for the TIMESTAMP column
        orders, _ = load_and_transform(LEEDS_CSV)
        for order in orders:
            ts = order["order_time"]
            assert len(ts) == 19, f"Unexpected timestamp format: {ts}"
            assert ts[4] == "-" and ts[7] == "-" and ts[10] == " "

    def test_payment_method_is_known_value(self):
        # All real transactions are CARD or CASH — anything else is a data issue
        known = {"CARD", "CASH"}
        orders, _ = load_and_transform(LEEDS_CSV)
        for order in orders:
            assert order["payment_method"] in known, \
                f"Unknown payment method: {order['payment_method']}"

    def test_sizes_are_known_values(self):
        # Only Large and Regular exist in our product catalogue
        known_sizes = {"Large", "Regular"}
        _, items = load_and_transform(LEEDS_CSV)
        for item in items:
            assert item["size"] in known_sizes, f"Unknown size: {item['size']}"

    def test_item_order_ids_match_real_orders(self):
        # Every order_item must reference an order that actually exists in the same batch
        orders, items = load_and_transform(LEEDS_CSV)
        order_ids = {o["id"] for o in orders}
        for item in items:
            assert item["order_id"] in order_ids, \
                f"order_item references unknown order_id: {item['order_id']}"


# ---------------------------------------------------------------------------
# Chesterfield data  (same invariants, different branch)
# ---------------------------------------------------------------------------
# Chesterfield's CSV header uses 'time' (no leading space) while Leeds uses
# ' time'.  The local transform hard-codes ' time' so it only works with Leeds.
# We use the deployment transform here because it assigns column names
# explicitly and ignores whatever the CSV header says.

def load_and_transform_chesterfield(csv_path):
    """Read Chesterfield CSV using the deployment transform's extract() so that
    the column-name spacing difference is handled transparently."""
    with open(csv_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    rows = deploy_transform.extract(lines)
    return deploy_transform.transform(rows)


@pytest.mark.skipif(not os.path.exists(CHESTERFIELD_CSV), reason="chesterfielddata.csv not present")
class TestChesterfieldDataQuality:

    def test_produces_rows(self):
        orders, _ = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        assert len(orders) > 0

    def test_no_card_numbers_in_orders(self):
        orders, _ = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        for order in orders:
            assert "card_number" not in order

    def test_all_order_amounts_positive(self):
        orders, _ = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        for order in orders:
            assert order["total_amount"] > 0

    def test_all_item_prices_positive(self):
        _, items = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        for item in items:
            assert item["price"] > 0

    def test_order_ids_are_unique(self):
        orders, _ = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        ids = [o["id"] for o in orders]
        assert len(ids) == len(set(ids))

    def test_sizes_are_known_values(self):
        known_sizes = {"Large", "Regular"}
        _, items = load_and_transform_chesterfield(CHESTERFIELD_CSV)
        for item in items:
            assert item["size"] in known_sizes, f"Unknown size: {item['size']}"
