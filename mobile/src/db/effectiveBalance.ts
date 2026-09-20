import { getAllDeals } from './deals';
import type { Player } from '../types';

/**
 * A player's real balance is only as fresh as the last successful backend
 * fetch (see src/api/players.ts) — it has no idea about a Fixed write-off
 * or Transfer entered locally five minutes ago. This computes each
 * player's net local adjustment from the saved Deals log and layers it on
 * top, so the app stays internally consistent between backend syncs
 * (e.g. writing off a player's debt actually lowers what the app shows as
 * their outstanding balance from then on, even though nothing has reached
 * the real ledger yet — see PLAN.md's "local-only for now" note).
 *
 * Profit Split doesn't move money at arrangement-creation time, so it has
 * no balance effect here.
 */
export async function getLocalAdjustments(): Promise<Map<number, number>> {
  const all = await getAllDeals();
  const adjustments = new Map<number, number>();
  const add = (playerId: number, delta: number) => adjustments.set(playerId, (adjustments.get(playerId) ?? 0) + delta);

  for (const d of all) {
    if (d.kind === 'FIXED') {
      add(d.playerId, d.amount); // a write-off reduces debt — a credit
    } else if (d.kind === 'TRANSFER') {
      add(d.sourcePlayerId, -d.amount);
      add(d.destinationPlayerId, d.amount);
    }
  }
  return adjustments;
}

export function applyAdjustments(players: Player[], adjustments: Map<number, number>): Player[] {
  return players.map((p) => {
    const delta = adjustments.get(p.id);
    return delta ? { ...p, balance: p.balance + delta } : p;
  });
}

/** Convenience wrapper: fetch adjustments and apply them in one call. */
export async function withEffectiveBalances(players: Player[]): Promise<Player[]> {
  const adjustments = await getLocalAdjustments();
  return applyAdjustments(players, adjustments);
}

export async function getEffectiveBalance(player: Player): Promise<number> {
  const adjustments = await getLocalAdjustments();
  return player.balance + (adjustments.get(player.id) ?? 0);
}
