import { describe, expect, it } from 'vitest';
import {
  calculateDailyQuota,
  hasQuotaRemaining,
  remainingQuota
} from '../src/services/quota.js';

describe('quota ramp-up', () => {
  it('starts at 20 and grows 20 percent per local day', () => {
    const base = {
      warmupStartedAt: '2026-05-01',
      timezone: 'America/Sao_Paulo',
      initialDailyQuota: 20,
      maxDailyQuota: 500,
      rampRate: 0.2
    };

    expect(calculateDailyQuota({ ...base, targetDate: '2026-05-01' })).toBe(20);
    expect(calculateDailyQuota({ ...base, targetDate: '2026-05-02' })).toBe(24);
    expect(calculateDailyQuota({ ...base, targetDate: '2026-05-03' })).toBe(28);
    expect(calculateDailyQuota({ ...base, targetDate: '2026-05-04' })).toBe(34);
  });

  it('caps quota growth at the configured maximum', () => {
    const quota = calculateDailyQuota({
      warmupStartedAt: '2026-05-01',
      targetDate: '2026-05-30',
      timezone: 'America/Sao_Paulo',
      initialDailyQuota: 20,
      maxDailyQuota: 100,
      rampRate: 0.2
    });

    expect(quota).toBe(100);
  });

  it('calculates remaining quota without going negative', () => {
    expect(remainingQuota(20, 0)).toBe(20);
    expect(remainingQuota(20, 19)).toBe(1);
    expect(remainingQuota(20, 20)).toBe(0);
    expect(remainingQuota(20, 25)).toBe(0);
    expect(hasQuotaRemaining(20, 19)).toBe(true);
    expect(hasQuotaRemaining(20, 20)).toBe(false);
  });
});
