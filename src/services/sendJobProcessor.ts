import type pg from 'pg';
import type { Queue } from 'bullmq';
import { getNumberById } from '../repositories/numbersRepository.js';
import { recordSendEvent } from '../repositories/sendEventsRepository.js';
import { reserveQuotaSlot } from '../repositories/warmupRepository.js';
import { createHealthSnapshot } from '../repositories/healthRepository.js';
import type { MessageProvider } from '../providers/MessageProvider.js';
import { renderMessage } from './messageVariation.js';
import {
  isWithinQuietHours,
  nextAllowedSendTime,
  nextQuotaWindowStart,
  type QuietHoursWindow
} from './quietHours.js';
import { SEND_JOB_NAME } from '../queues/sendQueue.js';
import type { SendJobPayload } from '../types/domain.js';

export interface SendJobProcessorDependencies {
  dbPool: pg.Pool;
  queue: Queue<SendJobPayload>;
  provider: MessageProvider;
  now?: () => Date;
}

export type SendJobProcessResult =
  | { status: 'sent'; providerMessageId: string | null; healthScore: number }
  | { status: 'failed'; error: string; healthScore: number }
  | { status: 'deferred'; reason: 'quiet_hours' | 'quota_exhausted'; runAt: string }
  | { status: 'skipped'; reason: string };

const requeue = async (
  queue: Queue<SendJobPayload>,
  payload: SendJobPayload,
  runAt: Date
): Promise<void> => {
  await queue.add(SEND_JOB_NAME, payload, {
    delay: Math.max(0, runAt.getTime() - Date.now()),
    attempts: 1,
    removeOnComplete: 1_000,
    removeOnFail: 5_000
  });
};

const providerErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'Unknown provider error.';

export async function processSendJob(
  payload: SendJobPayload,
  deps: SendJobProcessorDependencies
): Promise<SendJobProcessResult> {
  const now = deps.now?.() ?? new Date();
  const number = await getNumberById(deps.dbPool, payload.numberId);

  if (!number) {
    return { status: 'skipped', reason: 'number_not_found' };
  }

  if (number.status !== 'warming') {
    await recordSendEvent(deps.dbPool, {
      numberId: number.id,
      recipient: payload.recipient,
      template: payload.template,
      eventType: 'skipped',
      metadata: { reason: `number_status_${number.status}` }
    });
    return { status: 'skipped', reason: `number_status_${number.status}` };
  }

  const quietWindow: QuietHoursWindow = {
    timezone: number.timezone,
    start: number.quietHoursStart,
    end: number.quietHoursEnd
  };

  if (isWithinQuietHours(now, quietWindow)) {
    const runAt = nextAllowedSendTime(now, quietWindow);
    await requeue(deps.queue, payload, runAt);
    return { status: 'deferred', reason: 'quiet_hours', runAt: runAt.toISOString() };
  }

  let renderedMessage: string;
  try {
    renderedMessage = renderMessage(payload.template, payload.variables);
  } catch (error) {
    await recordSendEvent(deps.dbPool, {
      numberId: number.id,
      recipient: payload.recipient,
      template: payload.template,
      eventType: 'failed',
      errorMessage: providerErrorMessage(error),
      metadata: { reason: 'message_render_failed' }
    });
    const snapshot = await createHealthSnapshot(deps.dbPool, number.id);
    return {
      status: 'failed',
      error: providerErrorMessage(error),
      healthScore: snapshot.score
    };
  }

  const client = await deps.dbPool.connect();
  try {
    await client.query('BEGIN');
    const reservation = await reserveQuotaSlot(client, number, now);
    await client.query('COMMIT');

    if (!reservation.reserved) {
      const runAt = nextQuotaWindowStart(now, quietWindow);
      await requeue(deps.queue, payload, runAt);
      return { status: 'deferred', reason: 'quota_exhausted', runAt: runAt.toISOString() };
    }
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }

  try {
    const result = await deps.provider.send({
      numberId: number.id,
      from: number.phoneNumber,
      to: payload.recipient,
      body: renderedMessage,
      webhookUrl: number.providerConfig.webhookUrl,
      metadata: payload.metadata
    });

    await recordSendEvent(deps.dbPool, {
      numberId: number.id,
      recipient: payload.recipient,
      template: payload.template,
      renderedMessage,
      eventType: 'sent',
      providerMessageId: result.providerMessageId,
      metadata: { provider: result.raw }
    });
    await recordSendEvent(deps.dbPool, {
      numberId: number.id,
      recipient: payload.recipient,
      template: payload.template,
      renderedMessage,
      eventType: 'delivered',
      providerMessageId: result.providerMessageId,
      metadata: { deliveryStatus: result.deliveryStatus }
    });

    if (result.responded) {
      await recordSendEvent(deps.dbPool, {
        numberId: number.id,
        recipient: payload.recipient,
        template: payload.template,
        renderedMessage,
        eventType: 'responded',
        providerMessageId: result.providerMessageId
      });
    }

    if (result.optedOut) {
      await recordSendEvent(deps.dbPool, {
        numberId: number.id,
        recipient: payload.recipient,
        template: payload.template,
        renderedMessage,
        eventType: 'opt_out',
        providerMessageId: result.providerMessageId
      });
    }

    const snapshot = await createHealthSnapshot(deps.dbPool, number.id);
    return { status: 'sent', providerMessageId: result.providerMessageId, healthScore: snapshot.score };
  } catch (error) {
    await recordSendEvent(deps.dbPool, {
      numberId: number.id,
      recipient: payload.recipient,
      template: payload.template,
      renderedMessage,
      eventType: 'failed',
      errorMessage: providerErrorMessage(error)
    });
    const snapshot = await createHealthSnapshot(deps.dbPool, number.id);
    return {
      status: 'failed',
      error: providerErrorMessage(error),
      healthScore: snapshot.score
    };
  }
}
