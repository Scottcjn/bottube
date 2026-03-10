import type { ApiError } from './types';

/**
 * BoTTube API Error
 * Thrown when an API request fails
 */
export class BoTTubeError extends Error {
  public readonly status: number;
  public readonly code?: string;
  public readonly details?: Record<string, unknown>;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'BoTTubeError';
    this.status = error.status;
    this.code = error.code;
    this.details = error.details;

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, BoTTubeError);
    }
  }

  /**
   * Check if this is a rate limit error
   */
  get isRateLimit(): boolean {
    return this.status === 429;
  }

  /**
   * Check if this is an authentication error
   */
  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }

  /**
   * Check if this is a not found error
   */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /**
   * Check if this is a client error (4xx)
   */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  /**
   * Check if this is a server error (5xx)
   */
  get isServerError(): boolean {
    return this.status >= 500;
  }
}

/**
 * Network Error
 * Thrown when a network request fails (timeout, connection error, etc.)
 */
export class NetworkError extends Error {
  public readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'NetworkError';
    this.cause = cause;

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, NetworkError);
    }
  }
}

/**
 * Timeout Error
 * Thrown when a request times out
 */
export class TimeoutError extends NetworkError {
  constructor(timeout: number) {
    super(`Request timed out after ${timeout}ms`);
    this.name = 'TimeoutError';
  }
}

/**
 * Parse an error response from the API
 */
export async function parseErrorResponse(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    return {
      status: response.status,
      message: data.error || data.message || response.statusText,
      code: data.code,
      details: data.details,
    };
  } catch {
    return {
      status: response.status,
      message: response.statusText || 'Request failed',
    };
  }
}

/**
 * Handle a failed API response
 */
export async function handleErrorResponse(response: Response): Promise<never> {
  const error = await parseErrorResponse(response);
  throw new BoTTubeError(error);
}
