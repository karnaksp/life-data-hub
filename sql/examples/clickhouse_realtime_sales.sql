-- Target-state realtime sales examples.
-- Engine: ClickHouse.
-- Tables are populated by infra/clickhouse/init/002_kafka_event_ingestion.sql.

select
    toStartOfMinute(event_time) as minute,
    count() as orders,
    round(sum(amount), 2) as gross_sales,
    uniqExact(user_id) as active_customers
from analytics.orders
where event_time >= now() - interval 1 hour
group by minute
order by minute desc
limit 60;

select
    payment_status,
    count() as payments,
    round(count() / sum(count()) over (), 4) as share
from analytics.payments
where event_time >= now() - interval 1 day
group by payment_status
order by payments desc;

select
    product_id,
    sum(quantity_delta) as net_inventory_delta,
    count() as inventory_events
from analytics.inventory_changes
where event_time >= now() - interval 1 day
group by product_id
having abs(net_inventory_delta) > 25
order by abs(net_inventory_delta) desc
limit 50;
