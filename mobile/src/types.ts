// Shared types for the Deals app. See PLAN.md's mobile-app entry for the
// architecture this maps to: players/balances are read-only from the real
// Django backend (cached locally for offline viewing); Deal records
// themselves are written to local storage only for now — see src/db.

export type Player = {
  id: number;
  displayName: string;
  accountCode: string;
  /** Lifetime balance, Naira. Negative = owes the club, positive = credit. */
  balance: number;
};

export type ResetCadence = 'ONE_OFF' | 'DAILY' | 'WEEKLY' | 'MONTHLY';
export type PayoutBasis = 'BEFORE_BUYIN' | 'AFTER_BUYIN';
export type PayoutSplitMethod = 'STAKE_RATIO' | 'CUSTOM_RATIO' | 'FIXED';
export type PayoutLifespan = 'INDEFINITE' | 'DEBT_CLEARED' | 'CAPPED';

/**
 * One row in the local Deals log — see src/db/deals.ts. This is the
 * permanent local record for now (no sync yet, per PLAN.md's "manual
 * reconciliation" decision); `kind` mirrors the three Deal types from
 * CONCEPT.md.
 */
export type DealRecord =
  | {
      id: string;
      kind: 'FIXED';
      createdAt: string; // ISO 8601
      playerId: number;
      playerName: string;
      amount: number;
      reason: string;
    }
  | {
      id: string;
      kind: 'TRANSFER';
      createdAt: string;
      sourcePlayerId: number;
      sourcePlayerName: string;
      destinationPlayerId: number;
      destinationPlayerName: string;
      amount: number;
      reason: string;
    }
  | {
      id: string;
      kind: 'PROFIT_SPLIT_CREATED';
      createdAt: string;
      playerId: number;
      playerName: string;
      stakeOn: boolean;
      stakePct: number | null;
      cap: number | null;
      renews: ResetCadence | null;
      until: string | null;
      maxTimes: number | null;
      maxValue: number | null;
      payoutOn: boolean;
      payoutBasis: PayoutBasis | null;
      payoutSplitMethod: PayoutSplitMethod | null;
      customRatioPct: number | null;
      fixedAmount: number | null;
      fixedOffset: number | null;
      /** How long the payout split applies. Absent on records saved before
       * this existed — always treat that as 'INDEFINITE', the prior
       * behaviour (see dealText.ts::payoutLifespanLabel). */
      payoutLifespan: PayoutLifespan | null;
      /** Only meaningful when payoutLifespan is 'CAPPED': the house's
       * cumulative take across every payout event, before the split
       * stops. Not enforced anywhere — the app has no record of
       * individual payout events to sum against this, so it's advisory
       * only, same as Stake's own Until/Number of times/Max value. */
      payoutCapAmount: number | null;
    }
  | {
      id: string;
      kind: 'PROFIT_SPLIT_ENDED';
      createdAt: string;
      playerId: number;
      playerName: string;
      /** id of the PROFIT_SPLIT_CREATED record this ends. */
      arrangementId: string;
      reason: string;
    };

export type DealKindFilter = 'ALL' | 'FIXED' | 'TRANSFER' | 'PROFIT_SPLIT';
