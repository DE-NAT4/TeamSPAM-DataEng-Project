import psycopg2 as psy
import boto3
import logging
import json

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

ssm_client = boto3.client('ssm')


def get_ssm_param(param_name):
    """
    Fetches and parses the Redshift connection details from SSM Parameter Store.

    The parameter is stored as a JSON string containing host, port, database
    name, username, and password. Storing credentials in SSM means they are
    never hardcoded in source code.

    Args:
        param_name: The SSM parameter name, e.g. 'spam_redshift_settings'.
                    Set via the SSM_PARAMETER_NAME Lambda environment variable.

    Returns:
        A dictionary with keys: host, port, database-name, user, password.
    """
    LOGGER.info(f'get_ssm_param: getting param_name={param_name}')

    parameter_details = ssm_client.get_parameter(Name=param_name)
    redshift_details = json.loads(parameter_details['Parameter']['Value'])

    host = redshift_details['host']
    user = redshift_details['user']
    db = redshift_details['database-name']
    LOGGER.info(f'get_ssm_param: loaded for db={db}, user={user}, host={host}')

    return redshift_details


def open_sql_database_connection_and_cursor(redshift_details):
    """
    Opens a connection to the Redshift database and returns a cursor.

    Redshift is based on PostgreSQL so psycopg2 works with it directly.
    Redshift uses port 5439 by default.

    Args:
        redshift_details: Dictionary of connection details from get_ssm_param().

    Returns:
        Tuple of (db_connection, cursor).
    """
    try:
        LOGGER.info('open_sql_database_connection_and_cursor: opening connection...')

        db_connection = psy.connect(
            host=redshift_details['host'],
            database=redshift_details['database-name'],
            user=redshift_details['user'],
            password=redshift_details['password'],
            port=redshift_details['port'],
        )

        cursor = db_connection.cursor()

        LOGGER.info('open_sql_database_connection_and_cursor: connection ready')
        return db_connection, cursor

    except ConnectionError as ex:
        LOGGER.error(f'open_sql_database_connection_and_cursor: failed to open connection: {ex}')
        raise ex
