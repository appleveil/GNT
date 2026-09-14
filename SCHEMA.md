# Data Model / Schema Plan

Target: Django + PostgreSQL. This is a plan to review, not code — field names/types are Django-flavored so it translates directly into `models.py` once approved.

## Design principles

1. **One master ledger, four views.** All of Game-day ledger, Player game-day ledger, Outstanding ledger, and Main account ledger are read-only *filtered views* over a single `Transaction` table — never separately maintained tables. This is what makes the four ledgers structurally unable to disagree with each other (the mechanism behind "no reconciliation tool needed," discussed earlier).
2. **Balances are computed, not stored.** A player's balance, the game-day's running balance, and the Main account balance are all `SUM()` queries over `Transaction` rows up to a point in time — never a mutable running-total column. This avoids the classic stale-balance bug where a stored total drifts from its source rows.
3. **Corrections are soft.** Rows are voided (with an audit trail: who, when, why), never hard-deleted — matches the Cashier-same-day / Owner-post-close correction rules already decided.
4. **Money**: `DecimalField` in Naira-equivalent value. Chips are 1:1 with Naira value per the brief's own examples (500,000 chips ~ ₦500,000), so no separate "chip" unit exists in the schema.

## Entities

#### `Player`
- `account_code` — club-assigned short code (e.g. "WWI 7"), unique
- `display_name`
- `chips_limit` — `DecimalField`, nullable (null = no cap), Owner-set-and-edited only. Per-game-day credit ceiling: checked against the player's *current game-day debt* (chips issued minus paid/returned so far that game-day), not a lifetime or per-transaction cap. Added 2026-09-13 — see `CONCEPT.md`'s "Chips limit."
- `is_active`, `created_at`

#### `PaystackAccount`
Represents either the singleton **Main account** or a player's **Gaming Account** — merged into one table since both have identical shape. Revised 2026-09-13: there is only ONE Paystack integration for the whole club (one key pair, in Django settings — see `paystack_client.py`), not a separate integration per player as originally drafted — see `CONCEPT.md`'s "Built — real Paystack integration." A Gaming Account is a Paystack **Customer** + a **Dedicated Virtual Account** under that one integration.
- `account_type` — `MAIN` | `GAMING`
- `player` — FK → Player, null for `MAIN`, required+unique for `GAMING`
- `paystack_customer_code` — blank for `MAIN` (renamed from `paystack_integration_id` 2026-09-13)
- `label` — display name (renamed from `integration_name` 2026-09-13); e.g. "LPC Main Account", or the player's name for a `GAMING` row
- ~~`public_key`, `secret_key`, `webhook_secret`~~ — removed 2026-09-13: there's only ever one of each, already in settings (`PAYSTACK_SECRET_KEY`/`PAYSTACK_PUBLIC_KEY`); nothing per-row to store
- `created_at`
- App-level constraint: exactly one `MAIN` row must exist

#### `DedicatedVirtualAccount`
- `paystack_account` — FK → PaystackAccount
- `paystack_dva_id` — Paystack's own id for this DVA, for future deactivation calls. Added 2026-09-13.
- `bank_name`, `bank_code`, `account_number`, `account_name`
- `is_active`, `created_at`

#### `PlayerBankAccount` (receiving account for cash-outs; Cashier-managed)
- `player` — FK → Player
- `bank_name`, `bank_code`, `account_number`, `account_name`
- `is_default`, `created_at`
- `paystack_recipient_code` — cached Paystack transfer recipient, created once on first payout attempt and reused after. Added 2026-09-13.

#### `StaffProfile` (Cashier / Accountant / Owner — real logins)
- `user` — OneToOne → Django `User`
- `role` — `CASHIER` | `ACCOUNTANT` | `OWNER`
- `pin_hash` — hashed, nullable; mirrors `FloorManager.pin_hash`. In v1 only Owner-role rows have one set — it's how the Owner authenticates in-person for Open Game-Day / Set Conversion Rate without a full login-switch on the Cashier's device. Added 2026-09-13.
- `is_active`, `created_at`

#### `FloorManager` (not a login — a named confirmation credential)
- `name`
- `pin_hash` — hashed, never stored plaintext
- `is_active`
- `created_by` — FK → StaffProfile (an Owner)
- `created_at`

#### `GameDay`
- `number` — sequential display number, unique
- `started_at`, `ended_at` (null while open)
- `status` — `OPEN` | `CLOSED`
- `opened_by` — FK → StaffProfile, **nullable** (revised 2026-09-13). Set to the resolved **Owner** when an Owner's PIN or login authorized the open; **null** when a Floor Manager's PIN authorized it instead (a Floor Manager has no `StaffProfile` row to point to). Never set to a Cashier, regardless of which staff device/session the request came through — a Cashier is never the authorizer, only (at most) the one physically tapping the screen.
- `opened_by_floor_manager` — FK → FloorManager, null; set when a Floor Manager's PIN was the authorizer (mutually exclusive with `opened_by` being set to an Owner)
- `closed_by` — FK → StaffProfile
- `closed_by_floor_manager` — FK → FloorManager, null; optional — Cashier or Owner can close solo, or a Floor Manager PIN can authorize it instead

#### `ConversionRate`
- `currency` — `USD` | `GBP` | `EUR` | `OTHER` (NGN implicit = 1)
- `rate_to_naira`
- `game_day` — FK → GameDay, null = standing/default rate; set = override for that specific game-day
- `set_by` — FK → StaffProfile, **nullable** (revised 2026-09-13, same reasoning as `GameDay.opened_by`) — the resolved Owner, or null if a Floor Manager's PIN authorized it
- `set_by_floor_manager` — FK → FloorManager, null; set when a Floor Manager's PIN was the authorizer
- `created_at` — immutable; a rate change is a new row, never an edit, per the brief's "past rates can't be changed"

#### `Transaction` — the master ledger
- `game_day` — FK → GameDay, **null** for between-game-day entries (these feed the Outstanding ledger only)
- `player` — FK → Player, null only for `RAKE`/`TIP`
- `type` — one of:
  `CHIPS_OUT`, `CHIPS_IN`,
  `PAYMENT_CASH`, `PAYMENT_TRANSFER`, `PAYMENT_POS`, `PAYMENT_DEAL`,
  `PAYOUT`, `WRITE_OFF`, `RAKE`, `TIP`
  (`CHIPS_OFFSITE_OUT`/`CHIPS_OFFSITE_RETURN` **removed 2026-09-13** — off-site/excess chips are no longer a `Transaction` at all; see `GameDaySummary.chips_variance` below)
- `amount` — always positive
- `currency`, `conversion_rate` — relevant to `PAYMENT_CASH` only; `conversion_rate` is a snapshot value, not a live FK, so history never shifts
- `channel` — `CASHIER` | `TRANSFER_DVA` | `CASH` | `POS` | `CHIPS` | `DEAL` | `WRITE_OFF` (drives the ledger's "icon" column)
- `notes`
- `recorded_by` — FK → StaffProfile, null for webhook-auto-captured rows
- `floor_manager` — FK → FloorManager, set only for physical-count types (`CHIPS_OUT`, `CHIPS_IN`, `PAYMENT_CASH`, `RAKE`, `TIP`) — never Owner-authorized, a dual-witness count is always a Floor Manager PIN specifically
- `confirmed_at` — when the FM PIN was validated
- `status` — `POSTED` | `PENDING_APPROVAL` | `APPROVED` | `REJECTED` | `TRANSFER_FAILED` (only `PAYOUT` uses the non-`POSTED` states, per "every payout needs Owner approval"). `TRANSFER_FAILED` added 2026-09-13: the Owner approved, but the real Paystack transfer didn't go through (no bank account on file, Paystack rejected it, ...) — distinct from `REJECTED` (an Owner's business decision); a `TRANSFER_FAILED` payout can be re-approved once the underlying issue is fixed.
- `approved_by`, `approved_at` — FK → StaffProfile (Owner)
- `is_voided`, `voided_by`, `voided_at`, `void_reason` — soft-correction trail
- `external_reference` — Paystack transaction ID; unique when set, used for webhook idempotency (prevents double-processing a retried webhook)
- `created_at`

Note: `Deal` and write-off/credit are **not** separate tables — they're `Transaction` rows (`PAYMENT_DEAL`, `WRITE_OFF`) authored by an Owner. Their own approval is implicit: only an Owner can create them, so there's no separate approval workflow to model.

#### `GameDaySummary` (snapshot, written once at close — not computed live)
Captures "final position" fields the brief says only exist after a game-day closes: `num_players`, `chips_out_total`, `chips_in_total`, `rake_total`, `tips_total`, `chips_variance`, `total_payments`, `game_balance`. One row per `GameDay`, written at close time so historical game-days don't need recomputation.
- `chips_variance` — `DecimalField`, signed (renamed from the original, never-implemented `chips_outstanding` placeholder — same slot, precise definition added 2026-09-13). Computed at close as `chips_out_total − chips_in_total − rake_total − tips_total`: **positive** = unreturned/off-site chips for this game-day; **negative** = excess chips returned this game-day (chips that went off-site on an earlier day coming back into play). The club-wide **Outstanding Chips** figure shown to Accountant/Owner is a live `SUM(chips_variance)` over every closed `GameDaySummary` row — not a stored running total, consistent with the "balances computed, not stored" principle above.

## The four ledgers, as queries over `Transaction`

| Ledger | Filter |
|---|---|
| Game-day ledger | `game_day = X`, excluding `RAKE`/`TIP` |
| Player game-day ledger | above + `player = Y` |
| Outstanding ledger | `game_day IS NULL` (between-game-day payments/deals), per player — **Owner/Accountant only** as of 2026-09-13 (`IsOwnerOrAccountant`, replacing the current `IsAuthenticated`); a Cashier never reaches this, consistent with no cross-game-day history being shown to that role |
| Main account ledger | `channel = TRANSFER_DVA` (sweep-ins) OR `type = PAYOUT` (transfers out) — the only rows that actually touch the bank |

## ERD

```mermaid
erDiagram
    Player ||--o| PaystackAccount : "has a Gaming Account"
    Player ||--o{ PlayerBankAccount : "receiving accounts"
    Player ||--o{ Transaction : "party to"
    PaystackAccount ||--o{ DedicatedVirtualAccount : "DVAs"
    GameDay ||--o{ Transaction : "contains"
    GameDay ||--o| GameDaySummary : "closes into"
    GameDay ||--o{ ConversionRate : "rate override for"
    StaffProfile ||--o{ Transaction : "recorded / approved / voided"
    StaffProfile ||--o{ GameDay : "Owner PIN/login authorizes open"
    StaffProfile ||--o{ ConversionRate : "Owner PIN/login authorizes"
    FloorManager ||--o{ Transaction : "confirms"
    FloorManager ||--o{ GameDay : "PIN authorizes open/close"
    FloorManager ||--o{ ConversionRate : "PIN authorizes"
```

## Modeling calls made — flag if any should change

- Main account and Gaming Accounts merged into one `PaystackAccount` table (type-flagged) rather than two tables — they're structurally identical in the brief.
- `Deal` and write-off/credit given no dedicated table — modeled as `Transaction` subtypes, since only the Owner can author either and both just move an amount against a player.
- Balances (player, game-day, Main account) are always computed at query time — nothing is cached except the `GameDaySummary` snapshot taken at close.
- `CreditRequest` (Owner "approve credit request") isn't modeled yet — it depends on the deferred Player app (phase 2), since there's no v1 path for a player to originate a request without a login.
- Notification and general activity-log tables aren't modeled yet — pending the still-open notification matrix; most financial activity is already attributable via `recorded_by`/`approved_by`/`voided_by`/`floor_manager` on `Transaction`.
- **Chips-limit enforcement lives in `record_transaction`, not the serializer alone.** ✅ Built 2026-09-13: on a `CHIPS_OUT` attempt, computes the player's current game-day debt via `selectors.player_game_day_balance` + the new amount; raises `InvalidStateError` before the Floor Manager PIN step runs if `player.chips_limit` is set and would be exceeded.
- **Authorizer resolution generalizes from Floor-Manager-only to Floor-Manager-or-Owner.** ✅ Built 2026-09-13, shipped slightly differently than first sketched here: rather than renaming `_resolve_floor_manager(floor_manager_id, pin)` into one combined `_resolve_authorizer(authorizer_type, authorizer_id, pin)`, `_resolve_floor_manager` was kept as-is and a new `_resolve_owner_pin(owner_id, pin)` added alongside it, unified by a `_resolve_owner_or_floor_manager` wrapper — less churn on the existing FM-only call sites (physical-count confirmations), same effect. `GameDay.opened_by`/`ConversionRate.set_by` are now nullable (`limit_choices_to={'role': OWNER}`).
- **Cashier-facing "today's balance" is a new selector, not a new field.** ✅ Built 2026-09-13: `player_game_day_balance(player, game_day)` — a signed `SUM()` over `Transaction` rows scoped to one `game_day`, mirroring the existing lifetime `player_balance(player)` but bounded. `PlayerSerializer.get_balance` returns it instead of the lifetime `balance` for a Cashier caller when the lifetime figure is negative; positive values still return the lifetime figure regardless of caller role.
- **A "Gaming Account" is a Paystack Customer + Dedicated Virtual Account, not a separate Paystack integration.** ✅ Built 2026-09-13: the original brief modeled each GA with its own key pair and webhook (mirrored in `PaystackAccount`'s original `public_key`/`secret_key`/`webhook_secret` fields), which isn't a real Paystack primitive — there is one integration, one key pair, one webhook, club-wide. `payments/paystack_client.py` wraps the real endpoints (`/customer`, `/dedicated_account`, `/transferrecipient`, `/transfer`); `payments/services.provision_gaming_account(player)` creates a Customer+DVA on demand (no "next available GA" pool — see `CONCEPT.md`). One consequence: there's no real "sweep to Main account" money movement (only one Paystack balance exists), so `sweep_to_main_account` was retired; a payout's approval now calls the real Transfer API instead, landing in the new `TRANSFER_FAILED` status if it can't complete.
