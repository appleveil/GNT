import * as SQLite from 'expo-sqlite';

/**
 * The local Deals log — the permanent record for now, per PLAN.md's
 * "manual reconciliation later" decision (no backend sync for writes yet).
 * One `deals` table, `payload` a JSON blob of the kind-specific fields
 * (see src/types.ts's DealRecord union) — deliberately not fully
 * normalized: this is a small, low-volume local log, and a JSON payload
 * means adding a new Deal kind later never needs a schema migration.
 */

let dbPromise: Promise<SQLite.SQLiteDatabase> | null = null;

export function getDb(): Promise<SQLite.SQLiteDatabase> {
  if (!dbPromise) {
    dbPromise = SQLite.openDatabaseAsync('lpc_deals.db').then(async (db) => {
      await db.execAsync(`
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS deals (
          id TEXT PRIMARY KEY NOT NULL,
          kind TEXT NOT NULL,
          created_at TEXT NOT NULL,
          payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_deals_created_at ON deals (created_at);
        CREATE INDEX IF NOT EXISTS idx_deals_kind ON deals (kind);

        -- A cached copy of the real backend's player roster/balances, so the
        -- Deals screens have something to show (and validate against) even
        -- with no connectivity. Always overwritten wholesale on a
        -- successful fetch — see src/api/players.ts. Never the write path.
        CREATE TABLE IF NOT EXISTS players_cache (
          id INTEGER PRIMARY KEY NOT NULL,
          account_code TEXT NOT NULL,
          display_name TEXT NOT NULL,
          balance REAL NOT NULL,
          cached_at TEXT NOT NULL
        );
      `);
      return db;
    });
  }
  return dbPromise;
}
