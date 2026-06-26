import sys
import os

# Put deployment/src/ on the path so tests can do:
#   import transform
#   from utils import s3_utils
#   from utils import sql_utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment", "src")))
