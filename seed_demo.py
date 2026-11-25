"""Create a realistic demo group so the system can be shown during evaluation.

Run after importing database/schema.sql:
    python seed_demo.py
"""

from datetime import date, timedelta

import db
import services
from app import create_app

PASSWORD = "Seettu@123"

DEMO_USERS = [
    ("Nimal Perera", "nimal@seettu.lk", "0711234567", "organiser"),
    ("Sandunika Bandara", "sandunika@seettu.lk", "0772345678", "member"),
    ("Kasun Silva", "kasun@seettu.lk", "0763456789", "member"),
    ("Amara Fernando", "amara@seettu.lk", "0714567890", "member"),
    ("Dilshan Jayasinghe", "dilshan@seettu.lk", "0775678901", "member"),
    ("Tharindu Weerasinghe", "tharindu@seettu.lk", "0756789012", "member"),
]


def main():
    app = create_app()
    with app.app_context():
        for _, email, _, _ in DEMO_USERS:
            existing = services.user_by_email(email)
            if existing:
                db.execute("DELETE FROM users WHERE id = %s", (existing["id"],))

        ids = {}
        for name, email, phone, role in DEMO_USERS:
            ids[email] = services.create_user(name, email, phone, PASSWORD, role)

        organiser_id = ids["nimal@seettu.lk"]
        today = date.today()

        group_id = services.create_group(
            organiser_id,
            "Office Savers - Batch 24",
            5000,
            "weekly",
            today - timedelta(days=21),
            "Weekly office seettu for the IT batch.",
        )
        turn_order = [
            ("sandunika@seettu.lk", 1),
            ("kasun@seettu.lk", 2),
            ("amara@seettu.lk", 3),
            ("dilshan@seettu.lk", 4),
            ("tharindu@seettu.lk", 5),
        ]
        for email, _ in turn_order:
            services.add_member_by_email(group_id, email)
        members = services.list_group_members(group_id)
        wanted = dict(turn_order)
        services.save_turn_orders(group_id, {m["id"]: wanted[m["email"]] for m in members})
        services.start_group(group_id)

        schedule = {row["round_no"]: row for row in services.schedule_for_group(group_id)}
        ledger = services.ledger_for_group(group_id)

        def mark(round_no, names, method="cash", delay=0):
            due = schedule[round_no]["due_date"]
            paid_on = min(due + timedelta(days=delay), today)
            for name in names:
                payment = next(
                    p for p in ledger
                    if p["round_no"] == round_no and p["full_name"].startswith(name)
                )
                services.mark_payment(
                    payment["payment_id"],
                    True,
                    method=method,
                    paid_date=paid_on,
                    recorded_by=organiser_id,
                )

        everybody = ["Sandunika", "Kasun", "Amara", "Dilshan", "Tharindu"]
        mark(1, everybody, "cash")
        services.mark_payout(schedule[1]["id"], group_id)
        mark(2, ["Sandunika", "Kasun", "Amara", "Dilshan"], "bank", delay=1)
        mark(3, ["Sandunika", "Kasun"], "cash", delay=2)
        mark(4, ["Amara"], "bank")

        reminder_result = services.create_reminders([group_id], days=3)

        draft_id = services.create_group(
            organiser_id,
            "Family Circle",
            10000,
            "monthly",
            today + timedelta(days=10),
            "A smaller monthly group that is still being set up.",
        )
        draft_orders_by_email = {
            "sandunika@seettu.lk": 1,
            "dilshan@seettu.lk": 2,
            "amara@seettu.lk": 3,
        }
        for email, _ in draft_orders_by_email.items():
            services.add_member_by_email(draft_id, email)
        draft_members = services.list_group_members(draft_id)
        services.save_turn_orders(
            draft_id,
            {m["id"]: draft_orders_by_email[m["email"]] for m in draft_members},
        )

        main_group = services.get_group(group_id)
        draft_group = services.get_group(draft_id)

        print("Demo data created.")
        print("")
        print("Organiser : nimal@seettu.lk / %s" % PASSWORD)
        print("Member    : sandunika@seettu.lk / %s" % PASSWORD)
        print("Other members: kasun@seettu.lk, amara@seettu.lk, dilshan@seettu.lk, tharindu@seettu.lk")
        print("")
        print("Active group : %s (invite %s)" % (main_group["name"], main_group["invite_code"]))
        print("Draft group  : %s (invite %s)" % (draft_group["name"], draft_group["invite_code"]))
        print("Reminders created for upcoming/overdue payments: %d" % reminder_result["created"])


if __name__ == "__main__":
    main()
