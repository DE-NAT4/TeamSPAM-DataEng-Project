from utils import s3_utils
from utils import db_utils
from utils import sql_utils

import etl
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
        # STEP 1 & 2: get file location from S3 event, download the CSV
        bucket_name, file_path = s3_utils.get_file_info(event)
        csv_text = s3_utils.load_file(bucket_name, file_path)

        # STEP 3: parse CSV lines into raw row dictionaries
        data = etl.extract(csv_text)

        # STEP 4: clean and reshape into (orders, order_items)
        # card_number is dropped and customer_name is hashed inside transform()
        orders, order_items = etl.transform(data)

        # Log counts only - never log row contents as they may contain PII
        LOGGER.info(
            f'lambda_handler: transformed file={file_path}, '
            f'orders={len(orders)}, order_items={len(order_items)}'
        )

        # STEP 5: read the Redshift connection details from SSM
        # SSM_PARAMETER_NAME is set in etl-stack.yml as e.g. 'spam_redshift_settings'
        ssm_parameter_name = os.environ['SSM_PARAMETER_NAME']
        redshift_details = db_utils.get_ssm_param(ssm_parameter_name)

        # STEP 6: open a connection to Redshift
        db_connection, cursor = db_utils.open_sql_database_connection_and_cursor(redshift_details)

        # STEP 7: create tables (safe to call every time - uses IF NOT EXISTS)
        sql_utils.create_db_tables(db_connection, cursor)

        # STEP 8: seed lookup tables for sizes and flavours
        sql_utils.seed_lookup_tables(db_connection, cursor)

        # STEP 9: insert all orders and their items into Redshift
        sql_utils.save_data_in_db(db_connection, cursor, bucket_name, file_path, orders, order_items)

        LOGGER.info(f'lambda_handler: done, file={file_path}')

    except Exception as err:
        LOGGER.error(f'lambda_handler: failure: error={err}, file={file_path}')
        raise err
