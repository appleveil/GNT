import { getDb } from './database';
import type { DealRecord } from '../types';

/** Local id generator — not cryptographically strong, and doesn't need to
 * be: it's only ever a local primary key / arrangement reference, never a
 * security token. Avoids pulling in a UUID dependency for this alone. */
export function newId(): string {
  const rand = () => Math.floor(Math.random() * 16).toString(16);
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    if (c === 'x') return rand();
    return ((Math.random() * 4) | 8).toString(16); // y -> one of 8/9/a/b, per RFC4122
  });
}

async function insert(record: DealRecord): Promise<DealRecord> {
  const db = await getDb();
  const { id, kind, createdAt, ...rest } = record as any;
  await db.runAsync(
    'INSERT INTO deals (id, kind, created_at, payload) VALUES (?, ?, ?, ?)',
    id,
    kind,
    createdAt,
    JSON.stringify(rest),
  );
  return record;
}

// A plain Omit<DealRecord, ...> collapses DealRecord's discriminated union
// into only its common fields (losing e.g. FIXED's `amount` vs
// PROFIT_SPLIT_CREATED's `stakePct`) — this distributes the Omit over each
// union member individually instead, so callers still get the right
// kind-specific fields checked.
type DistributiveOmit<T, K extends keyof any> = T extends any ? Omit<T, K> : never;

export async function insertDeal(
  record: DistributiveOmit<DealRecord, 'id' | 'createdAt'> & { id?: string; createdAt?: string },
): Promise<DealRecord> {
  const full = {
    ...record,
    id: record.id ?? newId(),
    createdAt: record.createdAt ?? new Date().toISOString(),
  } as DealRecord;
  return insert(full);
}

type DealRow = { id: string; kind: string; created_at: string; payload: string };

function rowToRecord(row: DealRow): DealRecord {
  return { id: row.id, kind: row.kind, createdAt: row.created_at, ...JSON.parse(row.payload) } as DealRecord;
}

export async function getAllDeals(): Promise<DealRecord[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<DealRow>('SELECT * FROM deals ORDER BY created_at DESC');
  return rows.map(rowToRecord);
}

/**
 * The player's current arrangement, or null — "current" means the most
 * recent PROFIT_SPLIT_CREATED for this player that has no
 * PROFIT_SPLIT_ENDED referencing it. Computed in JS over the small local
 * log rather than in SQL — simplest given the low volume, and avoids a
 * self-join for a table that will realistically hold dozens, not
 * thousands, of rows on one Owner's phone.
 */
/** Every player id with a currently-active arrangement — one pass over the
 * local log, used to badge the Deals home player list without an N-query
 * loop per row. */
export async function getActiveProfitSplitPlayerIds(): Promise<Set<number>> {
  const all = await getAllDeals();
  const ended = new Set(all.filter((d) => d.kind === 'PROFIT_SPLIT_ENDED').map((d: any) => d.arrangementId));
  const activeIds = new Set<number>();
  for (const d of all) {
    if (d.kind === 'PROFIT_SPLIT_CREATED' && !ended.has(d.id)) activeIds.add((d as any).playerId);
  }
  return activeIds;
}

export async function getActiveProfitSplit(playerId: number): Promise<DealRecord | null> {
  const all = await getAllDeals();
  const ended = new Set(
    all.filter((d) => d.kind === 'PROFIT_SPLIT_ENDED').map((d: any) => d.arrangementId),
  );
  const created = all
    .filter((d) => d.kind === 'PROFIT_SPLIT_CREATED' && d.playerId === playerId && !ended.has(d.id))
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
  return created[0] ?? null;
}

function csvEscape(value: unknown): string {
  const s = String(value ?? '');
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

/**
 * A flat, human-readable export for manual reconciliation — deliberately
 * plain (one row per Deal event, common columns first) rather than trying
 * to preserve every kind-specific field, since whoever reconciles this by
 * hand needs to scan it quickly, not round-trip it programmatically.
 */
export function dealsToCsv(deals: DealRecord[]): string {
  const header = ['Date', 'Type', 'Player', 'Counterparty', 'Amount', 'Details'];
  const rows = deals.map((d) => {
    const date = new Date(d.createdAt).toLocaleString();
    switch (d.kind) {
      case 'FIXED':
        return [date, 'Fixed', d.playerName, '', d.amount, d.reason];
      case 'TRANSFER':
        return [date, 'Transfer', d.sourcePlayerName, d.destinationPlayerName, d.amount, d.reason];
      case 'PROFIT_SPLIT_CREATED': {
        const bits = [];
        if (d.stakeOn) bits.push(`${d.stakePct}% stake, cap ${d.cap}, renews ${d.renews}`);
        if (d.payoutOn) bits.push(`payout: ${d.payoutBasis}, ${d.payoutSplitMethod}`);
        return [date, 'Stake and Profit splits — set up', d.playerName, '', '', bits.join('; ') || 'no stake or payout set'];
      }
      case 'PROFIT_SPLIT_ENDED':
        return [date, 'Stake and Profit splits — ended', d.playerName, '', '', ''];
      default:
        return [date, (d as any).kind, '', '', '', ''];
    }
  });
  return [header, ...rows].map((r) => r.map(csvEscape).join(',')).join('\n');
}
