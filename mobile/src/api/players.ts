import { getDb } from '../db/database';
import { authorizedGet } from './client';
import type { Player } from '../types';

type ApiPlayer = {
  id: number;
  account_code: string;
  display_name: string;
  balance: string; // DecimalField serializes as a string
  is_active: boolean;
};

function toPlayer(p: ApiPlayer): Player {
  return { id: p.id, accountCode: p.account_code, displayName: p.display_name, balance: Number(p.balance) };
}

async function cachePlayers(players: Player[]): Promise<void> {
  const db = await getDb();
  const now = new Date().toISOString();
  await db.withTransactionAsync(async () => {
    await db.runAsync('DELETE FROM players_cache');
    for (const p of players) {
      await db.runAsync(
        'INSERT INTO players_cache (id, account_code, display_name, balance, cached_at) VALUES (?, ?, ?, ?, ?)',
        p.id,
        p.accountCode,
        p.displayName,
        p.balance,
        now,
      );
    }
  });
}

async function getCachedPlayers(): Promise<Player[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<{
    id: number;
    account_code: string;
    display_name: string;
    balance: number;
  }>('SELECT id, account_code, display_name, balance FROM players_cache ORDER BY display_name ASC');
  return rows.map((r) => ({ id: r.id, accountCode: r.account_code, displayName: r.display_name, balance: r.balance }));
}

export async function getCacheAge(): Promise<Date | null> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ cached_at: string }>('SELECT cached_at FROM players_cache LIMIT 1');
  return row ? new Date(row.cached_at) : null;
}

/**
 * Only players/balances are read live (see PLAN.md's mobile-app entry) —
 * Deal writes never touch the network. Tries the real backend first and
 * refreshes the local cache on success; any failure (offline, expired
 * session, server error) silently falls back to whatever was last cached,
 * with `stale: true` so the UI can say so rather than pretend it's live.
 */
export async function getPlayers(): Promise<{ players: Player[]; stale: boolean }> {
  try {
    const data = await authorizedGet<ApiPlayer[]>('/api/players/');
    const players = data.filter((p) => p.is_active).map(toPlayer);
    await cachePlayers(players);
    return { players, stale: false };
  } catch {
    const players = await getCachedPlayers();
    return { players, stale: true };
  }
}
