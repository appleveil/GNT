/**
 * src/utils/apiError.js
 *
 * readApiError(err) — the one place every form reads a failed API response,
 * replacing the six ad-hoc variants a 2026-10-02 site-wide audit found
 * (detail-only, first-field-only, first-field-then-detail, one hard-coded
 * field, detail-then-reason[0], AdminView's own `errors` array join — see
 * PLAN.md's dated entry). DRF's own shapes, all handled:
 *   - {"detail": "..."}                   — permission/auth/InvalidStateError
 *   - {"field_name": ["msg", ...], ...}   — serializer field errors
 *   - {"non_field_errors": ["msg", ...]}  — serializer-level errors
 *   - {"errors": ["msg", ...]}            — AccountCodeViewSet's bulk-upload shape
 *   - a plain string, or no response body at all — network failure
 *
 * Returns { message, fields }: `fields` maps field name -> first message
 * (feed straight to useFormValidation's applyServerErrors); `message` is
 * always one string — the right thing to show when there's nowhere more
 * specific to put it (non_field_errors, detail, a field this form doesn't
 * render, or no response at all).
 */
export function readApiError(err, fallback = 'Something went wrong. Try again.') {
  const data = err?.response?.data
  if (!data) return { message: fallback, fields: {} }
  if (typeof data === 'string') return { message: data, fields: {} }

  const fields = {}
  let message = null

  for (const [key, value] of Object.entries(data)) {
    const text = Array.isArray(value) ? value[0] : value
    if (key === 'detail') {
      message = text
    } else if (key === 'non_field_errors' || key === 'errors') {
      message = Array.isArray(value) ? value.join(' ') : text
    } else if (text) {
      fields[key] = text
    }
  }

  if (!message) {
    const firstField = Object.keys(fields)[0]
    message = firstField ? fields[firstField] : fallback
  }

  return { message, fields }
}
