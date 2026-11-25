# Digital Seettu — User Guide

This guide explains every screen of the application and ends with a ready-made script for the
evaluation day. It assumes the app is already installed and running (see the main README).

---

## 1. The two roles

| Role | Can do | Cannot do |
| --- | --- | --- |
| **Organiser** | Create groups, add members, assign turns, start the rotation, record payments, release payouts, send reminders, download reports | Join a group as a member |
| **Member** | Join a draft group with an invite code, view the schedule, ledger and reminders | Change payments, members, turns or payouts |

Every account is created with one role, chosen at registration. An organiser manages the groups
they create and may also join another organiser's draft group as a member. A member joins groups
with invite codes. Only a group's organiser and its members can open that group page — anyone else
gets the "Access denied" page.

---

## 2. Registering and logging in

### Create an account

1. Open <http://127.0.0.1:5000> and click **Create an account** (or **Get started**).
2. Fill in:
   - **Full name** (at least 3 characters)
   - **Email address** (must be unique; used to identify you when an organiser adds you)
   - **Mobile number** (optional)
   - **How will you use Seettu?** — choose **Organiser** or **Member**
   - **Password** (at least 8 characters) and **Confirm password**
3. Click **Create account**. You are logged in automatically and taken to your dashboard.

If the two passwords do not match, a toast message appears and the browser highlights the field.
Email format, duplicates and password length are also checked on the server.

### Log in

1. Click **Log in**, enter your email and password, then press **Log in**.
2. Use the **eye icon** beside the password to show/hide what you typed.
3. The **Log out** button is in the header menu.

---

## 3. Organiser walkthrough

### 3.1 Dashboard

After logging in as an organiser (`nimal@seettu.lk` in the demo) you see:

- **Active groups / Collected / Overdue / People** statistic cards.
- **Needs attention** — every pending payment that is due within the reminder window or already overdue,
  with a **Send reminders** button.
- **Your groups** — a card per group: contribution, member count, rounds, payment progress bar,
  next/overdue date, and the invite code for drafts.
- **Have an invite code?** — join another organiser's draft group as a member.
  You cannot join a group that you organise yourself.
- **Your inbox** — the latest reminder messages sent to you (only relevant if you are a member elsewhere).

### 3.2 Create a group

1. Click **New group**.
2. Enter:
   - **Group name** (3–100 characters)
   - **Description** (optional, up to 255 characters)
   - **Contribution amount** — what each member pays every round (e.g. `5000`)
   - **Frequency** — every week, every two weeks, or every month
   - **Start date** — today or a future date (past dates are rejected)
3. Click **Create group**.

The group is created in **Draft** status and a random six-character **invite code** is generated
(for example `GVAJT8`). The code is shown in a success message and on the group page.

### 3.3 Finish the draft setup

Open the draft group. The page has two steps.

**Step 1 — Members and turn order**

- Type a registered member's **email** and press **Add member**.
  The person must already have a Digital Seettu account; the organiser cannot be added to their own group.
- Every member gets a row. Type a **turn number** in the input beside each member.
  Turn 1 receives the pot in round 1, turn 2 in round 2, and so on.
- Use **Auto-number 1–N** to fill the inputs in the current order, then press **Save turn order**.
  Turn numbers must be unique and positive.
- The **invite code** card lets you copy the code. While the group is a draft, members can join
  themselves from their dashboard with that code. You can still add them manually by email.
- Remove a member with the **Remove** button (drafts only). A member can also leave on their own.

**Step 2 — Start the rotation**

The checklist explains what must be true:

- at least 2 members,
- every member has a turn number from 1 to N.

Press **Start group**. The system then, in one database transaction:

1. creates one **round** per member (in turn order) with due dates spaced by the frequency,
2. creates one **payment** per member per round,
3. changes the group status to **Active**.

Example: 5 members and a weekly group starting 4 November → 5 rounds due 4 Nov, 11 Nov,
18 Nov, 25 Nov, 2 Dec, and 25 payment records of Rs. 5,000 each.

After starting, members and turn order lock. **Delete draft** is only available while the group
is still a draft.

### 3.4 Run an active group

The active group page shows:

- **Members / Contribution / Pot per round / Collected** cards.
  Pot per round = contribution × number of members.
- **Collection progress** — collected vs expected, payments recorded, rounds complete,
  percentage bar, pending and overdue totals.
- **Rounds and payouts** — one row per round:
  due date, beneficiary, pot, paid count (e.g. `4/5`), status, and payout information.
  When a round reaches `5/5`, a **Release payout** button appears for the organiser.
  "LATE" marks a round whose due date has passed while payments are still missing.
- **Turn order** — table of members, their turn number and payout round, and
  "Paid out / Ready for payout / Collecting".
- **Payment ledger** — all payments, with search and two filters:
  - search matches member name, email or "round 3",
  - **All rounds** filter,
  - **All statuses** filter (Paid / Pending / Overdue).
  Every member can read this ledger; only the organiser sees the **Action** column.

### 3.5 Record a payment

In the ledger, find the payment, choose the method (**Cash**, **Bank**, **Other**) and click
**Mark paid**. The page updates instantly (no reload):

- the row badge changes to **Paid** and the paid date/method appear,
- the round's `paid/total` count and status update,
- the summary cards, progress bar and overdue counts update.

If finishing this payment completes the round, the page refreshes after a moment so the
**Release payout** button is rendered correctly.

**Undo** sets a payment back to pending. It is blocked after the round's payout has been recorded,
because undoing a paid-out round would break the accounts.

### 3.6 Release a payout

When every payment in a round is paid, press **Release payout** on that round row and confirm.
Today's date is stored as the payout date. The group becomes **Completed** automatically when
every round is completed.

### 3.7 Send reminders

There are three places to trigger reminders:

- **Send reminders** on the dashboard,
- **Send reminders for all my groups** on the reminders page,
- **Remind group** next to a specific group on the reminders page,
- **Send reminders** on a group page (sends for that group only).

A payment is in the reminder window when its due date is within the next `REMINDER_DAYS` days
(3 by default) or already passed. Each payment receives at most **one reminder per day**.
The flash message tells you how many reminders were created, or that they were already sent today.

The reminders page also shows the exact command used for daily automation
(`python send_reminders.py`, see README section 8).

### 3.8 Report and CSV

Open a group → **Report**:

- **Expected total** — contribution × members × rounds.
- **Collected / Pending / Overdue** — from the recorded payments.
- **Overall collection** — rounds complete and percentage.
- **Member summary — Who has paid what** — per member: paid/total payments, paid amount,
  pending amount, overdue amount, progress bar.
- **Round schedule — Collection and payout history** — one row per round with payout date.

**Download CSV** saves a file such as `seettu-report-office-savers-batch-24.csv` containing the
group summary, the member summary and the round schedule. It is UTF-8 with a BOM so Excel opens
it correctly, and amounts use two decimal places. **Print** opens the browser print dialog with a
clean print layout.

---

## 4. Member walkthrough

### 4.1 Join a group

Members join with the six-character **invite code** the organiser shares.

1. Ask the organiser for the code (it is on the draft group page and the organiser's dashboard).
2. On the member dashboard, use **Have an invite code?** → type the code → **Join group**.
3. You are taken to the group page, which shows "The organiser is setting up this group"
   and "Your turn: not assigned yet".
4. The organiser assigns your turn and starts the group.

Rules:

- The group must still be in **draft**.
- You must be logged in with a registered account.
- You cannot join the same group twice, and an organiser cannot join their own group.
- You can **Leave group** while it is still a draft.

### 4.2 Dashboard

The member dashboard shows:

- **Groups joined / Paid so far / Still to pay / Next payment** cards.
- Your group cards, including **"Your turn: round N"**.
- **Your inbox** — recent reminders, with a link to **View all**.
- The join-by-code form.

### 4.3 Group page (read-only)

Members see the same schedule, turn table and ledger as the organiser, but:

- no **Mark paid / Undo / Release payout / Report / Send reminders** controls,
- a **Your position** card showing the paid total, pending total and next due payment,
- a **My payments** button that scrolls to the ledger,
- a **YOU** tag on their own rows.

The ledger search and filters still work for members.

### 4.4 Reminders inbox

Open **Reminders** in the header menu:

- **Your inbox** lists every reminder with the message, group, round, due date, sent date and
  whether the payment is still pending.
- **Mark all as read** clears the red unread counter in the header.

Reminders are created by the organiser's **Send reminders** action or by the daily
`send_reminders.py` job. Members never create reminders themselves.

---

## 5. Evaluation-day demo script (about 7 minutes)

> Reset first: run `python seed_demo.py`, then start the server and open a private/incognito window.

**0:00 — Landing page (30 s)**
"Our project digitises a seettu. The proposal asked for six modules: users, groups, members,
payments, reminders and reports. This is a Flask + MySQL application with HTML, CSS and JavaScript."

**0:30 — Organiser login (30 s)**
Log in as `nimal@seettu.lk` / `Seettu@123`.
Point out: collected total, overdue amount, needs-attention list, group cards, draft group.

**1:00 — Active group (2 min)**
Open **Office Savers - Batch 24**.

- Pot per round = Rs. 5,000 × 5 = Rs. 25,000.
- Round 1 is complete and paid out; round 2 is `4/5` because Tharindu has not paid; round 3 is `2/5`.
- The collection bar shows 12 of 25 payments (48%) and Rs. 20,000 overdue.
- Scroll to the ledger: search "Amara", filter by round or status.

**3:00 — Record a payment live (1 min)**
Choose **Cash** on Tharindu's round 2 payment and press **Mark paid**.
"Notice it did not reload the page — JavaScript sent the request, received JSON and updated the
row, the round count, totals and progress bar." Round 2 becomes `5/5`; the page refreshes and a
**Release payout** button appears.

**4:00 — Payout + report (1 min)**
Press **Release payout** for round 2. Then open **Report** → show the member summary and round
schedule → press **Download CSV** and open the file.
"Report module complete: summary, member history, export."

**5:00 — Reminders (30 s)**
Open **Reminders** → show due/overdue list → press **Send reminders**.
Point out the message that reminders were already sent today — duplicate protection is a database
unique key on `(payment_id, sent_date)`. Mention `send_reminders.py` + Task Scheduler for daily runs.

**5:30 — Member view (1 min)**
Log out → log in as `sandunika@seettu.lk` / `Seettu@123`.
Show: "Your turn: round 1", the read-only group page, **Your position**, and the reminder inbox.
"There is no way for a member to change payments — the server checks the role on every action."

**6:30 — Draft setup (30 s)**
Log back in as the organiser → open **Family Circle** (draft).
Show adding a member by email, **Auto-number**, **Save turn order**, the invite code and
**Start group**. (Do not start it if you want to keep the draft for a later demo.)

**7:00 — Close**
"Data is stored in six normalised MySQL tables with foreign keys. Everything you saw — turn order,
payment schedule, overdue calculations, payouts and reports — comes from those tables."

---

## 6. Resetting and changing the demo

- **Reset everything** — re-import `database/schema.sql`, then run `python seed_demo.py`.
- **Reset demo users only** — run `python seed_demo.py`. It deletes the six demo accounts
  (their groups are removed by cascade) and recreates them with fresh dates relative to today.
  Invite codes change on every run.
- **Customise demo data** — open `seed_demo.py` and edit:
  - `DEMO_USERS` (names, emails, roles),
  - the first group's contribution, frequency and start offset (`today - timedelta(days=21)`),
  - the turn order list,
  - which payments are marked paid in `mark(...)` calls.
  The demo remains realistic because due dates are always relative to today.
- **Change the demo password** — edit `PASSWORD` at the top of `seed_demo.py` and re-run it.

---

## 7. Golden rules (useful for viva questions)

- A group is **Draft** until the organiser starts it; only then are rounds and payments created.
- Members and turn order cannot change after the start — this protects the rotation.
- Payments are recorded only by the organiser, and only after the group is active.
- A payout can only be released when the round is fully paid, and payments in a paid-out round
  cannot be undone.
- **Overdue** is calculated from the due date, not stored, so it is always up to date.
- A group becomes **Completed** automatically when every round is completed.
