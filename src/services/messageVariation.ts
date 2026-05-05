export class MessageVariationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MessageVariationError';
  }
}

export type RandomSource = () => number;

const getVariable = (variables: Record<string, unknown>, path: string): unknown => {
  const parts = path.split('.').map((part) => part.trim()).filter(Boolean);
  let current: unknown = variables;

  for (const part of parts) {
    if (
      current !== null &&
      typeof current === 'object' &&
      Object.prototype.hasOwnProperty.call(current, part)
    ) {
      current = (current as Record<string, unknown>)[part];
      continue;
    }

    throw new MessageVariationError(`Missing template variable: ${path}`);
  }

  return current;
};

export function renderMessage(
  template: string,
  variables: Record<string, unknown>,
  random: RandomSource = Math.random
): string {
  if (template.trim().length === 0) {
    throw new MessageVariationError('Template cannot be empty.');
  }

  let output = template;
  const spintax = /\{([^{}]*\|[^{}]*)\}/g;

  for (let depth = 0; depth < 20 && spintax.test(output); depth += 1) {
    output = output.replace(spintax, (_, group: string) => {
      const options = group.split('|').map((option) => option.trim()).filter(Boolean);
      if (options.length === 0) return '';
      const index = Math.min(options.length - 1, Math.floor(random() * options.length));
      return options[index];
    });
    spintax.lastIndex = 0;
  }

  return output.replace(/\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g, (_, key: string) => {
    const value = getVariable(variables, key);
    if (value === null || value === undefined) return '';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  });
}
