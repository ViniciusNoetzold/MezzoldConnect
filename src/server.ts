import { config } from './config.js';
import { buildApp } from './app.js';
import { pool } from './db/pool.js';
import { closeSendQueue } from './queues/sendQueue.js';

const app = buildApp();

const shutdown = async (): Promise<void> => {
  await app.close();
  await closeSendQueue();
  await pool.end();
};

app
  .listen({ port: config.port, host: '0.0.0.0' })
  .then((address) => {
    app.log.info(`HTTP API listening at ${address}`);
  })
  .catch((error) => {
    app.log.error(error);
    process.exitCode = 1;
  });

process.on('SIGINT', () => {
  shutdown().finally(() => process.exit(0));
});

process.on('SIGTERM', () => {
  shutdown().finally(() => process.exit(0));
});
