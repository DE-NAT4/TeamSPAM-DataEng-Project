"""
Tests for pipeline/ingestion/extract.py

extract_csv() is the entry point for all local CSV ingestion.
These tests verify file handling, error conditions, and output shape.
"""
import pytest
from ingestion.extract import extract_csv


def test_extract_csv_returns_list_of_dicts(tmp_path):
    # Normal case: a valid CSV with a header row should come back as
    # a list of dicts keyed by the header names
    f = tmp_path / "sample.csv"
    f.write_text("date,amount\n28/03/2025,5.00\n01/04/2025,3.50\n", encoding="utf-8")

    rows = extract_csv(str(f))

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0] == {"date": "28/03/2025", "amount": "5.00"}


def test_extract_csv_header_only_returns_empty_list(tmp_path):
    # A CSV with only a header row and no data rows should return []
    # rather than raising an error or returning the header as a row
    f = tmp_path / "empty.csv"
    f.write_text("date,amount\n", encoding="utf-8")

    rows = extract_csv(str(f))

    assert rows == []


def test_extract_csv_raises_for_missing_file():
    # If the file doesn't exist the function must raise FileNotFoundError
    # so the pipeline fails loudly rather than silently returning nothing
    with pytest.raises(FileNotFoundError):
        extract_csv("/does/not/exist/file.csv")


def test_extract_csv_preserves_column_values(tmp_path):
    # All values should come back as strings exactly as written —
    # no automatic type conversion should happen at this stage
    f = tmp_path / "types.csv"
    f.write_text("name,price,qty\nChai latte,2.60,3\n", encoding="utf-8")

    rows = extract_csv(str(f))

    assert rows[0]["price"] == "2.60"   # still a string, not a float
    assert rows[0]["qty"] == "3"         # still a string, not an int


def test_extract_csv_handles_utf8_characters(tmp_path):
    # Customer names can contain accented or non-ASCII characters;
    # the file is opened with utf-8 so these must round-trip correctly
    f = tmp_path / "utf8.csv"
    f.write_text("name,amount\nJoão,2.50\n", encoding="utf-8")

    rows = extract_csv(str(f))

    assert rows[0]["name"] == "João"
