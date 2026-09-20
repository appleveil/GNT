/**
 * "Ledger Slate" — the same design tokens as frontend/src/assets/tokens.css,
 * ported to plain hex/rgba since React Native's style system has no oklch()
 * support. Hex values below are computed directly from the web app's oklch()
 * definitions (via the standard OKLab conversion matrices), not eyeballed —
 * see PLAN.md's mobile-app entry for how they were derived. Do not hand-tune
 * a value here without updating that source of truth too.
 */

export const colors = {
  bg: '#F4F6F8',
  surface: '#FFFFFF',
  textPrimary: '#1C222B',
  textSecondary: '#5B6572',
  textTertiary: '#8B95A1',
  border: '#D7DEE5',
  borderStrong: '#C6D0DA',

  accent: '#116BB5',
  accentBg: '#DDEDFF',
  accentText: '#00488F',

  success: '#3E8343',
  successBg: '#DBF3DB',
  successText: '#095717',

  warning: '#D29922',
  warningBg: '#FFECC9',
  warningText: '#7A4A00',

  danger: '#C53637',
  dangerBg: '#FFE2DE',
  dangerText: '#900007',

  muted: '#C6D0DA',
  disabledSurface: '#FAFBFC',
  disabledBorder: '#E7EBEE',
} as const;

export const radii = {
  sm: 8,
  md: 10,
} as const;

// IBM Plex Sans/Mono aren't preloaded system fonts on iOS/Android — a later
// pass should bundle them via expo-font (see CONCEPT.md's Ledger Slate
// note). Falling back to the platform system font for now keeps v1 moving;
// this is a deliberate, cheap-to-fix gap, not an oversight.
export const fonts = {
  sans: undefined, // system default
  mono: undefined, // system default; swap to 'IBMPlexMono-SemiBold' once bundled
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
} as const;

export const controlHeights = {
  primary: 52,
  row: 44,
} as const;
