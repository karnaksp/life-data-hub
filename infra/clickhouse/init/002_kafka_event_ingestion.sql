CREATE TABLE IF NOT EXISTS analytics.kafka_orders
(
    order_id String,
    user_id String,
    product_id String,
    amount Float64,
    currency String,
    ts DateTime64(3, 'UTC')
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'orders.v1',
    kafka_group_name = 'clickhouse_orders_sink_v1',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081';

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_kafka_orders_to_orders
TO analytics.orders
AS
SELECT
    ts AS event_time,
    order_id,
    user_id,
    product_id,
    toDecimal64(amount, 2) AS amount,
    currency,
    now() AS ingested_at
FROM analytics.kafka_orders;

CREATE TABLE IF NOT EXISTS analytics.kafka_payments
(
    payment_id String,
    order_id String,
    method String,
    status String,
    ts DateTime64(3, 'UTC')
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'payments.v1',
    kafka_group_name = 'clickhouse_payments_sink_v1',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081';

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_kafka_payments_to_payments
TO analytics.payments
AS
SELECT
    ts AS event_time,
    payment_id,
    order_id,
    method AS payment_method,
    status AS payment_status,
    now() AS ingested_at
FROM analytics.kafka_payments;

CREATE TABLE IF NOT EXISTS analytics.kafka_inventory_changes
(
    change_id String,
    warehouse_id String,
    product_id String,
    change_type String,
    quantity_delta Int32,
    previous_qty Int32,
    new_qty Int32,
    reason Nullable(String),
    order_id Nullable(String),
    supplier_id Nullable(String),
    cost_per_unit Nullable(Float64),
    ts DateTime64(3, 'UTC')
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'inventory-changes.v1',
    kafka_group_name = 'clickhouse_inventory_changes_sink_v1',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081';

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_kafka_inventory_changes_to_inventory_changes
TO analytics.inventory_changes
AS
SELECT
    ts AS event_time,
    change_id,
    warehouse_id,
    product_id,
    change_type,
    quantity_delta,
    previous_qty,
    new_qty,
    reason,
    order_id,
    supplier_id,
    if(isNull(cost_per_unit), NULL, toDecimal64(cost_per_unit, 2)) AS cost_per_unit,
    now() AS ingested_at
FROM analytics.kafka_inventory_changes;
