import csv

def extract_csv(file_path):
    with open(file_path, mode="r", encoding="utf-8") as file:
        return list(csv.DictReader(file))

def extraction_successful(rows):
    return f"Extraction successful. Rows extracted: {len(rows)}"