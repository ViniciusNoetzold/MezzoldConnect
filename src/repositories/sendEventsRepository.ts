import type { Queryable } from '../db/pool.js';
import type { SendEvent, SendEventType } from '../types/domain.js';

interface SendEventRow {
  id: string;
  number_id: string;
  recipient: string | null;
  template: string | null;
  rendered_message: string | null;
  event_type: SendEventType;
  provider_message_id: string | null;
  error_message: string | null;
  metadata: Record<string, unknown> | string | null;
  occurred_at: Date;
}

export interface RecordSendEventInput {
  numberId: string;
  recipient?: string | null;
  template?: string | null;
  renderedMessage?: string | null;
  eventType: SendEventType;
  providerMessageId?: string | null;
  errorMessage?: string | null;
  metadata?: Record<string, unknown>;
}

const parseMetadata = (value: Record<string, unknown> | string | null): Record<string, unknown> => {
  if (!value) return {};
  if (typeof value === 'string') return JSON.parse(value) as Record<string, unknown>;
  return value;
};

const mapEvent = (row: SendEventRow): SendEvent => ({
  id: row.id,
  numberId: row.number_id,
  recipient: row.recipient,
  template: row.template,
  renderedMessage: row.rendered_message,
  eventType: row.event_type,
  providerMessageId: row.provider_message_id,
  errorMessage: row.error_message,
  metadata: parseMetadata(row.metadata),
  occurredAt: row.occurred_at
});

export async function recordSendEvent(
  db: Queryable,
  input: RecordSendEventInput
): Promise<SendEvent> {
  const result = await db.query<SendEventRow>(
    `
      INSERT INTO send_events (
        number_id,
        recipient,
        template,
        rendered_message,
        event_type,
        provider_message_id,
        error_message,
        metadata
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
      RETURNING *
    `,
    [
      input.numberId,
      input.recipient ?? null,
      input.template ?? null,
      input.renderedMessage ?? null,
      input.eventType,
      input.providerMessageId ?? null,
      input.errorMessage ?? null,
      JSON.stringify(input.metadata ?? {})
    ]
  );

  return mapEvent(result.rows[0]);
}
