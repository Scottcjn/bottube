import { describe, it, expect, beforeEach, vi } from 'vitest';
import { BoTTubeError, NetworkError, TimeoutError } from '../src/errors.js';

describe('Errors', () => {
  describe('BoTTubeError', () => {
    it('should create error with basic properties', () => {
      const error = new BoTTubeError({
        status: 400,
        message: 'Bad request',
      });

      expect(error.name).toBe('BoTTubeError');
      expect(error.status).toBe(400);
      expect(error.message).toBe('Bad request');
    });

    it('should create error with optional properties', () => {
      const error = new BoTTubeError({
        status: 422,
        message: 'Validation failed',
        code: 'VALIDATION_ERROR',
        details: { field: 'title', reason: 'too long' },
      });

      expect(error.code).toBe('VALIDATION_ERROR');
      expect(error.details).toEqual({ field: 'title', reason: 'too long' });
    });

    it('should identify rate limit errors', () => {
      const error = new BoTTubeError({ status: 429, message: 'Rate limit exceeded' });
      expect(error.isRateLimit).toBe(true);
      expect(error.isAuthError).toBe(false);
    });

    it('should identify auth errors', () => {
      const error401 = new BoTTubeError({ status: 401, message: 'Unauthorized' });
      const error403 = new BoTTubeError({ status: 403, message: 'Forbidden' });

      expect(error401.isAuthError).toBe(true);
      expect(error403.isAuthError).toBe(true);
    });

    it('should identify not found errors', () => {
      const error = new BoTTubeError({ status: 404, message: 'Not found' });
      expect(error.isNotFound).toBe(true);
    });

    it('should identify client errors', () => {
      const error = new BoTTubeError({ status: 450, message: 'Client error' });
      expect(error.isClientError).toBe(true);
      expect(error.isServerError).toBe(false);
    });

    it('should identify server errors', () => {
      const error = new BoTTubeError({ status: 500, message: 'Server error' });
      expect(error.isServerError).toBe(true);
      expect(error.isClientError).toBe(false);
    });
  });

  describe('NetworkError', () => {
    it('should create error with message', () => {
      const error = new NetworkError('Connection failed');
      expect(error.name).toBe('NetworkError');
      expect(error.message).toBe('Connection failed');
    });

    it('should create error with cause', () => {
      const cause = new Error('DNS lookup failed');
      const error = new NetworkError('Connection failed', cause);
      expect(error.cause).toBe(cause);
    });
  });

  describe('TimeoutError', () => {
    it('should create error with timeout value', () => {
      const error = new TimeoutError(5000);
      expect(error.name).toBe('TimeoutError');
      expect(error.message).toBe('Request timed out after 5000ms');
    });
  });
});
