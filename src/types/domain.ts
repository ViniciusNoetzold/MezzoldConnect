export type NumberStatus = 'registered' | 'warming' | 'paused' | 'auto_paused';

export type WarmupScheduleStatus = 'pending' | 'running' | 'paused' | 'completed';

export type SendEventType =
  | 'queued'
  | 'sent'
  | 'delivered'
  | 'failed'
  | 'responded'
  | 'opt_out'
  | 'skipped';

export interface ProviderConfig {
  webhookUrl?: string;
}

export interface MessagingNumber {
  id: string;
  phoneNumber: string;
  displayName: string | null;
  status: NumberStatus;
  dailyQuota: number;
  maxDailyQuota: number;
  rampRate: number;
  timezone: string;
  quietHoursStart: string;
  quietHoursEnd: string;
  providerConfig: ProviderConfig;
  warmupStartedAt: Date | null;
  pausedAt: Date | null;
  autoPausedReason: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface WarmupSchedule {
  id: string;
  numberId: string;
  scheduleDate: string;
  dailyQuota: number;
  sentCount: number;
  status: WarmupScheduleStatus;
  createdAt: Date;
  updatedAt: Date;
}

export interface SendEvent {
  id: string;
  numberId: string;
  recipient: string | null;
  template: string | null;
  renderedMessage: string | null;
  eventType: SendEventType;
  providerMessageId: string | null;
  errorMessage: string | null;
  metadata: Record<string, unknown>;
  occurredAt: Date;
}

export interface HealthMetrics {
  deliveryRate: number;
  failureRate: number;
  responseRate: number;
  optOutRate: number;
}

export interface HealthSnapshot extends HealthMetrics {
  id: string;
  numberId: string;
  score: number;
  windowStart: Date;
  windowEnd: Date;
  createdAt: Date;
}

export interface SendJobPayload {
  numberId: string;
  recipient: string;
  template: string;
  variables: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}
