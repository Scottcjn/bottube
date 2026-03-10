import type { ApiConfig } from './types';
import { BoTTubeError, NetworkError, TimeoutError, handleErrorResponse } from './errors';

/**
 * Default configuration
 */
const DEFAULT_CONFIG: Required<Omit<ApiConfig, 'apiKey'>> = {
  baseUrl: 'https://bottube.ai',
  timeout: 30000,
  userAgent: 'BoTTube-JS-SDK/0.1.0',
};

/**
 * Base HTTP client for BoTTube API
 * Handles request/response lifecycle, authentication, and error handling
 */
export class HttpClient {
  private baseUrl: string;
  private timeout: number;
  private userAgent: string;
  private apiKey?: string;
  private defaultHeaders: Record<string, string>;

  constructor(config: ApiConfig = {}) {
    const mergedConfig = { ...DEFAULT_CONFIG, ...config };
    this.baseUrl = mergedConfig.baseUrl?.replace(/\/$/, '') || DEFAULT_CONFIG.baseUrl;
    this.timeout = mergedConfig.timeout || DEFAULT_CONFIG.timeout;
    this.userAgent = mergedConfig.userAgent || DEFAULT_CONFIG.userAgent;
    this.apiKey = config.apiKey;

    this.defaultHeaders = {
      'Content-Type': 'application/json',
      'User-Agent': this.userAgent,
    };
  }

  /**
   * Set the API key for authentication
   */
  setApiKey(apiKey: string): void {
    this.apiKey = apiKey;
  }

  /**
   * Clear the API key
   */
  clearApiKey(): void {
    this.apiKey = undefined;
  }

  /**
   * Get the current API key
   */
  getApiKey(): string | undefined {
    return this.apiKey;
  }

  /**
   * Get the base URL
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Build request headers
   */
  private buildHeaders(customHeaders?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = { ...this.defaultHeaders };

    // Add API key if available
    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    // Merge custom headers
    if (customHeaders) {
      Object.assign(headers, customHeaders);
    }

    return headers;
  }

  /**
   * Build full URL from path and query params
   */
  private buildUrl(path: string, params?: Record<string, unknown>): string {
    let url = `${this.baseUrl}${path}`;

    if (params && Object.keys(params).length > 0) {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      }
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    return url;
  }

  /**
   * Create an abort controller with timeout
   */
  private createTimeoutController(): AbortController {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    // Clear timeout when request completes
    const originalAbort = controller.abort.bind(controller);
    controller.abort = (reason?: unknown) => {
      clearTimeout(timeoutId);
      originalAbort(reason);
    };

    return controller;
  }

  /**
   * Execute a fetch request with error handling
   */
  private async request<T>(
    path: string,
    options: RequestInit & { params?: Record<string, unknown> } = {}
  ): Promise<T> {
    const { params, headers: customHeaders, ...fetchOptions } = options;

    const url = this.buildUrl(path, params);
    const headers = this.buildHeaders(customHeaders as Record<string, string>);
    const controller = this.createTimeoutController();

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });

      // Handle non-OK responses
      if (!response.ok) {
        return handleErrorResponse(response) as Promise<T>;
      }

      // Handle empty responses
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        return {} as T;
      }

      return response.json() as Promise<T>;
    } catch (error) {
      // Handle timeout
      if (error instanceof Error && error.name === 'AbortError') {
        throw new TimeoutError(this.timeout);
      }

      // Handle network errors
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new NetworkError('Network request failed', error);
      }

      // Re-throw BoTTube errors
      if (error instanceof BoTTubeError) {
        throw error;
      }

      // Wrap unknown errors
      throw new NetworkError(
        error instanceof Error ? error.message : 'Unknown network error',
        error
      );
    }
  }

  /**
   * GET request
   */
  async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, { method: 'GET', params });
  }

  /**
   * POST request
   */
  async post<T>(path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, {
      method: 'POST',
      params,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T>(path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, {
      method: 'PUT',
      params,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PATCH request
   */
  async patch<T>(path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, {
      method: 'PATCH',
      params,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, { method: 'DELETE', params });
  }

  /**
   * Upload file
   */
  async upload<T>(
    path: string,
    formData: FormData,
    params?: Record<string, unknown>
  ): Promise<T> {
    const url = this.buildUrl(path, params);
    const headers = this.buildHeaders();

    // Remove Content-Type for FormData (browser sets it with boundary)
    delete headers['Content-Type'];

    const controller = this.createTimeoutController();

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        return handleErrorResponse(response) as Promise<T>;
      }

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        return {} as T;
      }

      return response.json() as Promise<T>;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new TimeoutError(this.timeout);
      }

      if (error instanceof BoTTubeError) {
        throw error;
      }

      throw new NetworkError(
        error instanceof Error ? error.message : 'Upload failed',
        error
      );
    }
  }
}
