import type { HealthMetrics } from '../types/domain.js';

export interface HealthEventCounts {
  sent: number;
  delivered: number;
  failed: number;
  responded: number;
  optOut: number;
}

const clampRate = (value: number): number => {
  if (Number.isNaN(value) || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
};

export function calculateHealthMetrics(counts: HealthEventCounts): HealthMetrics {
  const attempts = counts.sent + counts.failed;
  const delivered = Math.min(counts.delivered, attempts);

  return {
    deliveryRate: attempts === 0 ? 1 : clampRate(delivered / attempts),
    failureRate: attempts === 0 ? 0 : clampRate(counts.failed / attempts),
    responseRate: delivered === 0 ? 0 : clampRate(counts.responded / delivered),
    optOutRate: delivered === 0 ? 0 : clampRate(counts.optOut / delivered)
  };
}

export function calculateCompositeHealthScore(metrics: HealthMetrics): number {
  const deliveryComponent = clampRate(metrics.deliveryRate) * 50;
  const reliabilityComponent = (1 - clampRate(metrics.failureRate)) * 25;
  const engagementComponent = clampRate(metrics.responseRate) * 15;
  const consentComponent = (1 - clampRate(metrics.optOutRate)) * 10;
  const score = deliveryComponent + reliabilityComponent + engagementComponent + consentComponent;

  return Math.round(Math.max(0, Math.min(100, score)));
}

export function shouldAutoPause(score: number): boolean {
  return score < 40;
}
