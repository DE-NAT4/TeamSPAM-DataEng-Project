import uuid
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

SIZES = ['Large', 'Regular']
FLAVOURS = ['Hazelnut', 'Caramel', 'Vanilla', 'Gingerbread', 'Peppermint', 'Cinnamon']


def create_db_tables(connection, cursor):
    """
    Creates all tables in Redshift if they don't already exist.

    Tables:
        sizes     - lookup table for drink sizes (Large, Regular)
        flavours  - lookup table for flavour shots (Hazelnut, Caramel, etc.)
        orders    - one row per customer visit at a branch
        order_items - one row per distinct item line within an order

    Uses CREATE TABLE IF NOT EXISTS so this is safe to call on every invocation.
    In Redshift, PRIMARY KEY constraints are informational only (not enforced),
    but are kept for documentation and query optimiser hints.
    """
    LOGGER.info('create_db_tables: started')
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sizes (
                id   VARCHAR(36)  NOT NULL,
                name VARCHAR(20)  NOT NULL,
                PRIMARY KEY (id)
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flavours (
                id   VARCHAR(36)  NOT NULL,
                name VARCHAR(50)  NOT NULL,
                PRIMARY KEY (id)
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id             VARCHAR(36)   NOT NULL,
                branch_name    VARCHAR(100)  NOT NULL,
                customer_id    VARCHAR(36)   NOT NULL,
                order_time     TIMESTAMP     NOT NULL,
                payment_method VARCHAR(10)   NOT NULL,
                total_amount   DECIMAL(10,2) NOT NULL,
                PRIMARY KEY (id)
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id         VARCHAR(36)   NOT NULL,
                order_id   VARCHAR(36)   NOT NULL,
                item_name  VARCHAR(200)  NOT NULL,
                size_id    VARCHAR(36),
                flavour_id VARCHAR(36),
                price      DECIMAL(10,2) NOT NULL,
                quantity   SMALLINT      NOT NULL,
                PRIMARY KEY (id)
            );
        ''')

        connection.commit()
        LOGGER.info('create_db_tables: done')

    except Exception as ex:
        LOGGER.error(f'create_db_tables: failed: {ex}')
        raise ex


def seed_lookup_tables(connection, cursor):
    """
    Inserts the known sizes and flavours into the lookup tables if not present.

    Uses a SELECT-then-INSERT pattern because Redshift does not enforce UNIQUE
    constraints, so ON CONFLICT is not available. We check existence first to
    avoid inserting duplicates on repeated Lambda invocations.
    """
    LOGGER.info('seed_lookup_tables: started')
    try:
        for name in SIZES:
            cursor.execute('SELECT COUNT(*) FROM sizes WHERE name = %s', (name,))
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    'INSERT INTO sizes (id, name) VALUES (%s, %s)',
                    (str(uuid.uuid4()), name)
                )

        for name in FLAVOURS:
            cursor.execute('SELECT COUNT(*) FROM flavours WHERE name = %s', (name,))
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    'INSERT INTO flavours (id, name) VALUES (%s, %s)',
                    (str(uuid.uuid4()), name)
                )

        connection.commit()
        LOGGER.info('seed_lookup_tables: done')

    except Exception as ex:
        LOGGER.error(f'seed_lookup_tables: failed: {ex}')
        raise ex


def _get_size_id(cursor, size_name):
    cursor.execute('SELECT id FROM sizes WHERE name = %s', (size_name,))
    result = cursor.fetchone()
    return result[0] if result else None


def _get_flavour_id(cursor, flavour_name):
    if not flavour_name:
        return None
    cursor.execute('SELECT id FROM flavours WHERE name = %s', (flavour_name,))
    result = cursor.fetchone()
    return result[0] if result else None


def save_data_in_db(connection, cursor, bucket_name, file_path, orders, order_items):
    """
    Inserts all transformed orders and order_items into Redshift.

    Args:
        connection:  Active psycopg2 connection (used to commit)
        cursor:      psycopg2 cursor (used to execute SQL)
        bucket_name: S3 bucket the file came from (logging only)
        file_path:   S3 key of the uploaded file (logging only)
        orders:      List of order dictionaries from etl.transform()
        order_items: List of order item dictionaries from etl.transform()
    """
    LOGGER.info(
        f'save_data_in_db: started: file={file_path}, '
        f'orders={len(orders)}, order_items={len(order_items)}'
    )
    try:
        for order in orders:
            cursor.execute(
                '''
                INSERT INTO orders
                    (id, branch_name, customer_id, order_time, payment_method, total_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
                ''',
                (
                    order['id'],
                    order['branch_name'],
                    order['customer_id'],
                    order['order_time'],
                    order['payment_method'],
                    order['total_amount'],
                )
            )

        for item in order_items:
            size_id = _get_size_id(cursor, item['size'])
            flavour_id = _get_flavour_id(cursor, item['flavour'])
            cursor.execute(
                '''
                INSERT INTO order_items
                    (id, order_id, item_name, size_id, flavour_id, price, quantity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    item['id'],
                    item['order_id'],
                    item['item_name'],
                    size_id,
                    flavour_id,
                    item['price'],
                    item['quantity'],
                )
            )

        connection.commit()
        LOGGER.info(f'save_data_in_db: done: file={file_path}')

    except Exception as ex:
        LOGGER.error(f'save_data_in_db: error: ex={ex}, file={file_path}')
        raise ex
