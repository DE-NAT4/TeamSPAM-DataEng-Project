from utils import s3_utils

import etl
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def lambda_handler(event, context):
    print('Hello Team SPAM!')
