from utils import s3_utils
import etl
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

#This value was set in etl-stack.yml, the value will match a key in the AWS Systems Manager Parameter Store, which contains the Redshift connection details
SSM_ENV_VAR_NAME = 'SSM_PARAMETER_NAME'

def lambda_handler(event, context):
    
    LOGGER.info('lambda_handler: starting')

    # Block 1: Parse the event to get the bucket_name and file_path
    try:
        bucket_name, file_path = s3_utils.get_file_info(event)
    except Exception as err:
        LOGGER.error(f'lambda_handler: event parsing failed: error={err}, event={event}')
        raise err
    # Block 2: Confirmed that we have the bucket_name and file_path
    # Load the file from S3, extract, transform, and load into Redshift
    try:
        csv_text = s3_utils.load_file(bucket_name, file_path)
        #csv_text is a list of strings like:
        #[
        #     'name,age,city',
        #     'Alice,30,London',
        #     'Bob,25,New York'
        # ]
        data = etl.extract(csv_text)  
        #data is a list of dictionaries like:
        #[
        #     {'name': 'Alice', 'age': '30', 'city': 'London'},
        #     {'name': 'Bob', 'age': '25', 'city': 'New York'}
        # ]
        orders, order_items = etl.clean_data(data)
    
    except Exception as err:
        LOGGER.error(f'lambda_handler: processing failure: error={err}, file={file_path}')
        raise err