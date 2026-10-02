/**
 * src/composables/useAuthorizerConfirm.js
 *
 * Shared plumbing for every Owner-or-Floor-Manager-PIN-gated action (Open
 * Game-Day, Set FX Rate, and later Chips Out/In etc.) — one modal instance,
 * driven by module-level (not per-component) state so any view can trigger
 * it via confirm() without rendering its own copy. See
 * components/shared/AuthorizerConfirmModal.vue, mounted once in App.vue.
 *
 * The actual API call lives with the caller, passed in as `onSubmit` — the
 * modal just collects {owner_id, owner_pin} or {floor_manager_id,
 * floor_manager_pin} and reports the caller's success/failure back inline
 * (PinModalError / PinModalLoading in the design canvas), rather than
 * closing blindly and letting the caller sort out an error toast elsewhere.
 */
import { ref } from 'vue'
import api from '@/api/axios'
import { readApiError } from '@/utils/apiError'

export const isOpen = ref(false)
export const step = ref('select') // 'select' | 'pin'
export const title = ref('')
export const subtitle = ref('')
export const mode = ref('owner-or-fm') // 'owner-or-fm' | 'fm-only'
export const people = ref([]) // [{ type: 'owner'|'floor_manager', id, name, roleLabel }]
export const peopleLoading = ref(false)
export const selected = ref(null)
export const pin = ref('')
export const error = ref('')
export const submitting = ref(false)

let onSubmitCallback = null

async function loadPeople() {
  peopleLoading.value = true
  try {
    if (mode.value === 'fm-only') {
      // Physical-count entries (chips, cash, rake, tips) require a real Floor
      // Manager — gaming.services.record_transaction has no Owner-PIN bypass
      // branch the way open_game_day/set_conversion_rate do, so an Owner
      // can't stand in here; don't even offer the option.
      const { data } = await api.get('/floor-managers/')
      people.value = data.map(f => ({ type: 'floor_manager', id: f.id, name: f.name, roleLabel: 'Floor Manager' }))
      return
    }
    const [ownersRes, fmsRes] = await Promise.all([
      api.get('/staff-users/owners/'),
      api.get('/floor-managers/'),
    ])
    people.value = [
      ...ownersRes.data.map(o => ({
        type: 'owner', id: o.id, name: o.first_name || o.username, roleLabel: 'Owner',
      })),
      ...fmsRes.data.map(f => ({
        type: 'floor_manager', id: f.id, name: f.name, roleLabel: 'Floor Manager',
      })),
    ]
  } finally {
    peopleLoading.value = false
  }
}

export function useAuthorizerConfirm() {
  /**
   * @param {string} opts.title - e.g. "Open Game-Day #14"
   * @param {string} opts.subtitle - e.g. "Will start now"
   * @param {'owner-or-fm'|'fm-only'} [opts.mode] - 'fm-only' for physical-count
   *   entries (Chips Out/In, Cash, Rake, Tip): only Floor Managers are offered,
   *   never Owners. Defaults to 'owner-or-fm' (Open Game-Day, Set FX Rate).
   * @param {(payload: object) => Promise<void>} opts.onSubmit - performs the
   *   actual API call with the resolved {owner_id/owner_pin} or
   *   {floor_manager_id/floor_manager_pin}. Throw to show an inline error
   *   and let the user retry; resolve to close the modal.
   */
  function confirm({ title: t, subtitle: s, mode: m = 'owner-or-fm', onSubmit }) {
    title.value = t
    subtitle.value = s
    mode.value = m
    step.value = 'select'
    selected.value = null
    pin.value = ''
    error.value = ''
    onSubmitCallback = onSubmit
    isOpen.value = true
    loadPeople()
  }

  function selectPerson(person) {
    selected.value = person
    step.value = 'pin'
    pin.value = ''
    error.value = ''
  }

  function backToSelect() {
    step.value = 'select'
    pin.value = ''
    error.value = ''
  }

  function appendDigit(d) {
    if (submitting.value) return
    if (pin.value.length < 8) pin.value += d
  }

  function backspace() {
    if (submitting.value) return
    pin.value = pin.value.slice(0, -1)
  }

  function cancel() {
    isOpen.value = false
    onSubmitCallback = null
  }

  async function submit() {
    if (!selected.value || !pin.value || submitting.value) return
    const payload = selected.value.type === 'owner'
      ? { owner_id: selected.value.id, owner_pin: pin.value }
      : { floor_manager_id: selected.value.id, floor_manager_pin: pin.value }

    submitting.value = true
    error.value = ''
    try {
      await onSubmitCallback(payload)
      isOpen.value = false
      onSubmitCallback = null
    } catch (err) {
      // Was `detail`-only — a real bug (2026-10-02 fix): a field error (e.g.
      // on the amount this PIN sheet is confirming, not the PIN itself)
      // used to be swallowed into a generic "Something went wrong." See
      // utils/apiError.js's readApiError.
      error.value = readApiError(err).message
      pin.value = ''
    } finally {
      submitting.value = false
    }
  }

  return {
    isOpen, step, title, subtitle, mode, people, peopleLoading, selected, pin, error, submitting,
    confirm, selectPerson, backToSelect, appendDigit, backspace, cancel, submit,
  }
}
