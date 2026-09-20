import { API_BASE_URL, OWNER_USERNAME, OWNER_PASSWORD } from './config';

/**
 * Read-only API client. Silent auth (no login screen — see PLAN.md's
 * mobile-app entry and src/api/config.example.ts's security note):
 * re-authenticates once per app session on first use, caches the access
 * token in memory only (never persisted), and never retries indefinitely
 * — a failure just means callers fall back to their local cache. This
 * client is used ONLY for GET requests (fetching players/balances); Deal
 * writes never touch the network — see src/db.
 */

let accessToken: string | null = null;
let loginPromise: Promise<string> | null = null;

async function login(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: OWNER_USERNAME, password: OWNER_PASSWORD }),
  });
  if (!response.ok) {
    throw new Error(`Login failed (${response.status})`);
  }
  const data = await response.json();
  return data.access as string;
}

async function getAccessToken(): Promise<string> {
  if (accessToken) return accessToken;
  if (!loginPromise) {
    loginPromise = login()
      .then((token) => {
        accessToken = token;
        return token;
      })
      .finally(() => {
        loginPromise = null;
      });
  }
  return loginPromise;
}

/** GET a path, returning parsed JSON. Throws on any network/auth/HTTP failure — callers decide the offline fallback. */
export async function authorizedGet<T>(path: string): Promise<T> {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) {
    // Token expired mid-session — one silent retry with a fresh login.
    accessToken = null;
    const fresh = await getAccessToken();
    const retry = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Authorization: `Bearer ${fresh}` },
    });
    if (!retry.ok) throw new Error(`Request failed (${retry.status})`);
    return retry.json();
  }
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return response.json();
}
