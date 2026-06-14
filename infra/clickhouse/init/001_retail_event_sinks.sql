CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.orders
(
    event_time DateTime64(3, 'UTC'),
    order_id String,
    user_id String,
    product_id String,
    amount Decimal(12, 2),
    currency LowCardinality(String),
    ingested_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_time, order_id);

CREATE TABLE IF NOT EXISTS analytics.payments
(
    event_time DateTime64(3, 'UTC'),
    payment_id String,
    order_id String,
    payment_method LowCardinality(String),
    payment_status LowCardinality(String),
    ingested_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_time, payment_status, payment_id);

CREATE TABLE IF NOT EXISTS analytics.inventory_changes
(
    event_time DateTime64(3, 'UTC'),
    change_id String,
    warehouse_id String,
    product_id String,
    change_type LowCardinality(String),
    quantity_delta Int32,
    previous_qty Int32,
    new_qty Int32,
    reason Nullable(String),
    order_id Nullable(String),
    supplier_id Nullable(String),
    cost_per_unit Nullable(Decimal(12, 2)),
    ingested_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_time, product_id, warehouse_id, change_id);
