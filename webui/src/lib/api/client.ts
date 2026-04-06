import { PUBLIC_API_TOKEN } from '$env/static/public';

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

const API_TOKEN = PUBLIC_API_TOKEN;

// Retry delays for read-only requests: 500ms, 1000ms, 2000ms (exponential, max 3 retries)
const RETRY_DELAYS_MS = [500, 1000, 2000] as const;

function jittered(ms: number): number {
  return ms * (0.9 + Math.random() * 0.2);
}

function retryDelayMs(attempt: number, retryAfterHeader: string | null): number {
  if (retryAfterHeader !== null) {
    const seconds = parseInt(retryAfterHeader, 10);
    if (!isNaN(seconds)) return seconds * 1000;
  }
  return jittered(RETRY_DELAYS_MS[attempt] ?? 2000);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const isReadOnly = method === 'GET' || method === 'HEAD';
  const maxRetries = isReadOnly ? 3 : 0;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const isLastAttempt = attempt === maxRetries;

    try {
      const response = await fetch(path, {
        ...init,
        headers: {
          Authorization: `Bearer ${API_TOKEN}`,
          'Content-Type': 'application/json',
          ...(init.headers ?? {})
        }
      });

      if (!response.ok) {
        let details: unknown = null;
        try {
          details = await response.json();
        } catch {
          details = await response.text();
        }

        if (isReadOnly && !isLastAttempt && (response.status === 503 || response.status === 429)) {
          const delay = retryDelayMs(
            attempt,
            response.status === 429 ? response.headers.get('Retry-After') : null
          );
          await new Promise<void>((resolve) => setTimeout(resolve, delay));
          continue;
        }

        throw new ApiError(`API request failed: ${response.status}`, response.status, details);
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;

      // Network failure (fetch threw without a response)
      if (isReadOnly && !isLastAttempt) {
        await new Promise<void>((resolve) =>
          setTimeout(resolve, jittered(RETRY_DELAYS_MS[attempt] ?? 2000))
        );
        continue;
      }

      throw new ApiError('network unavailable', 0, error);
    }
  }

  // Unreachable; TypeScript requires an explicit exit after the loop
  throw new ApiError('max retries exceeded', 0);
}
