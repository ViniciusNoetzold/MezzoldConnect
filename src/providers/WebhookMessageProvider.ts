import { config } from '../config.js';
import type { MessageProvider, MessageSendResult, SendMessageCommand } from './MessageProvider.js';

export class ProviderSendError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly responseBody?: unknown
  ) {
    super(message);
    this.name = 'ProviderSendError';
  }
}

const readResponseBody = async (response: Response): Promise<unknown> => {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response.text();
};

const asBoolean = (value: unknown): boolean => value === true || value === 'true';

export class WebhookMessageProvider implements MessageProvider {
  constructor(private readonly defaultWebhookUrl = config.providerWebhookUrl) {}

  async send(command: SendMessageCommand): Promise<MessageSendResult> {
    const webhookUrl = command.webhookUrl ?? this.defaultWebhookUrl;
    if (!webhookUrl) {
      throw new ProviderSendError('No webhook URL configured for message provider.');
    }

    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify({
        numberId: command.numberId,
        from: command.from,
        to: command.to,
        message: command.body,
        metadata: command.metadata ?? {}
      }),
      signal: AbortSignal.timeout(15_000)
    });

    const body = await readResponseBody(response);

    if (!response.ok) {
      throw new ProviderSendError(
        `Webhook provider returned HTTP ${response.status}.`,
        response.status,
        body
      );
    }

    const json = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
    const status = String(json.deliveryStatus ?? json.status ?? 'accepted').toLowerCase();

    return {
      providerMessageId:
        typeof json.messageId === 'string'
          ? json.messageId
          : typeof json.id === 'string'
            ? json.id
            : response.headers.get('x-message-id'),
      deliveryStatus: status === 'delivered' ? 'delivered' : 'accepted',
      responded: asBoolean(json.responded),
      optedOut: asBoolean(json.optedOut ?? json.opt_out),
      raw: body
    };
  }
}
