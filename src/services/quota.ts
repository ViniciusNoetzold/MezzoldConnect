import { DateTime } from 'luxon';

export const INITIAL_DAILY_QUOTA = 20;
export const DEFAULT_RAMP_RATE = 0.2;

export interface QuotaCalculationInput {
  warmupStartedAt: Date | string;
  targetDate: Date | string;
  timezone: string;
  initialDailyQuota?: number;
  maxDailyQuota: number;
  rampRate?: number;
}

const asLocalDateTime = (value: Date | string, timezone: string): DateTime => {
  if (value instanceof Date) {
    return DateTime.fromJSDate(value, { zone: timezone }).startOf('day');
  }

  return DateTime.fromISO(value, { zone: timezone }).startOf('day');
};

const dayIndex = (date: DateTime): number =>
  Math.floor(Date.UTC(date.year, date.month - 1, date.day) / 86_400_000);

export const localDateISO = (value: Date, timezone: string): string =>
  DateTime.fromJSDate(value, { zone: timezone }).toISODate() ?? '';

export function calculateDailyQuota(input: QuotaCalculationInput): number {
  const initialDailyQuota = input.initialDailyQuota ?? INITIAL_DAILY_QUOTA;
  const rampRate = input.rampRate ?? DEFAULT_RAMP_RATE;
  const start = asLocalDateTime(input.warmupStartedAt, input.timezone);
  const target = asLocalDateTime(input.targetDate, input.timezone);
  const elapsedDays = Math.max(0, dayIndex(target) - dayIndex(start));
  const grownQuota = Math.floor(initialDailyQuota * (1 + rampRate) ** elapsedDays);

  return Math.max(0, Math.min(input.maxDailyQuota, grownQuota));
}

export function remainingQuota(dailyQuota: number, sentCount: number): number {
  return Math.max(0, dailyQuota - sentCount);
}

export function hasQuotaRemaining(dailyQuota: number, sentCount: number): boolean {
  return remainingQuota(dailyQuota, sentCount) > 0;
}
