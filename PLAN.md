# LPC Cashier / Player Payment Tracking — Project Plan

The living roadmap for this project. `CONCEPT.md`/`SCHEMA.md` are the domain reference (what the system does and why); this file is the execution tracker (what's built vs. what's next). Update the checkboxes here at the end of each work session — same discipline already applied to CONCEPT.md's dated "Built" sections.

Written 2026-09-14, from a direct audit of the repo (test run, `git log`, file/route inventory) — not from memory.

---

## 1. Completed

### Backend (Django + DRF + JWT — `backend/`)

- [x] `af1a283` Import concept brief, scope decisions, schema plan (`CONCEPT.md`/`SCHEMA.md`)
- [x] `21b287e` Scaffold Django apps: `accounts`, `gaming`, `payments`, per `SCHEMA.md`
- [x] `bc78645` Ledger selectors + authorization services (master-ledger pattern — all "ledgers" are queries over `Transaction`, nothing else stored)
- [x] `b3109df` DRF API layer + JWT auth
- [x] `50fbec4` Closed-game-day guard enforced server-side
- [x] `ed37258` Paystack webhook handler (signature verification, `charge.success`/`transfer.*` events)
- [x] `6de8326` `seed_demo_data` management command
- [x] `f3772e7` Owner PIN auth (distinct from login password), `chips_variance` (off-site/excess chips as a computed close-time figure, not a manual entry), chips-limit enforcement, Cashier balance-visibility split (never shows a negative lifetime balance)
- [x] `877c7c5` + `cff89f1` Real Paystack integration: one club-wide integration, Customer+DVA provisioning model (corrected from the original per-player-integration idea), real Transfer-API payouts with `TRANSFER_FAILED` state
- [x] `c0da822` Game-day seating (`GameDayPlayer` — "seated at tonight's table," a real new concept, not derivable from `Transaction` rows alone), case-insensitive login, payout hard-capped at the player's actual tonight's winnings, Cashier's Floor-Manager/Owner picker endpoints
- [x] `7d4f055` Paystack bank-list + account-number-resolve endpoints (`GET /api/payments/banks/`, `GET /api/payments/resolve-account/`)
- [x] `66b024a` Fixed a real balance bug: `game_day_ledger`'s club-wide running balance was being read as an individual player's own balance; added the correctly per-player-partitioned `game_day_activity_feed` selector + `GET /api/game-days/{id}/activity/`

**94/94 tests passing.**

### Frontend — Cashier (Vue 3 + Vite + Pinia — `frontend/`)

- [x] `f728bc0` Scaffold (Vite/Pinia/vue-router/axios, JWT-claim-decoding auth store, tokens.css design system — "Ledger Slate," built fresh via the `design` skill, not ported from anywhere), Login, Players list, Open/Close Game-Day
- [x] `c6103c3` Player Detail (game-day-scoped balance, Gaming Account/DVA status, bank accounts, Pay Out Balance) — found and fixed a real backend bug along the way (default-bank-account `IntegrityError`)
- [x] `7d4f055` + `ae19342` Bank-account picker: type-to-filter combobox over real Paystack banks, live account-number resolve ("is this you?" confirmation)
- [x] `9d2e40e` The real Active Game-Day working screen: general entries (Rake/Tip), per-player action grid (Issue Chips, Chips In, Cash/POS/Transfer payments, Payout), type-to-filter player picker + recent pills, `TransactionEntryModal` for all 7 Cashier-facing transaction types, Floor-Manager-only PIN mode (`useAuthorizerConfirm`'s `fm-only` mode) for physical counts
- [x] `08480ec` Fixed a real crash: blank screen on login (temporal-dead-zone bug in `ActiveGameDayView`'s setup order)
- [x] `66b024a` Frontend half of the per-player-balance fix above — the activity feed now calls `/activity/`, not `/ledger/`

**No Owner, Accountant, or Platform Administrator frontend exists yet** — every screen built so far is Cashier-only, reachable by any authenticated role (the `meta.roles` route-guard mechanism exists in the router but is unused).

---

## 2. Remaining work, in execution order

### Phase A — Round out Cashier v1
- [x] Void-entry UI — `VoidEntryModal.vue`, wired into the Active Game-Day activity feed's per-row trigger, `canVoid.js` mirroring the backend's own eligibility rule. Surfaced and fixed a real backend bug along the way: voided rows were being filtered out of every ledger listing entirely rather than staying visible-but-struck-through as designed.
- [x] **Player Game-Day History view** — built as a "Tonight's activity" section on `PlayerDetailView` (not a separate route): this player's own transaction list for tonight only, via `GET /api/game-days/{id}/players/{player_pk}/ledger/`, with the same void action available inline.
- [x] Payout status/history — "Payouts this game-day" list added to `PlayerDetailView`'s payout section (replaces the old single inline confirmation banner), status-badged, reusing the same ledger fetch as the history section above (filtered to `type === 'PAYOUT'`).
- [ ] Dedicated (club-wide) Game-Day Ledger view — replace the placeholder stub at `views/game-day/GameDayLedgerView.vue`; club-wide running balance (`GET .../ledger/`, already correct and tested — distinct from the per-player `.../activity/` endpoint the working screen uses)
- [x] Toasts — `useToast.js`/`AppToast.vue`, mounted once in `App.vue`; used for void-success feedback so far
- [ ] Rest of polish pass: loading/empty/error states audit, tablet-viewport check

### Phase B — Accountant frontend
- [ ] Dashboard: outstanding balances owed by/to players, Outstanding Chips (`GET /api/dashboard/` already returns this, gated correctly server-side)
- [ ] Game-day history/detail (read-only)
- [ ] Player list + per-player detail incl. any game-day's ledger, and the Outstanding (between-game-day) ledger (`GET /api/outstanding/`, already built, `IsOwnerOrAccountant`)
- [ ] Role-based route guarding actually wired up (the unused `meta.roles` mechanism) — needed the moment a second role's UI exists
- [ ] New, distinct style guide for this surface — see "Design decisions" below

### Phase C — Owner frontend
- [ ] Everything in Accountant's dashboard, plus the real Main-account balance
- [ ] Staff management (create/deactivate Cashier/Accountant, reset passwords) — `StaffUserViewSet` already supports this
- [ ] Floor Manager management (create/deactivate) — `FloorManagerViewSet` already supports this
- [ ] Chips-limit setting per player
- [ ] Deal / write-off entry — backend already accepts `PAYMENT_DEAL`/`WRITE_OFF` via `POST /transactions/` (Owner-only), no dedicated UI
- [ ] Payout approval queue (`POST /transactions/{id}/approve/` exists; needs a live pending-approvals list, not just history)
- [ ] FX rate setting (`POST /conversion-rates/set_rate/` exists, standing + per-game-day override)
- [ ] Open Game-Day trigger from Owner's own login (no FM PIN needed — backend already supports the Owner-login bypass branch)
- [ ] Post-close corrections/amendments

### Phase D — Platform Administrator role + Integration Settings
Today the Paystack integration (secret/public keys) is env-var-only (`settings.PAYSTACK_SECRET_KEY`/`PAYSTACK_PUBLIC_KEY`, read directly by `payments/paystack_client.py`) — there is no interface to configure it, by anyone. This phase gives it a real interface, owned by a **new role**, not folded into Owner:
- [ ] Add `PLATFORM_ADMIN` to `StaffUser.Role` (currently `OWNER`/`CASHIER`/`ACCOUNTANT`) — new migration, new permission class(es) alongside the existing `IsOwner`/`IsCashierOrOwner`/`IsOwnerOrAccountant`
- [ ] New DB-backed integration-settings model (singleton, like `PaystackAccount`'s `MAIN` row) to hold what's currently env-var-only: secret key, public key, webhook secret, preferred DVA bank, etc. — secret-bearing fields write-only/masked in API responses, mirroring `FloorManager.pin_hash`'s existing write-only pattern (never echo a live secret back)
- [ ] `payments/paystack_client.py` reads from this DB config (existing env vars stay as a documented local-dev fallback, not removed outright) — needs a caching/invalidation strategy since this is read on every Paystack call
- [ ] New endpoint(s): read/update the integration settings, restricted to `PLATFORM_ADMIN` + `OWNER`
- [ ] New screen in the **same Vue app** (decided over a Django-admin-panel alternative) — role-gated to Platform Admin + Owner, consistent auth/UX with the rest of the app
- [ ] Re-confirm scope before backend work starts: "gaming account details" beyond the integration keys likely means the preferred bank for DVA provisioning (`create_dedicated_account`'s `preferred_bank` param, currently hardcoded `'wema-bank'`) rather than any per-player data — per-player Gaming Accounts are already auto-provisioned via Paystack's API and have no separately-configurable "account number" today

### Phase E — Production readiness
- [ ] Paystack Dedicated NUBAN business KYC approval (external dependency, pending — blocks live Gaming Account DVAs)
- [ ] Real Paystack live keys + production webhook URL (currently test keys + local ngrok tunnel only) — likely superseded by Phase D's DB-backed config once that exists
- [ ] Deployment target decision (Railway, matching the user's Leyyow Affiliates project, is the likely default — needs confirming, not assuming)
- [ ] Production environment/secrets management

### Phase F — Backlog (deliberately deferred, revisit only if requested)
- [ ] Worker/Dealer first-class user-types (tips currently free-text `source`, not a recipient reference)
- [ ] WhatsApp interface + full notification matrix (explicitly "still open" in CONCEPT.md, out of v1 scope from the start)
- [ ] Fraud/transfer-limit settings UI (per-transaction, per-24hr, per-recipient-frequency)
- [ ] Period-over-period reporting (weekly/monthly trends, top debtors)
- [ ] Search/filter/export across player lists, game-day history, ledgers
- [ ] "Unattributed payment" queue (money landing outside the DVA-linked flow)

---

## 3. Design decisions

- **Owner/Accountant/Platform-Admin frontend: same Vue app** as Cashier, with role-gated routes+nav (mirrors how Leyyow Affiliates admin is structured — one app, many roles) — not a separate app/build. Cashier's own stores/axios setup already generalize cleanly for this.
- **New, distinct style guide** for Owner/Accountant/Platform-Admin surfaces — not reused from the Cashier's frozen "Ledger Slate" `tokens.css`, and not from Leyyow Affiliates' tokens either. Build it fresh via the `design` skill when Phase B starts, the same process the Cashier surfaces went through.
- **Platform Admin's Integration Settings screen lives in the same Vue app**, not Django's built-in `/admin/` panel — chosen explicitly over that alternative for auth/UX consistency.
- **Deployment target**: not yet decided (Railway, matching Leyyow Affiliates, is the likely default — confirm before Phase E).
