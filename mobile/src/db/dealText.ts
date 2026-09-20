import type { DealRecord } from '../types';
import { naira } from '../components/ui';

/** The row title shown in History — also the first line of a shared export. */
export function dealTitle(d: DealRecord): string {
  switch (d.kind) {
    case 'FIXED':
      return `Fixed — ${d.playerName}`;
    case 'TRANSFER':
      return `Transfer — ${d.sourcePlayerName} → ${d.destinationPlayerName}`;
    case 'PROFIT_SPLIT_CREATED':
      return `Stake and Profit splits — ${d.playerName}`;
    case 'PROFIT_SPLIT_ENDED':
      return `Stake and Profit splits ended — ${d.playerName}`;
  }
}

/**
 * The one-line summary shown under a History row. For a Profit Split,
 * this describes whichever of Stake/Payout is actually set — a stake if
 * one is set, otherwise the payout split if THAT'S set instead, since an
 * arrangement need not have both (see ProfitSplitScreen's opt-in toggles).
 */
export function dealSummary(d: DealRecord): string {
  switch (d.kind) {
    case 'FIXED':
      return d.reason;
    case 'TRANSFER':
      return d.reason;
    case 'PROFIT_SPLIT_CREATED':
      if (d.stakeOn) {
        return `${d.stakePct}% stake · ${naira(d.cap ?? 0)} cap · renews ${cadenceLabel(d.renews)}`;
      }
      if (d.payoutOn) {
        return `Payout only · ${d.payoutBasis === 'BEFORE_BUYIN' ? 'before buy-in' : 'after buy-in'} · ${splitMethodShort(d)}`;
      }
      return 'No stake or payout set';
    case 'PROFIT_SPLIT_ENDED':
      return 'Arrangement ended';
  }
}

function cadenceLabel(renews: string | null): string {
  const labels: Record<string, string> = { ONE_OFF: 'one-off', DAILY: 'daily', WEEKLY: 'weekly', MONTHLY: 'monthly' };
  return (renews && labels[renews]) || 'one-off';
}

function splitMethodShort(d: Extract<DealRecord, { kind: 'PROFIT_SPLIT_CREATED' }>): string {
  if (d.payoutSplitMethod === 'STAKE_RATIO') return 'ratio per stake';
  if (d.payoutSplitMethod === 'CUSTOM_RATIO') return `${d.customRatioPct}% to house`;
  if (d.payoutSplitMethod === 'FIXED') return `fixed ${naira(d.fixedAmount ?? 0)}`;
  return '';
}

/** The full, multi-line plain-text version — what gets shared/exported for one Deal. */
export function dealFullText(d: DealRecord): string {
  const when = new Date(d.createdAt).toLocaleString();
  const lines = [dealTitle(d), when, ''];

  switch (d.kind) {
    case 'FIXED':
      lines.push(`Amount cleared: ${naira(d.amount)}`, `Reason: ${d.reason}`);
      break;
    case 'TRANSFER':
      lines.push(
        `From: ${d.sourcePlayerName}`,
        `To: ${d.destinationPlayerName}`,
        `Amount: ${naira(d.amount)}`,
        `Reason: ${d.reason}`,
      );
      break;
    case 'PROFIT_SPLIT_CREATED':
      if (d.stakeOn) {
        lines.push(
          'Stake:',
          `  House stake: ${d.stakePct}%`,
          `  Cap: ${naira(d.cap ?? 0)} / period`,
          `  Renews: ${cadenceLabel(d.renews)}`,
        );
        if (d.until) lines.push(`  Until: ${d.until}`);
        if (d.maxTimes) lines.push(`  Number of times: ${d.maxTimes}`);
        if (d.maxValue) lines.push(`  Max value: ${naira(d.maxValue)}`);
      } else {
        lines.push('Stake: none set');
      }
      lines.push('');
      if (d.payoutOn) {
        lines.push(
          'Payout:',
          `  Basis: ${d.payoutBasis === 'BEFORE_BUYIN' ? 'Before buy-in' : 'After buy-in'}`,
          `  Split method: ${splitMethodShort(d)}`,
        );
      } else {
        lines.push('Payout: none set');
      }
      break;
    case 'PROFIT_SPLIT_ENDED':
      lines.push('This arrangement was ended.');
      break;
  }

  lines.push('', '— LPC Deals');
  return lines.join('\n');
}
