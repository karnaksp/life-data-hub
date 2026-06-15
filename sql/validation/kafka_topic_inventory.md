# Проверка Kafka topics

Запускайте после `docker compose --profile core --profile datagen up -d`.

```bash
docker compose exec kafka bash
kafka-topics.sh --bootstrap-server kafka:9092 --list
```

Ожидаемые topics бизнес-событий:

- `orders.v1`
- `payments.v1`
- `shipments.v1`
- `inventory-changes.v1`
- `customer-interactions.v1`

Ожидаемые Debezium CDC topics после запуска connector:

- `demo.public.users`
- `demo.public.products`
- `demo.public.inventory`
- `demo.public.warehouse_inventory`
- `demo.public.suppliers`
- `demo.public.customer_segments`
- `demo.public.product_suppliers`
- `demo.public.warehouses`

Проверить topic:

```bash
kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic orders.v1
```

Прочитать несколько records:

```bash
kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic orders.v1 \
  --from-beginning \
  --max-messages 5
```

Контракт проверки:

| Проверка | Ожидаемый результат |
| --- | --- |
| Business topics exist | присутствуют все пять generator topics |
| CDC topics exist | присутствуют как минимум `demo.public.users`, `demo.public.products`, `demo.public.inventory` |
| Messages are arriving | `orders.v1` и `customer-interactions.v1` возвращают records во время короткого запуска |
| Keys are stable | order topic keys выглядят как `ord_*`; inventory topic keys выглядят как `WH*:P*` |
| Schema Registry has subjects | subjects существуют для generated Avro topics |

Проверка Schema Registry:

```bash
curl -s http://localhost:8081/subjects | jq .
```
