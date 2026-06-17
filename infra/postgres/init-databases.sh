#!/bin/bash
set -euo pipefail

PGHOST="${POSTGRES_HOST:-localhost}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-postgres}"
REPLICATION_ROLE="${POSTGRES_CDC_USER:-cdc_reader}"
REPLICATION_PASSWORD="${POSTGRES_CDC_PASSWORD:-cdc_reader_pwd}"

escape_sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

escape_sql_identifier() {
  printf "%s" "$1" | sed 's/"/""/g'
}

echo "Checking/creating required databases..."

until pg_isready -U "$PGUSER" -d "$PGDB" -h "$PGHOST" >/dev/null 2>&1; do
  echo "Waiting for PostgreSQL to be ready..."
  sleep 2
done

if ! psql -U "$PGUSER" -d "$PGDB" -tAc "SELECT 1 FROM pg_database WHERE datname = 'demo'" | grep -q 1; then
  echo "Creating demo database..."
  psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 -c "CREATE DATABASE demo;"
fi

echo "Configuring logical replication parameters..."
psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 <<'EOSQL'
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_replication_slots = '16';
ALTER SYSTEM SET max_wal_senders = '16';
ALTER SYSTEM SET wal_keep_size = '256MB';
SELECT pg_reload_conf();
EOSQL

echo "Ensuring logical replication role exists..."
escaped_role_literal=$(escape_sql_literal "$REPLICATION_ROLE")
escaped_role_identifier=$(escape_sql_identifier "$REPLICATION_ROLE")
escaped_pwd_literal=$(escape_sql_literal "$REPLICATION_PASSWORD")

role_exists=$(psql -U "$PGUSER" -d "$PGDB" -At -v ON_ERROR_STOP=1 \
  -c "SELECT 1 FROM pg_roles WHERE rolname = '${escaped_role_literal}' LIMIT 1;")
role_exists=$(printf "%s" "$role_exists" | tr -d '[:space:]')

if [[ "$role_exists" != "1" ]]; then
  psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE \"${escaped_role_identifier}\" WITH LOGIN PASSWORD '${escaped_pwd_literal}' REPLICATION;"
else
  psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 \
    -c "ALTER ROLE \"${escaped_role_identifier}\" WITH LOGIN PASSWORD '${escaped_pwd_literal}' REPLICATION;"
fi

echo "Ensuring demo tables exist..."
psql -U "$PGUSER" -d demo -v ON_ERROR_STOP=1 -v replication_role="$REPLICATION_ROLE" <<EOSQL
-- ===== Core OLTP tables (match generator canvas) =====

CREATE TABLE IF NOT EXISTS users(
  user_id    TEXT PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  country    TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products(
  product_id TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  category   TEXT,
  price_usd  NUMERIC(10,2),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Legacy/global inventory snapshot (kept for simple sums)
CREATE TABLE IF NOT EXISTS inventory(
  product_id TEXT PRIMARY KEY REFERENCES products(product_id),
  qty        INT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouses(
  warehouse_id TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  country      TEXT,
  region       TEXT
);

CREATE TABLE IF NOT EXISTS suppliers(
  supplier_id TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  country     TEXT,
  rating      NUMERIC(3,2)
);

CREATE TABLE IF NOT EXISTS customer_segments(
  user_id         TEXT PRIMARY KEY REFERENCES users(user_id),
  segment         TEXT,
  lifetime_value  NUMERIC(12,2)
);

-- Multi-location stock (authoritative inventory-by-location)
CREATE TABLE IF NOT EXISTS warehouse_inventory(
  warehouse_id TEXT REFERENCES warehouses(warehouse_id),
  product_id   TEXT REFERENCES products(product_id),
  qty          INT NOT NULL,
  reserved_qty INT NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (warehouse_id, product_id)
);

CREATE TABLE IF NOT EXISTS product_suppliers(
  product_id      TEXT REFERENCES products(product_id),
  supplier_id     TEXT REFERENCES suppliers(supplier_id),
  cost_usd        NUMERIC(10,2),
  lead_time_days  INT,
  PRIMARY KEY(product_id, supplier_id)
);

-- ===== LifeHub local-only sports and wellbeing tables =====
CREATE TABLE IF NOT EXISTS life_user_preferences(
  preference_key   TEXT PRIMARY KEY,
  preference_value TEXT NOT NULL,
  updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_spots(
  spot_id    TEXT PRIMARY KEY,
  label      TEXT NOT NULL,
  latitude   DOUBLE PRECISION NOT NULL,
  longitude  DOUBLE PRECISION NOT NULL,
  tags       TEXT[] NOT NULL DEFAULT '{}',
  source     TEXT NOT NULL DEFAULT 'config',
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_activity_log(
  activity_id   BIGSERIAL PRIMARY KEY,
  activity_type TEXT NOT NULL CHECK (
    activity_type IN ('skate', 'snowboard', 'volleyball', 'moto_lesson', 'gym', 'walk', 'rest')
  ),
  start_time     TIMESTAMPTZ,
  end_time       TIMESTAMPTZ,
  location_label TEXT,
  intensity      INT CHECK (intensity BETWEEN 1 AND 10),
  mood           INT CHECK (mood BETWEEN 1 AND 10),
  fatigue        INT CHECK (fatigue BETWEEN 1 AND 10),
  pain_flag      BOOLEAN NOT NULL DEFAULT false,
  pain_text      TEXT,
  result         TEXT CHECK (result IN ('good', 'ok', 'bad', 'skipped')),
  notes          TEXT,
  logged_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_digest_runs(
  digest_id    BIGSERIAL PRIMARY KEY,
  digest_type  TEXT NOT NULL,
  sent_to      TEXT,
  status       TEXT NOT NULL CHECK (status IN ('planned', 'sent', 'skipped', 'failed')),
  summary      TEXT,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_recommendation_events(
  recommendation_id   BIGSERIAL PRIMARY KEY,
  recommendation_type TEXT NOT NULL,
  activity            TEXT NOT NULL,
  location_id         TEXT NOT NULL,
  score               INT NOT NULL CHECK (score BETWEEN 0 AND 100),
  decision            TEXT NOT NULL CHECK (decision IN ('go', 'caution', 'recover')),
  reasons             TEXT NOT NULL,
  generated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_decision_feedback(
  feedback_id BIGSERIAL PRIMARY KEY,
  activity    TEXT NOT NULL,
  action      TEXT NOT NULL CHECK (action IN ('followed', 'skipped', 'changed')),
  result      TEXT CHECK (result IN ('good', 'ok', 'bad', 'skipped')),
  note        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_signal_events(
  signal_id   TEXT PRIMARY KEY,
  domain      TEXT NOT NULL CHECK (domain IN ('market', 'github', 'career', 'wellbeing', 'system')),
  source      TEXT NOT NULL,
  title       TEXT NOT NULL,
  direction   TEXT NOT NULL CHECK (direction IN ('positive', 'negative', 'neutral')),
  urgency     INT NOT NULL CHECK (urgency BETWEEN 1 AND 10),
  confidence  INT NOT NULL CHECK (confidence BETWEEN 1 AND 100),
  summary     TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS life_daily_context_profiles(
  profile_date            DATE NOT NULL,
  timezone                TEXT NOT NULL,
  top_activity            TEXT NOT NULL,
  top_decision            TEXT NOT NULL CHECK (top_decision IN ('go', 'caution', 'recover')),
  top_score               INT NOT NULL CHECK (top_score BETWEEN 0 AND 100),
  readiness_state         TEXT NOT NULL,
  sessions_7d             INT NOT NULL CHECK (sessions_7d >= 0),
  avg_mood_7d             NUMERIC(4,2) NOT NULL CHECK (avg_mood_7d BETWEEN 0 AND 10),
  avg_fatigue_7d          NUMERIC(4,2) NOT NULL CHECK (avg_fatigue_7d BETWEEN 0 AND 10),
  pain_sessions_7d        INT NOT NULL CHECK (pain_sessions_7d >= 0),
  useful_decision_days_7d INT NOT NULL CHECK (useful_decision_days_7d BETWEEN 0 AND 7),
  follow_rate_7d          NUMERIC(5,3) NOT NULL CHECK (follow_rate_7d BETWEEN 0 AND 1),
  open_goal_count         INT NOT NULL CHECK (open_goal_count >= 0),
  signal_count_7d         INT NOT NULL CHECK (signal_count_7d >= 0),
  highest_signal_domain   TEXT NOT NULL,
  highest_signal_urgency  INT NOT NULL CHECK (highest_signal_urgency BETWEEN 0 AND 10),
  context_summary         TEXT NOT NULL,
  generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_date, timezone)
);

-- ===== Indexes (idempotent) =====
CREATE INDEX IF NOT EXISTS idx_users_country         ON users(country);
CREATE INDEX IF NOT EXISTS idx_users_created         ON users(created_at);

CREATE INDEX IF NOT EXISTS ix_products_category      ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_updated      ON products(updated_at);

CREATE INDEX IF NOT EXISTS idx_inventory_qty         ON inventory(qty);
CREATE INDEX IF NOT EXISTS idx_inventory_updated     ON inventory(updated_at);

CREATE INDEX IF NOT EXISTS idx_warehouses_country    ON warehouses(country);
CREATE INDEX IF NOT EXISTS idx_suppliers_country     ON suppliers(country);
CREATE INDEX IF NOT EXISTS idx_suppliers_rating      ON suppliers(rating);

CREATE INDEX IF NOT EXISTS idx_product_suppliers_cost ON product_suppliers(cost_usd);

CREATE INDEX IF NOT EXISTS ix_whinv_product          ON warehouse_inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_warehouse_inventory_qty ON warehouse_inventory(qty);

CREATE INDEX IF NOT EXISTS idx_customer_segments_segment ON customer_segments(segment);
CREATE INDEX IF NOT EXISTS idx_customer_segments_ltv     ON customer_segments(lifetime_value);
CREATE INDEX IF NOT EXISTS idx_life_activity_logged       ON life_activity_log(logged_at);
CREATE INDEX IF NOT EXISTS idx_life_activity_type         ON life_activity_log(activity_type);
CREATE INDEX IF NOT EXISTS idx_life_spots_tags            ON life_spots USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_life_recommendation_generated ON life_recommendation_events(generated_at);
CREATE INDEX IF NOT EXISTS idx_life_recommendation_activity  ON life_recommendation_events(activity);
CREATE INDEX IF NOT EXISTS idx_life_feedback_created         ON life_decision_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_life_feedback_activity        ON life_decision_feedback(activity);
CREATE INDEX IF NOT EXISTS idx_life_signal_occurred          ON life_signal_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_life_signal_domain            ON life_signal_events(domain);
CREATE INDEX IF NOT EXISTS idx_life_daily_context_generated  ON life_daily_context_profiles(generated_at);

-- ===== Grants (safe if run multiple times) =====
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO "$PGUSER";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "$PGUSER";

-- Ensure future objects are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES    TO "$PGUSER";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO "$PGUSER";

GRANT CONNECT ON DATABASE demo TO :"replication_role";
GRANT USAGE ON SCHEMA public TO :"replication_role";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"replication_role";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO :"replication_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO :"replication_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO :"replication_role";
EOSQL

echo "Ensuring CDC publication exists..."
publication_exists=$(psql -U "$PGUSER" -d demo -At -v ON_ERROR_STOP=1 \
  -c "SELECT 1 FROM pg_publication WHERE pubname = 'demo_publication' LIMIT 1;")
publication_exists=$(printf "%s" "$publication_exists" | tr -d '[:space:]')

if [[ "$publication_exists" != "1" ]]; then
  psql -U "$PGUSER" -d demo -v ON_ERROR_STOP=1 \
    -c "CREATE PUBLICATION demo_publication FOR TABLES IN SCHEMA public;"
else
  psql -U "$PGUSER" -d demo -v ON_ERROR_STOP=1 \
    -c "ALTER PUBLICATION demo_publication SET TABLES IN SCHEMA public;"
fi

echo "Database setup complete!"
