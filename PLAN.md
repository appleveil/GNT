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
