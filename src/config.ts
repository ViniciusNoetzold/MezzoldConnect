import 'dotenv/config';

const toInt = (value: string | undefined, fallback: number): number => {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const config = {
  nodeEnv: process.env.NODE_ENV ?? 'development',
  port: toInt(process.env.PORT, 3000),
  databaseUrl:
    process.env.DATABASE_URL ?? 'postgres://postgres:postgres@localhost:5432/messaging_warmup',
  redisUrl: process.env.REDIS_URL ?? 'redis://localhost:6379',
  providerWebhookUrl: process.env.WEBHOOK_PROVIDER_URL,
  defaultTimezone: process.env.DEFAULT_TIMEZONE ?? 'America/Sao_Paulo',
  defaultMaxDailyQuota: toInt(process.env.DEFAULT_MAX_DAILY_QUOTA, 500),
  healthWindowDays: toInt(process.env.HEALTH_WINDOW_DAYS, 7),
  sendSpacingSeconds: toInt(process.env.SEND_SPACING_SECONDS, 60)
} as const;
