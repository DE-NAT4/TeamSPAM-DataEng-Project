-- one row per customer visit at a branch
-- customer_id is a hashed UUID - identifies regulars without storing real names
CREATE TABLE IF NOT EXISTS orders (
    id              UUID            NOT NULL,
    branch_name     VARCHAR(100)    NOT NULL,
    customer_id     UUID            NOT NULL,
    order_time      TIMESTAMP       NOT NULL,
    payment_method  VARCHAR(10)     NOT NULL,
    total_amount    DECIMAL(10,2)   NOT NULL,
    PRIMARY KEY (id)
);
