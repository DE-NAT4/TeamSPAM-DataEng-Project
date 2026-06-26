import sys
import os

# Put pipeline/ on the path so tests can do:
#   from ingestion.extract import extract_csv
#   from etl.transform import transform_data
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "pipeline")))
