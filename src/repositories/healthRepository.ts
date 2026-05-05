import { DateTime } from 'luxon';
import type { Queryable } from '../db/pool.js';
import { config } from '../config.js';
import { autoPauseNumber } from './numbersRepository.js';
import {
  calculateCompositeHealthScore,
  calculateHealthMetrics,
  shouldAutoPause
} from '../services/healthScoring.js';
import type { HealthSnapshot } from '../types/domain.js';

interface HealthSnapshotRow {
  id: string;
  number_id: string;
  delivery_rate: string | number;
  failure_rate: string | number;
  response_rate: string | number;
  opt_out_rate: string | number;
  score: number;
  window_start: Date;
  window_end: Date;
  created_at: Date;
}

const mapSnapshot = (row: HealthSnapshotRow): HealthSnapshot => ({
  id: row.id,
  numberId: row.number_id,
  deliveryRate: Number(row.delivery_rate),
  failureRate: Number(row.failure_rate),
  responseRate: Number(row.response_rate),
  optOutRate: Number(row.opt_out_rate),
  score: Number(row.score),
  windowStart: row.window_start,
  windowEnd: row.window_end,
  createdAt: row.created_at
});

export async function createHealthSnapshot(
  db: Queryable,
  numberId: string,
  windowDays = config.healthWindowDays
): Promise<HealthSnapshot> {
  const windowEnd = new Date();
  const windowStart = DateTime.fromJSDate(windowEnd).minus({ days: windowDays }).toJSDate();

  const countsResult = await db.query<{
    sent: string;
    delivered: string;
    failed: string;
    responded: string;
    opt_out: string;
  }>(
    `
      SELECT
        COUNT(*) FILTER (WHERE event_type = 'sent')::int AS sent,
        COUNT(*) FILTER (WHERE event_type = 'delivered')::int AS delivered,
        COUNT(*) FILTER (WHERE event_type = 'failed')::int AS failed,
        COUNT(*) FILTER (WHERE event_type = 'responded')::int AS responded,
        COUNT(*) FILTER (WHERE event_type = 'opt_out')::int AS opt_out
      FROM send_events
      WHERE number_id = $1
        AND occurred_at >= $2
        AND occurred_at <= $3
    `,
    [numberId, windowStart, windowEnd]
  );

  const counts = countsResult.rows[0];
  const metrics = calculateHealthMetrics({
    sent: Number(counts.sent),
    delivered: Number(counts.delivered),
    failed: Number(counts.failed),
    responded: Number(counts.responded),
    optOut: Number(counts.opt_out)
  });
  const score = calculateCompositeHealthScore(metrics);

  const snapshotResult = await db.query<HealthSnapshotRow>(
    `
      INSERT INTO health_snapshots (
        number_id,
        delivery_rate,
        failure_rate,
        response_rate,
        opt_out_rate,
        score,
        window_start,
        window_end
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      RETURNING *
    `,
    [
      numberId,
      metrics.deliveryRate,
      metrics.failureRate,
      metrics.responseRate,
      metrics.optOutRate,
      score,
      windowStart,
      windowEnd
    ]
  );

  if (shouldAutoPause(score)) {
    await autoPauseNumber(db, numberId, `Health score ${score} is below auto-pause threshold 40.`);
  }

  return mapSnapshot(snapshotResult.rows[0]);
}

export async function getLatestHealthSnapshot(
  db: Queryable,
  numberId: string
): Promise<HealthSnapshot | null> {
  const result = await db.query<HealthSnapshotRow>(
    `
      SELECT *
      FROM health_snapshots
      WHERE number_id = $1
      ORDER BY created_at DESC
      LIMIT 1
    `,
    [numberId]
  );

  return result.rows[0] ? mapSnapshot(result.rows[0]) : null;
}
