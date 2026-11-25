import calendar
import random
import re
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

from flask import current_app
from werkzeug.security import generate_password_hash

import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
FREQUENCIES = {
    "weekly": "Every week",
    "biweekly": "Every two weeks",
    "monthly": "Every month",
}


# ---------------------------------------------------------------- users ----

def get_user(user_id):
    return db.query(
        "SELECT id, full_name, email, phone, role, created_at FROM users WHERE id = %s",
        (user_id,),
        one=True,
    )


def user_by_email(email):
    return db.query("SELECT * FROM users WHERE email = %s", (email,), one=True)


def create_user(full_name, email, phone, password, role):
    password_hash = generate_password_hash(password)
    return db.execute(
        """INSERT INTO users (full_name, email, phone, password_hash, role)
           VALUES (%s, %s, %s, %s, %s)""",
        (full_name, email, phone, password_hash, role),
    )


# --------------------------------------------------------------- groups ----

def get_group(group_id):
    return db.query(
        """SELECT g.*, u.full_name AS organiser_name, u.email AS organiser_email
           FROM seettu_groups g
           JOIN users u ON u.id = g.organiser_id
           WHERE g.id = %s""",
        (group_id,),
        one=True,
    )


def new_invite_code():
    for _ in range(30):
        code = "".join(random.choice(INVITE_ALPHABET) for _ in range(6))
        exists = db.query(
            "SELECT id FROM seettu_groups WHERE invite_code = %s", (code,), one=True
        )
        if not exists:
            return code
    raise RuntimeError("Could not generate a unique invite code")


def create_group(organiser_id, name, contribution, frequency, start_date, description=""):
    return db.execute(
        """INSERT INTO seettu_groups
           (name, description, organiser_id, contribution_amount, frequency, start_date, invite_code)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (name, description, organiser_id, contribution, frequency, start_date, new_invite_code()),
    )


def group_by_invite_code(code):
    return db.query(
        "SELECT * FROM seettu_groups WHERE invite_code = %s", (code.upper(),), one=True
    )


def groups_for_user(user_id):
    return db.query(
        """SELECT g.*, uo.full_name AS organiser_name,
                  my.id AS my_member_id, my.turn_order AS my_turn_order,
                  (SELECT COUNT(*) FROM group_members x WHERE x.group_id = g.id) AS member_count,
                  (SELECT COUNT(*) FROM rounds r WHERE r.group_id = g.id) AS round_count,
                  (SELECT COUNT(*) FROM rounds r WHERE r.group_id = g.id AND r.status = 'completed') AS rounds_completed,
                  (SELECT COUNT(*) FROM payments p JOIN rounds r ON r.id = p.round_id
                     WHERE r.group_id = g.id AND p.status = 'paid') AS paid_count,
                  (SELECT COUNT(*) FROM payments p JOIN rounds r ON r.id = p.round_id
                     WHERE r.group_id = g.id) AS total_count,
                  (SELECT MIN(r.due_date) FROM rounds r
                     WHERE r.group_id = g.id AND r.status = 'pending') AS next_due,
                  (SELECT MIN(r.due_date) FROM rounds r
                     JOIN payments p ON p.round_id = r.id
                     JOIN group_members gm ON gm.id = p.member_id
                     WHERE r.group_id = g.id AND gm.user_id = %s AND p.status = 'pending') AS my_next_due
           FROM seettu_groups g
           JOIN users uo ON uo.id = g.organiser_id
           LEFT JOIN group_members my ON my.group_id = g.id AND my.user_id = %s
           WHERE g.organiser_id = %s OR my.id IS NOT NULL
           ORDER BY CASE g.status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                    g.created_at DESC""",
        (user_id, user_id, user_id),
    )


# -------------------------------------------------------------- members ----

def list_group_members(group_id):
    return db.query(
        """SELECT gm.id, gm.group_id, gm.user_id, gm.turn_order, gm.joined_at,
                  u.full_name, u.email, u.phone
           FROM group_members gm
           JOIN users u ON u.id = gm.user_id
           WHERE gm.group_id = %s
           ORDER BY gm.turn_order IS NULL, gm.turn_order, gm.joined_at""",
        (group_id,),
    )


def membership(group_id, user_id):
    return db.query(
        "SELECT * FROM group_members WHERE group_id = %s AND user_id = %s",
        (group_id, user_id),
        one=True,
    )


def add_member_by_email(group_id, email):
    user = user_by_email(email)
    if not user:
        raise ValueError("No registered user has that email address. Ask them to register first.")
    group = get_group(group_id)
    if user["id"] == group["organiser_id"]:
        raise ValueError("The organiser cannot also be a group member.")
    if membership(group_id, user["id"]):
        raise ValueError("That person is already in this group.")
    db.execute(
        "INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
        (group_id, user["id"]),
    )


def remove_member(group_id, member_id):
    db.execute(
        "DELETE FROM group_members WHERE id = %s AND group_id = %s",
        (member_id, group_id),
    )


def join_group(group_id, user_id):
    group = get_group(group_id)
    if group["organiser_id"] == user_id:
        raise ValueError("You already organise this group.")
    if group["status"] != "draft":
        raise ValueError("This group has already started, so new members cannot join.")
    if membership(group_id, user_id):
        raise ValueError("You are already a member of this group.")
    db.execute(
        "INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
        (group_id, user_id),
    )


def organiser_group_ids(user_id, active_only=False):
    sql = "SELECT id FROM seettu_groups WHERE organiser_id = %s"
    if active_only:
        sql += " AND status = 'active'"
    return [row["id"] for row in db.query(sql, (user_id,))]


def save_turn_orders(group_id, orders):
    """orders maps group_member.id -> turn number (or None to clear)."""
    members = {m["id"] for m in list_group_members(group_id)}
    values = [v for v in orders.values() if v is not None]
    if any(v < 1 for v in values):
        raise ValueError("Turn numbers must be positive.")
    if len(values) != len(set(values)):
        raise ValueError("Each turn number can only be used once.")
    conn = db.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE group_members SET turn_order = NULL WHERE group_id = %s", (group_id,))
        for member_id, order in orders.items():
            if member_id in members and order is not None:
                cursor.execute(
                    "UPDATE group_members SET turn_order = %s WHERE id = %s AND group_id = %s",
                    (order, member_id, group_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def start_group(group_id):
    group = get_group(group_id)
    if group["status"] != "draft":
        raise ValueError("This group has already been started.")
    members = list_group_members(group_id)
    if len(members) < 2:
        raise ValueError("Add at least two members before starting the group.")
    orders = sorted(m["turn_order"] for m in members)
    if orders != list(range(1, len(members) + 1)):
        raise ValueError("Assign every member a turn number from 1 to %d." % len(members))

    conn = db.get_db()
    cursor = conn.cursor()
    try:
        for index, member in enumerate(members, start=1):
            due = add_interval(group["start_date"], group["frequency"], index - 1)
            cursor.execute(
                """INSERT INTO rounds (group_id, round_no, due_date, beneficiary_member)
                   VALUES (%s, %s, %s, %s)""",
                (group_id, index, due, member["id"]),
            )
            round_id = cursor.lastrowid
            for payer in members:
                cursor.execute(
                    "INSERT INTO payments (round_id, member_id, amount) VALUES (%s, %s, %s)",
                    (round_id, payer["id"], group["contribution_amount"]),
                )
        cursor.execute("UPDATE seettu_groups SET status = 'active' WHERE id = %s", (group_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
    return len(members)


def delete_group(group_id):
    db.execute("DELETE FROM seettu_groups WHERE id = %s", (group_id,))


# ---------------------------------------------------------------- dates ----

def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_interval(value, frequency, steps):
    if frequency == "weekly":
        return value + timedelta(weeks=steps)
    if frequency == "biweekly":
        return value + timedelta(weeks=2 * steps)
    return add_months(value, steps)


def days_until(value):
    return (value - date.today()).days


# ------------------------------------------------------------ schedules ----

def schedule_for_group(group_id):
    return db.query(
        """SELECT r.*, gm.turn_order, u.full_name AS beneficiary_name,
                  (SELECT COUNT(*) FROM payments p WHERE p.round_id = r.id AND p.status = 'paid') AS paid_count,
                  (SELECT COUNT(*) FROM payments p WHERE p.round_id = r.id) AS total_count
           FROM rounds r
           JOIN group_members gm ON gm.id = r.beneficiary_member
           JOIN users u ON u.id = gm.user_id
           WHERE r.group_id = %s
           ORDER BY r.round_no""",
        (group_id,),
    )


def ledger_for_group(group_id):
    return db.query(
        """SELECT p.id AS payment_id, p.amount, p.status, p.paid_date, p.method, p.notes,
                  p.round_id, r.round_no, r.due_date,
                  gm.id AS member_id, gm.user_id, gm.turn_order,
                  u.full_name, u.email
           FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN group_members gm ON gm.id = p.member_id
           JOIN users u ON u.id = gm.user_id
           WHERE r.group_id = %s
           ORDER BY r.round_no, gm.turn_order, u.full_name""",
        (group_id,),
    )


def summary_for_group(group_id):
    group = get_group(group_id)
    data = db.query(
        """SELECT (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count,
                  (SELECT COUNT(*) FROM rounds WHERE group_id = g.id) AS round_count,
                  (SELECT COUNT(*) FROM rounds WHERE group_id = g.id AND status = 'completed') AS rounds_completed,
                  (SELECT COUNT(*) FROM rounds WHERE group_id = g.id AND payout_date IS NOT NULL) AS payouts_done,
                  COALESCE((SELECT SUM(p.amount) FROM payments p JOIN rounds r ON r.id = p.round_id
                            WHERE r.group_id = g.id AND p.status = 'paid'), 0) AS collected,
                  COALESCE((SELECT SUM(p.amount) FROM payments p JOIN rounds r ON r.id = p.round_id
                            WHERE r.group_id = g.id AND p.status = 'pending'), 0) AS pending,
                  COALESCE((SELECT SUM(p.amount) FROM payments p JOIN rounds r ON r.id = p.round_id
                            WHERE r.group_id = g.id AND p.status = 'pending' AND r.due_date < CURDATE()), 0) AS overdue,
                  (SELECT COUNT(*) FROM payments p JOIN rounds r ON r.id = p.round_id
                     WHERE r.group_id = g.id AND p.status = 'paid') AS paid_count,
                  (SELECT COUNT(*) FROM payments p JOIN rounds r ON r.id = p.round_id
                     WHERE r.group_id = g.id) AS total_count
           FROM seettu_groups g WHERE g.id = %s""",
        (group_id,),
        one=True,
    )
    data["pot"] = group["contribution_amount"] * data["member_count"]
    data["expected"] = group["contribution_amount"] * data["member_count"] * data["round_count"]
    data["collected_pct"] = (
        round(float(data["collected"]) / float(data["expected"]) * 100) if data["expected"] else 0
    )
    data["overdue_count"] = db.query(
        """SELECT COUNT(*) AS n FROM payments p JOIN rounds r ON r.id = p.round_id
           WHERE r.group_id = %s AND p.status = 'pending' AND r.due_date < CURDATE()""",
        (group_id,),
        one=True,
    )["n"]
    return data


def member_summary(group_id, user_id):
    data = db.query(
        """SELECT gm.id AS member_id, gm.turn_order,
                  COALESCE(SUM(CASE WHEN p.status = 'paid' THEN p.amount ELSE 0 END), 0) AS paid_total,
                  COALESCE(SUM(CASE WHEN p.status = 'pending' THEN p.amount ELSE 0 END), 0) AS pending_total,
                  COALESCE(SUM(CASE WHEN p.status = 'pending' AND r.due_date < CURDATE()
                                    THEN p.amount ELSE 0 END), 0) AS overdue_total,
                  COUNT(p.id) AS total_count,
                  COALESCE(SUM(p.status = 'paid'), 0) AS paid_count
           FROM group_members gm
           LEFT JOIN payments p ON p.member_id = gm.id
           LEFT JOIN rounds r ON r.id = p.round_id
           WHERE gm.group_id = %s AND gm.user_id = %s
           GROUP BY gm.id, gm.turn_order""",
        (group_id, user_id),
        one=True,
    )
    data["next_due"] = db.query(
        """SELECT p.amount, r.round_no, r.due_date
           FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN group_members gm ON gm.id = p.member_id
           WHERE gm.group_id = %s AND gm.user_id = %s AND p.status = 'pending'
           ORDER BY r.due_date LIMIT 1""",
        (group_id, user_id),
        one=True,
    )
    return data


# ------------------------------------------------------------- payments ----

def mark_payment(payment_id, paid, method=None, notes=None, paid_date=None, recorded_by=None):
    payment = db.query(
        """SELECT p.*, r.group_id, r.round_no, r.due_date, r.beneficiary_member,
                  gm.user_id, u.full_name
           FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN group_members gm ON gm.id = p.member_id
           JOIN users u ON u.id = gm.user_id
           WHERE p.id = %s""",
        (payment_id,),
        one=True,
    )
    if not payment:
        raise ValueError("Payment not found.")
    if not paid and payment["payout_date"]:
        raise ValueError("This round's payout is already recorded, so its payments cannot be undone.")
    if paid:
        if method not in ("cash", "bank", "other"):
            method = "cash"
        db.execute(
            """UPDATE payments SET status = 'paid', paid_date = %s, method = %s,
                      notes = %s, recorded_by = %s WHERE id = %s""",
            (paid_date or date.today(), method, (notes or "").strip()[:255] or None, recorded_by, payment_id),
        )
    else:
        db.execute(
            """UPDATE payments SET status = 'pending', paid_date = NULL, method = NULL,
                      notes = NULL, recorded_by = NULL WHERE id = %s""",
            (payment_id,),
        )

    round_row = refresh_round_status(payment["round_id"])
    group_status = refresh_group_status(payment["group_id"])
    summary = summary_for_group(payment["group_id"])
    updated = db.query(
        """SELECT p.*, r.round_no, r.due_date FROM payments p
           JOIN rounds r ON r.id = p.round_id WHERE p.id = %s""",
        (payment_id,),
        one=True,
    )
    return {
        "payment": updated,
        "round": round_row,
        "group_status": group_status,
        "summary": summary,
    }


def refresh_round_status(round_id):
    counts = db.query(
        """SELECT COUNT(*) AS total, COALESCE(SUM(status = 'paid'), 0) AS paid
           FROM payments WHERE round_id = %s""",
        (round_id,),
        one=True,
    )
    status = "completed" if counts["total"] and counts["paid"] == counts["total"] else "pending"
    db.execute("UPDATE rounds SET status = %s WHERE id = %s", (status, round_id))
    return db.query("SELECT * FROM rounds WHERE id = %s", (round_id,), one=True)


def refresh_group_status(group_id):
    current = db.query("SELECT status FROM seettu_groups WHERE id = %s", (group_id,), one=True)
    if not current or current["status"] == "draft":
        return current["status"] if current else None
    counts = db.query(
        """SELECT COUNT(*) AS total, COALESCE(SUM(status = 'completed'), 0) AS done
           FROM rounds WHERE group_id = %s""",
        (group_id,),
        one=True,
    )
    status = "completed" if counts["total"] and counts["done"] == counts["total"] else "active"
    db.execute("UPDATE seettu_groups SET status = %s WHERE id = %s", (status, group_id))
    return status


def mark_payout(round_id, group_id):
    row = db.query(
        "SELECT * FROM rounds WHERE id = %s AND group_id = %s", (round_id, group_id), one=True
    )
    if not row:
        raise ValueError("Round not found.")
    if row["status"] != "completed":
        raise ValueError("The payout can be released once every member has paid for this round.")
    if row["payout_date"]:
        raise ValueError("This payout has already been recorded.")
    db.execute("UPDATE rounds SET payout_date = %s WHERE id = %s", (date.today(), round_id))
    return db.query("SELECT * FROM rounds WHERE id = %s", (round_id,), one=True)


# -------------------------------------------------------------- reports ----

def member_totals(group_id):
    return db.query(
        """SELECT gm.id AS member_id, gm.turn_order, u.full_name, u.email,
                  COALESCE(SUM(CASE WHEN p.status = 'paid' THEN p.amount ELSE 0 END), 0) AS paid_total,
                  COALESCE(SUM(CASE WHEN p.status = 'pending' THEN p.amount ELSE 0 END), 0) AS pending_total,
                  COALESCE(SUM(CASE WHEN p.status = 'pending' AND r.due_date < CURDATE()
                                    THEN p.amount ELSE 0 END), 0) AS overdue_total,
                  COUNT(p.id) AS total_count,
                  COALESCE(SUM(p.status = 'paid'), 0) AS paid_count
           FROM group_members gm
           JOIN users u ON u.id = gm.user_id
           LEFT JOIN payments p ON p.member_id = gm.id
           LEFT JOIN rounds r ON r.id = p.round_id
           WHERE gm.group_id = %s
           GROUP BY gm.id, gm.turn_order, u.full_name, u.email
           ORDER BY gm.turn_order IS NULL, gm.turn_order, u.full_name""",
        (group_id,),
    )


# -------------------------------------------------------- dashboard stats ----

def organiser_stats(user_id):
    row = db.query(
        """SELECT
             (SELECT COUNT(*) FROM seettu_groups WHERE organiser_id = %s AND status = 'draft') AS draft_groups,
             (SELECT COUNT(*) FROM seettu_groups WHERE organiser_id = %s AND status = 'active') AS active_groups,
             COALESCE((SELECT SUM(p.amount) FROM payments p
                       JOIN rounds r ON r.id = p.round_id
                       JOIN seettu_groups g ON g.id = r.group_id
                       WHERE g.organiser_id = %s AND p.status = 'paid'), 0) AS collected,
             COALESCE((SELECT SUM(p.amount) FROM payments p
                       JOIN rounds r ON r.id = p.round_id
                       JOIN seettu_groups g ON g.id = r.group_id
                       WHERE g.organiser_id = %s AND p.status = 'pending'
                         AND r.due_date < CURDATE()), 0) AS overdue,
             (SELECT COUNT(DISTINCT gm.user_id) FROM group_members gm
                       JOIN seettu_groups g ON g.id = gm.group_id
                       WHERE g.organiser_id = %s) AS people""",
        (user_id, user_id, user_id, user_id, user_id),
        one=True,
    )
    row["overdue_payments"] = db.query(
        """SELECT COUNT(*) AS n FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN seettu_groups g ON g.id = r.group_id
           WHERE g.organiser_id = %s AND p.status = 'pending' AND r.due_date < CURDATE()""",
        (user_id,),
        one=True,
    )["n"]
    return row


def member_stats(user_id):
    row = db.query(
        """SELECT
             (SELECT COUNT(*) FROM group_members WHERE user_id = %s) AS groups_joined,
             COALESCE((SELECT SUM(p.amount) FROM payments p
                       JOIN group_members gm ON gm.id = p.member_id
                       WHERE gm.user_id = %s AND p.status = 'paid'), 0) AS paid_total,
             COALESCE((SELECT SUM(p.amount) FROM payments p
                       JOIN rounds r ON r.id = p.round_id
                       JOIN group_members gm ON gm.id = p.member_id
                       WHERE gm.user_id = %s AND p.status = 'pending'), 0) AS pending_total,
             COALESCE((SELECT SUM(p.amount) FROM payments p
                       JOIN rounds r ON r.id = p.round_id
                       JOIN group_members gm ON gm.id = p.member_id
                       WHERE gm.user_id = %s AND p.status = 'pending'
                         AND r.due_date < CURDATE()), 0) AS overdue_total""",
        (user_id, user_id, user_id, user_id),
        one=True,
    )
    row["next_due"] = db.query(
        """SELECT p.amount, r.round_no, r.due_date, g.name AS group_name, g.id AS group_id
           FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN group_members gm ON gm.id = p.member_id
           JOIN seettu_groups g ON g.id = r.group_id
           WHERE gm.user_id = %s AND p.status = 'pending' AND g.status = 'active'
           ORDER BY r.due_date LIMIT 1""",
        (user_id,),
        one=True,
    )
    return row


# ------------------------------------------------------------ reminders ----

def reminder_candidates(group_ids, days):
    if not group_ids:
        return []
    placeholders = ", ".join(["%s"] * len(group_ids))
    return db.query(
        f"""SELECT p.id AS payment_id, p.amount, r.round_no, r.due_date,
                   r.group_id, g.name AS group_name, gm.id AS member_id, gm.user_id,
                   u.full_name, u.email, (r.due_date < CURDATE()) AS is_overdue
            FROM payments p
            JOIN rounds r ON r.id = p.round_id
            JOIN seettu_groups g ON g.id = r.group_id
            JOIN group_members gm ON gm.id = p.member_id
            JOIN users u ON u.id = gm.user_id
            WHERE p.status = 'pending'
              AND r.due_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
              AND g.id IN ({placeholders})
            ORDER BY r.due_date, g.name, u.full_name""",
        (days, *group_ids),
    )


def _reminder_message(candidate):
    due = candidate["due_date"].strftime("%d %b %Y")
    amount = f"Rs. {candidate['amount']:,.2f}"
    if candidate["is_overdue"]:
        return (
            f"Overdue: round {candidate['round_no']} payment of {amount} for "
            f"{candidate['group_name']} was due on {due}."
        )
    return (
        f"Reminder: round {candidate['round_no']} payment of {amount} for "
        f"{candidate['group_name']} is due on {due}."
    )


def create_reminders(group_ids, days=None, send_email=False):
    days = current_app.config["REMINDER_DAYS"] if days is None else days
    candidates = reminder_candidates(group_ids, days)
    today = date.today()
    created = 0
    emailed = 0
    for candidate in candidates:
        last = db.query(
            """SELECT id FROM reminders
               WHERE payment_id = %s AND sent_date = %s""",
            (candidate["payment_id"], today),
            one=True,
        )
        if last:
            continue
        db.execute(
            """INSERT INTO reminders (payment_id, member_id, message, channel, sent_date)
               VALUES (%s, %s, %s, 'in_app', %s)""",
            (candidate["payment_id"], candidate["member_id"], _reminder_message(candidate), today),
        )
        created += 1
        if send_email and candidate["email"]:
            if send_email_message(
                candidate["email"],
                f"Seettu reminder - {candidate['group_name']}",
                _reminder_message(candidate) + "\n\nPlease contact your organiser once you have paid.",
            ):
                emailed += 1
    return {"candidates": len(candidates), "created": created, "emailed": emailed}


def send_email_message(to_email, subject, body):
    config = current_app.config
    if not config["SMTP_HOST"] or not config["SMTP_FROM"]:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["SMTP_FROM"]
    message["To"] = to_email
    message.set_content(body)
    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as smtp:
            if config["SMTP_USE_TLS"]:
                smtp.starttls()
            if config["SMTP_USER"]:
                smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            smtp.send_message(message)
        return True
    except Exception:
        current_app.logger.exception("Could not send reminder email to %s", to_email)
        return False


def reminders_for_user(user_id):
    return db.query(
        """SELECT rm.id, rm.message, rm.is_read, rm.created_at, rm.channel,
                  p.amount, p.status AS payment_status, p.paid_date,
                  r.round_no, r.due_date, g.id AS group_id, g.name AS group_name
           FROM reminders rm
           JOIN group_members gm ON gm.id = rm.member_id
           JOIN payments p ON p.id = rm.payment_id
           JOIN rounds r ON r.id = p.round_id
           JOIN seettu_groups g ON g.id = r.group_id
           WHERE gm.user_id = %s
           ORDER BY rm.created_at DESC, rm.id DESC
           LIMIT 60""",
        (user_id,),
    )


def unread_reminder_count(user_id):
    row = db.query(
        """SELECT COUNT(*) AS n FROM reminders rm
           JOIN group_members gm ON gm.id = rm.member_id
           WHERE gm.user_id = %s AND rm.is_read = 0""",
        (user_id,),
        one=True,
    )
    return int(row["n"]) if row else 0


def mark_reminders_read(user_id):
    db.execute(
        """UPDATE reminders rm
           JOIN group_members gm ON gm.id = rm.member_id
           SET rm.is_read = 1
           WHERE gm.user_id = %s""",
        (user_id,),
    )


def due_payments_ledger(organiser_id, days=None):
    days = current_app.config["REMINDER_DAYS"] if days is None else days
    return db.query(
        """SELECT p.id AS payment_id, p.amount, r.round_no, r.due_date,
                  g.id AS group_id, g.name AS group_name,
                  u.full_name, u.email
           FROM payments p
           JOIN rounds r ON r.id = p.round_id
           JOIN seettu_groups g ON g.id = r.group_id
           JOIN group_members gm ON gm.id = p.member_id
           JOIN users u ON u.id = gm.user_id
           WHERE g.organiser_id = %s
             AND g.status = 'active'
             AND p.status = 'pending'
             AND r.due_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
           ORDER BY r.due_date, g.name, u.full_name""",
        (organiser_id, days),
    )
