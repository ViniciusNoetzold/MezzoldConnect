CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS numbers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_number text NOT NULL UNIQUE,
  display_name text,
  status text NOT NULL DEFAULT 'registered'
    CHECK (status IN ('registered', 'warming', 'paused', 'auto_paused')),
  daily_quota integer NOT NULL DEFAULT 20 CHECK (daily_quota >= 0),
  max_daily_quota integer NOT NULL DEFAULT 500 CHECK (max_daily_quota >= 20),
  ramp_rate numeric(8, 4) NOT NULL DEFAULT 0.20 CHECK (ramp_rate >= 0),
  timezone text NOT NULL DEFAULT 'America/Sao_Paulo',
  quiet_hours_start time NOT NULL DEFAULT TIME '00:00',
  quiet_hours_end time NOT NULL DEFAULT TIME '07:00',
  provider_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  warmup_started_at timestamptz,
  paused_at timestamptz,
  auto_paused_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warmup_schedule (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  number_id uuid NOT NULL REFERENCES numbers(id) ON DELETE CASCADE,
  schedule_date date NOT NULL,
  daily_quota integer NOT NULL CHECK (daily_quota >= 0),
  sent_count integer NOT NULL DEFAULT 0 CHECK (sent_count >= 0),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'paused', 'completed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (number_id, schedule_date)
);

CREATE TABLE IF NOT EXISTS send_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  number_id uuid NOT NULL REFERENCES numbers(id) ON DELETE CASCADE,
  recipient text,
  template text,
  rendered_message text,
  event_type text NOT NULL
    CHECK (event_type IN ('queued', 'sent', 'delivered', 'failed', 'responded', 'opt_out', 'skipped')),
  provider_message_id text,
  error_message text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  number_id uuid NOT NULL REFERENCES numbers(id) ON DELETE CASCADE,
  delivery_rate numeric(7, 4) NOT NULL CHECK (delivery_rate >= 0 AND delivery_rate <= 1),
  failure_rate numeric(7, 4) NOT NULL CHECK (failure_rate >= 0 AND failure_rate <= 1),
  response_rate numeric(7, 4) NOT NULL CHECK (response_rate >= 0 AND response_rate <= 1),
  opt_out_rate numeric(7, 4) NOT NULL CHECK (opt_out_rate >= 0 AND opt_out_rate <= 1),
  score integer NOT NULL CHECK (score >= 0 AND score <= 100),
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_warmup_schedule_number_date
  ON warmup_schedule(number_id, schedule_date DESC);

CREATE INDEX IF NOT EXISTS idx_send_events_number_time
  ON send_events(number_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_send_events_number_type_time
  ON send_events(number_id, event_type, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_number_time
  ON health_snapshots(number_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_numbers_updated_at ON numbers;
CREATE TRIGGER trg_numbers_updated_at
BEFORE UPDATE ON numbers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_warmup_schedule_updated_at ON warmup_schedule;
CREATE TRIGGER trg_warmup_schedule_updated_at
BEFORE UPDATE ON warmup_schedule
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
