/**
 * src/composables/useFormValidation.js
 *
 * Shared field-level validation for every form in the app — added
 * 2026-10-02 after a site-wide audit found ~4 different validation styles
 * spread across 22 forms (see PLAN.md's dated entry). One style everywhere
 * from here on:
 *   - a field's problem shows as red text under it, plus a red border,
 *     once that field has been touched (blurred) or a submit was attempted
 *   - Save stays clickable; clicking it with problems touches every field
 *     so they all reveal at once
 *   - a server-side field error (applyServerErrors, fed by
 *     utils/apiError.js's readApiError) marks that field the same way,
 *     even when no client-side rule caught it
 *   - `formError` holds anything that isn't a specific field
 *     (non_field_errors, detail, a field this form doesn't render)
 *
 * Usage:
 *   const amount = ref('')
 *   const { touched, errors, isValid, formError, touch, touchAll, applyServerErrors } =
 *     useFormValidation({ amount: { value: amount, rules: [required(), maxValue(1000000)] } })
 *   // template:
 *   //   <input v-model="amount" @blur="touch('amount')" :class="{ 'input--invalid': touched.amount && errors.amount }" />
 *   //   <p v-if="touched.amount && errors.amount" class="field-error">{{ errors.amount }}</p>
 *   //   <button :disabled="submitting" @click="onSubmit">Save</button>
 *   // onSubmit: touchAll(); if (!isValid.value) return; ... catch (err) { applyServerErrors(err) }
 */
import { computed, reactive, ref } from 'vue'
import { readApiError } from '@/utils/apiError'

// --- rule factories — each returns (value) => message|null ---

export function required(message = 'Required.') {
  return value => (value === '' || value == null ? message : null)
}
export function minValue(n, message = `Must be at least ${n}.`) {
  return value => (value !== '' && value != null && Number(value) < n ? message : null)
}
export function maxValue(n, message = `Must be at most ${n.toLocaleString()}.`) {
  return value => (value !== '' && value != null && Number(value) > n ? message : null)
}
export function maxPct(message = "Can't be more than 100%.") {
  return maxValue(100, message)
}
export function minPct(message = "Can't be negative.") {
  return minValue(0, message)
}
export function digits(n, message = `Must be ${n} digits.`) {
  return value => (value && String(value).length !== n ? message : null)
}
export function minLength(n, message = `Must be at least ${n} characters.`) {
  return value => (value && String(value).length < n ? message : null)
}

export function useFormValidation(fields) {
  const touched = reactive({})
  const serverErrors = reactive({})
  const formError = ref('')

  const errors = computed(() => {
    const result = {}
    for (const [name, field] of Object.entries(fields)) {
      const value = field.value?.value
      let message = null
      for (const rule of field.rules || []) {
        message = rule(value)
        if (message) break
      }
      result[name] = message || serverErrors[name] || null
    }
    return result
  })

  const isValid = computed(() => Object.values(errors.value).every(m => !m))

  function touch(name) {
    touched[name] = true
  }
  function touchAll() {
    for (const name of Object.keys(fields)) touched[name] = true
  }
  function clearServerErrors() {
    for (const key of Object.keys(serverErrors)) delete serverErrors[key]
  }

  // Feed straight from a catch block: applyServerErrors(err). Maps a field
  // error from readApiError onto the matching field (and touches it, so it
  // shows immediately without needing a blur first); anything left over —
  // non_field_errors/detail, or a field this form doesn't render — becomes
  // formError.
  function applyServerErrors(err) {
    const { message, fields: fieldErrors } = readApiError(err)
    clearServerErrors()
    let matchedAny = false
    for (const [name, msg] of Object.entries(fieldErrors)) {
      if (name in fields) {
        serverErrors[name] = msg
        touched[name] = true
        matchedAny = true
      }
    }
    formError.value = matchedAny ? '' : message
  }

  function reset() {
    for (const key of Object.keys(touched)) delete touched[key]
    clearServerErrors()
    formError.value = ''
  }

  return { touched, errors, isValid, formError, touch, touchAll, applyServerErrors, reset }
}
