# Phone Health Ramp-Up Service

Node.js service for B2B phone number warmup, quota enforcement, quiet-hour scheduling, message variation, provider abstraction, and health auto-pausing.

## Folder Structure

```text
migrations/
  001_init.sql
src/
  api/routes.ts
  app.ts
  config.ts
  db/migrate.ts
  db/pool.ts
  providers/MessageProvider.ts
  providers/WebhookMessageProvider.ts
  queues/sendQueue.ts
  repositories/healthRepository.ts
  repositories/numbersRepository.ts
  repositories/sendEventsRepository.ts
  repositories/warmupRepository.ts
  services/healthScoring.ts
  services/messageVariation.ts
  services/quietHours.ts
  services/quota.ts
  services/sendJobProcessor.ts
  server.ts
  types/domain.ts
test/
  healthScoring.test.ts
  quota.test.ts
```

## Run

```powershell
npm install
Copy-Item .env.example .env
npm run migrate
npm run dev
npm run worker
```

PostgreSQL must be available at `DATABASE_URL`, and Redis must be available at `REDIS_URL`.

## Local Test With Docker

Start Postgres and Redis:

```powershell
docker compose up -d
npm run migrate
```

Open three terminals:

```powershell
npm run dev
```

```powershell
npm run worker
```

```powershell
npm run dev:webhook
```

Then run the end-to-end smoke test:

```powershell
npm run smoke
```

The API opens at:

```text
http://localhost:3000/healthz
```

The local test webhook opens at:

```text
http://localhost:4000/healthz
```

If Docker Desktop cannot run Linux containers, install or enable WSL first, or run PostgreSQL and Redis locally on ports `5432` and `6379`.

## API

```http
POST   /numbers
POST   /numbers/:id/warmup/start
POST   /numbers/:id/warmup/pause
GET    /numbers/:id/status
GET    /numbers/:id/health
GET    /warmup/report
```

`POST /numbers/:id/warmup/start` accepts recipients and a template. Templates support `{{variable}}` interpolation and spintax such as `{Hi|Hello|Good morning}`.

```json
{
  "recipients": ["+5511999999999"],
  "template": "{Hi|Hello} {{name}}, checking in about {{company}}.",
  "variables": {
    "company": "Acme"
  },
  "perRecipientVariables": {
    "+5511999999999": {
      "name": "Ana"
    }
  }
}
```

The webhook provider sends a JSON `POST` to `WEBHOOK_PROVIDER_URL` or the per-number `webhookUrl` supplied during registration.
