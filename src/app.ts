import Fastify from 'fastify';
import { ZodError } from 'zod';
import { pool } from './db/pool.js';
import { sendQueue } from './queues/sendQueue.js';
import { registerApiRoutes, type ApiDependencies } from './api/routes.js';
import { registerDashboardRoute } from './api/dashboard.js';

export function buildApp(deps: Partial<ApiDependencies> = {}) {
  const app = Fastify({
    logger: true
  });
  const apiDeps: ApiDependencies = {
    db: deps.db ?? pool,
    queue: deps.queue ?? sendQueue
  };

  app.setErrorHandler((error, _request, reply) => {
    if (error instanceof ZodError) {
      reply.code(400).send({
        error: 'validation_error',
        details: error.issues.map((issue) => ({
          path: issue.path.join('.'),
          message: issue.message
        }))
      });
      return;
    }

    const pgError = error as { code?: string; detail?: string; message?: string };
    if (pgError.code === '23505') {
      reply.code(409).send({
        error: 'conflict',
        message: pgError.detail ?? 'Resource already exists.'
      });
      return;
    }

    if (pgError.message?.includes('Phone number must contain')) {
      reply.code(400).send({ error: 'validation_error', message: pgError.message });
      return;
    }

    app.log.error(error);
    reply.code(500).send({ error: 'internal_server_error' });
  });

  app.get('/healthz', async () => ({ ok: true }));
  void registerDashboardRoute(app);
  void registerApiRoutes(app, apiDeps);

  return app;
}
