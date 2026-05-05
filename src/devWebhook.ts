import Fastify from 'fastify';

const app = Fastify({ logger: true });

app.post('/messages', async (request) => {
  const body = request.body as {
    numberId?: string;
    from?: string;
    to?: string;
    message?: string;
    metadata?: Record<string, unknown>;
  };

  return {
    messageId: `local-${Date.now()}`,
    deliveryStatus: 'delivered',
    responded: body.metadata?.responded === true,
    optedOut: body.metadata?.optedOut === true,
    echo: {
      numberId: body.numberId,
      from: body.from,
      to: body.to,
      message: body.message
    }
  };
});

app.get('/healthz', async () => ({ ok: true }));

app
  .listen({ host: '0.0.0.0', port: 4000 })
  .then((address) => {
    app.log.info(`Local webhook provider listening at ${address}`);
  })
  .catch((error) => {
    app.log.error(error);
    process.exitCode = 1;
  });
