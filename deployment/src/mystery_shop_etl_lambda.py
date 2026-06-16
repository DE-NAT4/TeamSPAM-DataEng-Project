import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):
    
    LOGGER.info('lambda_handler: starting')
    print('Hello Team SPAM!')