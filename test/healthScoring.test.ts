import { describe, expect, it } from 'vitest';
import {
  calculateCompositeHealthScore,
  calculateHealthMetrics,
  shouldAutoPause
} from '../src/services/healthScoring.js';

describe('health scoring', () => {
  it('keeps a new number above the auto-pause threshold before events exist', () => {
    const metrics = calculateHealthMetrics({
      sent: 0,
      delivered: 0,
      failed: 0,
      responded: 0,
      optOut: 0
    });

    expect(metrics).toEqual({
      deliveryRate: 1,
      failureRate: 0,
      responseRate: 0,
      optOutRate: 0
    });
    expect(calculateCompositeHealthScore(metrics)).toBe(85);
    expect(shouldAutoPause(calculateCompositeHealthScore(metrics))).toBe(false);
  });

  it('rewards delivery reliability and responses while penalizing opt-outs', () => {
    const metrics = calculateHealthMetrics({
      sent: 100,
      delivered: 96,
      failed: 4,
      responded: 18,
      optOut: 2
    });

    expect(metrics.deliveryRate).toBeCloseTo(96 / 104, 4);
    expect(metrics.failureRate).toBeCloseTo(4 / 104, 4);
    expect(metrics.responseRate).toBeCloseTo(18 / 96, 4);
    expect(metrics.optOutRate).toBeCloseTo(2 / 96, 4);
    expect(calculateCompositeHealthScore(metrics)).toBe(83);
  });

  it('auto-pauses numbers with severe failures and opt-outs', () => {
    const metrics = calculateHealthMetrics({
      sent: 1,
      delivered: 1,
      failed: 9,
      responded: 0,
      optOut: 1
    });
    const score = calculateCompositeHealthScore(metrics);

    expect(score).toBe(8);
    expect(shouldAutoPause(score)).toBe(true);
  });
});
