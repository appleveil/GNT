/**
 * src/composables/useCloseGameDay.js
 *
 * Shared "Close Game-Day" flow — module-level state (same pattern as
 * useAuthorizerConfirm/useToast), one <CloseGameDayModal /> mounted once in
 * App.vue. Moved out of ActiveGameDayView.vue (2026-09-21) so the trigger
 * can live in AppShell's topbar, next to the "Game-Day #N · OPEN" status
 * pill it acts on, instead of a small link buried at the bottom of the
 * ledger — see the Cashier layout wireframe review this came out of.
 *
 * Revised 2026-09-22 — three checks now run before the PIN step, in order:
 *   1. Hard block (preview.close_blocked_reason) — a player is still
 *      seated. Not overridable; nothing to acknowledge, just not ready.
 *   2. Chip discrepancy (preview.chip_discrepancy) — chips don't
 *      reconcile (gaming.services.game_day_chip_discrepancy). Doesn't
 *      block closing outright any more (a player may genuinely have
 *      walked off with chips) — it must be ACKNOWLEDGED: a reason is
 *      required, and authorization widens from Floor-Manager-only to
 *      Owner-or-Floor-Manager for that close.
 *   3. Rake exactly ₦0 — a likely miscount, one extra "are you sure?"
 *      (unrelated to the discrepancy check — both can apply to the same
 *      close, discrepancy first).
 * Whichever checks apply run in that order before the shared
 * useAuthorizerConfirm PIN modal opens.
 */
import { ref } from 'vue'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import { useClubSettingsStore } from '@/stores/clubSettings'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import { usePlainConfirm } from '@/composables/usePlainConfirm'

export const preview = ref(null) // null = dialog closed; the close-preview payload otherwise
export const error = ref('') // preview-LOAD failures only — see confirm()'s own error handling
export const discrepancyReason = ref('') // bound to the reason textarea when preview.chip_discrepancy is set
// True while showing "are you sure there's no rake?" in place of the
// normal actions row.
export const rakeConfirmStep = ref(false)

export function useCloseGameDay() {
  const gameDay = useGameDayStore()
  const clubSettings = useClubSettingsStore()
  const { confirm: authorize } = useAuthorizerConfirm()
  const { plainConfirm } = usePlainConfirm()

  async function openConfirm() {
    error.value = ''
    discrepancyReason.value = ''
    rakeConfirmStep.value = false
    try {
      const { data } = await api.get(`/game-days/${gameDay.current.id}/close-preview/`)
      preview.value = data
    } catch {
      error.value = 'Could not load game-day totals.'
    }
  }

  function proceedToAuthorize() {
    const hasDiscrepancy = !!preview.value?.chip_discrepancy
    const opts = {
      title: `Close Game-Day #${gameDay.current?.number}`,
      subtitle: hasDiscrepancy
        ? 'Chip discrepancy acknowledged — requires the Owner or a Floor Manager PIN.'
        : "Requires a Floor Manager PIN — the night's final chip count.",
      mode: hasDiscrepancy ? 'owner-or-fm' : 'fm-only',
      onSubmit: async payload => {
        await api.post(`/game-days/${gameDay.current.id}/close/`, {
          ...payload,
          discrepancy_reason: hasDiscrepancy ? discrepancyReason.value.trim() : '',
        })
        preview.value = null
        gameDay.current = null
      },
    }
    // ClubSettings.require_approval_close_game_day (Owner-editable) only
    // ever streamlines the ORDINARY close — a discrepancy always requires
    // sign-off regardless, so `authorize` is the only path once hasDiscrepancy.
    if (!hasDiscrepancy && clubSettings.current?.require_approval_close_game_day === false) plainConfirm(opts)
    else authorize(opts)
  }

  // The rake check — shared by the plain "Close Game-Day" button and by
  // acknowledgeDiscrepancy() below, since a discrepancy and a zero rake
  // can both apply to the same close (discrepancy is asked about first).
  function afterDiscrepancyStep() {
    if (Number(preview.value?.rake_total) === 0) {
      rakeConfirmStep.value = true
      return
    }
    proceedToAuthorize()
  }

  // The dialog's plain "Close Game-Day" button — only shown once there's
  // no discrepancy to acknowledge first.
  function confirm() {
    afterDiscrepancyStep()
  }

  function acknowledgeDiscrepancy() {
    if (!discrepancyReason.value.trim()) return
    afterDiscrepancyStep()
  }

  function confirmNoRake() {
    rakeConfirmStep.value = false
    proceedToAuthorize()
  }

  function cancelRakeConfirm() {
    rakeConfirmStep.value = false
  }

  function cancel() {
    preview.value = null
    error.value = ''
    discrepancyReason.value = ''
    rakeConfirmStep.value = false
  }

  return {
    preview, error, discrepancyReason, rakeConfirmStep,
    openConfirm, confirm, acknowledgeDiscrepancy, confirmNoRake, cancelRakeConfirm, cancel,
  }
}
