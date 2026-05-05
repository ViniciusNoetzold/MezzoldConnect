import type pg from 'pg';
import type { Queryable } from '../db/pool.js';
import { calculateDailyQuota, localDateISO } from '../services/quota.js';
import type { MessagingNumber, WarmupSchedule, WarmupScheduleStatus } from '../types/domain.js';

interface ScheduleRow {
  id: string;
  number_id: string;
  schedule_date: string;
  daily_quota: number;
  sent_count: number;
  status: WarmupScheduleStatus;
  created_at: Date;
  updated_at: Date;
}

export interface QuotaReservation {
  reserved: boolean;
  schedule: WarmupSchedule;
}

const mapSchedule = (row: ScheduleRow): WarmupSchedule => ({
  id: row.id,
  numberId: row.number_id,
  scheduleDate: row.schedule_date,
  dailyQuota: Number(row.daily_quota),
  sentCount: Number(row.sent_count),
  status: row.status,
  createdAt: row.created_at,
  updatedAt: row.updated_at
});

export async function getOrCreateSchedule(
  db: Queryable,
  number: MessagingNumber,
  targetDate: Date
): Promise<WarmupSchedule> {
  const scheduleDate = localDateISO(targetDate, number.timezone);
  const warmupStartedAt = number.warmupStartedAt ?? targetDate;
  const dailyQuota = calculateDailyQuota({
    warmupStartedAt,
    targetDate,
    timezone: number.timezone,
    initialDailyQuota: number.dailyQuota,
    maxDailyQuota: number.maxDailyQuota,
    rampRate: number.rampRate
  });

  const result = await db.query<ScheduleRow>(
    `
      INSERT INTO warmup_schedule(number_id, schedule_date, daily_quota, status)
      VALUES ($1, $2::date, $3, 'pending')
      ON CONFLICT (number_id, schedule_date)
      DO UPDATE SET daily_quota = EXCLUDED.daily_quota
      RETURNING
        id,
        number_id,
        schedule_date::text AS schedule_date,
        daily_quota,
        sent_count,
        status,
        created_at,
        updated_at
    `,
    [number.id, scheduleDate, dailyQuota]
  );

  return mapSchedule(result.rows[0]);
}

export async function getScheduleForDate(
  db: Queryable,
  numberId: string,
  scheduleDate: string
): Promise<WarmupSchedule | null> {
  const result = await db.query<ScheduleRow>(
    `
      SELECT
        id,
        number_id,
        schedule_date::text AS schedule_date,
        daily_quota,
        sent_count,
        status,
        created_at,
        updated_at
      FROM warmup_schedule
      WHERE number_id = $1 AND schedule_date = $2::date
    `,
    [numberId, scheduleDate]
  );

  return result.rows[0] ? mapSchedule(result.rows[0]) : null;
}

export async function reserveQuotaSlot(
  client: pg.PoolClient,
  number: MessagingNumber,
  now: Date
): Promise<QuotaReservation> {
  const schedule = await getOrCreateSchedule(client, number, now);
  const locked = await client.query<ScheduleRow>(
    `
      SELECT
        id,
        number_id,
        schedule_date::text AS schedule_date,
        daily_quota,
        sent_count,
        status,
        created_at,
        updated_at
      FROM warmup_schedule
      WHERE id = $1
      FOR UPDATE
    `,
    [schedule.id]
  );
  const current = mapSchedule(locked.rows[0]);

  if (current.sentCount >= current.dailyQuota) {
    return { reserved: false, schedule: current };
  }

  const updated = await client.query<ScheduleRow>(
    `
      UPDATE warmup_schedule
      SET sent_count = sent_count + 1,
          status = CASE
            WHEN sent_count + 1 >= daily_quota THEN 'completed'
            ELSE 'running'
          END
      WHERE id = $1
      RETURNING
        id,
        number_id,
        schedule_date::text AS schedule_date,
        daily_quota,
        sent_count,
        status,
        created_at,
        updated_at
    `,
    [current.id]
  );

  return { reserved: true, schedule: mapSchedule(updated.rows[0]) };
}

export async function pauseSchedulesForNumber(db: Queryable, numberId: string): Promise<void> {
  await db.query(
    `
      UPDATE warmup_schedule
      SET status = 'paused'
      WHERE number_id = $1
        AND status IN ('pending', 'running')
    `,
    [numberId]
  );
}
