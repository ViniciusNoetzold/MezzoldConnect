import { Queue, type JobsOptions } from 'bullmq';
import { Redis } from 'ioredis';
import { config } from '../config.js';
import type { SendJobPayload } from '../types/domain.js';

export const SEND_QUEUE_NAME = 'send-jobs';
export const SEND_JOB_NAME = 'send-message';

export const redisConnection = new Redis(config.redisUrl, {
  maxRetriesPerRequest: null
});

export const sendQueue = new Queue<SendJobPayload>(SEND_QUEUE_NAME, {
  connection: redisConnection
});

export async function enqueueSendJob(
  payload: SendJobPayload,
  options: JobsOptions = {}
) {
  return sendQueue.add(SEND_JOB_NAME, payload, {
    attempts: 1,
    removeOnComplete: 1_000,
    removeOnFail: 5_000,
    ...options
  });
}

export async function closeSendQueue(): Promise<void> {
  await sendQueue.close();
  await redisConnection.quit();
}
