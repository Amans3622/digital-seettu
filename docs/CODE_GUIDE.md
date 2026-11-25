# Digital Seettu — Code Guide

This document explains **how the system is built**, file by file, so you can answer questions
about any part of it during the evaluation. Read it once end-to-end, then use the Q&A section
at the end for rehearsal.

---

## 1. Big picture

```
Browser (HTML + CSS + JavaScript)
        │  HTTP request / fetch (JSON)
        ▼
Flask application (app.py)
  ├── auth.py        → login, register, logout, guards
  ├── dashboard.py   → dashboard, join by code, reminders
  └── groups.py      → group setup, payments, payouts, report, CSV
        │  calls Python functions
        ▼
services.py  (business logic)
        │  uses query()/execute()
        ▼
db.py  → mysql-connector-python → MySQL database "digital_seettu"
        │
        ▼
Jinja2 templates + static CSS/JS produce the page
```

The design follows a simple layered pattern:

1. **Routes** (`auth.py`, `dashboard.py`, `groups.py`) read the request, check permissions,
   and call services. They never build SQL strings with user input.
2. **Services** (`services.py`) hold every business rule and all SQL. Each function does one job.
3. **Database helpers** (`db.py`) give every request one connection and two helpers:
   `query()` for SELECT and `execute()` for INSERT/UPDATE/DELETE.
4. **Templates** only display data. Any calculation that matters (money totals, statuses,
   permissions) is done in Python/SQL, not in JavaScript.

---

## 2. How a request flows (two examples)

### Example A — opening the group page

1. Browser requests `GET /groups/<id>` (for example the group id printed in its card link).
2. `groups.detail()` runs. `@login_required` first checks the session and that the user still exists.
3. `_load_access(<id>)` loads the group, checks that the current user is the organiser or a member,
   otherwise returns 403.
4. `services.list_group_members`, `summary_for_group`, `schedule_for_group`, `ledger_for_group`
   run their SQL.
5. The route renders `templates/groups/detail.html` with that data.
6. Jinja filters (`money`, `datefmt`) format values while the page is generated.

### Example B — pressing "Mark paid" (AJAX)

1. `static/js/main.js` intercepts the form submit and sends
   `POST /groups/3/payments/17/mark-paid` with `X-Requested-With: fetch` and the chosen method.
2. `groups._set_payment()` checks access, that the group is active and that the payment belongs to
   this group.
3. `services.mark_payment()` updates the row, recalculates the round and group status, and returns
   the payment, round and fresh summary.
4. The route sees the `X-Requested-With` header and returns **JSON** instead of redirecting:
   `{ok, payment, round, summary, group_status}`.
5. JavaScript updates the badge, date, method, round count, totals and progress bar using
   `textContent`, and shows a toast.
6. If this payment completed the round, JS reloads the page after a moment so the
   **Release payout** button is rendered.

If JavaScript is disabled, the same form posts normally: the server flashes a message and
redirects. The feature works either way.

---

## 3. Files explained

### `app.py` — application factory and shared behaviour

- `create_app()` builds the Flask app, loads `Config`, registers the three blueprints
  (`auth`, `dashboard`, `groups`), and configures the session cookie
  (`HttpOnly`, `SameSite=Lax`).
- `@app.teardown_appcontext(db.close_db)` closes the MySQL connection at the end of every request.
- **Template filters** used by the HTML:
  - `money` → `Rs. 1,250.00`
  - `datefmt` → `25 Nov 2026` (or `—` when empty)
  - `frequency` → "Every week", "Every two weeks", "Every month"
  - `initials` → "SB" for Sandunika Bandara (avatar circles)
- **Context processor** injects `current_user`, `unread_reminders`, `today` and `reminder_days`
  into every template, so the header can show the user's name/avatar and the reminder badge.
- **Error handlers**: friendly 403, 404 and 500 pages, plus a special handler for
  `mysql.connector.Error` that returns a 503 page telling the user to start MySQL in XAMPP.
- The last line runs the development server on port 5000 with `debug=True`.

### `config.py` — settings from `.env`

Loads `.env` with `python-dotenv` and exposes a `Config` class: database host/port/user/password/name,
`SECRET_KEY`, `REMINDER_DAYS`, and optional SMTP settings. Defaults match XAMPP
(`root`, empty password, port 3306). `SECRET_KEY` signs the session cookie, so it must be secret
and long.

### `db.py` — one connection per request

```python
def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(..., autocommit=False)
    return g.db
```

- Flask's `g` object lives for one request; the connection is reused inside that request and
  closed in `close_db`.
- `query(sql, params, one=False)` uses a **dictionary cursor**, so rows behave like
  `row["full_name"]` instead of tuples. All values are passed as parameters (`%s`), never
  glued into the SQL string.
- `execute(sql, params)` commits on success and rolls back on error; it returns
  `lastrowid`, which is how a new user or group id is obtained.

### `auth.py` — accounts and guards

- `login_required` — redirects to `/login` when there is no session, and also clears the session
  if the stored `user_id` no longer exists (for example after a database reset). Without this,
  a stale cookie would crash pages that expect a user row.
- `organiser_required` — aborts with 403 unless the logged-in user's role is `organiser`.
- `/register` — validates name length, email format (regex), role value, password length and
  confirmation, and duplicate email. On success: creates the user, clears the session,
  stores `user_id`, flashes a welcome message.
  Passwords are stored with `werkzeug.security.generate_password_hash` — a salted, intentionally
  slow hash (scrypt in Werkzeug 3), never plain text.
- `/login` — looks up the email and verifies with `check_password_hash`.
  The error message never reveals whether the email or the password was wrong.
- `/logout` — POST only, clears the session.

### `dashboard.py` — role-aware home page

- `/dashboard` — loads the user's groups (organiser or member), calls `organiser_stats` or
  `member_stats`, the latest four reminders, and the six most urgent due payments for organisers.
- `/join` (POST) — finds a group by invite code and calls `services.join_group`, which enforces
  the rules: group must be draft, user must not already be a member, organiser cannot join their
  own group.
- `/reminders` — member inbox + organiser "due and overdue" table.
- `/reminders/run` (POST, organiser only) — creates reminders for one group (if `group_id` is sent)
  or all active groups owned by the organiser. `services.create_reminders` skips payments that
  already have a reminder today.
- `/reminders/read` (POST) — marks the current user's reminders as read.

### `groups.py` — the largest route file

Helpers:

- `_load_access(group_id)` — loads the group or 404, finds the user's membership, and aborts 403
  if the user is neither the organiser nor a member. Every group route starts here.
- `_require_manager(group, is_organiser, draft_only=False)` — only the organiser may continue;
  some actions (add/remove member, turn order, start, delete) are also limited to drafts.
- `_wants_json()` — true when the request has `X-Requested-With: fetch` or asks for JSON.
- `_payment_display(payment)` — returns (label, badge class): Paid / Overdue / Pending.

Routes:

| Route | Purpose |
| --- | --- |
| `GET/POST /groups/new` | Validate and create a group (server-side validation, Decimal money parsing) |
| `GET /groups/<id>` | Group page: members, summary, schedule, ledger, member view |
| `POST /groups/<id>/members` | Add a registered member by email (draft only) |
| `POST /groups/<id>/members/<mid>/remove` | Remove a member (draft only) |
| `POST /groups/<id>/turn-order` | Save turn numbers (draft only) |
| `POST /groups/<id>/start` | Generate rounds + payments and activate (draft only) |
| `POST /groups/<id>/delete` | Delete a draft group |
| `POST /groups/<id>/leave` | A member leaves a draft group |
| `POST /groups/<id>/payments/<pid>/mark-paid` | Record a payment |
| `POST /groups/<id>/payments/<pid>/mark-pending` | Undo a payment |
| `POST /groups/<id>/rounds/<rid>/payout` | Release the payout for a completed round |
| `GET /groups/<id>/report` | Report page (organiser only) |
| `GET /groups/<id>/report.csv` | CSV download (organiser only) |

`_set_payment()` is shared by mark-paid and mark-pending. It:

1. checks access and that the group is active,
2. verifies the payment belongs to this group (otherwise 404),
3. calls `services.mark_payment`,
4. returns JSON for the AJAX path, or flashes + redirects for the normal form path.

### `services.py` — business logic

Grouped into sections:

- **users** — `get_user`, `user_by_email`, `create_user`
- **groups** — `get_group`, `new_invite_code`, `create_group`, `group_by_invite_code`,
  `groups_for_user`
- **members** — `list_group_members`, `membership`, `add_member_by_email`, `remove_member`,
  `join_group`, `save_turn_orders`, `start_group`, `delete_group`
- **dates** — `add_months` (handles 31 Jan + 1 month → 28/29 Feb), `add_interval`, `days_until`
- **schedules and summaries** — `schedule_for_group`, `ledger_for_group`, `summary_for_group`,
  `member_summary`
- **payments** — `mark_payment`, `refresh_round_status`, `refresh_group_status`, `mark_payout`
- **reports** — `member_totals`
- **dashboard stats** — `organiser_stats`, `member_stats`
- **reminders** — `reminder_candidates`, `create_reminders`, `send_email_message`,
  `reminders_for_user`, `unread_reminder_count`, `mark_reminders_read`, `due_payments_ledger`

Key rules inside services:

- `groups_for_user` uses a `LEFT JOIN` on membership so it returns both groups the user organises
  and groups the user joined. Correlated subqueries add member count, round count, paid counts
  and the next due date for the group and for the user personally.
- `add_member_by_email` rejects unknown emails, the organiser, and duplicates.
- `save_turn_orders` validates positive unique numbers and updates all rows inside **one
  transaction**, so a failure cannot leave half the members re-numbered.
- `start_group` also uses a transaction: all rounds and all payments are created, or none.
- `mark_payment` refuses to undo a payment whose round already has a `payout_date`.
- `mark_payout` refuses unless the round is `completed` and has no payout yet.
- After every payment change: `refresh_round_status` sets the round completed/pending, then
  `refresh_group_status` sets the group active/completed.

### `templates/`

Jinja2 HTML. `base.html` has the header (logo, nav, reminder badge, avatar, mobile menu),
the flash stack, the footer, the toast element and `main.js`.
Pages extend it with `{% extends "base.html" %}`.

- `index.html` — public landing page (hero photo with floating status chips, illustrated
  three-step "how it works", feature list, roles and call to action). Images live in
  `static/img/` and are referenced with `url_for('static', ...)`.
- `dashboard.html` — branches on `is_organiser` for stat cards and tables.
- `groups/detail.html` — three states: draft setup (organiser), active organiser view, active
  member view. It carries the `data-*` attributes that JavaScript uses:
  `data-payment-id`, `data-round-id`, `data-round-row`, `data-payment-form`,
  `data-ledger-search`, `js-collected`, `js-progress-bar`, etc.
- `groups/report.html`, `reminders.html`, `auth/*.html`, `errors/error.html`.

Jinja **autoescapes** all variables by default, so user-entered text (names, descriptions) cannot
inject HTML.

### `static/css/style.css`

One stylesheet with:

- CSS variables for the colour palette (cream background, teal primary, gold accent, red for
  overdue), spacing and radii;
- reusable components: buttons, cards, badges, stat cards, tables, forms, flash messages, toast,
  landing sections;
- responsive breakpoints at 1100, 900, 720 and 520 px;
- on small screens tables scroll horizontally with a **sticky last column** (the action buttons),
  and a "swipe" hint appears;
- `@media print` rules for the report page (hide navigation and buttons).

### `static/js/main.js`

Vanilla JavaScript in one IIFE (`"use strict"`), initialised on `DOMContentLoaded`:

1. mobile menu toggle (closes on outside click, Escape, or link click),
2. password show/hide,
3. auto-dismiss flash messages (7 s),
4. copy invite code to clipboard (with fallback for non-secure contexts),
5. confirmation dialogs for forms with `data-confirm` (Undo, delete, payout),
6. **Auto-number** button for turn inputs,
7. print button,
8. registration password match check,
9. ledger search + round/status filters (reads `data-search`, `data-round`, `data-status`),
10. **AJAX payment forms**: disables the button, posts `FormData` with the custom header,
    updates rows and summary, shows a toast; reloads only when a round becomes complete/payout
    state changes.

It updates the DOM with `textContent` and class names — never `innerHTML` — which avoids XSS.

### `database/schema.sql`

Creates the database (utf8mb4) and the six tables. It **drops** the tables first, so it is a
"fresh start" script only. Engine is InnoDB so foreign keys and transactions work.

### `seed_demo.py`

Builds a realistic dataset:

1. deletes the six demo users (their groups are deleted by `ON DELETE CASCADE`),
2. recreates them with hashed passwords,
3. creates the active weekly group and five members, saves turns 1–5,
4. starts the group (5 rounds × 5 payments),
5. marks payments to create a realistic mix: round 1 complete with payout, round 2 one late payer,
   round 3 two payers, round 4 one early payer,
6. creates the day's reminders,
7. creates the "Family Circle" draft with three members and turns.

Dates are always relative to `date.today()`, so the demo never looks stale.

### `send_reminders.py`

Command-line job: parses `--days`, `--group`, `--email`, opens an app context, calls
`services.create_reminders` for one group or for every active group in the database, and prints
a one-line result.
Designed to be run daily by Task Scheduler. Without `--email` it only creates in-app reminders.

---

## 4. Database design

Six tables, all InnoDB, all relationships enforced by foreign keys.

### `users`

| Column | Type | Notes |
| --- | --- | --- |
| id | INT PK AI | |
| full_name | VARCHAR(100) | |
| email | VARCHAR(120) UNIQUE | login identifier |
| phone | VARCHAR(25) NULL | optional |
| password_hash | VARCHAR(255) | salted hash, never plain text |
| role | ENUM('organiser','member') | chosen at registration |
| created_at | DATETIME | default now |

### `seettu_groups`

| Column | Notes |
| --- | --- |
| organiser_id | FK → users, `ON DELETE CASCADE` |
| contribution_amount | DECIMAL(12,2) — exact money, not float |
| frequency | ENUM weekly / biweekly / monthly |
| start_date | first round's due date |
| invite_code | CHAR(6), UNIQUE |
| status | ENUM draft / active / completed |

### `group_members`

Join table between users and groups. `turn_order` is NULL until the organiser assigns it.
Two unique keys prevent abuse:

- `(group_id, user_id)` — the same person cannot be added twice,
- `(group_id, turn_order)` — two members cannot share a turn.

Both FKs cascade: deleting a group or a user removes the membership.

### `rounds`

One row per payout round.

| Column | Notes |
| --- | --- |
| group_id | FK → seettu_groups |
| round_no | 1..N, UNIQUE per group |
| due_date | start_date + (round_no − 1) × frequency |
| beneficiary_member | FK → group_members — who receives the pot |
| status | pending / completed |
| payout_date | NULL until released |

### `payments`

One row per member per round.

| Column | Notes |
| --- | --- |
| round_id | FK → rounds |
| member_id | FK → group_members |
| amount | DECIMAL(12,2) copied from the group at start time |
| status | pending / paid |
| paid_date, method, notes | filled when paid |
| recorded_by | FK → users, `SET NULL` if that user is deleted |
| UNIQUE(round_id, member_id) | one payment per member per round |

Notice that **overdue is not a stored status**: it is computed as
"pending AND due_date < today" whenever data is read. This keeps it correct without a cron job.

### `reminders`

| Column | Notes |
| --- | --- |
| payment_id, member_id | FKs, cascade |
| message | text shown in the inbox |
| channel | in_app (email is optional and not stored per row) |
| is_read | 0/1 |
| sent_date | date the reminder was created |
| UNIQUE(payment_id, sent_date) | **at most one reminder per payment per day** |

### Relationship diagram

```
users 1 ──< seettu_groups   (organiser)
users 1 ──< group_members >── 1 seettu_groups
group_members 1 ──< rounds  (beneficiary)
rounds 1 ──< payments >── 1 group_members
payments 1 ──< reminders
```

### Group status lifecycle

```
draft ──(organiser presses Start)──► active ──(all rounds completed)──► completed
```

Round status: `pending → completed` when all its payments are paid.
Payment status: `pending ↔ paid` (undo allowed until the payout is recorded).

---

## 5. The rotation algorithm (most likely viva topic)

**Inputs:** contribution `C`, members with turns `1..N`, frequency `F`, start date `S`.

**On Start:**

```
for turn = 1..N:
    due_date = add_interval(S, F, turn - 1)
    create round(round_no=turn, due_date, beneficiary=member with turn)
    for every member:
        create payment(round, member, amount=C, status=pending)
set group.status = active
```

**Example:** C = 5,000; N = 5; weekly; S = 4 Nov 2026.

| Round | Due date | Beneficiary | Pot | Payments created |
| --- | --- | --- | --- | --- |
| 1 | 04 Nov | Turn 1 (Sandunika) | 25,000 | 5 × 5,000 |
| 2 | 11 Nov | Turn 2 (Kasun) | 25,000 | 5 × 5,000 |
| 3 | 18 Nov | Turn 3 (Amara) | 25,000 | 5 × 5,000 |
| 4 | 25 Nov | Turn 4 (Dilshan) | 25,000 | 5 × 5,000 |
| 5 | 02 Dec | Turn 5 (Tharindu) | 25,000 | 5 × 5,000 |

Expected collection for the whole rotation = 25 payments × 5,000 = **125,000**.
Each member pays 25,000 in total and receives a 25,000 pot once — the point of a seettu.

`add_months` handles month ends correctly (31 Jan + 1 month → 28/29 Feb), which naive
"add 30 days" logic would get wrong.

Everything is created up front so members can see the full schedule and their pending balance
from day one. Payments reference the membership, so the rotation survives even if a user changes
their name or email.

---

## 6. Money, totals and overdue calculations

- Money is stored as `DECIMAL(12,2)` and handled as Python `Decimal` on input.
  JavaScript only formats numbers for display.
- `summary_for_group` returns: member count, round count, rounds completed, payouts done,
  collected, pending, overdue, paid count, total count. It also derives:
  - `pot = contribution × member count`
  - `expected = pot × round count`
  - `collected_pct = collected / expected × 100`
- `member_totals` groups payments per member with
  `SUM(CASE WHEN status='paid' THEN amount ELSE 0 END)` and similar expressions for pending
  and overdue. This single query powers the report's member summary.
- **Overdue** always uses `due_date < CURDATE()` in SQL, so it follows the database clock.

---

## 7. Reminder engine

`services.reminder_candidates(group_ids, days)` selects pending payments whose round is due within
`days` days **or already overdue**:

```sql
WHERE p.status = 'pending'
  AND r.due_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
  AND g.id IN (...)
```

`create_reminders` then, for each candidate:

1. checks whether a reminder already exists for `(payment_id, today)` — if yes, skip,
2. inserts an in-app reminder with a human message ("Reminder: … due on 25 Nov 2026" or
   "Overdue: … was due on 18 Nov 2026"),
3. optionally sends an email when SMTP is configured and `send_email=True`.

The database unique key is the real protection against duplicates; the SELECT check just avoids
a wasted insert. If email sending fails, the error is logged and the in-app reminder still exists.

Automation paths:

- UI button → `/reminders/run` → same service,
- CLI → `python send_reminders.py [--days N] [--group ID] [--email]`,
- Windows Task Scheduler runs the CLI daily.

---

## 8. Reports and CSV

`/groups/<id>/report` is organiser-only. It uses `summary_for_group`, `member_totals` and
`schedule_for_group`.

`/groups/<id>/report.csv` builds the file in memory with Python's `csv` module:

1. header block (group, organiser, contribution, frequency, dates, expected/collected/pending/overdue),
2. member summary table,
3. round schedule table.

Amounts are written as `"%.2f"` strings. The response is prefixed with a UTF-8 BOM (`\ufeff`)
so Excel recognises the encoding, and `Content-Disposition` makes the browser download it
with a safe slugged filename.

---

## 9. Security choices

| Concern | How it is handled |
| --- | --- |
| Password storage | `generate_password_hash` / `check_password_hash` (salted, slow hash) |
| Session tampering | Flask signed cookie using `SECRET_KEY`; `HttpOnly` and `SameSite=Lax` |
| SQL injection | Every value uses `%s` parameters through mysql-connector; no string concatenation with user input |
| XSS | Jinja autoescaping; JS writes with `textContent`, never `innerHTML` |
| Authorization | `login_required` on every private route; `_load_access` checks organiser/member; organiser-only actions re-checked server-side; members get 403 on report and payment endpoints |
| Mass assignment | Forms read only expected fields |
| Duplicate/invalid data | DB unique keys + service-level validation (turn numbers, duplicates, payout state) |
| CSRF | State-changing actions are POST-only; session cookie is `SameSite=Lax`; AJAX endpoints require a custom `X-Requested-With` header (cross-site forms cannot send it and the app enables no CORS). A token-based CSRF system (e.g. Flask-WTF) is a known improvement, not included in this project scope |
| Information leaks | Login error does not reveal whether the email exists; password hashes never sent to templates |

---

## 10. Manual test checklist

Use this to show the system is tested, not just written:

- [ ] Register with a short password → rejected; mismatched passwords → rejected; duplicate email → rejected.
- [ ] Register a valid member → automatically logged in → empty-state dashboard.
- [ ] Organiser creates a group with a past start date → rejected; with valid data → draft + invite code.
- [ ] Add an unregistered email → friendly error; add organiser's own email → rejected; add twice → rejected.
- [ ] Save duplicate turn numbers → rejected; **Auto-number** then save → success.
- [ ] Start with one member → rejected; with complete turns → rounds and payments created.
- [ ] Member tries to open the report URL → 403 page; member tries to mark a payment → cannot see the control and POST is rejected.
- [ ] Mark a payment paid as organiser → live update of row, round, totals and progress.
- [ ] Undo a normal payment → allowed; undo after payout → blocked with a message.
- [ ] Release payout before the round is complete → blocked; after complete → allowed.
- [ ] Complete every round → group status becomes completed.
- [ ] Ledger search "amara", round filter, status filter → correct rows only.
- [ ] Join with an invalid code → error; join an active group → error; join a draft → success; leave draft → success.
- [ ] Send reminders twice in one day → second time reports "already sent today".
- [ ] CSV opens in Excel with correct columns and two-decimal amounts.
- [ ] 404 page for a missing group; 503 page when MySQL is stopped (optional demo).
- [ ] Resize the browser to phone width → tables scroll, menu collapses.

---

## 11. Likely viva questions and short answers

**Q: What is a seettu?**
A traditional rotating savings group: every member contributes a fixed amount each round, and one
member receives the whole pot each round, in an agreed order.

**Q: Why Flask and not Django/Java?**
Flask is lightweight and explicit: routes, templates and services stay small and easy to explain.
The proposal allowed a web-based system; Python + Flask kept the code short and readable.
The database is MySQL, matching the relational model.

**Q: How do you know whose turn it is?**
Each member has a `turn_order` in `group_members`. When the group starts, one `round` is created
per member in that order; the round stores `beneficiary_member`.

**Q: Why create all rounds and payments at the start?**
So every member immediately sees the full schedule, amounts and pending totals, and so overdue
calculations and reports work at any point without generating data on the fly.

**Q: How is the pot calculated?**
`contribution_amount × number of members` (computed in `summary_for_group`). Expected total for
the whole rotation is that pot × number of rounds.

**Q: How is "overdue" determined?**
It is not stored. A payment is overdue when `status = 'pending' AND round.due_date < CURDATE()`.
This is always correct and needs no scheduled job.

**Q: What prevents a member being charged twice in a round?**
`UNIQUE(round_id, member_id)` on `payments`, plus the fact that payments are generated exactly once
when the group starts.

**Q: What prevents two members having turn 3?**
Service validation in `save_turn_orders` plus `UNIQUE(group_id, turn_order)` in the database.

**Q: What happens when a member leaves mid-rotation?**
They cannot. Leaving and member removal are allowed only while the group is a draft. After the
rotation starts, the membership list is locked to protect the schedule.

**Q: How does a payout work?**
When every payment in a round is paid, the organiser presses **Release payout**; `mark_payout`
checks the round is completed and not already paid out, then stores today's date. A group becomes
completed when all rounds are completed.

**Q: Why can't a payment be undone after payout?**
The payout would have been given based on collected money; allowing undo would corrupt the record.
`mark_payment` raises an error when `round.payout_date` is set.

**Q: How are passwords protected?**
Salted, slow hashes (Werkzeug `generate_password_hash`, scrypt by default). Plain passwords are
never stored, logged or displayed.

**Q: How do you prevent SQL injection?**
All queries use parameter placeholders `%s` via mysql-connector. The only f-string in SQL builds
a list of `%s` placeholders from the number of group ids, not from user text.

**Q: How do you prevent XSS?**
Jinja autoescapes template output, and the JavaScript updates text with `textContent`.
User-generated names and descriptions therefore render as text, not HTML.

**Q: How do you handle CSRF?**
Private actions are POST-only and the session cookie is `SameSite=Lax`. AJAX calls also require a
custom `X-Requested-With` header, which cross-site forms cannot send, and CORS is not enabled.
A per-form CSRF token would be the next hardening step.

**Q: How do members only see their own groups?**
`_load_access` checks the user is the organiser or a member; `groups_for_user` only selects groups
where the user is organiser or joined. Other groups return 403.

**Q: How are reminders automated?**
`send_reminders.py` runs the same service as the UI button. Task Scheduler runs it daily.
The unique key `(payment_id, sent_date)` prevents duplicate reminders. Email is optional via SMTP.

**Q: How is money stored and formatted?**
`DECIMAL(12,2)` in MySQL, `Decimal` on input, formatted as `Rs. 1,250.00` by the `money` filter.

**Q: Why six tables?**
They separate identity (users), configuration (groups), participation (members), schedule (rounds),
transactions (payments) and notifications (reminders). Each table has one clear responsibility, and
foreign keys keep them consistent.

**Q: How would you add online payments?**
Add a payment-gateway integration; a webhook would update the `payments` row to paid. It was
explicitly out of scope in the proposal, where payments are recorded manually after cash/bank
transfers.

**Q: How would you deploy this for real?**
Use a production WSGI server (waitress/gunicorn) instead of `debug=True`, a dedicated MySQL user
with a strong password, HTTPS, environment-based secrets, and backups. The current server is the
Flask development server, suitable for the demo.

**Q: What was the hardest part?**
Keeping the rotation consistent: generating rounds/payments transactionally, avoiding duplicate
turn numbers, keeping round and group statuses in sync after every payment, and blocking edits
after payout.

**Q: What would you improve next?**
CSRF tokens, email verification, password reset, profile editing, per-group organiser notes,
partial payments, SMS reminders, an audit log, and unit tests with pytest.

---

## 12. Glossary

| Term | Meaning in this project |
| --- | --- |
| Seettu | Rotating savings group (also called a "chit" or "committee") |
| Round | One collection cycle; one member receives the pot |
| Pot | Total collected in a round = contribution × members |
| Beneficiary | Member who receives the pot in a round |
| Turn order | The sequence in which members receive the pot |
| Draft | Group being configured; rounds do not exist yet |
| Active | Rotation running; payments can be recorded |
| Completed | All rounds finished |
| Overdue | Pending payment whose round due date has passed |
| Payout | Money handed to the round's beneficiary, recorded by the organiser |
