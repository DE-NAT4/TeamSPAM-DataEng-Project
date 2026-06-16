-- one row per distinct item within an order
-- quantity handles duplicates e.g. 3x Large Chai latte = 1 row with quantity 3
-- size_id and flavour_id reference the lookup tables but are not enforced as FK
-- constraints so this stays compatible with Redshift later
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
