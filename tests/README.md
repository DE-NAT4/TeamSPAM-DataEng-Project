# Tests

## How to run

Install dependencies (only needed once):
```
pip install -r tests/requirements-test.txt
```

Run everything:
```
venv\Scripts\python.exe -m pytest tests/ -v
```

Run a specific folder:
```
venv\Scripts\python.exe -m pytest tests/local/ -v
venv\Scripts\python.exe -m pytest tests/deployment/ -v
venv\Scripts\python.exe -m pytest tests/scripts/ -v
```

---

## Folder structure

```
tests/
├── local/          — tests for the local Postgres pipeline (pipeline/)
├── deployment/     — tests for the AWS Lambda pipeline (deployment/src/)
└── scripts/        — tests for the bash deployment scripts
```

---

## local/

Tests the pipeline that runs on your machine and loads into the local Postgres/Podman database.

| File | What it tests |
|---|---|
| `test_extract.py` | `extract_csv()` — reading a CSV file into a list of dicts |
| `test_transform.py` | `parse_item()`, `hash_customer()`, `transform_data()` — all the cleaning and reshaping logic |
| `test_data_quality.py` | Runs the real Leeds and Chesterfield CSV files through the pipeline and checks that the output is sane (no card numbers stored, all prices positive, no duplicate order IDs, etc.) |

---

## deployment/

Tests the Lambda pipeline that runs on AWS and loads into Redshift. No AWS credentials are needed — external services are replaced with mocks.

| File | What it tests |
|---|---|
| `test_transform.py` | `extract()` and `transform()` in `deployment/src/transform.py` — same logic as local but structured for Lambda |
| `test_s3_utils.py` | `get_file_info()` (parses the S3 trigger event) and `load_file()` (downloads from S3). The S3 client is mocked so no real AWS call is made. |
| `test_sql_utils.py` | `create_db_tables()`, `seed_lookup_tables()`, `save_data_in_db()` — all Redshift interactions. The database cursor and connection are mocked. |

---

## scripts/

Tests the bash deployment and teardown scripts without actually calling AWS.

| File | What it tests |
|---|---|
| `test_bash_scripts.py` | Syntax validity (`bash -n`), argument validation (`set -eu` causes immediate exit with missing args), content checks (correct region, `SKIP_PIP_INSTALL` flag, teardown ordering), and optional `shellcheck` static analysis |

The bash tests that actually invoke the scripts run them from a **temporary copy** so that `deploy.sh`'s self-modifying `sed -i '$0'` line (which strips Windows line endings) cannot alter the real file in the repo.

---

## Infrastructure files

### `conftest.py`

A special file that pytest loads automatically before running tests in that folder. You never import it yourself.

Each `conftest.py` in this project does one thing: add the right source folder to Python's import path so the tests can import the actual pipeline code.

- `tests/local/conftest.py` adds `pipeline/` to the path
- `tests/deployment/conftest.py` adds `deployment/src/` to the path

Without these, imports like `from ingestion.extract import extract_csv` would fail because Python wouldn't know where to find the code.

### `__init__.py`

An empty file that marks a folder as a Python package. Its presence is all that matters — there is no content to read.

Without it, if two test files in different subfolders share a name (e.g. both are called `test_transform.py`), Python gets confused about which is which and pytest throws a collection error. With it, pytest treats each subfolder as its own namespace and they don't clash.
