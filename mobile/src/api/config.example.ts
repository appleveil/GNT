// Copy this file to config.ts (gitignored) and fill in real values.
//
// SECURITY NOTE: config.ts's credentials end up compiled into the JS
// bundle — readable by anyone who unpacks the app. That's an accepted,
// deliberate simplification ONLY because v1 has no login screen and is
// meant for a single trusted personal device (see PLAN.md's mobile-app
// entry). It MUST be replaced by a real per-user login before this app is
// ever shared with anyone else or distributed beyond that one phone.
//
// This account only ever needs to READ players/balances — Deal writes are
// saved locally only for now (see src/db), so a compromised credential
// here can't move money, only view the roster.

export const API_BASE_URL = 'https://your-backend.example.com';
export const OWNER_USERNAME = 'owner-readonly-username';
export const OWNER_PASSWORD = 'owner-password';
