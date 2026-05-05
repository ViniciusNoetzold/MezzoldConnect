export interface SendMessageCommand {
  numberId: string;
  from: string;
  to: string;
  body: string;
  webhookUrl?: string;
  metadata?: Record<string, unknown>;
}

export interface MessageSendResult {
  providerMessageId: string | null;
  deliveryStatus: 'accepted' | 'delivered';
  responded: boolean;
  optedOut: boolean;
  raw: unknown;
}

export interface MessageProvider {
  send(command: SendMessageCommand): Promise<MessageSendResult>;
}
