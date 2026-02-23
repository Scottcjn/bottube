export type Session = { apiKey: string; agentName?: string };
let current: Session | null = null;
export function setSession(s: Session | null) { current = s; }
export function getSession() { return current; }
