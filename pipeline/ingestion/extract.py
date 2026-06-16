import csv
import os


def extract_csv(file_path):
    # read the CSV and return every row as a dictionary
    # the keys are the column headers from the first line of the file
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV not found at: {file_path}")

    with open(file_path, mode="r", encoding="utf-8") as file:
        return list(csv.DictReader(file))
