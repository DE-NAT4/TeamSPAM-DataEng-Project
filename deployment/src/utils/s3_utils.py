import boto3
import logging

#Use logger instead of print statements for better logging and debugging
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

#aws s3 client
s3_client = boto3.client('s3')


def get_file_info(event):
    LOGGER.info('get_file_info: starting')

        #Retrieves the first record from the event (json) looks like this:
    # {
    #   "Records": [
    #     {
    #       "s3": {
    #         "bucket": {
    #           "name": "example-bucket"
    #         },
    #         "object": {
    #           "key": "example-file.txt"
    #         }
    #       }
    #     }
    #   ]
    # }

    first_record = event['Records'][0]
    bucket_name = first_record['s3']['bucket']['name']
    file_name = first_record['s3']['object']['key']

    LOGGER.info(f'get_file_info: file={file_name}, bucket_name={bucket_name}')
    return bucket_name, file_name


def load_file(bucket_name, s3_key):
    LOGGER.info(f'load_file: loading s3_key={s3_key} from bucket_name={bucket_name}')
    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
    #response would look like this:
    # {
#     'Body': <botocore.response.StreamingBody object at 0x7fcb12345678>,
#     'AcceptRanges': 'bytes',
#     'ContentType': 'text/csv',
#     'ContentLength': 1056,
#     'ETag': '"d41d8cd98f00b204e9800998ecf8427e"',
#     'LastModified': datetime.datetime(2026, 6, 17, 14, 30, 0, tzinfo=tzutc()),
#     'Metadata': {},
#     'ResponseMetadata': {
#         'RequestId': 'A1B2C3D4E5F6G7H8',
#         'HostId': 'ab12cd34ef56gh78ij90kl12mn34op56qr78st90uv12wx34yz56',
#         'HTTPStatusCode': 200,
#         'HTTPHeaders': {
#             'x-amz-id-2': 'ab12cd34ef56gh78ij90...',
#             'x-amz-request-id': 'A1B2C3D4E5F6G7H8',
#             'date': 'Wed, 17 Jun 2026 15:21:51 GMT',
#             'last-modified': 'Wed, 17 Jun 2026 14:30:00 GMT',
#             'etag': '"d41d8cd98f00b204e9800998ecf8427e"',
#             'accept-ranges': 'bytes',
#             'content-type': 'text/csv',
#             'server': 'AmazonS3',
#             'content-length': '1056'
#         },
#         'RetryAttempts': 0
#     }
# }

    body_text = response['Body'].read().decode('utf-8').splitlines()
    #StreamingBody -> read() -> bytes -> decode('utf-8') -> str -> splitlines() -> list[str]
    # e.g., body_text = ['Alice,30,Engineer', 'Bob,25,Designer', 'Charlie,35,Manager']
    LOGGER.info(f'load_file: done: s3_key={s3_key} result_chars={len(body_text)}')
    return body_text