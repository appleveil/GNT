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
- [x] View Player nav / Leave Table / active-seat cap of 9 (`GameDayPlayer.left_at`, `TableFullError`, `POST /game-days/{id}/players/{id}/leave/`) — see Phase A below
- [x] Staff password reset (`POST /api/staff-users/{id}/reset-password/`, `StaffPasswordResetSerializer`) — a real gap closed for Phase C, see below

**109/109 tests passing** (this line updated 2026-09-14 alongside Phase C; the individual phase entries below carry the count at the time each was done).

### Frontend — Cashier (Vue 3 + Vite + Pinia — `frontend/`)

- [x] `f728bc0` Scaffold (Vite/Pinia/vue-router/axios, JWT-claim-decoding auth store, tokens.css design system — "Ledger Slate," built fresh via the `design` skill, not ported from anywhere), Login, Players list, Open/Close Game-Day
- [x] `c6103c3` Player Detail (game-day-scoped balance, Gaming Account/DVA status, bank accounts, Pay Out Balance) — found and fixed a real backend bug along the way (default-bank-account `IntegrityError`)
- [x] `7d4f055` + `ae19342` Bank-account picker: type-to-filter combobox over real Paystack banks, live account-number resolve ("is this you?" confirmation)
- [x] `9d2e40e` The real Active Game-Day working screen: general entries (Rake/Tip), per-player action grid (Issue Chips, Chips In, Cash/POS/Transfer payments, Payout), type-to-filter player picker + recent pills, `TransactionEntryModal` for all 7 Cashier-facing transaction types, Floor-Manager-only PIN mode (`useAuthorizerConfirm`'s `fm-only` mode) for physical counts
- [x] `08480ec` Fixed a real crash: blank screen on login (temporal-dead-zone bug in `ActiveGameDayView`'s setup order)
- [x] `66b024a` Frontend half of the per-player-balance fix above — the activity feed now calls `/activity/`, not `/ledger/`

**No Owner or Platform Administrator frontend exists yet.** Accountant's frontend is Phase B, below (`meta.roles` is now wired and used).

---

## 2. Remaining work, in execution order

### Phase A — Round out Cashier v1
- [x] Void-entry UI — `VoidEntryModal.vue`, wired into the Active Game-Day activity feed's per-row trigger, `canVoid.js` mirroring the backend's own eligibility rule. Surfaced and fixed a real backend bug along the way: voided rows were being filtered out of every ledger listing entirely rather than staying visible-but-struck-through as designed.
- [x] **Player Game-Day History view** — built as a "Tonight's activity" section on `PlayerDetailView` (not a separate route): this player's own transaction list for tonight only, via `GET /api/game-days/{id}/players/{player_pk}/ledger/`, with the same void action available inline.
- [x] Payout status/history — "Payouts this game-day" list added to `PlayerDetailView`'s payout section (replaces the old single inline confirmation banner), status-badged, reusing the same ledger fetch as the history section above (filtered to `type === 'PAYOUT'`).
- [x] Dedicated (club-wide) Game-Day Ledger view — replaced the placeholder stub at `views/game-day/GameDayLedgerView.vue`; header stats reuse the close-preview endpoint while OPEN (Rake shown as "pending — at close" per the hi-fi, even though a partial live figure technically exists) and the frozen `GameDaySummary` once CLOSED. Reachable via a new "Full Ledger →" link on the Active Game-Day screen (this route had no nav entry point at all before — a true orphan). Same void wiring as the other two ledger surfaces.
- [x] Toasts — `useToast.js`/`AppToast.vue`, mounted once in `App.vue`; used for void-success feedback so far
- [x] Polish pass: audited every `api.*()` call for missing error handling — found and fixed two real silent-failure gaps (`PlayerDetailView.onSetDefault`, `PlayerFormView`'s roster fetch) plus the root cause underneath both, `gameDay.fetchCurrent()` had no `catch` at all (every caller across the app was exposed); reviewed CSS for tablet/narrow-viewport overflow risk and fixed one real gap (`LoginView`'s card had no `max-width`/page padding fallback below 480px)
- [x] **UX simplification, per user feedback (2026-09-14)**: removed the Players list page and the bottom nav entirely — a Cashier has exactly one screen now. `PlayersListView.vue`/`PlayerFormView.vue` deleted; `/players` and `/players/new` routes gone (`/players/:id` stays, still reachable via Payout). New `AddPlayerModal.vue` (bottom sheet, opened from Game Day) replaces the routed add-player page: defaults to the **Existing** tab (not New), and existing-player selection is now **multi-select** — pick several returning players and seat them all in one submit (`Promise.allSettled`, so one failure doesn't lose the others), with the roster filtered to exclude anyone already seated tonight (a real gap the old page had). New-player mode is still exactly one at a time. The Active Game-Day screen's search-to-pick combobox is gone too — every seated player shows as a pill immediately (`flex-wrap`, not horizontal scroll, so up to ~10 stay glanceable at once); tapping one selects it.
- [x] **"View Player" + "Leave the table" + a real active-seat cap (2026-09-14)**: closes the navigation gap above (Payout was the only door to `PlayerDetailView`'s already-built "Tonight's activity"/payout-history sections) and delivers the "leave the table" mechanism deferred in the entry above, now with the cap it was originally deferred over. `GameDayPlayer.left_at` (nullable) added; `gaming.services.seat_player` enforces `MAX_ACTIVE_PLAYERS_PER_GAME_DAY = 9` (active = `left_at IS NULL`) — new player *registration* always succeeds, only *seating* is capped, via a new `TableFullError` the view catches to return `registered_not_seated`/`player_id`. `_ensure_seated` revives a departed player (clears `left_at`) on any re-seat or recorded transaction — deliberately permissive there, unlike the explicit seat action. New `POST /game-days/{id}/players/{id}/leave/`. Frontend: the action grid's 8th button is context-aware ("Leave Table" ↔ "Return to Table"); leaving asks whether chips are being returned first — **No** marks them left directly, **Yes** opens the normal `CHIPS_IN` sheet and *that* save is what marks them left, chained in `ActiveGameDayView` with no changes to `TransactionEntryModal`. Departed players stay in the pills row (recolored, "left" tag, still tappable) rather than disappearing, plus an "N active · M left tonight" count line. `AddPlayerModal` shows an inline "table is full" notice and disables existing-player selection (never new-player registration) at the cap. 11 new backend tests (106/106 passing); verified live end-to-end against the dev DB (filled to 9 active, confirmed the 10th fails with the right response shape, chained a real chips-in-then-leave, confirmed the freed slot let the earlier failed registration get seated).

**Phase A is done.**

### Phase B — Accountant frontend
- [x] **New, distinct style guide (2026-09-14)** — built via the `design` skill (canvas: https://claude.ai/code/artifact/4abda5dc-bbf5-486b-8745-e6ac14293695), extracted into `accountant-tokens.css`: same variable vocabulary and type family as Cashier's "Ledger Slate" (IBM Plex Sans/Mono), distinct warm-neutral/navy palette, tighter radii (6/8px), desktop-sized controls (40px vs Cashier's touch-first 56/72px). Scoped under a `.theme-accountant` class rather than `:root` — `AppShell.vue`'s root element wears it for any non-Cashier role, so every shared component (`common.css`'s `.btn`/`.badge`/`.card`/`.money`, `AppToast`) re-themes automatically with zero per-component changes. `cashier-common.css` renamed to `common.css` (generic utility classes, not Cashier-specific).
- [x] **Dashboard** (`DashboardView.vue`, `/dashboard`) — four stat cards from `GET /api/dashboard/` (outstanding from/to players, debtor count, outstanding chips), quick links to Outstanding and Game Days.
- [x] **Game-day history/detail** (`GameDaysListView.vue` + `GameDayDetailView.vue`, `/game-days` + `/game-days/:id`) — read-only, no void action. Detail reuses the same data sources as Cashier's `GameDayLedgerView.vue` (close-preview while OPEN, frozen `GameDaySummary` while CLOSED, the club-wide `/ledger/` feed), plus a seated-players list linking into Roster.
- [x] **Player list + per-player detail incl. any game-day's ledger, and the Outstanding ledger** (`RosterListView.vue` + `RosterDetailView.vue`, `/roster` + `/roster/:id` — not `/players`, which Cashier's live-view route already owns). Roster detail's "any game-day" picker needed no new backend endpoint: confirmed by reading `gaming/selectors.py`'s `player_game_day_ledger` directly that `GET /game-days/{id}/players/{player_pk}/ledger/` is a plain queryset filter — 200 + `[]` for a game-day the player wasn't part of, not a 404 — so the picker just offers every game-day and shows an empty state.
- [x] **Role-based route guarding wired up** — the five new routes above carry `meta: { roles: ['ACCOUNTANT', 'OWNER'] }` (Owner included now since Phase C's plan is "everything in Accountant's dashboard, plus…"). Existing Cashier routes deliberately left unrestricted — Owner has no dedicated operational UI until Phase C, so still needs `/game-day` etc. reachable. Landing/redirect made role-aware in five places (root redirect, catch-all, login-guard bounce, role-rejection fallback, `LoginView`'s post-login push) via a shared `homeRouteFor(role)` helper: CASHIER → `/game-day`, ACCOUNTANT/OWNER → `/dashboard`. `AppShell.vue`'s `tabs` computed now returns the 4-tab back-office nav for those roles; brand text and `AppToast`'s bottom offset made role-aware too.
- No backend changes — a pre-implementation audit found every endpoint this phase needed already existed and was already correctly permissioned (`GET /api/dashboard/`, `/api/outstanding/`, `/api/game-days/`, `/api/game-days/{id}/ledger/`, `/api/game-days/{id}/players/`, `/api/game-days/{id}/players/{player_pk}/ledger/`, `/api/players/`). Verified live against the dev DB as `accountant1`: all six new views' data sources confirmed by direct curl (including the game-day-picker empty-state case above); `npm run build` clean.

**Phase B is done.**

### Phase C — Owner frontend
- [x] **Everything in Accountant's dashboard, plus the real Main-account balance (2026-09-14)** — `DashboardView.vue` (Phase B's, extended not duplicated) shows a 5th stat card for `main_account_balance`, already present in `GET /api/dashboard/`'s response only for OWNER — no backend change.
- [x] **Staff management** — new `AdminView.vue` (`/admin`, Owner-only). Create/deactivate reuse `StaffUserViewSet` as-is (`PATCH {is_active}`). Reset password needed a real backend gap closed: `StaffUserSerializer` (used for update) had no `password` field at all — there was no way to change an existing user's password via the API. Added `POST /api/staff-users/{id}/reset-password/` (new `StaffPasswordResetSerializer`, `IsOwner` inherited from the viewset), 3 new backend tests.
- [x] **Floor Manager management** — same `AdminView.vue` page, second section. Create/deactivate/PIN-reset all reuse `FloorManagerViewSet` as-is (PIN reset is just `PATCH {pin}`, already supported, no backend change).
- [x] **Chips-limit setting per player** — `RosterDetailView.vue` (Phase B's, extended), the Chips Limit stat card becomes inline-editable for Owner, `PATCH /api/players/{id}/ {chips_limit}` — already Owner-gated server-side (`PlayerSerializer.validate_chips_limit`), no backend change.
- [x] **Deal / write-off entry** — same `RosterDetailView.vue`, a small form (type/amount/reason) posting `POST /api/transactions/` with `game_day` omitted, so the new row lands directly in that player's Outstanding section already on the page.
- [x] **Payout approval queue** — new `PayoutsView.vue` (`/payouts`, Owner-only): Pending section (client-filtered `PENDING_APPROVAL`/`TRANSFER_FAILED`, since `TransactionViewSet` has no server-side filter — accepted trade-off at this club's scale) with an Approve/Retry button, plus recent history for context.
- [x] **FX rate setting** — same `AdminView.vue`, third section: standing rate per currency (computed client-side from `GET /api/conversion-rates/`) plus a set-rate form with an optional per-game-day override, posting to `set_rate`. Confirmed live via curl that the Owner-login bypass applies here too (same `_resolve_owner_or_floor_manager` helper as Open Game-Day) — no PIN needed.
- [x] **Open Game-Day trigger from Owner's own login** — `DashboardView.vue`: when no game-day is open, a direct "Open Game-Day #N" button posts straight to `/api/game-days/open/` with just `{number}` (computed the same way as `ActiveGameDayView.vue`'s `nextGameDayNumber()`) — no `AuthorizerConfirmModal` picker/PIN step at all, since that modal exists for a *Cashier's* device, not the Owner's own already-authenticated session.
- [x] **Post-close corrections/amendments** — scoped to what's actually built: confirmed there is no backend mechanism beyond `void_transaction` for touching a closed game-day (no edit-in-place, no reopen — CONCEPT.md's own last line is "How to reverse mistakes? Do this later"). `void_transaction` already lets an Owner void any transaction, any time, regardless of game-day status; that capability is now surfaced in the UI via a void trigger (reusing `VoidEntryModal.vue`, `canVoid.js`) on `GameDayDetailView.vue` and `OutstandingView.vue`, visible only for Owner. Backend already had a passing test for this exact scenario (`test_only_owner_can_void_after_close`) — confirmed rather than assumed before building on it.
- 3 new backend tests (109/109 passing). `npm run build` clean. Verified live against the dev DB as `owner1`: chips-limit set/clear, a real Deal transaction recorded and confirmed in Outstanding, FX rate set with no PIN, staff password reset and reverted, Floor Manager PIN reset — all via a disposable throwaway Floor Manager/test transaction so no real staff/player data was touched, cleaned up afterward. The Payout queue and post-close void were verified by reading the exact code paths plus existing passing backend tests, not exercised live against real pending/closed data, to avoid triggering a real Paystack transfer or altering the user's actual historical records during verification.

**Phase C is done.**

### Refinements (2026-09-15) — user-reported fixes against Phases A–C
- [x] **"Chips In" renamed to "Return Chips"** everywhere (the constant, plus `ActiveGameDayView.vue`'s action-grid button, which hardcoded its own label rather than reading the constant).
- [x] **Live thousands-separator formatting** on every amount-magnitude text input, not just displays (which already had it via a `toLocaleString()` `N()` helper everywhere, audited): `TransactionEntryModal.vue`'s amount field, `RosterDetailView.vue`'s chips-limit and Deal-amount fields. New `src/utils/amountInput.js` (`formatAmountForDisplay`/`parseAmountInput`) keeps the underlying stored value a plain numeric string — only the `<input>`'s displayed text gets commas.
- [x] **"Return to Table" removed; a departed player returns ONLY by being issued chips (`CHIPS_OUT`)** — not any other transaction type, and never a bare re-add. `gaming/services.py`'s `_ensure_seated` unified: a `revive` param (default `False`) is the only thing that clears a departed player's `left_at`, passed `True` only from `record_transaction`'s `CHIPS_OUT` case; `initiate_payout` and every other transaction type record normally against a departed player without reviving them. `seat_player` no longer calls `_ensure_seated` for an already-seated-but-departed player at all — it raises a clear `InvalidStateError` instead. Creating a brand-new seat (never seated tonight, any transaction type) is capped exactly like a revival is — closes a sibling gap where `record_transaction`/`initiate_payout` could otherwise seat a 10th active player bypassing `seat_player`'s check entirely. `ActiveGameDayView.vue`'s 8th action-grid button only renders "Leave Table" for a still-active player now (no "Return to Table" branch); `AddPlayerModal.vue`'s existing-player list now excludes anyone seated tonight at all (active or departed), closing the side door that let a departed player be silently re-added with zero chips involved. 5 new/replaced backend tests (115/115 passing).
- [x] **Deal recorded with a game-day selected lands in that game-day's ledger** (Cashier's and Accountant's), not Outstanding — `RecordTransactionSerializer` already accepted an optional `game_day` and `player_game_day_ledger`/`game_day_ledger` already included `PAYMENT_DEAL` rows once one was set; `RosterDetailView.vue`'s Deal/Write-off form was just always omitting it. **Superseded same day, see the correction below** — the manual `<select>`-of-every-game-day built here was wrong; kept as a record of the initial (incorrect) pass.
- [x] **Payout rejection** — `Transaction.Status.REJECTED` existed but nothing ever set it. New `gaming/services.py::reject_payout` reuses `void_transaction`'s own fields (`is_voided`/`voided_by`/`voided_at`/`void_reason`) rather than a parallel set — a rejected payout must drop out of every balance sum exactly like a voided one does (confirmed a real, separate need: a `PENDING_APPROVAL` payout already counts against the player's balance the moment it's created, since balance selectors filter only `is_voided`, never `status`). New `POST /api/transactions/{id}/reject/` action; new `RejectPayoutModal.vue` wired into `PayoutsView.vue`'s Pending section next to Approve/Retry; "Recent history" now shows a "Declined" badge with the reason. 3 new backend tests.
- Confirmed already correct, no change needed: a Deal already positively affects balance (`PAYMENT_DEAL` is in `CREDIT_TYPES`); outside-game-day transactions already reach a player's overall balance (`player_balance` has no `game_day` filter).
- 115/115 backend tests passing (was 109). `npm run build` clean. Verified live against the dev DB via disposable throwaway players (created, exercised, then fully deleted via a Django shell script — the real 6-player game-day was untouched): return-to-table now raises instead of reviving; issuing chips to a departed player revives them and is blocked at the 9-active cap; a game-day-tied Deal appeared in that game-day's ledger and not in Outstanding; a payout was rejected and the player's balance correctly reverted.

### Correction (2026-09-15, same day) — Deal/write-off routing is automatic, not a manual pick from history
User feedback: a Deal isn't tied to any particular game-day by manual choice — it's implicitly tied to whichever game-day is open *at the moment it happens*. If one's open, the deal belongs to it (both that game-day's ledger and the master/lifetime ledger); if none is open, it's Outstanding-only (but still on the master ledger — unaffected either way, `player_balance` never filters by `game_day`). The one allowed exception: the Owner may retroactively attribute a deal to the game-day that **just ended** — entered a few minutes after close — but never to any older one.
- [x] **`RosterDetailView.vue`'s Deal/Write-off form** — removed the full-history `<select>`. Now: if a game-day is open right now, the deal is sent with that `game_day` automatically (shown as a read-only note, no choice offered); if none is open, a single checkbox offers "attach to Game-Day #N (just ended)" — only ever the most-recently-closed game-day, sourced from the same already-fetched `gameDays` list (newest-number-first, so `find(status === 'CLOSED')` is exactly "the last one"); left unchecked, it's Outstanding, same as before.
- [x] **Backend gap found and closed while live-verifying**: `gaming/services.py::_require_open_game_day` unconditionally rejected *any* transaction against a non-`OPEN` game-day — meaning the original manual-picker version (and any stale/direct API call) would have 400'd the moment a closed game-day was actually selected; this had only ever been exercised live against the currently-open one. Added a narrow, server-side-enforced exception: a `PAYMENT_DEAL`/`WRITE_OFF` (`DEAL_TYPES`) may target the single most-recently-closed `GameDay` (looked up by `-number`, not trusted from the client) — every other type, and any older closed game-day, is still rejected. `record_transaction` also now skips `_ensure_seated` entirely when the target game-day isn't `OPEN`, so a retroactive deal never re-seats/resurrects a player into a closed night's roster or trips its (no-longer-relevant) active-player cap.
- 7 new backend tests (`DealOnClosedGameDayTests`; 122/122 passing overall). `npm run build` clean. Verified live: a Deal against the real currently-open game-day auto-attaches and seats normally; a disposable player + service-layer calls against the real closed game-days confirmed the just-closed one is accepted (lands in its ledger, not Outstanding, no seat created) while an older closed one and a non-deal type against the just-closed one are both still rejected with a clear error — all via throwaway players, cleaned up after, real game-day rows (#1–#5) confirmed untouched.

### Ledgers: list rows → tabular "Ledger Grid" (2026-09-17)
User wanted every ledger feed changed from the two-line flex-row list
(colored dot, title+badge line, meta line, right-aligned amount+balance
stack) to a real table — one entry per row. Presented three concrete
directions with ASCII previews (Ledger Grid / Compact Scan / Statement
Style); **chosen: Ledger Grid** — Time · Type · Player · Amount · Balance ·
Status as real columns, a colored lane-stripe cell instead of a dot, sticky
header — applied everywhere, including Cashier's touch-first live screens.
- [x] New shared, presentational `components/shared/LedgerTable.vue` —
  collapses 7 near-duplicate row implementations into one `<table>`
  component (no API/store access; parents still fetch data and handle
  voiding exactly as before). Props: `rows`, `showPlayer`, `playerTo`
  (function, for `RouterLink` vs plain text), `dateFormat`
  (`'time'`/`'datetime'`), `voidable`, `canVoidFn`. Row height comes from
  the existing `--control-row-min` token, so Cashier's tables stay
  touch-sized and Accountant/Owner's stay desktop-dense automatically — no
  separate density prop needed.
- [x] Wired into all 7 locations: `GameDayLedgerView.vue`,
  `GameDayDetailView.vue`, `OutstandingView.vue`, `RosterDetailView.vue`
  (both its Outstanding and any-game-day panels), `ActiveGameDayView.vue`'s
  "Today's activity", `PlayerDetailView.vue`'s "Tonight's activity" — each
  view's old `.feed-row`/`.ledger-row`/`.activity-row` markup and its scoped
  CSS removed, replaced with `<LedgerTable>` plus a small per-row
  `player_name`-resolving computed. Left untouched (different row shapes):
  `OutstandingView.vue`'s "By player" balance summary, `PlayerDetailView.vue`'s
  "Payouts this game-day" mini-list, `PayoutsView.vue`, `AdminView.vue`.
- Backend untouched (pure display change) — 122/122 tests still passing.
  `npm run build` clean, noticeably smaller per-view bundles from the
  de-duplication (e.g. `RosterDetailView` 9.97kB → 8.35kB).

### Jumping from a Game-Day to a player now lands on that game-day's activity (2026-09-17)
Clicking a player from `GameDayDetailView.vue` (its ledger table or "Players
seated" panel) went to `/roster/:id`'s general/lifetime view, with the
"Any game-day's activity" panel defaulting to a blank picker — the Owner had
to manually reselect the very game-day they just came from.
- [x] Both player links in `GameDayDetailView.vue` now carry that game-day's
  id as a `?gameDay=<id>` query param instead of a bare path.
- [x] `RosterDetailView.vue`'s `load()` pre-sets `selectedGameDayId` from
  `route.query.gameDay` when present, firing the existing `watch` that
  already fetches/display's that game-day's ledger for this player — no new
  endpoint, reuses `GET /game-days/{id}/players/{playerId}/ledger/` exactly
  as the manual picker already did. A direct `/roster/:id` visit (no query
  param) is unchanged.
- Pure frontend routing change. `npm run build` clean.

### Chip variance flagging, payout sequencing, and a Main Account ledger page (2026-09-17)
Five related reconciliation-correctness items from the user. Investigated
each against the actual code before changing anything — two were already
built with only a display gap, two were real gaps, one was already correct
by design (confirmed, no change), and the last turned out to already exist
on the backend, just never wired to a screen.
- [x] **Chip deficit/excess flagging** — `GameDaySummary.chips_variance`
  (signed: out − in − rake − tips) was already computed and already shown
  in the close-confirmation dialog, but always labeled "Unreturned chips"
  regardless of sign. New `utils/chipsVariance.js` (`describeChipsVariance`)
  gives every screen the same sign-aware "Chips deficit" (positive, warn) /
  "Chips excess returned" (negative, informational) / "Chips balanced"
  (zero) treatment. Applied to `ActiveGameDayView.vue`'s close dialog (both
  tonight's variance and the club-wide `outstanding_chips_after_close`);
  added as a 5th stat (same "pending — at close" treatment as Rake while
  OPEN) to `GameDayLedgerView.vue` and `GameDayDetailView.vue`, which had
  the data already but never displayed `chips_in_total`/`chips_variance` at
  all; added a compact "Chips" column to `GameDaysListView.vue`'s history
  table so a problem night is visible while just scanning history.
- [x] **A payout requires the player to have left the table** —
  `gaming/services.py::initiate_payout` had no such check at all. Added one
  (the seat's `left_at` must be set), before the existing balance-cap check.
  `leave_table` itself is unchanged — leaving still doesn't trigger a
  payout, the two stay independent. Mirrored in `PlayerDetailView.vue`'s
  Payout button (disabled + explanatory note).
- [x] **A bank account is required before a payout can even be requested** —
  previously only discovered at Owner-approval time (`TRANSFER_FAILED`).
  Added an upfront check to `initiate_payout` (a default `PlayerBankAccount`
  must exist); kept the approval-time check too, as defense in depth for an
  account removed between request and approval. Mirrored in
  `PlayerDetailView.vue`'s Payout button/note.
- Confirmed correct, no change: balances are deliberately debited at
  payout-**request** time (not on transfer success) to prevent two pending
  requests from double-spending the same winnings; a failed transfer stays
  debited until an Owner retries or explicitly rejects it (which reverses
  it) — already correct and already re-surfaces in `PayoutsView.vue`'s
  Pending queue automatically.
- [x] **Main Account ledger page** — `GET /api/main-account/ledger/`
  (`gaming/views.py`'s `MainAccountLedgerView`, `IsOwner`-gated) already
  existed and already excluded every chip transaction (only DVA sweep-ins
  and payouts) — it simply had no frontend page. New Owner-only
  `views/owner/MainAccountLedgerView.vue` (reuses `LedgerTable.vue`),
  defaulting to `status === 'POSTED'` rows only with a "Show all statuses"
  toggle; new `/main-account` route + nav tab. Payout rows stay on the
  Game-Day ledger too (its `game_balance` total already includes them) —
  this is a second, focused view, not a replacement.
- 8 new/replaced backend tests (126/126 passing, was 122). `npm run build`
  clean. Verified live via a disposable throwaway player + game-day
  (deleted after): payout correctly blocked while seated, then blocked
  again with no bank account, then succeeds once both are satisfied;
  `chips_variance` sign confirmed on a deliberately unbalanced day. Real
  game-day history (#1–#6) confirmed untouched throughout.

### Numbered seats, free-seat visibility, and moving/swapping seats (2026-09-17)
Confirmed zero seat-position concept existed anywhere before this —
`GameDayPlayer` only ever tracked presence (`left_at` null/set),
`MAX_ACTIVE_PLAYERS_PER_GAME_DAY = 9` was a pure headcount cap.
- [x] `GameDayPlayer.seat_number` (nullable — unassigned until placed) +
  a partial unique constraint (`unique_active_seat_per_game_day`, only
  while `left_at IS NULL`) — leaving the table frees the seat number
  automatically, no extra code needed for that part.
- [x] `seat_player` gains an optional `seat_number`; new `move_seat`
  (handles both a plain move into a free seat and a swap with whoever's
  in the destination seat — nulls both rows first inside one atomic
  block, sidestepping the unique constraint portably); new
  `free_seat_numbers` selector; new `POST .../players/{id}/move-seat/`.
- [x] `ActiveGameDayView.vue`'s player pills are now seat-ordered 1–9,
  empty seats shown as their own pill (tapping one opens `AddPlayerModal`
  pre-targeted at that seat — now single-select when opened this way,
  still bulk multi-select from the generic "+ Add Player" button);
  players seated without a specific seat show under "Unassigned"; the
  action grid gains "Move Seat" (a small picker of every other seat,
  free ones move, occupied ones swap).
- 8 new backend tests (135/135 passing, was 127). `npm run build` clean.
  Verified live against the real dev DB (migration applied) via disposable
  throwaway players: seating into specific seats, a seat freeing on
  leave and being reused, and a same-game-day swap all confirmed correct;
  real game-day history untouched.

### Floor Manager becomes a real logged-in role, plus a Service Staff roster (2026-09-17)
Confirmed Floor Manager had zero login/account of its own before this —
CONCEPT.md was explicit ("not a role with its own account or interface"),
purely a name+PIN witness credential entered inline on whoever's device.
Per the user's decision, that changes: Floor Manager now ALSO gets a real
login, on top of (not instead of) that existing PIN — a Service Staff
roster (named people Service tips get attributed to) is the first thing
that login is for.
- [x] `StaffUser.Role.FLOOR_MANAGER` — a real login (username/password,
  JWT), migration, new `IsFloorManager`/`IsFloorManagerOrOwner`
  permissions. The existing `FloorManager` model (name + PIN) is
  unchanged — still looked up directly by `_resolve_floor_manager` for the
  inline physical-count witnessing, completely unaffected by a Floor
  Manager also having a login. New `FloorManager.staff_user` (nullable
  OneToOne) optionally links the two records for the same real person.
- [x] New `ServiceStaff` model (mirrors `FloorManager`'s shape minus the
  PIN — a named recipient, not a witness) + `ServiceStaffViewSet`
  (read: any staff; write: Floor Manager or Owner) + new
  `views/floor-manager/ServiceStaffView.vue` (copies `AdminView.vue`'s
  Floor-Managers-section list/toggle/create pattern) as the Floor
  Manager's own home screen/nav tab.
- [x] `AdminView.vue`'s existing "Staff accounts" role picker gains
  "Floor Manager" as a selectable role (creates the login); its separate
  "Floor Managers" section (the PIN-witness records) gains an optional
  "Link to login" dropdown, sourced from the staff list already fetched
  there — two sequential existing-endpoint calls, no new combined
  endpoint needed.
- `seed_demo_data.py` gains a demo `floormanager1` login, linked to the
  existing demo "Femi Floor" PIN record.
- 7 new backend tests (142/142 passing, was 135). `npm run build` clean.
  Verified live: migrated the real dev DB (additive, nullable columns
  only); a disposable throwaway Floor Manager login could log in via real
  HTTP, list/create Service Staff (200/201), and was correctly refused
  `/api/dashboard/` (403, not Accountant/Owner) — all cleaned up after,
  real staff/game-day data confirmed untouched.

### Dealer vs Service tip categorization (2026-09-17)
Final piece of the Floor-Manager/Service-Staff batch — the actual reason
that roster exists. Confirmed no chip/tip "category" concept existed
anywhere before this; `TIP` was always anonymous/aggregate with no
recipient field, and CONCEPT.md had already flagged this exact gap as
deliberately deferred ("Worker/Dealer as first-class user-types... will
likely require a schema change to Transaction.TIP").
- [x] `Transaction.TipCategory` (`DEALER`/`SERVICE`) + `tip_category` +
  `service_staff` (FK → `ServiceStaff`, `PROTECT` — a historical tip never
  loses who it was attributed to even if that person is later deactivated).
  Both fields are meaningful only for `type=TIP`; validated in
  `record_transaction` (a TIP requires a category; `SERVICE` requires an
  active recipient; `DEALER` must not have one) — same pattern as every
  other type-conditional field on this model.
- [x] `TransactionEntryModal.vue`'s Tip flow gains a Dealer/Service radio
  and, only for Service, a select of active Service Staff (fetched from
  the roster built in the previous entry) — everything else about
  recording a Tip (amount, FM-PIN confirmation) is unchanged. Dealer tips
  keep today's exact behavior: anonymous, aggregate, no recipient.
- No change to `tips_total`/`chips_variance` arithmetic — this is
  attribution layered on top of the existing sum, not a new figure.
- 9 new backend tests (151/151 passing, was 142). `npm run build` clean.
  Verified live against the real dev DB (migration applied) via a
  disposable throwaway game-day/Floor-Manager/Service-Staff record: a
  Dealer tip recorded with no recipient, a Service tip recorded with one,
  and a Service tip missing a recipient correctly rejected — all cleaned
  up after, real game-day history confirmed untouched.

### "Deals" backend — Fixed write-off cap, player-to-player Transfer, and Profit Split (2026-09-20)
New Owner-only "Deals" feature, backend-first per the approved plan (a
mobile Android/iOS app follows, starting with a visual mockup before any
app code — not part of this entry). Three deal types, all creating real
`Transaction` rows so they show up correctly in every existing ledger for
free (master-ledger pattern) — no reconciliation tooling needed, as usual.

- [x] **Fixed write-off** — reused the existing `WRITE_OFF` type (already
  Owner-gated) almost as-is; added the two things it was missing: a
  mandatory reason (`notes`), and a hard cap at the player's current
  lifetime outstanding balance so a write-off can only relieve debt, never
  push a player positive. `test_owner_can_record_write_off` (pre-existing)
  updated to give the player debt first and supply a reason, since both
  are now enforced.
- [x] **Transfer** — genuinely new: settles one player's debt using
  another's excess. Two linked `Transaction` rows (`DEAL_TRANSFER_OUT`/
  `DEAL_TRANSFER_IN`, `Transaction.linked_transaction` self-FK pointing at
  each other) created atomically via `record_deal_transfer`. Capped at the
  source's positive *lifetime* balance (same basis as the write-off cap);
  no cap on the destination side beyond that. Voiding either leg now voids
  its linked leg too (`void_transaction` extended) — otherwise one
  player's debit could be undone without undoing the other's matching
  credit. New endpoint `POST /api/deals/transfer/`.
- [x] **Profit Split** — the one genuinely new subsystem, no precedent
  anywhere in the schema before this. New `ProfitSplitArrangement` model
  (house stake %, per-period cap, reset cadence One-off/Daily/Weekly/
  Monthly, optional end date/max resets/max cumulative value — confirmed
  meaning: cumulative amount the *house has covered*). "How much covered so
  far" is never stored — always a live `SUM` over new `PROFIT_SPLIT_STAKE`
  Transaction rows FK'd to the arrangement (`selectors.profit_split_status`),
  matching this codebase's computed-not-stored balance philosophy. Reset
  periods are computed live from `created_at` + cadence + `now()` — no
  Celery job needed (Celery/Beat stay idle, as before), using `dateutil`
  for real calendar-month boundaries (added `python-dateutil` to
  `requirements.txt`; days/weeks are fixed-length, unambiguous without it).
  Wired into the one place it needed to touch existing logic:
  `record_transaction`'s `CHIPS_OUT` branch now splits a buy-in into a
  player-owed portion and a house-covered portion (capped by whatever's
  left of the current period's — and, if set, the lifetime max's —
  allowance) *before* the existing `chips_limit` check runs, since that
  limit caps the player's own debt, not the total chips issued.
  `PROFIT_SPLIT_STAKE` deliberately sits in neither `DEBIT_TYPES` nor
  `CREDIT_TYPES` — it never touches player_balance, by construction.
  **Scope decision, matching the concept doc's own wording**: only the
  stake/buy-in side is actually applied automatically. The payout-split
  fields (before/after buy-in basis, stake-ratio/custom-ratio/fixed+offset
  method) are captured as configuration only for now, not yet wired into
  `initiate_payout` — the concept doc itself says the Fixed method's
  off-set is "for now... only setting the off-set amount, not actually
  doing the maths for what goes to whom," and no worked example was given
  for the ratio methods either. Revisit once that math is actually wanted.
  New endpoints: `POST /api/deals/profit-split/` (create — auto-deactivates
  any previous active arrangement for that player), `GET
  /api/deals/profit-split/<player_id>/` (current arrangement + live
  figures), `POST /api/deals/profit-split/<id>/deactivate/`.
- All three: Owner-only at both the DRF permission layer (`IsOwner`) and
  explicitly in the service layer (`operator.role` check) — Transfer and
  Profit Split are standalone single-purpose actions with no other
  legitimate caller, same pattern as `approve_payout`/`reject_payout`.
- 36 new backend tests across the three units (4 + 11 + 21) — 187/187
  passing, was 151. Verified live against the real dev DB (all three migrations applied) via
  disposable throwaway players/game-days/arrangements — write-off cap,
  transfer cap/void-both-legs, and profit-split per-period/cumulative-cap/
  deactivation behavior all confirmed, then fully cleaned up; real game-day
  history confirmed untouched throughout.
- Next: a phone-frame HTML mockup of the mobile Deals screens (Ledger
  Slate tokens, no app code yet) for review, then the actual Android/iOS
  Expo app — see the approved plan.

### "Deals" mobile app — real Expo build, v1 kicked off (2026-09-20)
The HTML mockup above went through many rounds of feedback (sticky
search/filter headers with a scroll shadow, a bottom tab bar, ineligible
deal types greyed out, a redesigned Transfer layout, Stake/Payout as
separate opt-in section cards, a read-only Profit Split history detail
screen, required/optional field marking) before this started — see the
artifact history in that conversation for the full trail. Two real
architecture decisions were made along the way, both deliberate departures
from "wired into the Django API from day one":

- **Deal writes are local-only for now.** The Owner needs to start using
  Deals immediately, before the rest of the Owner app exists on mobile —
  waiting for a real sync/conflict-resolution layer risked exactly the
  "forgotten deal" problem this exists to prevent. Every Deal (Fixed,
  Transfer, Profit Split create/end) is saved to an on-device SQLite table
  and nothing else — no queue, no retry, no backend call at all on that
  path. **A manual reconciliation into the real system is expected later**,
  once the rest of the Owner app is ready; an **Export** action on History
  (CSV via the native share sheet) exists specifically to make that
  reconciliation less error-prone than transcribing off the phone screen.
- **Players/balances ARE read from the real backend**, cached locally and
  falling back to that cache on any failure (offline, expired session,
  server error) — the one exception to "no network calls," because the
  Deal-type picker's disabled states and every cap check are meaningless
  without real balances. Silent auth (no login screen in v1 — see the
  approved plan): a dedicated Owner login lives in a gitignored
  `src/api/config.ts` (`config.example.ts` checked in as the template),
  used only for `GET` requests. Flagged plainly in code comments as a
  security simplification acceptable only for a single trusted personal
  device — must become real per-user login before this is ever shared or
  distributed.
- Deferred to later, noted but not built: exporting/sharing a Deal
  **to WhatsApp specifically** to notify the player directly, possibly via
  a future player-facing app instead of (or alongside) WhatsApp.

Built: Expo (React Native + TypeScript) project at `mobile/`, SDK 57.
`src/theme/tokens.ts` — Ledger Slate's palette ported from the web app's
`oklch()` values to plain hex (computed via the standard OKLab conversion
matrices, not eyeballed). `src/db/` — the local `deals` log (one table,
JSON payload per kind — deliberately not fully normalized, so a new Deal
kind never needs a schema migration) plus the CSV export. `src/api/` — the
read-only players client with local caching. Navigation: a bottom-tab root
(Deals / History) matching the mockup, each a native-stack for its
drill-down flow. All seven screens built: Deals home (search, live
balances, "profit split active" tag), the deal-type picker (disabled
states), Fixed, Transfer (fixed-top/scroll-middle/fixed-bottom layout),
Profit Split (Stake/Payout opt-in toggles, an active arrangement's status
card + End action), History (filter chips + export), and the read-only
Profit Split detail screen.
- Verified: `tsc --noEmit` clean across the whole project; `expo export`
  succeeds for both iOS and Android bundle targets (1000+ modules each,
  no resolution/native-module errors); a real login against the running
  dev backend (`owner1`) confirmed working via curl before wiring the
  client to it.
- Not yet done: a real Android AVD/updated-Xcode simulator run (verified
  instead via Expo Go on a physical device — see the follow-up entry
  below), IBM Plex Sans/Mono bundled via `expo-font` (currently falls back
  to the system font), and the WhatsApp-export idea above.

### "Deals" mobile app — first real-device pass: networking, ledger effects, UX fixes (2026-09-20)
Getting it running in Expo Go on a physical phone surfaced one infra gap,
then a batch of real usability feedback once players were visible.

- [x] **Django dev server unreachable from the phone** — was bound to
  `127.0.0.1:8000` (meaningless from any device but the Mac itself).
  Restarted bound to `0.0.0.0:8000`; added the Mac's LAN IP to
  `ALLOWED_HOSTS` (`backend/lpc_backend/settings/local.py`); pointed
  `mobile/src/api/config.ts`'s `API_BASE_URL` at that LAN IP. Noted in
  code comments that the IP can change if Wi-Fi reconnects.
- [x] **Local balance overlay** — since Deal writes are local-only (no
  backend call), the cached backend balance alone would drift stale the
  moment a Deal is saved. New `src/db/effectiveBalance.ts` computes each
  player's net local adjustment from the saved Deal log (Fixed: `+amount`;
  Transfer: `-amount` source / `+amount` destination; Profit Split: no
  balance effect) and layers it on the cached balance everywhere a balance
  is shown or capped against (Deals home list, Transfer's source balance
  and target list).
- [x] On-screen success/failure feedback (`Alert.alert`) on every Deal
  save/end, replacing silent navigation.
  "Ratio: according to stake" — meaningless with no stake set — is now a
  disabled `RadioOption`; toggling stake off auto-switches away from it if
  it was selected.
- [x] History's Profit-Split row summary now shows stake details if a
  stake is set, else payout details if a payout is set, else neither
  (`src/db/dealText.ts::dealSummary`) — previously showed nothing useful
  when only one of the two was configured.
- [x] Per-Deal share, text or PDF (`src/db/export.ts`: `shareDealAsText`
  via RN's `Share.share`, `shareDealAsPdf` via `expo-print` +
  `expo-sharing`) — offered only for Stake/Profit-Split rows in History,
  since Fixed and Transfer deals have no player-facing notification need.
- [x] **Renamed "Profit split" → "Stake and Profit splits"** everywhere
  user-facing (deal-type picker, screen/stack titles, History filter
  chip, CSV labels) — the sub-concepts "Stake" and "Payout" inside the
  form keep their own names.
- [x] Transfer: picking a different recipient after an amount/reason is
  already entered now confirms first (would otherwise silently
  misattribute what was typed) rather than switching immediately.
- [x] Bottom tab bar hidden on every Deals sub-screen except the Deals
  home list (`RootTabs.tsx`, via `getFocusedRouteNameFromRoute`) — these
  are single-purpose task flows, and it was one more variable in the
  keyboard-avoidance math below.
- [x] **Keyboard covering the bottom-most field in a form — three
  attempts before landing on a correct fix.** First pass added
  `KeyboardAvoidingView` + header-height offset generally. Second pass
  fixed Fixed's Reason field but not Transfer's (its Amount/Reason/Submit
  footer is pinned below a separately-scrolling player list) or Profit
  Split's Off-set field (the form's dynamic bottom-most field). Third pass
  tried permanent extra scroll padding + a permanently-elevated
  shrink-priority on Transfer's player list — this visibly, permanently
  shrank the list even with the keyboard down (a ScrollView's un-styled
  outer container sizes to its own content, so a large static
  `paddingBottom` inflated its measured size at rest, stealing space from
  its sibling). Final, correct fix: new `useKeyboardVisible()` hook
  (`src/hooks/useKeyboardVisible.ts`) tracking actual
  `keyboardWillShow`/`keyboardWillHide` events — not field focus/blur,
  which restores too early (tabbing between fields) or not at all
  (keyboard dismissed by tapping outside, not by blurring the field).
  Transfer's list-shrink-priority and scroll padding, and Profit Split's
  scroll padding, now key off that hook: expanded only while the keyboard
  is actually on screen, restored immediately when it closes, however it
  closed. User-confirmed fixed on a real device.
- Verified: `tsc --noEmit` clean and `expo export --platform ios` bundles
  cleanly after each round; final keyboard fix confirmed working on the
  user's own device (prior two rounds were not — logged here as the
  record of what didn't work, not just what did).

### "Deals" mobile app — History cleanup, End confirm+reason, Payout lifespan (2026-09-21)
- [x] **History rows no longer repeat the deal-type name** ("Fixed —",
  "Transfer —", "Stake and Profit splits —") — the row's icon plus
  `dealSummary()` underneath already say what kind of deal it is. New
  `dealRowTitle()` (`src/db/dealText.ts`) used only for the row itself;
  Transfer keeps its "source → destination" since that's not inferable
  from the icon alone. `dealTitle()` (the full type name) is unchanged
  and still used where there's no icon to lean on — the share action
  sheet's title, and the first line of shared text/PDF.
- [x] **Ending an arrangement now requires a reason and a confirmation
  dialog** — previously a single tap, no undo, no record of why. Tapping
  "End arrangement" reveals a required Reason field in place; a second
  tap opens a real confirm dialog ("can't be undone"), only then ends
  it. The reason is saved on the `PROFIT_SPLIT_ENDED` record and now
  shows up everywhere that record is referenced: History's summary, the
  read-only detail screen, the CSV export, and shared text/PDF.
- [x] **"Until" (Stake's Renews condition) is a real calendar picker** —
  `@react-native-community/datetimepicker`, `minimumDate` set to today so
  a past date can't be selected at all. Updated mid-work to the
  library's current `onValueChange`/`onDismiss` API after `onChange` was
  flagged deprecated at runtime.
- [x] **New Payout lifespan** — Indefinite / Until debt clears / Until a
  set amount is reached, decided via a short design exchange (see that
  conversation for the fuller reasoning): "debt clears" checks the
  player's live overall balance (the same figure Fixed write-off already
  reads), and — because that data already exists — the app can actually
  *do* something with it: a banner nudges the Owner to end the
  arrangement once the balance has cleared, checked whenever the screen
  is opened. The cumulative-cap option is recorded and shown but
  **can't be enforced or nudged** — the app has no record of individual
  payout events to sum against it, the same limitation Stake's existing
  Until/Number of times/Max value already have. The whole Lifespan
  section is hidden until a real (applicable) split method is chosen,
  not while the default, possibly-inapplicable selection is still
  showing.
- [x] Deals home's "Stake and Profit splits" button shows an ACTIVE
  badge when the player already has a live arrangement, re-checked on
  every screen focus.
- Verified: `tsc --noEmit` clean, `expo export --platform ios` bundles
  cleanly after each change.

### Multi-tenancy — schema-per-tenant via django-tenants (2026-09-21)
The user is building this as a product for multiple clubs (2 confirmed,
possibly 5-20 if it goes well), not just the one club this schema
implicitly assumed. Decided against both a fork-per-client codebase and
row-level tenancy (a `club_id` on every table) — for financial/
reconciliation data specifically, a missed `.filter(club=...)` is a real
cross-client data leak, not a cosmetic bug. **Schema-per-tenant** instead:
each club's data lives in its own Postgres schema, physically separate,
enforced by the database rather than by remembering a filter everywhere.
Done now, pre-launch, specifically because it's far cheaper before any
client's real data exists than after.

- [x] **`django-tenants==3.14.0`** added. New `tenants` app: `Client`
  (`TenantMixin` — one row per club, `auto_create_schema=True` so saving
  one creates+migrates its schema automatically) and `Domain`
  (`DomainMixin` — maps a hostname to a Client; tenant resolution is via
  the request's Host header, stripped of port, exact match required).
- [x] `INSTALLED_APPS` split into `SHARED_APPS` (public schema:
  `django_tenants`, `tenants`, `contenttypes`, plus the apps with no
  models — `staticfiles`/`corsheaders`/`rest_framework`) and
  `TENANT_APPS` (everything else — `accounts`, `gaming`, `payments`,
  `admin`, `auth`, `sessions`, `token_blacklist`, both Celery apps —
  replicated into every club's own schema). `contenttypes` deliberately
  listed in both, per django-tenants' own requirement.
  `DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']`;
  `TenantMainMiddleware` first in `MIDDLEWARE`; DB engine switched to
  `django_tenants.postgresql_backend` in both `local.py`/`production.py`.
- [x] Local dev DB reset clean (pre-launch, disposable demo data) and
  rebuilt: `migrate_schemas --shared` for the public schema, then a
  `test1` tenant created and seeded via `seed_demo_data` (wrapped by
  django-tenants' `tenant_command`) — verified real cross-tenant
  isolation end to end: `owner1`/`demo-pass-1` logs in successfully
  against `test1`'s domain and 401s against an empty second tenant with
  the identical credentials, over real HTTP requests through
  `TenantMainMiddleware`, not just at the ORM level.
- [x] New `onboard_club` management command (named to avoid colliding
  with django-tenants' own built-in `create_tenant` command, confirmed by
  hitting that collision directly): `manage.py onboard_club <schema_name>
  <name> <domain...> [--seed]` — creates the Client + Domain rows and
  optionally seeds demo data, the entire "provision a new client"
  operation in one command. Deliberately no admin UI for this yet — at
  2-20 clients, a developer-run command for an infrequent operation is
  the right amount of tooling; a real platform-admin panel is a later
  problem, not blocking today.
- [x] **Full existing test suite (187 tests) migrated and green.** Plain
  `TestCase`/DRF `APITestCase` can't see any TENANT_APPS table at all
  (they run against the public schema) — new `lpc_backend/testing.py`
  provides drop-in `TestCase`/`APITestCase` built on django-tenants'
  `TenantTestCase`, with two bugs in that base class worked around
  explicitly (documented in the module): (1) its default test domain
  doesn't match Django's test client's default `Host: testserver`, so
  every request 404'd at the tenant-resolution middleware regardless of
  view correctness; (2) `TenantTestCase.setUpClass` never calls
  `super().setUpClass()`, which silently skips Django's own activation of
  a class-level `@override_settings(...)` decorator — surfaced by
  `payments/tests.py`'s Paystack-signature tests, which run against real
  settings instead of the overridden test secret with no error, just a
  wrong result. All three apps' `tests.py` updated to import from
  `lpc_backend.testing` instead of `django.test`/`rest_framework.test`
  directly — nothing else about how the tests are written changed.
- [x] `Procfile`'s release step: `migrate` → `migrate_schemas`.
- [x] Incidental fix, unrelated to tenancy: the Mac's LAN IP had changed
  (`192.168.100.2` → `192.168.88.12`, a Wi-Fi reconnect) since the last
  session, breaking the mobile app's connection to the dev backend
  independently of this work — caught while verifying the LAN-IP request
  path still resolves tenants correctly; updated `ALLOWED_HOSTS`,
  `mobile/src/api/config.ts`, and the `test1` tenant's `Domain` rows to
  match. Confirmed the exact mobile-app request path (login + players
  fetch over the LAN IP) still works end to end under the new setup.
- Not yet done: a real platform-admin surface for onboarding/managing
  clients (currently the `onboard_club` command, run by a developer —
  see above); tenant-aware Celery Beat (no periodic tasks exist yet, so
  nothing depends on this today, but `django-tenants` + scheduled tasks
  needs its own solution when one is added — plain Beat has no schema
  concept); the mobile app's "resolve club → API base URL" step (today
  it hits one fixed `API_BASE_URL`, fine while there's one club to test
  against, but will need a real "which club" resolution step before a
  second real club's data needs to be reachable from the app).

### A genuine site-wide Django admin login, not tied to any club (2026-09-21)
`django.contrib.admin`/`auth`/`sessions` and `accounts` were TENANT_APPS
only — every StaffUser, including any superuser, only ever existed inside
one club's own schema, so `/admin/` was necessarily that club's admin,
logged in as that club's own staff. Requested explicitly: a real
platform-wide admin, separate from every client.

- [x] `accounts`, `admin`, `auth`, `sessions` now listed in **both**
  `SHARED_APPS` and `TENANT_APPS` (same pattern already used for
  `contenttypes`) — their migrations now also run against the `public`
  schema, giving it its own, independent `accounts_staffuser` table
  (and everything else those apps need) separate from every club's.
- [x] The `public` schema is now itself registered as a tenant (a
  `Client` row with `schema_name='public'`) with its own `Domain`
  (`admin.localhost` in dev) — `TenantMainMiddleware` can only route a
  request into a schema that has a matching Domain row, public included.
- [x] `manage.py createsuperuser`, run with no tenant specified, now
  does exactly what's expected: defaults to the `public` schema, so the
  resulting superuser exists there only. Verified real isolation:
  `admin` exists in `public`'s `accounts_staffuser` and does **not**
  exist in `test1`'s.
- [x] One rough edge, hit and worked around while wiring this up: the
  first `migrate_schemas --shared` after this change failed
  (`relation "auth_permission" does not exist`) because the *previous*
  `--shared` run (before these apps were shared) had already recorded
  their migrations as "applied" in public — django-tenants' migration
  executor marks every app's migrations as applied in its bookkeeping
  table regardless of whether the router actually let the tables get
  created, so Django's `migrate` saw "already applied" and skipped
  re-running them for real this time. Fixed by clearing the stale
  `django_migrations` rows for the newly-shared (and, to keep the
  ledger internally consistent, the still-tenant-only) apps in `public`
  before re-running — a one-time fix, not something that recurs.
- [x] `StaffUser.role` (required, no default) isn't set by
  `createsuperuser` — it has no opinion on custom fields outside
  `REQUIRED_FIELDS`. Ends up `''` rather than erroring (Django's
  `CharField` defaults to an empty string, which satisfies the column's
  `NOT NULL`). Harmless — `is_superuser` bypasses every permission
  check this app has, `role` is never consulted for this account — but
  cosmetic: `StaffUser.__str__`'s `get_role_display()` shows nothing
  for it. Not fixed; none of the existing Role choices (Cashier/
  Accountant/Owner/Floor Manager) fit a platform-wide account anyway.
- Verified: full 187-test suite still green after the SHARED_APPS
  change.

### Game/Table selection at start + two-step chip custody (2026-09-21)
New: a real "Start game-day" flow (Game → Table → Buy-in), and a
two-step model for how chips move — the house issues chips to the player
(a custody balance, not tied to any table), and separately the player
puts them into play at a table. Confirmed via a follow-up: buy-in is an
independent choice each night with a pre-filled default (not baked into
the table); the default buy-in auto-fires with **no** Floor Manager PIN
(the one deliberate automation); leaving a table became a 3-way
disposition, and the counted amount is never capped at the original
buy-in (winnings/losses). See `SCHEMA.md`'s matching dated entry for the
full modeling rationale.

- [x] **New `Game`/`Table` models** — `Game(name)`, `Table(game, name,
  default_buy_in)`. "One table per game, for now" is a seed-data/UI
  convention, not a DB constraint. `GameDay` gains nullable `game`/`table`/
  `buy_in_amount` — the last **snapshotted** from `table.default_buy_in` at
  open time (same precedent as `Transaction.conversion_rate`), editable
  before confirming. Owner-managed CRUD for games/tables/buy-ins is
  explicitly parked — the two initial games/tables (Texas Hold'em/Omaha,
  one table each, ₦500k/₦100k) are seeded via a data migration
  (`0011_seed_games_and_tables`). New read-only `GET /api/games/` and
  `GET /api/tables/?game=<id>` back the flow's first two steps.
- [x] **Chip custody**: two new `Transaction.Type`s, `TABLE_BUY_IN`/
  `TABLE_CASH_OUT` (new `table` FK, set only on these) — following the
  exact precedent `PROFIT_SPLIT_STAKE` already established: tracked, but
  deliberately outside `selectors.DEBIT_TYPES`/`CREDIT_TYPES`, so neither
  ever touches `player_balance`, `player_game_day_balance`, or
  `GameDaySummary`'s chips figures (still computed purely from
  `CHIPS_OUT`/`CHIPS_IN`, unchanged) — explicit regression tests prove
  this bit-for-bit. New selectors `player_chips_in_hand`/
  `table_chips_in_play` compute the custody/table-side figures live. A
  new **Table ledger** (`GET /game-days/<id>/table-ledger/`) is the fifth
  view over `Transaction`, for physical chip reconciliation — its
  `running_balance` uses a different sign convention from every other
  ledger (`TABLE_BUY_IN` adds, `TABLE_CASH_OUT` subtracts) since it means
  "chips in play here," not a player's owed balance.
- [x] **Seating auto-issues the default buy-in**: `seat_player`, when the
  game-day has a table+buy-in set and the player has no `CHIPS_OUT` yet,
  now auto-creates a `CHIPS_OUT` (house → player) with **no PIN**, wrapped
  atomically with the seat itself (a rejection — e.g. `chips_limit`
  exceeded — rolls the seat back too, rather than leaving someone seated
  but unchipped). `record_transaction`'s `CHIPS_OUT` branch separately
  auto-links a `TABLE_BUY_IN` for the full amount (player's own portion
  *plus* any Profit Split house portion — the total chip value actually
  put into play) whenever the player has an active seat at the game-day's
  table — this applies to *every* `CHIPS_OUT`, including a manual rebuy
  through the normal endpoint, which still requires its PIN exactly as
  before (the linked `TABLE_BUY_IN` just reuses that same witness, no
  second PIN). A private `_skip_pin_check` param (never exposed via any
  serializer/view) is the only way to bypass the PIN, used solely by
  `seat_player`'s automatic path.
- [x] **Leaving a table is now a 3-way disposition**
  (`gaming.services.LeaveDisposition`), chosen at the moment the seat is
  freed: `NO_RETURN` (unchanged — nothing counted, no PIN), `HOLD` (FM-PIN
  count moves chips off the table into the player's own custody —
  `TABLE_CASH_OUT` — without reducing what they owe the house), `CASH_OUT`
  (the same count, chained into `CHIPS_IN`, one PIN covering both linked
  rows). No new field records which happened — always derivable from which
  `Transaction` rows (if any) accompany `left_at`, matching this schema's
  "compute, don't store" convention throughout. The counted amount is
  never capped at the original buy-in, proven with an explicit
  winnings-example test (left with *more* than bought in) and a
  losses-example test (left with *less*).
- **Deliberately not built this round**: general cross-table chip
  movement (moving custody chips to a *different* table) — flagged
  directly by the user as "not fully defined yet." The `player_chips_in_hand`
  selector and the balance-neutral `TABLE_BUY_IN` type are the foundation
  for it, but no dedicated endpoint/UI exists yet, since `GameDay.table`
  is still singular (one table per game-day) — there's nowhere for such a
  move to go until multi-table support is designed. `TransactionViewSet`
  explicitly rejects a direct `TABLE_BUY_IN`/`TABLE_CASH_OUT` POST (mirrors
  the existing `PAYOUT` block) so this stays a clean, fully
  system-orchestrated pair rather than a half-built public surface.
- 24 new backend tests (`StartGameDayFlowTests`,
  `AutomaticTableBuyInTests`, `LeaveTableDispositionTests`) — 211/211
  passing, was 187. Verified live against the real dev DB (`test1`
  tenant schema) via a disposable throwaway game-day/player: automatic
  buy-in issued correctly with no PIN, custody/table-in-play figures
  correct, and the cash-out disposition correctly rejected an incorrect
  Floor Manager PIN — then fully cleaned up; real game-day history
  confirmed untouched throughout.
- Frontend (Start-game-day flow, 3-way leave UI, Table ledger view) not
  yet built — backend-first, matching this project's established
  sequencing convention.

### Revert two-step chip custody back to one step (2026-09-21)
The Start-game-day flow (previous entry) shipped its frontend half this
same day — but every normal buy-in fires the auto-pair (`CHIPS_OUT` +
`TABLE_BUY_IN`) at once, so the Cashier's ledger always showed two rows
for one buy-in. Reported back as confusing ("what's the difference, why
are they both there"), and on investigation `HOLD`/`CASH_OUT` (the only
path that ever creates a `TABLE_CASH_OUT`) turned out to be unreachable
from the frontend — "Leave Table" always POSTs an empty body, defaulting
to `NO_RETURN`, and "return chips" happens via a separate, pre-existing
`CHIPS_IN` call instead. User's call: full removal, not just disabling
the auto-pairing — `CHIPS_OUT` alone represents a buy-in again, exactly
like before this feature existed.

- [x] Removed `Transaction.Type.TABLE_BUY_IN`/`TABLE_CASH_OUT` and the
  `table` FK on `Transaction` (migration `0014`, which also deletes any
  existing rows of those two types — pure duplicates of information the
  paired `CHIPS_OUT` already carries, so nothing real is lost).
- [x] `record_transaction`'s `CHIPS_OUT` branch no longer auto-links a
  `TABLE_BUY_IN` — seating still auto-issues the default `CHIPS_OUT` with
  no PIN (that automation was separately requested and stays), just
  without a second linked row.
- [x] `leave_table` is back to its pre-feature shape —
  `leave_table(game_day, player, operator=None)`, just sets `left_at`.
  `LeaveDisposition`/`LeaveTableSerializer` removed entirely (the frontend
  never populated them, so this is a no-op from the app's point of view).
- [x] Removed `player_chips_in_hand`/`table_chips_in_play`/
  `game_day_table_ledger` selectors and the Table ledger endpoint
  (`GET /game-days/<id>/table-ledger/`) — back to four ledger views.
- [x] Removed `TransactionViewSet.create`'s now-pointless
  `TABLE_BUY_IN`/`TABLE_CASH_OUT` guard, and `chips_in_hand` off
  `GameDaySeatedPlayerSerializer`.
- **Unaffected, stays exactly as-is**: `Game`/`Table` models,
  `Game.max_players`, `GameDay.game`/`table`/`buy_in_amount`, and the
  "Start game-day" 3-step flow (`StartGameDayModal.vue`) — this revert is
  only the custody *tracking* layer, not game/table selection itself.
- Removed the 19 tests that covered only the reverted behavior
  (`AutomaticTableBuyInTests`, `LeaveTableDispositionTests`) — 136/136
  passing, was 155. `LeaveTableTests`/`StartGameDayFlowTests` needed no
  changes, confirming the simplified signatures are drop-in compatible
  with every existing caller.
- Frontend: removed the `TABLE_BUY_IN`/`TABLE_CASH_OUT` entries from
  `constants/transactionTypes.js` (added earlier the same day to label
  the now-removed rows) — no other frontend change needed, since the
  Leave Table UI never sent the disposition params this removes.

### Payout-failed badge on the Cashier's player panel (2026-09-23)
Item #8 off the "what am I missing" review — a payout that lands
`TRANSFER_FAILED` (Owner approved it, but the Paystack transfer itself
didn't go through) was only ever visible in the Owner's Payouts view; the
Cashier who initiated it had no way to know without asking. Chose to
surface it as a status badge, reusing the same "field" the player panel
already uses for "Left the table"/chips-limit — not a separate
notification system.
- [x] New `selectors.player_has_failed_payout(player, game_day)` — any
  non-voided `PAYOUT` transaction still sitting at `TRANSFER_FAILED`
  tonight. Clears itself the moment the Owner retries successfully
  (`APPROVED`) or rejects it (`REJECTED`+voided) — same `Transaction` row,
  no separate acknowledge step.
- [x] `GameDaySeatedPlayerSerializer.payout_failed` — exposed on both the
  seated-players list and single-player detail endpoints the Cashier's
  page already polls.
- [x] Frontend: a red `payout-failed-badge` next to the existing
  "Left the table"/chips-limit badge on the player panel — additive, not
  exclusive, since a departed player can also have a stuck payout.
- Two new backend tests (158/158 passing); `npm run build` clean.
- **Discarded from the same list**: #1 (cash drawer reconciliation) and
  #6 (per-dealer/service-staff tip summary) — not being pursued.
- **Deferred to Phase F backlog** (below): #2 (void-after-return-posted
  can create a silent excess), #3 (idle/session timeout), #4 (shift
  handoff), #5 (forgotten entries after close), #7 (duplicate player
  registration), #9 (printable end-of-night report).

### Masseuse/Dealer/Service staff roles + tip-category rename (2026-09-23)
Two related but independent changes, both from "add dealer and masseuse to
the list of staff an owner can add":
- [x] ~~Three new `StaffUser.Role` login roles — `MASSEUSE`/`DEALER`/
  `SERVICE` — addable from the Admin page's "Staff accounts" dropdown~~ —
  **superseded the same day**, see "Masseuse/Dealer/Service corrected:
  never log in, no dashboard" below: this was wrong, all three never
  actually log in. Left here as a historical record of what was briefly
  built (including the `StaffHomeView.vue`/`homeRouteFor` redirect-loop
  fix this required) before the correction; none of it exists any more.
- [x] `Transaction.TipCategory`'s two values renamed — `DEALER` (anonymous/
  aggregate) is now `SERVICE_STAFF` ("Service staff"), and `SERVICE`
  (named recipient) is now `MASSEUSE` — behavior of each side unchanged,
  only the label, per the Owner's explicit framing: Masseuses get tracked
  by name, "Service staff" stays the aggregate/anonymous bucket dealers
  used to be. Deliberately decoupled from the new login roles above —
  `StaffUser.Role.SERVICE` is who can log in, `TipCategory.SERVICE_STAFF`
  is who a tip gets attributed to; a real Masseuse or Dealer doesn't need
  a login for tips to work.
- [x] `accounts.ServiceStaff` (the named-recipient roster) renamed to
  `Masseuse` — matches what it's actually for now that "Service" no
  longer means the named side. `RenameModel` + a companion `RenameField`
  on `Transaction.service_staff` -> `masseuse`, plus a `RunPython` data
  migration remapping every existing row's stored `tip_category` value.
  One real migration-ordering gotcha hit and fixed: the cross-app
  `RenameModel` needed an explicit dependency on gaming's last migration,
  or the graph's topological sort was free to apply it before gaming's
  *historical* migrations that still reference the old model name,
  producing a lazy-reference error rebuilding project state from scratch.
  (`Masseuse` was generalized further to `StaffMember` the same day — see
  the correction entry below; this rename step itself still stands.)
- [x] Frontend: Floor Manager's "Service Staff" screen/tab/route renamed
  to "Masseuses" (`/masseuses`, `MasseuseListView.vue`); the Tip entry
  form's Dealer/Service radio is now Service staff/Masseuse.
- 216/216 backend tests passing (2 new role tests, `TipCategoryTests`
  renamed/updated in place); `npm run build` clean.

### Rake/tips netted out of the on-the-spot chips-returned ceiling (2026-09-23)
The 2026-09-22 "chips returned can never exceed chips issued" per-transaction
gate (`record_transaction`'s CHIPS_IN branch) compared raw `chips_out_total`
vs `chips_in_total` only — the exact bug already caught and fixed once
before, at close time, for `chips_variance` (rake/tips are chips that
legitimately never come back as a CHIPS_IN, skimmed from play / handed to
staff). Left uncorrected here, the on-the-spot check was strictly *looser*
than the close-time one: it would silently let a return through that
`game_day_chip_discrepancy` would immediately flag as an excess at close.
- [x] `selectors.game_day_chips_totals` now also returns `rake_total`/
  `tips_total`; `record_transaction`'s ceiling is
  `chips_out_total - rake_total - tips_total`, matching `chips_variance`'s
  formula exactly.
- [x] Frontend: the persistent chips-caption on the Cashier's page (added
  2026-09-22 specifically to preview this same check) now nets out
  rake/tips too, showing an extra "(₦X returnable after rake/tips)" once
  either is nonzero — otherwise unchanged, so a normal night before any
  rake/tip is recorded stays exactly as slim as before.
- 4 new backend tests (rake alone, tips alone, both stacking, and the
  error message reporting the adjusted ceiling) — 220/220 passing;
  `npm run build` clean.

**Follow-up bug, same day**: the caption still never actually showed the
rake/tips adjustment live — it was computed by filtering the frontend's
`ledger` ref, but `ledger` (and `activity`) *exclude RAKE/TIP entirely*
(`EXCLUDED_FROM_GAME_DAY_LEDGER` — they're day-level entries, not scoped to
any player), so no amount of client-side filtering could ever surface them.
- [x] New `GET /game-days/<id>/chips-totals/` endpoint (new
  `GameDayChipsTotalsSerializer`), wrapping `selectors.game_day_chips_totals`
  directly — the dedicated live data source the caption actually needed.
- [x] Frontend: `ActiveGameDayView.vue`'s chips-caption computeds now read
  from this endpoint (fetched alongside players/ledger in `refreshAll()`)
  instead of deriving anything from `ledger`.
- 1 new backend test (`chips-totals` includes rake/tips) — 221/221 passing.

### Masseuse/Dealer/Service corrected: never log in, no dashboard (2026-09-23)
Same-day correction to the earlier "Masseuse/Dealer/Service staff roles"
entry above: it added them as real `StaffUser.Role` logins (username +
password), which was wrong — clarified they never actually log in and have
no dashboard of their own.
- [x] Removed `MASSEUSE`/`DEALER`/`SERVICE` from `StaffUser.Role` entirely
  — back to Cashier/Accountant/Owner/Floor Manager only.
- [x] `accounts.Masseuse` generalized to `accounts.StaffMember` — same
  named, non-login roster the Masseuse tip category already used, now
  with a `role` field (`MASSEUSE`/`DEALER`/`SERVICE`). `Transaction.masseuse`
  still only ever points at a `role=MASSEUSE` row — enforced at both the
  serializer (queryset filter) and service layer (explicit role check,
  new `test_masseuse_tip_rejects_a_dealer_or_service_staffmember`).
- [x] `/api/masseuses/` renamed `/api/staff-members/`, with a `?role=`
  filter (mirrors `StaffUserViewSet.owners`' own role-filtering pattern) —
  used by the Tip picker and the Floor Manager's "Masseuses" screen (both
  hardcode `?role=MASSEUSE`; that screen's own scope is unchanged, still
  just the named tip-recipient roster).
- [x] New "Other Staff" section on the Admin page (Owner-only) — the actual
  place Masseuse/Dealer/Service get added from now: name + role, no
  username/password, no login.
- [x] Frontend: removed the dead `/staff-home` placeholder route,
  `StaffHomeView.vue`, and the `homeRouteFor`/`AppShell.vue` branches that
  existed only to keep those three roles from hitting an infinite redirect
  loop — none of it was ever reachable once the roles themselves were
  reverted.
- One more cross-app migration-ordering dependency needed (same shape as
  the original Masseuse rename's own gotcha — see that entry): the
  `RenameModel` had to depend on gaming's last migration, which still
  referenced `accounts.masseuse`.
- 221/221 backend tests passing; `npm run build` clean.

### Removed the original (pre-2026-09-22) cashier ledger (2026-09-23)
The everyone-at-once, unscoped ledger table — superseded by the
per-selected-player ledger feed — had been kept commented out in
`ActiveGameDayView.vue`'s template since the swap, in case that experiment
needed reverting. Confirmed no longer needed and deleted outright, along
with the stale comments pointing at it (`playerLedgerRows`' own comment,
the template's own "original cashier ledger" note). `ledgerRows`/`ledger`
themselves are unaffected — `playerLedgerRows` (the live feed) still
depends on both.

### Close Game-Day sign-off modal fix + ActiveGameDayView.vue cleanup (2026-09-23)
- [x] Fixed the sign-off (PIN) modal rendering behind the close-game-day
  summary: `CloseGameDayModal.vue`'s `.overlay` was `z-index: 100`, tied
  with `AuthorizerConfirmModal`'s own 100 — with equal z-index, later-mounted
  wins, and `App.vue` mounts `AuthorizerConfirmModal` first. Dropped to
  `z-index: 90`, matching the existing convention (`TransactionEntryModal`'s
  own overlay is already 90 for the same reason). Every other modal that
  can stay open while `AuthorizerConfirmModal` layers on top of it was
  checked — none had the same bug.
- [x] `ActiveGameDayView.vue` cleaned up at the user's request: stripped
  the file's accumulated dated/changelog-style comments ("Added
  2026-09-22 — see the Cashier layout wireframe review", "was X, now Y",
  ...) down to only what a reader would otherwise get wrong (sign/polarity
  conventions, why a fetch can't be derived from another one, cross-file
  couplings) — roughly 1180 lines to 894. Also removed two dead CSS rules
  found in the process (`.hero-caption`, `.empty-players` — no matching
  markup anywhere in the template). No behavior change; `npm run build`
  clean throughout.

### Owner/Floor-Manager-configurable Club Settings (2026-09-23)
New "Settings" screen (`/settings`, visible to both Owner and Floor
Manager) covering what used to be fixed in code:
- [x] `ClubSettings` — new singleton model (`pk=1` convention, `load()`
  classmethod), Owner-only: 5 `require_approval_*` toggles (open/close a
  game-day, return chips, add a tip, add rake) and
  `payout_auto_approve_threshold` (default ₦500,000). `GET
  /club-settings/` open to any role (the frontend needs the toggles to
  decide PIN-vs-plain-confirm); `PATCH` Owner-only.
- [x] `Table` gets 5 new Owner/Floor-Manager-editable fields:
  `max_chips_issuable`, `rake_percentage`, `small_blind`, `big_blind`,
  `max_players` (all nullable — null = no override/no cap). `TableViewSet`
  changed from read-only to a full `ModelViewSet` (read: anyone; write:
  Owner-or-Floor-Manager, same split as `StaffMemberViewSet`); `name`/
  `game`/`is_active` stay locked. `selectors.max_active_players` gained a
  table-first tier ahead of `Game.max_players`. `max_chips_issuable` is
  enforced in `record_transaction`'s CHIPS_OUT branch.
  **Corrected same day**: first built as a running/cumulative cap on total
  chips outstanding at the table (netting rake/tips like the CHIPS_IN
  ceiling) — live-tested and found wrong. The real rule: a ceiling on any
  ONE issuance only (`amount > table.max_chips_issuable`) — a player can
  buy in at the cap as many times as they like over the night, and there's
  no limit at all on total chips outstanding at once.
- [x] Each `require_approval_*` toggle is consulted inline in
  `open_game_day`/`close_game_day`/`record_transaction` — off skips the
  PIN-resolution call entirely (`owner`/`fm` stay `None`, exactly like
  every already-nullable case those fields supported before). A chip-
  discrepancy close always still requires Owner-or-FM sign-off regardless
  of the close toggle — a genuine anomaly, not the routine case it
  streamlines. CHIPS_OUT/PAYMENT_CASH have no toggle at all, unaffected.
- [x] Payout auto-approval: `approve_payout`'s funds-check + real transfer
  extracted into `_execute_payout_transfer(transaction_obj, approved_by)`;
  `initiate_payout` now calls it immediately (`approved_by=None`, the
  "auto-approved" marker) when the amount is at or under the threshold,
  instead of always landing `PENDING_APPROVAL`. No frontend change needed
  — `PayoutsView.vue`/`RejectPayoutModal.vue` only react to `status`.
- [x] Frontend: new `usePlainConfirm.js`/`PlainConfirmModal.vue` (mirrors
  `useAuthorizerConfirm.js`/`AuthorizerConfirmModal.vue`'s module-singleton
  shape, mounted once in `App.vue`) — the "still confirm, just no PIN"
  fallback when a toggle is off, wired into `StartGameDayModal.vue`,
  `useCloseGameDay.js`, and `TransactionEntryModal.vue`. New
  `stores/clubSettings.js` (mirrors `stores/gameDay.js`), fetched once
  from `AppShell.vue`'s `onMounted` alongside `gameDay.fetchCurrent()`.
  New `views/shared/ClubSettingsView.vue`, routed at `/settings` for both
  roles (Owner-only sections hidden inline via `v-if`), copying
  `AdminView.vue`'s per-section CRUD-lite pattern.
- Tests: `ClubSettingsModelTests`, `RequireApprovalTogglesTests`,
  `MaxChipsIssuablePerTableTests`, `TableMaxPlayersOverrideTests`,
  `PayoutAutoApprovalThresholdTests`, `ClubSettingsAndTablePermissionsAPITests`
  (24 new, all green) — plus 3 pre-existing payout tests updated
  (`_disable_payout_auto_approval()` helper) since their fixture amounts
  fell under the new default threshold, which is unrelated to what they
  were actually testing (manual-approval behavior).

### Whole Naira only — no kobo anywhere (2026-09-23)
Every Naira AMOUNT field, backend and frontend, is now `decimal_places=0` —
this club never deals in fractional Naira. Scoped deliberately: RATES and
PERCENTAGES are not amounts and keep their own precision — `Table.
rake_percentage`, `ConversionRate.rate_to_naira`/`Transaction.
conversion_rate` (both decimal_places=4), and `ProfitSplitArrangement`'s
`house_stake_pct`/`custom_ratio_pct` are all untouched.
- [x] Every money `DecimalField` changed `decimal_places=2` -> `0`:
  `Transaction.amount`, `GameDaySummary`'s six total/balance fields,
  `GameDay.buy_in_amount`, `Table.default_buy_in`/`small_blind`/
  `big_blind`/`max_chips_issuable`, `ClubSettings.
  payout_auto_approve_threshold`, `Player.chips_limit`,
  `ProfitSplitArrangement.cap_amount`/`max_cumulative_value`/
  `fixed_amount`/`fixed_offset` — plus every matching explicit
  `serializers.DecimalField` declaration (`gaming/serializers.py`, ~18
  fields). Two migrations (`accounts.0007`, `gaming.0020`), both plain
  `AlterField` — checked the dev DB first for any real fractional Naira
  value anywhere (none existed) before applying, so no data was rounded.
  `_apply_profit_split_stake`'s `.quantize(Decimal('0.01'))` -> `
  Decimal('1')`.
- [x] `utils/amountInput.js` — `parseAmountInput` now strips a typed `.`
  outright instead of allowing one decimal point; `formatAmountForDisplay`
  no longer has a decimal-part branch. Both call sites
  (`TransactionEntryModal.vue`'s amount field, `RosterDetailView.vue`'s
  chips-limit/deal-amount fields) needed no changes beyond this — same
  function signatures. `inputmode="decimal"` on all three -> `"numeric"`
  (the FX-rate and conversion-rate inputs elsewhere keep `"decimal"`, not
  Naira amounts).
- Note: DRF's `DecimalField(decimal_places=0)` rejects "500000.00" outright
  (extra zero decimal places, not just a nonzero fraction) rather than
  silently rounding — confirmed live. Not a practical issue since every
  money `<input>` in the app is `type="number"`/digit-stripped text, which
  never produces a trailing-zero decimal string, but worth knowing if a
  future integration ever posts a formatted amount here.

### `Table.max_chips_issuable` semantics correction (2026-09-23)
Live-tested immediately after the Club Settings entry above and found
wrong: it was built as a running/cumulative cap on total chips outstanding
at a table (net of returns/rake/tips), which blocked a normal new buy-in
once the table's cumulative issuance crossed the configured number. The
actual rule, per the Owner: it's a ceiling on any ONE issuance — a player
can buy in at the cap as many times as they like over the course of the
night, and there is no limit at all on total chips outstanding on a table
at once. Fixed in `record_transaction`'s CHIPS_OUT branch
(`amount > table.max_chips_issuable`, no totals lookup); `Table`'s own
docstring, the error message, and `ClubSettingsView.vue`'s label/help text
("Max chips per buy-in") updated to match. `MaxChipsIssuablePerTableTests`
rewritten for the corrected behavior (multiple same-cap buy-ins now
explicitly asserted to NOT raise).

### Fixed: every Cashier entry (chips, cash, rake, tip, ...) 400ing (2026-09-23)
Missed spot from the whole-Naira change above: `TransactionEntryModal.vue`'s
`doSave` built its payload with `nairaAmount.value.toFixed(2)` — always a
`".00"`-suffixed string. `Transaction.amount` is `decimal_places=0` now, and
DRF's `DecimalField` rejects a value with EXTRA (even all-zero) decimal
places outright rather than rounding it away — so every entry through this
modal (Chips Out/In, Cash, POS, Transfer, Rake, Tip — the Cashier's main
working screen) 400'd unconditionally. Fixed: `Math.round(nairaAmount.value
).toFixed(0)` — also correctly handles the one place a real fraction could
appear here (a foreign-currency amount × conversion_rate, e.g. 100 × 1547.83
NGN/unit). Confirmed live: reproduced the exact 400 with the old
`"15000.00"` payload, confirmed `"15000"` succeeds. `utils/amountInput.js`
itself and its other two callers (`RosterDetailView.vue`) were already
correct — this was the one remaining `.toFixed(2)` in the whole frontend.

### Added "Issue chips" to the require-approval toggle list (2026-09-23)
`ClubSettings.require_approval_issue_chips` (new `BooleanField`, default
`True`, migration `gaming.0021`) — CHIPS_OUT joins CHIPS_IN/TIP/RAKE in
`_APPROVAL_SETTING_BY_TYPE`; PAYMENT_CASH remains the one physical-count
type with no toggle at all. Doesn't touch `seat_player`'s own automatic
default buy-in (`_skip_pin_check=True`) — that bypass short-circuits
before this lookup is ever consulted, same as before this toggle existed.
Frontend: added to `TransactionEntryModal.vue`'s own
`APPROVAL_SETTING_BY_TYPE` and `ClubSettingsView.vue`'s `APPROVAL_TOGGLES`
list (between Close a game-day and Return chips). Tests: renamed the old
"CHIPS_OUT/PAYMENT_CASH always require a PIN" test to cover PAYMENT_CASH
only, added `test_issue_chips_needs_no_pin_once_disabled`/
`test_issue_chips_still_requires_a_pin_by_default`.

### Nav/layout fixes + Outstanding folded into Dashboard + auto-approved payout badge (2026-09-23)
Four small frontend fixes from a lo-fi nav review:
- **Top nav no longer scrolls away.** `AppShell.vue`'s `.stage` was
  `min-height: 100vh` — a box that can only grow taller than the viewport
  never actually triggers `.content`'s own `overflow-y: auto`, so the whole
  document scrolled (topbar and tabbar included) instead of just the
  content between them. Changed to `height: 100vh` (paired with the
  `overflow: hidden` already there) so `.content` is the one scrolling
  region and the topbar/tabbar stay put.
- **Game-day status pill scoped to the Cashier's screen.** It was showing
  in every role's topbar regardless of what they were looking at
  (Dashboard, Payouts, Admin, ...). Gated behind a new
  `showGameDayStatus = route.name === 'game-day'` — still shows for Owner
  too, since Owner can also reach that same route (router/index.js's
  existing comment on why it stays unrestricted for Owner).
- **`OutstandingView.vue` deleted; its content (full-activity feed + by-
  player summary, void trigger included) merged wholesale into
  `DashboardView.vue`**, which Accountant and Owner already share. Removed
  the `/outstanding` route, its `outstanding` nav tab, and the "View
  outstanding ledger" quick-link (now redundant — it's inline on the same
  page). `DashboardView.vue` now fetches `/players/` + `/outstanding/`
  alongside `/dashboard/`.
- **Payout history distinguishes Approved from Auto-approved.** A payout at
  or under `ClubSettings.payout_auto_approve_threshold` gets
  `approved_by=None` (see `_execute_payout_transfer`, 2026-09-23 session
  above) — `PayoutsView.vue`'s history badge now checks
  `status === 'APPROVED' && !approved_by` and renders "Auto-approved" in
  its own cool-blue badge (`--status-auto-approved-bg/text`, new tokens in
  `tokens.css`), instead of both cases reading as a plain "APPROVED". No
  backend change needed — `approved_by` was already on `TransactionSerializer`.

### Hi-fi Game Days page: paginated list + inline detail + per-player drill-down (2026-09-23)
Implements the lo-fi Game Days wireframe from this session for real.
`GameDayDetailView.vue` and its standalone `/game-days/:id` route are gone —
`GameDaysListView.vue` now carries the whole thing:
- **List paginated 7/page** (client-side — the full list was already fetched
  in one call, no new endpoint), with Prev/Next + numbered page buttons and
  a "Showing X–Y of N" label.
- **Clicking "View" on a row opens that game-day's detail inline, below the
  list on the same page** (scrolls to it), instead of navigating away — the
  same stat grid, full club-wide ledger, and players-seated list
  `GameDayDetailView.vue` had, just relocated. Clicking "View" again (now
  "Hide") on the open row collapses it; a "× Close" button in the detail
  header does the same.
- **New: tapping a seated player's pill narrows the view to just their own
  activity** — a 4-box mini stat row (chips out, payments, chips returned,
  balance) plus that player's own ledger, replacing the club-wide ledger
  panel while a player's selected. No new backend endpoint: reuses
  `GET /game-days/{id}/players/{player_id}/ledger/` (already existed for
  `RosterDetailView.vue`'s own per-game-day section) — the mini stats are
  summed client-side from those rows (chips out/returned by type, payments
  by the same 4 `PAYMENT_TYPES` `gaming/selectors.py`'s
  `game_day_summary_data` already uses), voided rows excluded from the
  sums but still shown (struck through) in the ledger table itself.
- Void still works from either ledger (club-wide or per-player) — reloads
  whichever is showing afterward.
- Confirmed via search that nothing else in the app linked to
  `/game-days/:id` before removing the route.

### Fixed: "Owed to players" stat card had a hardcoded "7 players" (2026-09-23)
`DashboardView.vue`'s "Owed by players" card correctly used `totals.debtor_count`;
its sibling "Owed to players" card had a literal `7 players` in the template
instead — never wired to real data. `selectors.dashboard_totals()` now
returns a 4-tuple (`total_debt, total_credit, debtor_count, creditor_count`)
instead of 3 — `creditor_count` computed the same way `debtor_count` already
was (count of players with `balance > 0` from the same grouped query, no
extra query). `DashboardView` (gaming/views.py) adds `creditor_count` to the
response for both Accountant and Owner. Test added:
`test_dashboard_creditor_count_is_computed_not_hardcoded`.

### Hi-fi sidebar nav + FX Rates moved to Settings + rake-this-month stat (2026-09-23)
- **Hi-fi sidebar nav for Owner/Accountant/Floor Manager.** `AppShell.vue`'s
  bottom `.tabbar` is retired for these roles (Cashier still has no nav —
  `tabs.length === 0` for that role either way, unaffected) in favor of a
  left sidebar below the topbar, per the lo-fi nav review sketch: `.shell`
  now stacks `.topbar` over a new `.below-topbar` row (`.sidebar` +
  `.content` side by side, `min-height: 0` load-bearing so `.content`'s own
  scroll still works — same fix as the earlier `height: 100vh` stage change).
  `tabs` is split into `mainTabs`/`settingsTab` computeds so Settings can
  render pinned to the bottom of the sidebar, below a spacer, matching the
  sketch — `tabs` itself is unchanged, still the one source of truth.
- **FX Rates moved from Admin to Settings**, into the Owner-only block
  (`ClubSettingsView.vue`, alongside Approvals and Payout auto-approval) —
  same `/conversion-rates/`+`set_rate` endpoints, state, and markup, just
  relocated; `AdminView.vue` loses the section, its now-unused state/
  functions, and its FX-only CSS. Still gated to Owner only (the section
  itself — the Settings route stays open to Floor Manager for Tables above
  it), matching the old Owner-only Admin route's behavior exactly.
- **Owner Dashboard: "Unreturned chips" → "Total rake this month".** New
  `selectors.total_rake_this_month()` (RAKE transactions since the start of
  the current Africa/Lagos calendar month, live — not gated behind a
  game-day close the way `outstanding_chips_total()`'s `GameDaySummary` rows
  are). `DashboardView` (gaming/views.py) now sends `total_rake_this_month`
  instead of `outstanding_chips` for OWNER; ACCOUNTANT's response is
  unchanged (`outstanding_chips`, unaffected — this was an Owner-dashboard-
  only ask). Frontend: `DashboardView.vue`'s 3rd stat card branches on
  whichever field actually came back.

### Owner Dashboard's per-load computation, explained (not fixed) (2026-09-23)
Asked, not filed as a bug: `GET /dashboard/` (gaming/views.py's
`DashboardView`) recomputes everything from raw `Transaction` rows on every
single request, no caching, no stored running totals anywhere:
- `selectors.dashboard_totals()` — every non-voided Transaction with a
  player, grouped by player and summed (`signed_amount`) in one query, then
  split into "owed by"/"owed to"/debtor-count with a **Python loop over
  every player** (not done in the DB) — the heaviest of the three, and the
  one that gets slower as the player roster grows, independent of how much
  activity happened recently.
- `selectors.main_account_balance()` (Owner only) — every MAIN_ACCOUNT_FILTER
  Transaction ever posted, summed.
- `selectors.outstanding_chips_total()` (Accountant) / `total_rake_this_month()`
  (Owner, new this session) — the former sums every closed game-day's
  `chips_variance` ever recorded; the latter scopes to the current month, so
  it's the one number here that doesn't grow unbounded with the club's age.
At this club's current scale (per PLAN.md's own "accepted trade-off" note on
the Payouts page's client-side filtering) this is fine — flagged here only
because the question was asked, not because it's misbehaving. If it ever
needs to change, the shape would likely be a stored per-player running
balance (maintained incrementally by `record_transaction`, the way
`GameDayPlayer`/`GameDaySummary` already snapshot other totals) rather than
recomputing the whole ledger on every dashboard load.

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
- [ ] Flag a void at void-time when it would silently create/change a chips
  excess (voiding a `CHIPS_OUT` after its matching `CHIPS_IN` already
  posted) — currently only surfaces later, at close, via `chips_variance`
- [ ] Idle/session timeout at the Cashier desk (a logged-in session left
  unattended has no auto-lock today)
- [ ] Shift handoff — no record of "Cashier A hands off to Cashier B"
  mid-game-day
- [ ] A path back in for a forgotten entry discovered after close (deal/
  write-off can still post to a closed game-day; nothing else can)
- [ ] Merge/delete path for a duplicate/mistaken player registration
  ("+ New Player" always creates a real, permanent `Player` row)
- [ ] Printable/exportable end-of-night report for the Cashier to hand over

---

## 3. Design decisions

- **Owner/Accountant/Platform-Admin frontend: same Vue app** as Cashier, with role-gated routes+nav (mirrors how Leyyow Affiliates admin is structured — one app, many roles) — not a separate app/build. Cashier's own stores/axios setup already generalize cleanly for this.
- **New, distinct style guide** for Owner/Accountant/Platform-Admin surfaces — not reused from the Cashier's frozen "Ledger Slate" `tokens.css`, and not from Leyyow Affiliates' tokens either. Build it fresh via the `design` skill when Phase B starts, the same process the Cashier surfaces went through.
- **Platform Admin's Integration Settings screen lives in the same Vue app**, not Django's built-in `/admin/` panel — chosen explicitly over that alternative for auth/UX consistency.
- **Deployment target**: not yet decided (Railway, matching Leyyow Affiliates, is the likely default — confirm before Phase E).
