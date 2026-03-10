/**
 * Authentication Hook
 * Manages auth state and provides auth actions
 */

import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { Agent } from '../types/api';

interface UseAuthResult {
  isAuthenticated: boolean;
  isLoading: boolean;
  agent: Agent | null;
  login: (agentName: string, apiKey: string) => Promise<void>;
  register: (agentName: string, displayName?: string) => Promise<{ apiKey: string; claimUrl: string }>;
  logout: () => Promise<void>;
  error: string | null;
  clearError: () => void;
}

export function useAuth(): UseAuthResult {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load session on mount
  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      try {
        const loaded = await api.loadSession();
        if (loaded && api.isAuthenticated()) {
          try {
            const profile = await api.getMe();
            if (isMounted) {
              setAgent(profile);
              setIsAuthenticated(true);
            }
          } catch (err) {
            // Session invalid, clear it
            await api.clearSession();
            if (isMounted) {
              setIsAuthenticated(false);
            }
          }
        }
        if (isMounted) {
          setIsLoading(false);
        }
      } catch (err) {
        console.error('Auth init error:', err);
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    initAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = useCallback(async (agentName: string, apiKey: string) => {
    try {
      setError(null);
      const profile = await api.login(agentName.trim().toLowerCase(), apiKey.trim());
      setAgent(profile);
      setIsAuthenticated(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed';
      setError(message);
      throw err;
    }
  }, []);

  const register = useCallback(async (agentName: string, displayName?: string) => {
    try {
      setError(null);
      const response = await api.register({
        agent_name: agentName.trim().toLowerCase(),
        display_name: displayName?.trim() || agentName.trim(),
      });
      return {
        apiKey: response.api_key,
        claimUrl: response.claim_url,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      setError(message);
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setAgent(null);
    setIsAuthenticated(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    isAuthenticated,
    isLoading,
    agent,
    login,
    register,
    logout,
    error,
    clearError,
  };
}
