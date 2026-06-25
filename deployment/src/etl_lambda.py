from utils import s3_utils
from utils import db_utils
from utils import sql_utils

import transform
import logging
import os

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main entry point called by AWS Lambda when a CSV file is uploaded to S3.

    Flow:
        1. Extract bucket name and file key from the S3 trigger event
        2. Download the CSV from S3
        3. Parse CSV rows (Extract)
        4. Clean and reshape into orders + order_items (Transform)
        5. Fetch Redshift credentials from SSM Parameter Store
        6. Connect to Redshift
        7. Create tables if they don't exist
        8. Seed sizes and flavours lookup tables
        9. Insert orders and order_items (Load)
    """
    LOGGER.info('lambda_handler: starting')
    file_path = 'NOT_SET'

    try:
        bucket_name, file_path = s3_utils.get_file_info(event)
        csv_text = s3_utils.load_file(bucket_name, file_path)

        data = transform.extract(csv_text)
        orders, order_items = transform.transform(data)

        LOGGER.info(
            f'lambda_handler: transformed file={file_path}, '
            f'orders={len(orders)}, order_items={len(order_items)}'
        )

        ssm_parameter_name = os.environ['SSM_PARAMETER_NAME']
        redshift_details = db_utils.get_ssm_param(ssm_parameter_name)
        db_connection, cursor = db_utils.open_sql_database_connection_and_cursor(redshift_details)

        sql_utils.create_db_tables(db_connection, cursor)
        sql_utils.seed_lookup_tables(db_connection, cursor)
        sql_utils.save_data_in_db(db_connection, cursor, bucket_name, file_path, orders, order_items)

        LOGGER.info(f'lambda_handler: done, file={file_path}')

    except Exception as err:
        LOGGER.error(f'lambda_handler: failure: error={err}, file={file_path}')
        raise err
