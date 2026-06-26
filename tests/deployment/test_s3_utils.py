"""
Tests for deployment/src/utils/s3_utils.py

s3_utils wraps the two things the Lambda needs from S3:
  - get_file_info(event)       → parse the S3 trigger event for bucket/key
  - load_file(bucket, key)     → download and return lines from S3

Because s3_client is created at module level (to be reused across warm Lambda
invocations) we patch it in place with unittest.mock rather than starting a
real boto3 connection.  No AWS credentials are needed to run these tests.
"""
import pytest
from unittest.mock import patch, MagicMock
from utils import s3_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_s3_event(bucket="test-bucket", key="leedsdata.csv"):
    """Build a minimal S3 trigger event dict as AWS sends to Lambda."""
    return {
        "Records": [{
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key},
            }
        }]
    }


# ---------------------------------------------------------------------------
# get_file_info — S3 event parsing
# ---------------------------------------------------------------------------

def test_get_file_info_returns_bucket_and_key():
    bucket, key = s3_utils.get_file_info(make_s3_event())
    assert bucket == "test-bucket"
    assert key == "leedsdata.csv"


def test_get_file_info_different_values():
    # Make sure the function reads from the event, not a hardcoded default
    bucket, key = s3_utils.get_file_info(make_s3_event(bucket="spam-raw", key="chesterfielddata.csv"))
    assert bucket == "spam-raw"
    assert key == "chesterfielddata.csv"


def test_get_file_info_missing_records_raises():
    # A malformed event (no Records key) must raise rather than silently return None
    with pytest.raises((KeyError, IndexError)):
        s3_utils.get_file_info({})


def test_get_file_info_empty_records_raises():
    # An event with an empty Records list should also raise
    with pytest.raises((KeyError, IndexError)):
        s3_utils.get_file_info({"Records": []})


# ---------------------------------------------------------------------------
# load_file — S3 download
# ---------------------------------------------------------------------------

def test_load_file_returns_list_of_lines():
    # load_file must return one string per line so it's compatible with
    # csv.DictReader in transform.extract()
    mock_body = MagicMock()
    mock_body.read.return_value = b"col1,col2\nval1,val2\n"
    mock_response = {"Body": mock_body}

    with patch.object(s3_utils, "s3_client") as mock_client:
        mock_client.get_object.return_value = mock_response
        result = s3_utils.load_file("my-bucket", "my-file.csv")

    assert result == ["col1,col2", "val1,val2"]


def test_load_file_passes_correct_bucket_and_key():
    # Verify the right bucket and key are forwarded to get_object
    mock_body = MagicMock()
    mock_body.read.return_value = b"header\nrow"
    mock_response = {"Body": mock_body}

    with patch.object(s3_utils, "s3_client") as mock_client:
        mock_client.get_object.return_value = mock_response
        s3_utils.load_file("spam-bucket", "data/leedsdata.csv")

    mock_client.get_object.assert_called_once_with(
        Bucket="spam-bucket", Key="data/leedsdata.csv"
    )


def test_load_file_handles_windows_line_endings():
    # Files edited on Windows may have \r\n; splitlines() strips them correctly
    mock_body = MagicMock()
    mock_body.read.return_value = b"col1,col2\r\nval1,val2\r\n"
    mock_response = {"Body": mock_body}

    with patch.object(s3_utils, "s3_client") as mock_client:
        mock_client.get_object.return_value = mock_response
        result = s3_utils.load_file("bucket", "file.csv")

    # splitlines() strips \r so each line should be clean
    assert "\r" not in result[0]
    assert "\r" not in result[1]


def test_load_file_propagates_s3_error():
    # If S3 raises (e.g. NoSuchKey) it should bubble up, not be swallowed
    with patch.object(s3_utils, "s3_client") as mock_client:
        mock_client.get_object.side_effect = Exception("NoSuchKey")
        with pytest.raises(Exception, match="NoSuchKey"):
            s3_utils.load_file("bucket", "missing.csv")
