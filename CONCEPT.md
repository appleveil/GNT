# LPC Reconciliation Project Brief

## Background

A gaming club needs a way to track payments from its players. Players come in, collect chips - which can be used to play a variety of games - and then cash out any chips they have when they are done playing and want to leave. On rare occasions the players leave the club with chips and return at a later date to play with it or cash it. Below is an outline of the current process:

- Player collects chips from cashier
- Cashier registers quantity of chips collected by player
- Player pays cashier (or settles) through any of the following methods (channel / mode):
    - Transfer (transferring to a bank account number provided by the club)
    - Cash (typically naira, but also other currencies)
    - Point of sale card reader
    - On occasion, a player is able to reach a deal with a club owner that absolves them of some or all payment

A player is allowed to combine a variety of channels when making payment.

#### Challenges

The problem with the present system is that reconciliation can be tedious - and sometimes impossible - especially when a player pays using different transfer methods, or when the owner has a promotional agreement with a player but does not inform the accountant - which makes it difficult to keep track of dues. Below is a list of scenarios that make reconciliation particularly challenging:

- Having to reconcile with statements from multiple bank accounts
- A player paying into multiple banks or with different channels for the same game-day. Worse when this happens with multiple players.
- A player making payment one or more days after a game-day.
- A player making payment from an account or source with a different name such that it is not obvious who made the payment or what it is for.
- A player making payments in instalments or fragments.

#### Problem statment

The gaming club has a fragmented payments system resulting in a tedious and time-consuming, and occasionally impossible, reconciliation process.

## Solution

A payments collection system that results in a seamless and accurate reconciliation. The solution will be achieved by:

- Ensure payments from each individual player is automatically tracked irrespective of the method of payment, time taken to pay, fragmentation, or instalment.
- Track agreements with the owner.

## Solution overview

*NB: The club has existing processes and procedures for game-day operations and reconciliation. These are inadequate to achieve the required solution and need to be revised.*

**The key to the solution** is being able to track payments from players consistently and accurately over their lifespans albeit anonymously. The existing process for receiving payments will be refined by introducing a payment system that is able to match payments to players irrespective of the payment method, source, instalment, or date. Achieving this and combining it with the already accurate process of tracking chips issued to players will make it possible to build accurate and up-to-date player-specific-ledgers for any game-day and across any time frame, from the day the new system is implemented.

The solution will require behavioural or process changes for players and other personnel. The personnel categories (users) are listed below, as well as their relation to each other.

#### Clubhouse personnel / users

**Player** (club house patron)

- Receives chips
- Makes payments to club

**Cashier**

- Issues chips to players
- Tracks payments received from players on game-day

**Accountant**

- Responsible for reconciliation

**Owner** (Business owner)

- Requires visibility into all club activities
- Modify player payment obligations *(can only reduce amount owed, not increase)*

The finished solution will have four physical and/or virtual interfaces - one for each user - to view and update information required to accurately reconcile every game-day. The goal of each interface is outlined below. 

#### Apps/Interfaces

**Club interface and users**  (necessary)

1. Cashier
2. Accountant
3. Owner

**Player interface**

1. Player

#### 1. Cashier

- Add player
- Update player bank details
- Issue chips
- Register game-day payments from existing payment providers. ***Deprecated / Anathema to reconciliation***
- Receive chips
- Optional
    - Initiate payment to players that cash-out (will require approval by owner)

#### 2. Accountant

- Present club health
    - Outstanding balances (total being owed by players)
    - Outstanding obligations (total owed to players)
    - Cash in bank  ***access to be confirmed***
- View game-day summary and details
- View game-day history
- View players
    - List of players
    - Details for any game-day (required for player disputes and for reconciliation)

After a game, they have to enter how much chips was returned (in chips and cash - to send to player)

#### 3. Owner

- All accountant views
- Edit outstanding player balances downwards
    - *Player, Amount, Reason/notes*
- Approve credit request (if approved)

#### 4. Player

- Get chips (for playing)
- Pay for chips - through new payment ecosystem; in order to track payments for each player irrespective of payment method, source, date, or fragmentation. ***Core of solution***
- Provide bank details (for cashing out)
- Optional player app/interface
    - Player to view their game-day details
    - Player to view their historical/previous game-day data
    - Player to request/initiate payment for any existing balance
    - Player to deposit funds before game-day
    - Request credit from owner

The new payment ecosystem will prioritise payment tracking in the following order (priority order to be confirmed):

- Payment via transfer (local)
- Payments via Point of Sale card reader (local cards)
- Payments via Point of Sale card reader (foreign cards)
- Cash payments (foreign currency)
- Others

# Player Payment Tracking

Status: Not started

[LPC Reconciliation Project Brief](https://app.notion.com/p/LPC-Reconciliation-Project-Brief-3d5f3934f31480a19235dfa4ab40e06d?pvs=21)

---

## Scope decisions (resolved 2026-09-13)

The brief above used "Promoter," "Manager," and "Owner" interchangeably for the same person, and left several behaviors ("how to reverse mistakes," auth, who enters what) unresolved. Decisions below supersede those ambiguities; role names in the rest of this doc have been normalized accordingly.

- **Roles**: One business-owner role, standardized to **Owner** everywhere (was Promoter/Manager/Owner).
- **Chip returns**: Cashier enters chips-returned in real time as each player cashes out (not a post-game Accountant step).
- **Corrections/reversals**: Cashier can void/edit their own entries same-day, while the game-day is still open. Once a game-day is closed/locked, only the Owner can amend it.
- **Auth**: Cashier, Accountant, and Owner get accounts (staff auth) for v1. Players do not log in — the optional player app, and player-side auth, is explicitly deferred to a later phase.
- **Deals**: Only the Owner can create a Deal entry (a deal is the Owner's agreement with a player, so the Cashier has no path to log one on the Owner's behalf).
- **Accountant visibility**: Accountant sees outstanding balances/obligations only — not the actual Main account bank balance. That stays Owner-only.
- **Payout approval**: Every cashier-initiated player payout requires Owner approval, no threshold exemption, for v1.
- **Player bank accounts**: Cashier manages a player's receiving bank account(s) on their behalf (players have no login), and one account can be marked default.

**Still open** (flagged, not blocking v1 feature scope, revisit before/while building):
- WhatsApp interface: exact action set available to the Owner via WhatsApp vs. the full app.
- Notification matrix: which event notifies which role via which channel (partially specified in brief).
- Failure handling: webhook/sweep failure, insufficient Main-account balance at payout time, failed transfer to a player.
- Whether Cashier can see a player's full cross-game-day history at seating time, or only the current game-day.
- ~~Technical validation of the Paystack dedicated-virtual-account-per-player approach~~ — confirmed feasible directly with Paystack support (2026-09-13); proceeding on that basis.

## Completeness pass (resolved 2026-09-13)

Reviewed each role's v1 scope against the Challenges/Problem statement. Decisions:

- **Why no reconciliation tooling is needed**: every entry is either externally verified at the source (Paystack webhook — money genuinely landed in a bank account) or physically double-counted by two people (Cashier + Floor Manager) *before* it's keyed into the system. Reconciliation therefore happens either automatically (webhook capture) or at the point of entry (dual physical count) — not as a separate after-the-fact step. This is why the four ledgers, being derived from one single stream of pre-verified entries, can never disagree with each other. Accountant's job is to monitor that read-only picture, chase debtors, and flag anything that still looks off — not to run a matching process.
- **Floor Manager**: Not a platform role/interface — a named individual's confirmation PIN, entered inline on the Cashier's device for every physical-count entry, formalizing the dual-count the brief already implied ("cashier and supervisor confirm..."). See Cashier scope below.
- **Player deposit notifications**: Stay excluded for v1, per the original brief. Player experience remains verbal confirmation via Cashier only.
- **Chips taken off-site**: Added as an explicit v1 feature (was previously an untracked edge case). See Cashier scope below.
- **Staff account management**: Owner manages Cashier and Accountant accounts in-app (create, deactivate, reset password), plus Floor Manager staff records (name + PIN only, no login).
- **Game-day open/close authorization**: Opening a game-day requires the Owner or a Floor Manager (PIN) — Cashier cannot open one alone. Closing/locking a game-day can be done by the Cashier, the Owner, or a Floor Manager (PIN) — any of the three.
- **FX conversion rate ownership**: Owner or Floor Manager (PIN) can set/update the rate per currency, including per-game-day overrides. Cashier and Accountant cannot.

### Known gaps / backlog (deliberately out of v1, revisit later)

- Owner: pending-approvals *queue* (a live inbox), not just an approval history list
- Owner: settings UI for the fraud/transfer limits the brief flags as needed (per-transaction, per-24hr, per-recipient-frequency)
- Period-over-period reporting (weekly/monthly trends, top debtors) beyond per-game-day and live totals
- Search/filter/export across player lists, game-day history, and ledgers
- An "unattributed payment" queue for money landing in a non-DVA club account or cash with an unclear source — the DVA design solves this for player-linked transfers, but manually-registered transfers/cash into shared accounts have no matching workflow

## Role feature scope (v1)

#### Cashier (staff account, logged in)

- Close/lock a game-day at the end (alone, no extra authorization needed)
- Cannot open/start a game-day alone — needs the Owner or a Floor Manager PIN to authorize it (see Floor Manager note below)
- Add player (create profile → linked to next available Gaming Account/DVA)
- Update player details, incl. receiving bank account(s) and default
- Issue chips to a player (logged with issuing cashier for activity tracking)
- Register chips returned, in real time, per player
- Mark chips as **taken off-site** by a player (distinct from a normal cash-out) — carries as an open balance/liability across game-days until the player returns to play them or cash them
- Register a player's return of previously off-site chips (either back into play, or cashed out)
- Register manual payments: Cash (with currency + conversion rate), POS card reader, and confirm auto-captured Transfer/POS payments
- Register rake and tips (qty + source)
- Initiate a player payout (cash-out transfer) — always requires Owner approval before funds move
- Void/edit their own entries for the current, still-open game-day
- Cannot: create/edit a Deal; approve payouts; amend a closed game-day; set FX conversion rates; open a game-day unassisted
- Out of scope / explicitly excluded: registering payments via the old/existing payment providers (flagged in the brief as "deprecated / anathema to reconciliation")
- Every physical-count entry (chip issuance/return/off-site, cash, rake, tips) requires a Floor Manager confirmation password entered inline, in the same form, before it saves — see Floor Manager note below.

**Floor Manager — not a role with its own account or interface.** It's a confirmation credential, not a platform user: formalizes the dual physical count the brief already implied ("cashier and supervisor confirm the amount..."). Whichever Floor Manager is on shift enters their own short PIN/password, right there on the Cashier's device at the moment of a physical-count entry, since they already independently witnessed the same count — nothing async, no separate queue to check later.

- The PIN/password is tied to a named individual (not shared), so the entry's audit trail records exactly who confirmed it — consistent with activity tracking elsewhere in the system
- Blocking, but trivial: the entry can't save without it, but since the Floor Manager is standing right there for the count anyway, it's a few keystrokes, not a workflow — shouldn't meaningfully slow game night
- A wrong/mismatched PIN simply blocks the save, prompting a recount/correction on the spot rather than surfacing as a later dispute
- Needs a lightweight staff record (name + PIN) for each Floor Manager, managed by the Owner alongside other staff accounts — but no login, dashboard, or permissions of their own beyond that PIN
- The same PIN also gates three higher-stakes actions, entered on whichever staff device is performing the action:
    - **Opening a game-day** — requires the Owner's own login, or a Floor Manager PIN (Cashier cannot open one solo)
    - **Closing a game-day** — Cashier, Owner, or a Floor Manager PIN can each do this alone
    - **Setting/updating the FX conversion rate** — Owner's own login, or a Floor Manager PIN (Cashier and Accountant cannot)

#### Accountant (staff account, logged in — read-only + no write actions in v1)

- Dashboard: outstanding balances (total owed by players), outstanding obligations (total owed to players); no Main account bank balance
- View game-day summary, detail, and full history
- View player list and per-player detail, including any game-day's ledger (for disputes/reconciliation)
- No correction rights (corrections are Cashier same-day / Owner post-close, per decision above)

#### Owner (staff account, logged in; some actions also via WhatsApp — exact set TBD)

- All Accountant views, plus the actual Main account balance
- Edit a player's outstanding balance downward only (player, amount, reason/notes) — write-offs/credit
- Create and record Deal entries
- Approve every player payout before funds move
- Approve credit requests
- Amend/correct any entry after its game-day is closed/locked
- History views: approvals, transfers, forgiveness/write-offs
- Manage staff accounts: create/deactivate Cashier and Accountant logins, reset passwords
- Set/update FX conversion rates per currency (incl. per-game-day overrides; past rates stay immutable per the original brief) — a Floor Manager PIN can also authorize this
- Open a game-day alone (a Floor Manager PIN can also authorize this; Cashier cannot open one solo)

#### Player (no login in v1 — interacts only through the Cashier and notifications)

- Receives chips from Cashier
- Pays for chips via the payment ecosystem (transfer to their DVA, cash, POS, or a Deal) — any channel or combination, any timing, tracked automatically to their profile
- Provides a receiving bank account (via Cashier) for cash-outs
- Receives notifications (channel TBD — see open items)
- **Deferred to a later phase** (optional player app): viewing own game-day/history, self-initiating payment on an existing balance, pre-game-day deposits, requesting credit from the Owner directly

## Specifications

### Platform setup

The platform collectively consists of five modules: four with an interface, and one backend. The modules are:

- Main platform backend
- Player interface (mobile app)
- Cashier interface (mobile app, desktop app, web)
- Accountant interface (web, desktop app)
- Owner interface (mobile app, desktop app, web, whatsapp)

#### Main account

**Purpose / Function**

- All player funds will be swept into this account. It will serve as the source of truth for the club’s account balance.
- It will be used to credit players instantly - with approval by the owner - when they return their chips.

**Properties**

- One or more dedicated virtual account numbers (for deposits)
    - Bank name
    - Bank account number
    - Bank code
- Keys
    - Private key
    - Public key
- Webhook url (and setup - to receive notifications from Paystack whenever a deposit is made into the integration via any of its dedicated virtual accounts)
- API endpoints to initiate automatic transfers to other accounts

#### Gaming account (GA)/ Player profile

Gaming accounts (GA) are Paystack accounts/integrations (similar to Stripe). Multiple GAs will be created with each one linked to a player. GAs have the following data/properties

- One or more dedicated virtual account numbers (DVA) - primarily to capture deposits. A DVA is effectively a bank account, and each one has a:
    - Bank name
    - Bank account number
    - Bank code
    - Account name
- Keys
    - Private key
    - Public key
- Webhook url (and setup - to receive notifications from Paystack whenever a deposit is made into the GA via any of its DVAs)
- API endpoints to initiate automatic transfers to other accounts

#### Platform rules

- **Deposits**
    
    Whenever a webhook linked to a GA notifies the platform that funds have been received, it should immediately sweep the funds to the Main account. Relevant parties should be notified at relevant stages.
    
    1. Funds are sent into a GA via any of its DVAs
    2. The webhook setup linked to the GA sends a notification to the platform, which acts as a cue to trigger the following actions:
        - Confirms the authenticity of the webhook e.g. source, amount, and so on. *Check the dev docs for how to achieve this, or suggest the best conventional methods.*
        - Notify the following users.
            - Cashier
                
                Email subject: Payment received
                Body: $_amount received from $player_name
                
            - Owner
                
                Email subject: Payment received
                Body: $_amount received from $player_name. Your balance is $_balance_amount
                
            - ~~Player~~
        - Forward the payment - less transfer charges - to the main account.
        - Update the following ledgers in the “Deposit” columns:
            - Player ledger
            - Player game-day ledger (if applicable)
            - Game-day ledger
            - Club ledger
            
            (“Deposit”  of type “Transfer”)
            
    3. Main account Webhook captures the deposit and does the following:
        - Updates the main account ledger
        - Notify relevant parties:
            - Owner (email / interface)
            - Accountant (interface)
    
    **Deposit / payment modes:**
    Deposits can be made through the methods/modes below.
    
    - Cash: This is manually registered into the system by the cashier
        - Currency
            - Naira (default)
            - Dollars
            - Pounds
            - Euros
            - Other
        - Each currency has its conversion rate relative to naira
            - The conversion rate can be changed
            - The conversion rate can be changed for any game day
            - Past conversion rates can’t be changed
    - Transfer: This can be manually registered, or automatically captured
        - Can have multiple accounts to receive transfers
    - Card (Point of Sale card reader): This can be manually registered or automatically captured
        - Can have multiple card readers, each one connected to a separate bank account
    - Chips (players returning chips counts as payment): This is manually registered
    - Deal (this is for when an agreement or deal is made with the owner. Deals are able settle outstanding player balances hence considered a form of payment). This can be manually registered or automatically captured
- **Transfer out (function/module)**
    
    The transfer module should be used for all transfer functions e.g. when sweeping funds from a GA to the Main account, or from the main account to a player.
    
    - Permission and authentication
    - Amount
    - Recipient:
        - Bank account name
        - Bank code
        - Account number
    - Can transfer naira only
        
        ---
        
    
    **Update db/ledger after transfer**
    
    After a successful transfer, note/update the following:
    
    - Transfer initiator (activity tracking)
    - Main account balance
    - Player profile
    
    Fraud checks:
    *It can only be initiated by an authorised personnel, and approved by an authorised approver, and to the authorised limits per transaction, per 24hr period, and frequency. As well as number of transfers to the same account per period. The owner has no limits… More details to be provided.*
    
    Withdrawals are typically initiated by the cashier and approved by the Owner but can be initiated by a player.
    
- **Player profile**
    - Player name
    - Gaming account (linked to account)
    *Properties include*
        - Paystack integration ID
        - Integration name
    - Player bank account (note that this is the player’s receiving bank account i.e. the bank account in which they receive their money when they return chips. It is different from the account they pay into when they collect chips).
        
        A player can have multiple receiving bank accounts.
        
    
    ~~A player can have multiple receiving bank accounts, and a default. The default can be changed, new accounts added, and existing ones deleted (this will happen on the player side)~~
    

#### Ledgers

There are four ledgers - which are served from a master ledger (or database)

- **Game-day ledger**
    
    This captures activities of a game within the time frame of the said game i.e. from the start date/time of a game, to the end date/time of the game. This ledger captures issuing of chips in addition to payments received.
    
    Properties
    
    - Captures all activities of a game
    - Time boundary is from game start to game end (date/time)
    - Includes activity of all players, cashier, club owner.
    - Does not capture tips nor rake
    
    Page summary / highlights
    
    - Game-day number
    - Start date and time
    - End date and time
    
    | Date | Account name | Player name | Chips out | Payment | Balance | Channel / Mode | Notes |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    |  | WWI 7 | Marco | 500000 | - | -500000 | Cashier | Chips out |
    |  | WWI 12 | Moses | 1000000 | - | -1500000 | Cashier | Chips out |
    |  | WWI 6 | Mary | 500000 | - | -2000000 | Cashier | Chips out |
    |  | WWI 9 | Martin | 500000 | - | -2500000 | Cashier | Chips out |
    |  | WWI 27 | Mama | 500000 | - | -3000000 | Cashier | Chips out |
    |  | WWI 2 | Musa | 1500000 | - | -4500000 | Cashier | Chips out |
    |  | WWI 7 | Marco | - | 700000 | -3800000 | Transfer (DVA) | Player deposit  |
    |  | WWI 7 | Marco | 2000000 | - | -5800000 | Cashier | Chips out |
    |  | WWI 7 | Marco | - | 500000 | -5300000 | Chips | Chips in |
    |  | WWI 7 | Marco | - | 100000 | -5200000 | Cash | Player deposit |
    |  | WWI 2 | Musa | - | 1000000 | -4200000 | Cash | Player deposit |
    |  | WWI 5 | Mike | 1500000 | - | -5700000 | Cashier | Chips out |
    |  | WWI 5 | Mike | - | 1500000 | -4200000 | Transfer (DVA) | Player deposit |
    |  | WWI 6 | Mary | - | 700000 | -3500000 | Chips | Chips in |
    |  | WWI 9 | Martin | - | 500000 | -3,000,000 | Transfer (DVA) | Player deposit |
    |  | WWI 7 | Marco | - | 1,000,000 | -2,900,000 | Deal | Deal |
    
    The channel/mode should be an icon within the appropriate column, not an actual column
    
    **Key:**
    
    - Date: Date of transaction
    - Account name: Name of account given by club
    - Player name: Player’s chosen name - from player profile
    - Chips out - Chips given to player
    - Payment - Payment for chips received
    - Balance: This is the club’s balance/position after the line transaction for this game only
    - Method / Mode - Payment method or Cashier - for “Chips out”
    - Notes:
        - If transaction is Deposit: Player deposit;
        - If  Chips out: Chips out;
        - If Chips returned: Chips in;
        - If transaction is Deal: Deal
- **Outstanding ledger**
    
    This ledger covers activities between games - typically payments and deals. It is automatically populated.
    
    Properties
    
    - Time bound between the end of one game-day (date/time) and the start of the next (date/time)
    
    | Date | Account name | Player name | Payment | Outstanding | Channel / Mode |
    | --- | --- | --- | --- | --- | --- |
    |  | WWI 7 | Marco | 500,000 | 0 | Transfer |
    |  | WWI 12 | Moses | 500,000 | 1,000,000 | Transfer |
    |  | WWI 6 | Mary | 200,000 | 0 | Deal |
    |  | WWI 12 | Moses | 200,000 | 800,000 | Deal |
    
    **Key:**
    
    *Definitions persist from previous definitions unless stated otherwise*
    
    - Date: Game date
    - Outstanding: Amount owed, or still owed by player
- **Main account ledger** - (the bank account view)
    
    This ledger captures only deposits and withdrawals (transfers) from the main account - which are automatically registered. Transactions that are manually entered occur on an external platform and can’t be automatically verified.
    
    Properties:
    
    - Captures only transactions from the Main account
    - Does not capture chips issuing, deals, and other deposit methods
    - There is no time boundary i.e. it contains transactions outside game-day
    
    | Date | Transfer out | Deposit | Balance | Notes |
    | --- | --- | --- | --- | --- |
    |  | - | 700000 | 3200000 | Deposit from WWI 7 |
    |  | - | 1500000 | 4700000 | Deposit from WWI 5 |
    |  | 200000 | - | 4500000 | Transfer to WWI 6 |
    |  | - | 500000 | 5000000 | Deposit from WWI 9 |
    
    **Key:**
    
    - Transfer out: Amount transferred out of the account (typically player winnings)
    - Deposit
    - Balance
    - Notes
- **Player game-day ledger**
    
    This ledger tracks all activities related to a player on a game-day. It is time-bound within the game-day.
    
    | Date | Chips | Payment | Balance | Channel / Mode | Notes |
    | --- | --- | --- | --- | --- | --- |
    |  | 500000 | - | -500,000 | Cashier | Chips out |
    |  | - | 700,000 | 200,000 | DVA | Player deposit  |
    |  | 2000000 | - | -1,800,000 | Cashier | Chips out |
    |  | - | 500,000 | -1,300,000 | Chips | Chips in |
    |  | - | 100,000 | -1,200,000 | Cash | Player deposit |
    
    **Key:**
    
    - Date
    - Chips
    - Payment
    - Balance
    - Channel/Mode
    - Notes

### Player experience

#### Buy-in

- Player visits cashier
    - New player
        
        
        Cashier adds a new/unlinked player by
        
        - Select Create New Profile (*Cashier is presented with form to add the following)*
            - Player’s name or chosen name (*Compulsory field)*
            - Player’s bank account details - for them to receive future winnings. (*Optional field)*
                - Bank name
                - Account number
            - Save
                
                ***Backend:** Links the profile to the next available GA and returns the DVAs linked to it.*
                
        - Cashier gives player the dedicated virtual account (DVA) details.
    - Existing player
        
        
        - Cashier retrieves player account
        - Cashier informs player of their GA details - in case they need reminding
- Player receives chips
- Player receives player account details to pay for chips

---

#### Return chips

- Player returns chips
    
    
    - Cashier receives chips
    - Cashier counts and confirms how many chips were returned
    - Cashier enters qty of chips returned into system
        
        ***Backend***: Update master ledger/db with:
        
        - Qty of chips returned
        - Player balance

### Cashier experience

*Note that the platform knows what player made the deposit because players are linked to player profile integrations i.e. any incoming funds to this DVA is assumed to be for the linked player profile.*

#### **Player seating**

- Cashier issues chips
    - **If new player**
    - **If existing player**
- Cashier enters chips issued to player into platform
    
    ***Backend***:
    
    - Update ledger database:
        - Qty of chips issued
        - Issuing cashier (activity tracking)

#### **Player return chips**

#### **Paying Players**

**Cashier initiates transfer to player**

- Cashier may initiate transfer of any positive balance to the player if there is sufficient balance in the Main account. *Requires two people to confirm the amount of chips returned and possibly owner approval.*
- Player may be asked for bank details if not already given

***Backend***: Update:

Player profile:

- Amount received (transferred to player)
- Player balance

Main account:

- Balance
- Amount transferred

#### Rake and tips

- Cashier receives chips from the table (rake) and tips
- Cashier and supervisor confirm amount of chips received
- Cashier enters amount of chips received into system
    
    *Cashier provided with interface to enter:*
    
    - Qty of chips
    - Source (Rake or Tips)
- Backend updates:
    - rake amount
    - tips amount
    - Balance

### Accountant experience

- View ledgers
- View game-day history

Landing page: Game-day history page

#### Views

**Club**

- Overview (section on page)
    - Current balance (cumulative from all game-days)
    - Total outstanding (from debtors) / count of debtors
- List of debtors and corresponding debt (section on page)
    
    
    | Player | Outstanding |
    | --- | --- |
    | Marco | ₦500,000 |
    | Martin | ₦200,000 |
- Game-days history (section on page)
    
    This view/table captures the final position after every game-day. Properties like rake, tips, and the balance from that game day can only be viewed on this ledger - there is no other ledger/view for them. Each row is a game-day summary. The user can click any row to view more details*.*
    
    The cashier updates the details after every game-day and closes/locks it.
    
    | Game-day | Date | No of players | Chips out | Rake | Tips | Chips outstanding | Total payments | Game Balance |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 12 |  | 7 | 14,000,000 | 2,800,000 | 0 | 0 | 13,600,000 | -400,000 |
    | 13 | 05/06/26 | 9 | 24,000,000 | 4,800,000 | 0 | 0 | 24,000,000 | 0 |
    | 14 | 07/06/26 | 13 | 31,500,000 | 7,500,000 | 0 | 0 | 20,500,000 | -11,000,000 |
    
    Display a page to show details of the game day - when a row is clicked.
    
    **Game-day Detail** *(when a row is clicked)*
    
    - Summary / overview (section on page)
        - Game-day #
        - Start date (and time)
        - End date (and time)
        - Closing balance
        - Rake *(appears twice)*
        - # of players
        - Total chips given out
        - Total chips returned
            - Player
            - Rake
            - Tips
        - Payments received
            - Cash
                - Currency & Exchange rate
            - Main account (cumulative from GAs)
            - PoS
                - Provider
            - Transfer
                - Bank
            - Deals
                - Player
                - Amount
                - Reason
- List of players
    - WWI 1
    - WWI 7
    - WWI 6
    
    *Clicking on a player should display the Game-day ledger of the player but not lead away from the game-day detail - maybe a back function or drawer*
    

**Game-day ledger** *(display the ledger - without date, because already in header/title - below the summary)*

**Player Game-day ledger**

*Game-day ledger for a given player*

**WWI 7 (Marco)
Game-day 12
Wednesday, June 12, 2026**

Balance: ₦-200,000 *(styled appropriately)*

*Except that the date column might not be necessary here because it will likely be the heading of the page - along with the player profile details.*

**Player**

- Players
    
    **List of all players**
    
    | Player | Name | Balance |
    | --- | --- | --- |
    | WWI 1 | Lewis | 0 |
    | WWI 2 | Mark | 1,000,000 |
    | WWI n | Patrick | -500,000 |
    - Clicking any player should display the player detail
    
    **Player detail** 
    
    Player: WWI 8
    Name: Teeto
    Balance: -550,000
    
    **Player Game-day history** (days player played)
    
    | Date | Game-day # | Balance |
    | --- | --- | --- |
    | 01/04/26 | 21 | -350,000 |
    | 04/04/26 | 56 | -1,200,000 |
    | 02/05/26 | 87 | 0 |
    
    **Player Game-day (actual)**
    
    **Owner credit/write-offs**
    
    *The following are credits/debt write-off amounts given by the Owner*
    
    | Date | Amount | Reason |
    | --- | --- | --- |
    | 14/05/26 | 1,000,000 | Received $700 |
    |  |  |  |
    
    Balance after game day
    
    Payments after game day
    
    Deals after game day
    

### Owner experience

Paying a player

**View**

- Balance of funds in main account at all times
- ~~List of last x deposits~~
- List of players for the day and amount outstanding
- History of approvals (and transfers)
- History of transfers
- History of player forgiveness

**Actions**

- Initiate transfers
- Approve transfers
- Add player balance (can only add, not subtract i.e. can only reduce player debt, but can’t add) *-* via app or whatsapp
    - Player
    - Amount
    - Reason

### Others

#### Notifications

- Email
- Whatsapp
- Web app
- Mobile app (if available)
- Cashier
    - Channel:

#### Activity tracking

#### Authentication / login

- What happens if a player’s transfer to their DVA fails
- If DVA to main account transfer fails
- If there isn’t enough funds in the main account to transfer winnings
- This of other transfer areas and what should happen if they fail
- Let players know that if they want instant crediting, they should pay by transfer to the bank account

| Date | Chips | Payment | Channel / Mode | Balance | Notes |  |
| --- | --- | --- | --- | --- | --- | --- |
|  | 500000 | - | Cashier | -500000 | Chips out |  |
|  | - | 700000 | DVA | 200000 | Player deposit  |  |
|  | 2000000 | - | Cashier | -1800000 | Chips out |  |
|  | - | 500000 | Chips | -1300000 | Chips in |  |
|  | - | 100000 | Cash | -1,200,000 | Player deposit |  |
|  | - | 1000000 | Owner | -200,000 | Owner |  |

How to reverse mistakes? Do this later

