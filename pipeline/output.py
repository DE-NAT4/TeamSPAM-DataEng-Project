import os
from extract import extract_csv, extraction_successful

BASE_DIR = os.path.dirname(__file__)
file_path = os.path.join(BASE_DIR, "leedsdata.csv")

rows = extract_csv(file_path)

print(extraction_successful(rows))

for row in rows[:5]:
    print(row)

# Load data
rows = extract_csv("pipeline/leedsdata.csv")

# Confirm load worked
print(extraction_successful(rows))

# ---- BASIC INSPECTION ----
print("\nColumns in dataset:")
print(rows[0].keys())

print("\nFirst 5 rows:")
for row in rows[:5]:
    print(row)

print("\nTotal rows:")
print(len(rows))

# ---- EXAMPLE ANALYSIS ----

# Example 1: Count unique values in a column (change 'City' to your real column)
if "City" in rows[0]:
    cities = set(row["City"] for row in rows)
    print("\nUnique cities:", len(cities))

# Example 2: Filter rows (change condition to match your data)
if "City" in rows[0]:
    leeds_rows = [row for row in rows if row["City"] == "Leeds"]
    print("Rows for Leeds:", len(leeds_rows))