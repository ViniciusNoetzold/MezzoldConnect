import { Worker } from 'bullmq';
import { pool } from './db/pool.js';
import { WebhookMessageProvider } from './providers/WebhookMessageProvider.js';
import { redisConnection, sendQueue, SEND_QUEUE_NAME } from './queues/sendQueue.js';
import { processSendJob } from './services/sendJobProcessor.js';
import type { SendJobPayload } from './types/domain.js';

const provider = new WebhookMessageProvider();

const worker = new Worker<SendJobPayload>(
  SEND_QUEUE_NAME,
  async (job) =>
    processSendJob(job.data, {
      dbPool: pool,
      queue: sendQueue,
      provider
    }),
  {
    connection: redisConnection,
    concurrency: 5
  }
);

worker.on('completed', (job, result) => {
  console.log(`Send job ${job.id} completed: ${JSON.stringify(result)}`);
});

worker.on('failed', (job, error) => {
  console.error(`Send job ${job?.id ?? 'unknown'} failed: ${error.message}`);
});

const shutdown = async (): Promise<void> => {
  await worker.close();
  await sendQueue.close();
  await redisConnection.quit();
  await pool.end();
};

process.on('SIGINT', () => {
  shutdown().finally(() => process.exit(0));
});

process.on('SIGTERM', () => {
  shutdown().finally(() => process.exit(0));
});
