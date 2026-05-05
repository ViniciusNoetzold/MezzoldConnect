import type { FastifyInstance, FastifyReply } from 'fastify';
import type { Queue } from 'bullmq';
import { z } from 'zod';
import { config } from '../config.js';
import type { Queryable } from '../db/pool.js';
import {
  createNumber,
  getNumberById,
  getWarmupReport,
  normalizePhoneNumber,
  pauseNumberWarmup,
  startNumberWarmup
} from '../repositories/numbersRepository.js';
import {
  getOrCreateSchedule,
  getScheduleForDate,
  pauseSchedulesForNumber
} from '../repositories/warmupRepository.js';
import { recordSendEvent } from '../repositories/sendEventsRepository.js';
import { createHealthSnapshot } from '../repositories/healthRepository.js';
import { SEND_JOB_NAME } from '../queues/sendQueue.js';
import { localDateISO, remainingQuota } from '../services/quota.js';
import {
  isWithinQuietHours,
  nextAllowedSendTime,
  type QuietHoursWindow
} from '../services/quietHours.js';
import type { SendJobPayload } from '../types/domain.js';

export interface ApiDependencies {
  db: Queryable;
  queue: Queue<SendJobPayload>;
}

const uuidParamSchema = z.object({
  id: z.string().uuid()
});

const clockSchema = z
  .string()
  .regex(/^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/, 'Expected HH:mm or HH:mm:ss.');

const createNumberSchema = z.object({
  phoneNumber: z.string().min(1),
  displayName: z.string().min(1).max(120).optional(),
  maxDailyQuota: z.number().int().min(20).max(100_000).optional(),
  timezone: z.string().min(1).optional(),
  quietHoursStart: clockSchema.optional(),
  quietHoursEnd: clockSchema.optional(),
  webhookUrl: z.string().url().optional()
});

const warmupStartSchema = z
  .object({
    recipients: z.array(z.string().min(1)).max(10_000).default([]),
    template: z.string().min(1).optional(),
    variables: z.record(z.unknown()).default({}),
    perRecipientVariables: z.record(z.record(z.unknown())).default({}),
    metadata: z.record(z.unknown()).default({}),
    sendSpacingSeconds: z.number().int().min(1).max(86_400).optional()
  })
  .refine((value) => value.recipients.length === 0 || Boolean(value.template), {
    message: 'template is required when recipients are provided.',
    path: ['template']
  });

const parseOrReply = <T>(
  schema: z.Schema<T>,
  value: unknown,
  reply: FastifyReply
): T | null => {
  const parsed = schema.safeParse(value);
  if (parsed.success) return parsed.data;

  reply.code(400).send({
    error: 'validation_error',
    details: parsed.error.issues.map((issue) => ({
      path: issue.path.join('.'),
      message: issue.message
    }))
  });
  return null;
};

const notFound = (reply: FastifyReply, resource: string): void => {
  reply.code(404).send({ error: 'not_found', message: `${resource} not found.` });
};

export async function registerApiRoutes(app: FastifyInstance, deps: ApiDependencies): Promise<void> {
  app.post('/numbers', async (request, reply) => {
    const body = parseOrReply(createNumberSchema, request.body, reply);
    if (!body) return;

    const number = await createNumber(deps.db, body);
    reply.code(201).send({ number });
  });

  app.post('/numbers/:id/warmup/start', async (request, reply) => {
    const params = parseOrReply(uuidParamSchema, request.params, reply);
    const body = parseOrReply(warmupStartSchema, request.body ?? {}, reply);
    if (!params || !body) return;

    const number = await startNumberWarmup(deps.db, params.id);
    if (!number) {
      notFound(reply, 'number');
      return;
    }

    const now = new Date();
    const schedule = await getOrCreateSchedule(deps.db, number, now);
    const quietWindow: QuietHoursWindow = {
      timezone: number.timezone,
      start: number.quietHoursStart,
      end: number.quietHoursEnd
    };
    const recipients = body.recipients ?? [];
    const variables = body.variables ?? {};
    const perRecipientVariables = body.perRecipientVariables ?? {};
    const metadata = body.metadata ?? {};
    const spacingMs = (body.sendSpacingSeconds ?? config.sendSpacingSeconds) * 1_000;
    const scheduledJobs: Array<{ recipient: string; jobId: string | number | undefined; runAt: string }> = [];
    let cursor = now;

    for (const rawRecipient of recipients) {
      const recipient = normalizePhoneNumber(rawRecipient);
      const recipientVariables =
        perRecipientVariables[rawRecipient] ?? perRecipientVariables[recipient] ?? {};
      const runAt = nextAllowedSendTime(cursor, quietWindow);
      const payload: SendJobPayload = {
        numberId: number.id,
        recipient,
        template: body.template as string,
        variables: {
          ...variables,
          ...recipientVariables,
          recipient
        },
        metadata
      };
      const job = await deps.queue.add(SEND_JOB_NAME, payload, {
        delay: Math.max(0, runAt.getTime() - now.getTime()),
        attempts: 1,
        removeOnComplete: 1_000,
        removeOnFail: 5_000
      });

      await recordSendEvent(deps.db, {
        numberId: number.id,
        recipient,
        template: payload.template,
        eventType: 'queued',
        metadata: { jobId: job.id, runAt: runAt.toISOString() }
      });

      scheduledJobs.push({ recipient, jobId: job.id, runAt: runAt.toISOString() });
      cursor = new Date(runAt.getTime() + spacingMs);
    }

    reply.send({
      number,
      schedule,
      scheduledJobs
    });
  });

  app.post('/numbers/:id/warmup/pause', async (request, reply) => {
    const params = parseOrReply(uuidParamSchema, request.params, reply);
    if (!params) return;

    const number = await pauseNumberWarmup(deps.db, params.id);
    if (!number) {
      notFound(reply, 'number');
      return;
    }

    await pauseSchedulesForNumber(deps.db, number.id);
    reply.send({ number });
  });

  app.get('/numbers/:id/status', async (request, reply) => {
    const params = parseOrReply(uuidParamSchema, request.params, reply);
    if (!params) return;

    const number = await getNumberById(deps.db, params.id);
    if (!number) {
      notFound(reply, 'number');
      return;
    }

    const now = new Date();
    const today = localDateISO(now, number.timezone);
    const schedule =
      (await getScheduleForDate(deps.db, number.id, today)) ??
      (number.warmupStartedAt ? await getOrCreateSchedule(deps.db, number, now) : null);
    const quietWindow: QuietHoursWindow = {
      timezone: number.timezone,
      start: number.quietHoursStart,
      end: number.quietHoursEnd
    };
    const quietHoursActive = isWithinQuietHours(now, quietWindow);

    reply.send({
      number,
      schedule,
      quotaRemaining: schedule ? remainingQuota(schedule.dailyQuota, schedule.sentCount) : 0,
      quietHoursActive,
      nextAllowedSendAt: nextAllowedSendTime(now, quietWindow).toISOString()
    });
  });

  app.get('/numbers/:id/health', async (request, reply) => {
    const params = parseOrReply(uuidParamSchema, request.params, reply);
    if (!params) return;

    const number = await getNumberById(deps.db, params.id);
    if (!number) {
      notFound(reply, 'number');
      return;
    }

    const snapshot = await createHealthSnapshot(deps.db, number.id);
    reply.send({ numberId: number.id, snapshot });
  });

  app.get('/warmup/report', async (_request, reply) => {
    const numbers = await getWarmupReport(deps.db);
    const totals = numbers.reduce(
      (acc, row) => {
        acc.totalNumbers += 1;
        acc.byStatus[row.status] = (acc.byStatus[row.status] ?? 0) + 1;
        acc.sentInLatestSchedules += row.latestSentCount ?? 0;
        return acc;
      },
      {
        totalNumbers: 0,
        sentInLatestSchedules: 0,
        byStatus: {} as Record<string, number>
      }
    );

    reply.send({ totals, numbers });
  });
}
