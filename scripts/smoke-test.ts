const API_URL = process.env.API_URL ?? 'http://localhost:3000';

const requestJson = async <T>(
  path: string,
  options: RequestInit = {}
): Promise<T> => {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'content-type': 'application/json',
      ...(options.headers ?? {})
    }
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(`${options.method ?? 'GET'} ${path} failed: ${response.status} ${JSON.stringify(body)}`);
  }

  return body as T;
};

const created = await requestJson<{ number: { id: string; phoneNumber: string } }>('/numbers', {
  method: 'POST',
  body: JSON.stringify({
    phoneNumber: `+5511999${Date.now().toString().slice(-8)}`,
    displayName: 'Local smoke test',
    webhookUrl: 'http://localhost:4000/messages'
  })
});

console.log(`number: ${created.number.id} (${created.number.phoneNumber})`);

const started = await requestJson<{
  scheduledJobs: Array<{ recipient: string; runAt: string }>;
}>(`/numbers/${created.number.id}/warmup/start`, {
  method: 'POST',
  body: JSON.stringify({
    recipients: ['+5511888887777'],
    template: '{Oi|Olá} {{name}}, teste local da plataforma {{company}}.',
    variables: {
      name: 'Ana',
      company: 'Mezzold Connect'
    }
  })
});

console.log(`scheduled jobs: ${started.scheduledJobs.length}`);
console.log(`first run at: ${started.scheduledJobs[0]?.runAt ?? 'none'}`);

await new Promise((resolve) => setTimeout(resolve, 3_000));

const status = await requestJson(`/numbers/${created.number.id}/status`);
console.log(`status: ${JSON.stringify(status, null, 2)}`);

const health = await requestJson(`/numbers/${created.number.id}/health`);
console.log(`health: ${JSON.stringify(health, null, 2)}`);

const report = await requestJson('/warmup/report');
console.log(`report: ${JSON.stringify(report, null, 2)}`);
