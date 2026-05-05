import type { Queryable } from '../db/pool.js';
import { config } from '../config.js';
import type { MessagingNumber, NumberStatus, ProviderConfig } from '../types/domain.js';

interface NumberRow {
  id: string;
  phone_number: string;
  display_name: string | null;
  status: NumberStatus;
  daily_quota: number;
  max_daily_quota: number;
  ramp_rate: string | number;
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  provider_config: ProviderConfig | string | null;
  warmup_started_at: Date | null;
  paused_at: Date | null;
  auto_paused_reason: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface CreateNumberInput {
  phoneNumber: string;
  displayName?: string;
  maxDailyQuota?: number;
  timezone?: string;
  quietHoursStart?: string;
  quietHoursEnd?: string;
  webhookUrl?: string;
}

export interface WarmupReportRow {
  id: string;
  phoneNumber: string;
  displayName: string | null;
  status: NumberStatus;
  timezone: string;
  maxDailyQuota: number;
  currentDailyQuota: number;
  latestScheduleDate: string | null;
  latestScheduleQuota: number | null;
  latestSentCount: number | null;
  latestHealthScore: number | null;
  latestHealthAt: Date | null;
}

const parseProviderConfig = (value: ProviderConfig | string | null): ProviderConfig => {
  if (!value) return {};
  if (typeof value === 'string') return JSON.parse(value) as ProviderConfig;
  return value;
};

const mapNumber = (row: NumberRow): MessagingNumber => ({
  id: row.id,
  phoneNumber: row.phone_number,
  displayName: row.display_name,
  status: row.status,
  dailyQuota: Number(row.daily_quota),
  maxDailyQuota: Number(row.max_daily_quota),
  rampRate: Number(row.ramp_rate),
  timezone: row.timezone,
  quietHoursStart: String(row.quiet_hours_start),
  quietHoursEnd: String(row.quiet_hours_end),
  providerConfig: parseProviderConfig(row.provider_config),
  warmupStartedAt: row.warmup_started_at,
  pausedAt: row.paused_at,
  autoPausedReason: row.auto_paused_reason,
  createdAt: row.created_at,
  updatedAt: row.updated_at
});

export function normalizePhoneNumber(phoneNumber: string): string {
  const trimmed = phoneNumber.trim();
  const hasLeadingPlus = trimmed.startsWith('+');
  const digits = trimmed.replace(/\D/g, '');

  if (digits.length < 8 || digits.length > 16) {
    throw new Error('Phone number must contain between 8 and 16 digits.');
  }

  return `${hasLeadingPlus ? '+' : ''}${digits}`;
}

export async function createNumber(db: Queryable, input: CreateNumberInput): Promise<MessagingNumber> {
  const providerConfig: ProviderConfig = input.webhookUrl ? { webhookUrl: input.webhookUrl } : {};
  const result = await db.query<NumberRow>(
    `
      INSERT INTO numbers (
        phone_number,
        display_name,
        max_daily_quota,
        timezone,
        quiet_hours_start,
        quiet_hours_end,
        provider_config
      )
      VALUES ($1, $2, $3, $4, $5::time, $6::time, $7::jsonb)
      RETURNING *
    `,
    [
      normalizePhoneNumber(input.phoneNumber),
      input.displayName ?? null,
      input.maxDailyQuota ?? config.defaultMaxDailyQuota,
      input.timezone ?? config.defaultTimezone,
      input.quietHoursStart ?? '00:00',
      input.quietHoursEnd ?? '07:00',
      JSON.stringify(providerConfig)
    ]
  );

  return mapNumber(result.rows[0]);
}

export async function getNumberById(db: Queryable, id: string): Promise<MessagingNumber | null> {
  const result = await db.query<NumberRow>('SELECT * FROM numbers WHERE id = $1', [id]);
  return result.rows[0] ? mapNumber(result.rows[0]) : null;
}

export async function startNumberWarmup(db: Queryable, id: string): Promise<MessagingNumber | null> {
  const result = await db.query<NumberRow>(
    `
      UPDATE numbers
      SET status = 'warming',
          warmup_started_at = COALESCE(warmup_started_at, now()),
          paused_at = NULL,
          auto_paused_reason = NULL
      WHERE id = $1
      RETURNING *
    `,
    [id]
  );

  return result.rows[0] ? mapNumber(result.rows[0]) : null;
}

export async function pauseNumberWarmup(db: Queryable, id: string): Promise<MessagingNumber | null> {
  const result = await db.query<NumberRow>(
    `
      UPDATE numbers
      SET status = 'paused',
          paused_at = now()
      WHERE id = $1
      RETURNING *
    `,
    [id]
  );

  return result.rows[0] ? mapNumber(result.rows[0]) : null;
}

export async function autoPauseNumber(
  db: Queryable,
  id: string,
  reason: string
): Promise<MessagingNumber | null> {
  const result = await db.query<NumberRow>(
    `
      UPDATE numbers
      SET status = 'auto_paused',
          paused_at = now(),
          auto_paused_reason = $2
      WHERE id = $1
        AND status <> 'paused'
      RETURNING *
    `,
    [id, reason]
  );

  return result.rows[0] ? mapNumber(result.rows[0]) : null;
}

export async function getWarmupReport(db: Queryable): Promise<WarmupReportRow[]> {
  const result = await db.query<{
    id: string;
    phone_number: string;
    display_name: string | null;
    status: NumberStatus;
    timezone: string;
    max_daily_quota: number;
    daily_quota: number;
    latest_schedule_date: string | null;
    latest_schedule_quota: number | null;
    latest_sent_count: number | null;
    latest_health_score: number | null;
    latest_health_at: Date | null;
  }>(`
    SELECT
      n.id,
      n.phone_number,
      n.display_name,
      n.status,
      n.timezone,
      n.max_daily_quota,
      n.daily_quota,
      ws.schedule_date::text AS latest_schedule_date,
      ws.daily_quota AS latest_schedule_quota,
      ws.sent_count AS latest_sent_count,
      hs.score AS latest_health_score,
      hs.created_at AS latest_health_at
    FROM numbers n
    LEFT JOIN LATERAL (
      SELECT schedule_date, daily_quota, sent_count
      FROM warmup_schedule
      WHERE number_id = n.id
      ORDER BY schedule_date DESC
      LIMIT 1
    ) ws ON true
    LEFT JOIN LATERAL (
      SELECT score, created_at
      FROM health_snapshots
      WHERE number_id = n.id
      ORDER BY created_at DESC
      LIMIT 1
    ) hs ON true
    ORDER BY n.created_at DESC
  `);

  return result.rows.map((row) => ({
    id: row.id,
    phoneNumber: row.phone_number,
    displayName: row.display_name,
    status: row.status,
    timezone: row.timezone,
    maxDailyQuota: Number(row.max_daily_quota),
    currentDailyQuota: Number(row.daily_quota),
    latestScheduleDate: row.latest_schedule_date,
    latestScheduleQuota:
      row.latest_schedule_quota === null ? null : Number(row.latest_schedule_quota),
    latestSentCount: row.latest_sent_count === null ? null : Number(row.latest_sent_count),
    latestHealthScore:
      row.latest_health_score === null ? null : Number(row.latest_health_score),
    latestHealthAt: row.latest_health_at
  }));
}
