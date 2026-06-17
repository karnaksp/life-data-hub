# Managed Source Subscriptions

LifeHub has two source layers:

- `config/lifehub/source_registry.yaml` is the platform contract: source families, privacy rules, tables, consumers and onboarding expectations.
- `data/private/lifehub/source_subscriptions.json` is your local user-managed list of concrete links: Telegram channels, RSS feeds, news URLs, API JSON endpoints and event streams.

The public repo contains only `config/lifehub/source_subscriptions.example.json` and synthetic fixtures. Real links can be personal context, so they stay under `data/private/` and are ignored by git.

## Telegram Flow

Add a source by sending one command:

```text
/source_add https://t.me/s/some_public_channel label=MotoNews domain=moto tags=moto,spb
/source_add rss_feed https://example.com/feed.xml label=MarketFeed domain=trading tags=market,watchlist
/source_add https://example.com/news label=NewsPage domain=news tags=spb
/source_add event_stream https://example.com/events.jsonl label=EventStream domain=events tags=ops
```

Supported commands:

| Command | Purpose |
| --- | --- |
| `/source_add [type] <url> label=... domain=... tags=a,b` | Add or update a managed source. Type may be omitted and inferred from the URL. |
| `/source_list` | Show enabled/paused sources with short ids. |
| `/source_pause <id_prefix>` | Pause a source without deleting it. |
| `/source_resume <id_prefix>` | Enable a paused source. |
| `/source_remove <id_prefix>` | Remove a source from the local list. |
| `/source_sync [id_prefix]` | Fetch enabled sources and write privacy-safe `external_source_items` events to landing. |

## CLI Flow

The same operations are available locally:

```bash
PYTHONPATH=infra/lifehub python -m lifehub.cli source-add \
  https://example.com/feed.xml \
  --label DemoFeed \
  --domain news \
  --tags news,demo

PYTHONPATH=infra/lifehub python -m lifehub.cli source-list

PYTHONPATH=infra/lifehub python -m lifehub.cli source-sync \
  --fetch \
  --output-root tmp/lake
```

For reproducible fixture proof:

```bash
make lifehub-source-subscription-demo
```

## Source Type Inference

| Input | Type |
| --- | --- |
| `https://t.me/...` or `https://telegram.me/...` | `telegram_channel` |
| URL containing `rss`, `feed`, `.rss`, `.xml`, `.atom` | `rss_feed` |
| `ws://`, `wss://`, or URL path containing `stream`/`events` | `event_stream` |
| URL ending in `.json` or containing `/api/` | `api_json` |
| Other `http(s)` URL | `news_url` |

## Storage Contract

Concrete subscriptions are local. Landing events use source `external_source_items` and keep raw URLs out of payloads:

- `reference_hash` and `item_url_hash` instead of raw URLs;
- `reference_host` for coarse provenance;
- short `title_preview` in `payload_summary` for public RSS/news usefulness;
- `tags`, `domain`, `source_type` and `subscription_id` for routing;
- `quality_flags` for parse/fetch status.

This keeps adding a Telegram channel or RSS feed a user operation rather than a code change, while the platform still has one stable medallion contract.
