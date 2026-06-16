"""Entry point for the TeamSPAM ETL pipeline.

Run from the project root with:
    python -m pipeline.etl.run_pipeline
"""

import os
import sys

# add project root to path - must come before any local imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from warehouse.schema.postgrestable import create_database, create_tables  # noqa: E402
from pipeline.ingestion.extract import extract_csv  # noqa: E402
from pipeline.etl.transform import CSV_PATH, OUTPUT_PATH, transform_data, load_json, save_to_csv  # noqa: E402
from pipeline.etl.load import load_to_database  # noqa: E402


def run():
    """Run the full ETL pipeline end to end."""
    print("=== TeamSPAM ETL Pipeline ===\n")

    # step 1 - create the database if it doesn't exist yet
    print("Step 1: Creating database...")
    create_database()

    # step 2 - create tables and seed lookup data (sizes, flavours)
    print("\nStep 2: Creating tables...")
    create_tables()

    # step 3 - read the raw CSV from the branch sources folder
    print("\nStep 3: Extracting CSV...")
    rows = extract_csv(CSV_PATH)
    print(f"Extracted {len(rows)} rows")

    # step 4 - clean and reshape the data to match our schema
    print("\nStep 4: Transforming data...")
    orders, order_items = transform_data(rows)
    print(f"Transformed into {len(orders)} orders and {len(order_items)} order items")

    # step 5 - save snapshots as JSON and CSV (useful for debugging and sharing)
    print("\nStep 5: Saving JSON and CSV snapshots...")
    load_json({"orders": orders, "order_items": order_items}, OUTPUT_PATH)
    save_to_csv(orders, order_items, os.path.dirname(OUTPUT_PATH))

    # step 6 - load into postgres
    print("\nStep 6: Loading into database...")
    load_to_database(orders, order_items)

    print("\n=== Pipeline complete ===")


if __name__ == "__main__":
    run()
