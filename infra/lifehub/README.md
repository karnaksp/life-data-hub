# LifeHub

Why: Local-only sports and wellbeing data product for Saint Petersburg outdoor readiness and Telegram diary digests.

## Profile

- `lifehub`

## How

- Fixture smoke without tokens:
  - `make lifehub-score-fixture`
  - `make lifehub-demo`
- Local stack:
  - `cp .env.example .env`
  - Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` only in `.env`.
  - `docker compose --profile lifehub up -d`

## Services

- `lifehub-weather-ingest`: fetches Open-Meteo weather or fixture weather.
- `lifehub-place-sync`: loads public OSM/Overpass spot candidates, with config fallback.
- `lifehub-score`: computes readiness scores and explanations.
- `lifehub-telegram-bot`: handles `/today`, `/spots`, `/week`, `/log`, and the daily digest.
- `scripts/capture_lifehub_evidence.py`: captures redacted runtime counts.

## Notes

- Real Telegram tokens and activity logs stay local.
- Demo fixtures are synthetic and safe to commit.
- The MVP does not use Strava, market signals, or private locations.
