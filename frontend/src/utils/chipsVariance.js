/**
 * src/utils/chipsVariance.js
 *
 * GameDaySummary.chips_variance (backend: gaming/selectors.py's
 * game_day_summary_data) is signed: chips_out_total - chips_in_total -
 * rake_total - tips_total. Positive = a deficit (chips still off-site/
 * unreturned tonight); negative = excess (chips from an earlier off-site
 * day coming back into play). Every screen that shows this figure (or the
 * club-wide running total, outstanding_chips/outstanding_chips_after_close,
 * same sign meaning) needs the same sign-aware label/styling rather than a
 * bare signed number under a label that only makes sense for the positive
 * case — added 2026-09-17 after that was flagged as reading like a warning
 * even on a night with excess chips returned.
 */
export function describeChipsVariance(variance) {
  const v = Number(variance)
  if (v > 0) return { label: 'Chips deficit', amount: v, className: 'variance--deficit' }
  if (v < 0) return { label: 'Chips excess returned', amount: -v, className: 'variance--excess' }
  return { label: 'Chips balanced', amount: 0, className: 'variance--balanced' }
}
