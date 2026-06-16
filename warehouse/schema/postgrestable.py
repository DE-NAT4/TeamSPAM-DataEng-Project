import os
import psycopg2
import uuid
from dotenv import load_dotenv

load_dotenv()

host_name = os.getenv("POSTGRES_HOST")
database_name = os.getenv("POSTGRES_DB")
user_name = os.getenv("POSTGRES_USER")
user_password = os.getenv("POSTGRES_PASSWORD")


def get_connection():
    return psycopg2.connect(
        host=host_name,
        dbname=database_name,
        user=user_name,
        password=user_password,
        port=os.getenv("POSTGRES_PORT", "5432")
    )


def create_database():
    # we can't create a database while connected to it
    # so we connect to the default 'postgres' db first, create ours, then switch
    conn = psycopg2.connect(
        host=host_name,
        dbname="postgres",
        user=user_name,
        password=user_password
    )
    # autocommit must be on - CREATE DATABASE can't run inside a transaction
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {database_name}")
        print(f"Database '{database_name}' created!")
    else:
        print(f"Database '{database_name}' already exists, skipping.")

    cur.close()
    conn.close()


def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    # lookup table for drink sizes - only ever Large or Regular
    # seeded once at setup, ETL reads from it, never writes to it
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sizes (
        id      UUID            NOT NULL,
        name    VARCHAR(20)     NOT NULL UNIQUE,
        PRIMARY KEY (id)
    );
    """)

    # lookup table for flavours e.g. Hazelnut, Caramel, Vanilla
    # seeded once at setup, ETL reads from it, never writes to it
    cur.execute("""
    CREATE TABLE IF NOT EXISTS flavours (
        id      UUID            NOT NULL,
        name    VARCHAR(50)     NOT NULL UNIQUE,
        PRIMARY KEY (id)
    );
    """)

    # one row per customer visit at a branch
    # customer_id is a hash of their name - lets us spot regulars without storing real names
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id              UUID            NOT NULL,
        branch_name     VARCHAR(100)    NOT NULL,
        customer_id     UUID            NOT NULL,
        order_time      TIMESTAMP       NOT NULL,
        payment_method  VARCHAR(10)     NOT NULL,
        total_amount    DECIMAL(10,2)   NOT NULL,
        PRIMARY KEY (id)
    );
    """)

    # one row per distinct item in an order
    # quantity handles duplicates e.g. 3x Large Chai latte = 1 row with quantity 3
    # size_id and flavour_id are logical references to the lookup tables, not enforced
    # as FK constraints so this stays compatible with Redshift later
    cur.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id          UUID            NOT NULL,
        order_id    UUID            NOT NULL,
        item_name   VARCHAR(200)    NOT NULL,
        size_id     UUID,
        flavour_id  UUID,
        price       DECIMAL(10,2)   NOT NULL,
        quantity    SMALLINT        NOT NULL DEFAULT 1,
        PRIMARY KEY (id)
    );
    """)

    conn.commit()
    print("Tables created successfully!")

    seed_lookup_tables(cur, conn)

    cur.close()
    conn.close()


def seed_lookup_tables(cur, conn):
    # -------------------------
    # SEED SIZES
    # -------------------------
    sizes = ["Large", "Regular"]

    for name in sizes:
        cur.execute("""
            INSERT INTO sizes (id, name)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING;
        """, (str(uuid.uuid4()), name))

    # -------------------------
    # SEED FLAVOURS
    # -------------------------
    flavours = [
        "Hazelnut",
        "Caramel",
        "Vanilla",
        "Gingerbread",
        "Peppermint",
        "Cinnamon",
    ]

    for name in flavours:
        cur.execute("""
            INSERT INTO flavours (id, name)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING;
        """, (str(uuid.uuid4()), name))

    conn.commit()
    print("Lookup tables seeded successfully!")


if __name__ == "__main__":
    create_tables()
