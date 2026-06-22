import boto3
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3_client = boto3.client('s3')


def get_file_info(event):
    """
    Extracts the S3 bucket name and file path from the Lambda trigger event.

    When a file is uploaded to S3, AWS sends a JSON event to Lambda describing
    what happened. This function pulls out the bucket name and the file key.

    Returns:
        Tuple of (bucket_name, file_name) both as strings.
    """
    LOGGER.info('get_file_info: starting')

    first_record = event['Records'][0]
    bucket_name = first_record['s3']['bucket']['name']
    file_name = first_record['s3']['object']['key']

    LOGGER.info(f'get_file_info: file={file_name}, bucket_name={bucket_name}')
    return bucket_name, file_name


def load_file(bucket_name, s3_key):
    """
    Downloads a file from S3 and returns its content as a list of lines.

    Args:
        bucket_name: The S3 bucket containing the file
        s3_key: The file path/name within the bucket

    Returns:
        A list of strings, one per line in the file (including the header row).
    """
    LOGGER.info(f'load_file: loading s3_key={s3_key} from bucket_name={bucket_name}')

    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
    body_text = response['Body'].read().decode('utf-8').split('\n')

    LOGGER.info(f'load_file: done: s3_key={s3_key} lines={len(body_text)}')
    return body_text
