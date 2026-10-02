/**
 * src/composables/usePlainConfirm.js
 *
 * The "require approval" toggle's OFF fallback (added 2026-09-23, see
 * ClubSettings/PLAN.md's Settings entry): the same shape as
 * useAuthorizerConfirm.js — one modal instance, module-level (not
 * per-component) state, mounted once as PlainConfirmModal.vue in App.vue —
 * but with no owner/FM picker and no PIN, just a plain "are you sure?"
 * step. `onSubmit` is called with an empty payload (`{}`), so a call site
 * built for useAuthorizerConfirm's `onSubmit(payload)` can pass the exact
 * same closure to either composable unchanged — only which one gets
 * called differs (see StartGameDayModal.vue/useCloseGameDay.js/
 * TransactionEntryModal.vue for the branch itself).
 */
import { ref } from 'vue'
import { readApiError } from '@/utils/apiError'

export const isOpen = ref(false)
export const title = ref('')
export const subtitle = ref('')
export const submitting = ref(false)
export const error = ref('')

let onSubmitCallback = null

export function usePlainConfirm() {
  /**
   * @param {string} opts.title
   * @param {string} [opts.subtitle]
   * @param {(payload: object) => Promise<void>} opts.onSubmit - called with
   *   `{}` (no authorizer, no PIN). Throw to show an inline error and let
   *   the user retry; resolve to close the modal.
   */
  function plainConfirm({ title: t, subtitle: s, onSubmit }) {
    title.value = t
    subtitle.value = s || ''
    error.value = ''
    onSubmitCallback = onSubmit
    isOpen.value = true
  }

  function cancel() {
    isOpen.value = false
    onSubmitCallback = null
  }

  async function submit() {
    if (submitting.value) return
    submitting.value = true
    error.value = ''
    try {
      await onSubmitCallback({})
      isOpen.value = false
      onSubmitCallback = null
    } catch (err) {
      // Was `detail`-only — see useAuthorizerConfirm.js's matching fix.
      error.value = readApiError(err).message
    } finally {
      submitting.value = false
    }
  }

  return { isOpen, title, subtitle, submitting, error, plainConfirm, cancel, submit }
}
