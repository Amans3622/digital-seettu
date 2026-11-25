"""Generate reminder notifications for payments that are due soon or overdue.

Examples:
    python send_reminders.py
    python send_reminders.py --days 5
    python send_reminders.py --group 1
    python send_reminders.py --email

Schedule this script once a day with Windows Task Scheduler to make reminders automatic.
"""

import argparse
from datetime import date

import db
import services
from app import create_app


def main():
    parser = argparse.ArgumentParser(description="Send Digital Seettu payment reminders.")
    parser.add_argument("--days", type=int, default=None, help="Days ahead to look for due payments.")
    parser.add_argument("--group", type=int, default=None, help="Only remind members of this group id.")
    parser.add_argument("--email", action="store_true", help="Also send email when SMTP is configured.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.group:
            group = services.get_group(args.group)
            if not group:
                raise SystemExit("Group %s does not exist." % args.group)
            group_ids = [group["id"]]
        else:
            group_ids = [
                row["id"]
                for row in db.query("SELECT id FROM seettu_groups WHERE status = 'active'")
            ]

        result = services.create_reminders(
            group_ids, days=args.days, send_email=args.email
        )
        print(
            "%s: %d due payment(s) checked, %d reminder(s) created, %d email(s) sent."
            % (date.today().strftime("%d %b %Y"), result["candidates"], result["created"], result["emailed"])
        )
        if args.email and not app.config["SMTP_HOST"]:
            print("Email was requested but SMTP_HOST is empty in .env, so only in-app reminders were created.")


if __name__ == "__main__":
    main()
