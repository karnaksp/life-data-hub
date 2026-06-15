# Documentation Guidelines - Data Forge

Data Forge - локальная reference-платформа для retail CDC, streaming ingestion, lakehouse checks и аналитических sinks. В документации важны не эффектные формулировки, а воспроизводимые команды, понятные ограничения и проверяемый runtime contract.

---

## Goals

- **Clarity** - пишем для будущего себя и teammates, а не для впечатления.
- **Pragmatism** - каждая строка должна помогать запустить, debug-ить или расширить stack.
- **Consistency** - одинаковый стиль для services и profiles: `core`, `airflow`, `explore`.

---

## Tone

- Спокойно, коротко, без hype.
- Explain, don’t sell. Reader умный, но уставший.
- Fact -> context: сначала command/config, затем зачем это нужно.

Пример:

> Wrong: “Kafka is the backbone of streaming at internet scale!”
> Correct: “Kafka provides the message bus for Debezium CDC events into Spark and ClickHouse.”

---

## Structure of Every Doc

1. **Title** - короткий и фактический.
2. **Why** - одно предложение, зачем нужен service/module.
3. **How** - instructions, configs, `docker compose` profiles.
4. **Notes** - gotchas, caveats или links to deeper docs.

---

## Copilot And AI Usage

- Относитесь к Copilot как к junior teammate: быстро scaffold-ит, но слаб в decisions.
- Всегда упрощайте и заново объясняйте AI-generated blocks.
- Если raw Copilot snippets остаются в docs, явно помечайте их.

---

## Styling

- Не используйте decoration ради decoration.
- Markdown tables нужны для contracts, services, topics и evidence.
- Code fences должны содержать runnable commands или минимальные snippets.
- Links должны вести на реальные files, docs pages или external references.

---

## Examples

Good:

```markdown
## Running Airflow (profile: airflow)

To start all Airflow services:

docker compose --profile airflow up -d

Note: requires `postgres` and `redis` profiles enabled and healthy.
```

Bad:

```markdown
## Airflow is awesome!!!

Just run docker-compose up and it should work lol
```
