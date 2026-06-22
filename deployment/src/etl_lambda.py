import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

#This value was set in etl-stack.yml, the value will match a key in the AWS Systems Manager Parameter Store, which contains the Redshift connection details
SSM_ENV_VAR_NAME = 'SSM_PARAMETER_NAME'

def lambda_handler(event, context):
    
    LOGGER.info('lambda_handler: starting')
    print('Hello Team SPAM!')