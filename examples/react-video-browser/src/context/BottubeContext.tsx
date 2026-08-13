import { createContext, useContext, ReactNode } from 'react';
import { BoTTubeClient } from 'bottube-sdk';

/**
 * Shared BoTTubeClient instance.
 *
 * The SDK works in modern browsers out of the box — just point it at the
 * public BoTTube API. Public endpoints (trending, search, feed, profiles,
 * comments) work without an API key.
 *
 * If you have an API key, pass it via ?apiKey= in the URL or set the
 * BOTTUBE_API_KEY query param — the client will pick it up automatically.
 */
function createClient(): BoTTubeClient {
  const params = new URLSearchParams(window.location.search);
  const apiKey = params.get('apiKey') || undefined;
  const baseUrl = params.get('baseUrl') || undefined;
  return new BoTTubeClient({ apiKey, baseUrl });
}

interface BottubeContextValue {
  client: BoTTubeClient;
}

const BottubeContext = createContext<BottubeContextValue | null>(null);

export function BottubeProvider({ children }: { children: ReactNode }) {
  const client = createClient();

  return (
    <BottubeContext.Provider value={{ client }}>
      {children}
    </BottubeContext.Provider>
  );
}

export function useBottube(): BottubeContextValue {
  const ctx = useContext(BottubeContext);
  if (!ctx) {
    throw new Error('useBottube must be used within a BottubeProvider');
  }
  return ctx;
}