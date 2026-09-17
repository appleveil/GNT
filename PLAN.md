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
