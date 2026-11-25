import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import db
import services
from auth import login_required, organiser_required

groups_bp = Blueprint("groups", __name__)


def _load_access(group_id):
    group = services.get_group(group_id)
    if not group:
        abort(404)
    my_membership = services.membership(group_id, session["user_id"])
    is_organiser = group["organiser_id"] == session["user_id"]
    if not is_organiser and not my_membership:
        abort(403)
    return group, my_membership, is_organiser


def _require_manager(group, is_organiser, draft_only=False):
    if not is_organiser:
        abort(403)
    if draft_only and group["status"] != "draft":
        flash("This action is only available while the group is a draft.", "error")
        return False
    return True


def _wants_json():
    return (
        request.headers.get("X-Requested-With") == "fetch"
        or request.accept_mimetypes.best == "application/json"
    )


def _payment_display(payment):
    if payment["status"] == "paid":
        return "Paid", "badge-paid"
    if payment["due_date"] < date.today():
        return "Overdue", "badge-overdue"
    return "Pending", "badge-pending"


@groups_bp.route("/groups/new", methods=["GET", "POST"])
@login_required
@organiser_required
def new():
    today = date.today().isoformat()
    form = {
        "name": "",
        "description": "",
        "contribution_amount": "",
        "frequency": "weekly",
        "start_date": today,
    }
    if request.method == "POST":
        form["name"] = request.form.get("name", "").strip()
        form["description"] = request.form.get("description", "").strip()
        form["contribution_amount"] = request.form.get("contribution_amount", "").strip()
        form["frequency"] = request.form.get("frequency", "weekly")
        form["start_date"] = request.form.get("start_date", today)

        errors = []
        if not 3 <= len(form["name"]) <= 100:
            errors.append("The group name must be between 3 and 100 characters.")
        if len(form["description"]) > 255:
            errors.append("The description must be 255 characters or fewer.")
        try:
            contribution = Decimal(form["contribution_amount"].replace(",", ""))
            contribution = contribution.quantize(Decimal("0.01"))
            if contribution <= 0 or contribution > Decimal("10000000"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            errors.append("Enter a contribution amount between Rs. 1 and Rs. 10,000,000.")
            contribution = None
        if form["frequency"] not in services.FREQUENCIES:
            errors.append("Choose a valid payment frequency.")
        try:
            start_date = datetime.strptime(form["start_date"], "%Y-%m-%d").date()
            if start_date < date.today():
                errors.append("The start date cannot be in the past.")
        except ValueError:
            errors.append("Choose a valid start date.")
            start_date = None

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            group_id = services.create_group(
                session["user_id"],
                form["name"],
                contribution,
                form["frequency"],
                start_date,
                form["description"],
            )
            group = services.get_group(group_id)
            flash(
                "Group created. Invite code: %s. Add members and assign their turns, then start the group."
                % group["invite_code"],
                "success",
            )
            return redirect(url_for("groups.detail", group_id=group_id))

    return render_template("groups/new.html", form=form, frequencies=services.FREQUENCIES)


@groups_bp.route("/groups/<int:group_id>")
@login_required
def detail(group_id):
    group, my_membership, is_organiser = _load_access(group_id)
    members = services.list_group_members(group_id)
    summary = services.summary_for_group(group_id)
    schedule = services.schedule_for_group(group_id) if group["status"] != "draft" else []
    ledger = services.ledger_for_group(group_id) if group["status"] != "draft" else []
    member_view = (
        services.member_summary(group_id, session["user_id"]) if my_membership else None
    )
    return render_template(
        "groups/detail.html",
        group=group,
        members=members,
        summary=summary,
        schedule=schedule,
        ledger=ledger,
        my_membership=my_membership,
        is_organiser=is_organiser,
        can_manage=is_organiser and group["status"] == "draft",
        member_view=member_view,
    )


@groups_bp.route("/groups/<int:group_id>/members", methods=["POST"])
@login_required
def add_member(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not _require_manager(group, is_organiser, draft_only=True):
        return redirect(url_for("groups.detail", group_id=group_id))
    email = request.form.get("email", "").strip().lower()
    if not services.EMAIL_RE.match(email):
        flash("Enter the email address the member registered with.", "error")
    else:
        try:
            services.add_member_by_email(group_id, email)
            flash("Member added. Assign their turn order below.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/members/<int:member_id>/remove", methods=["POST"])
@login_required
def remove_member(group_id, member_id):
    group, _, is_organiser = _load_access(group_id)
    if not _require_manager(group, is_organiser, draft_only=True):
        return redirect(url_for("groups.detail", group_id=group_id))
    member = db.query(
        "SELECT id FROM group_members WHERE id = %s AND group_id = %s",
        (member_id, group_id),
        one=True,
    )
    if not member:
        abort(404)
    services.remove_member(group_id, member_id)
    flash("Member removed from the group.", "success")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/turn-order", methods=["POST"])
@login_required
def save_turn_order(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not _require_manager(group, is_organiser, draft_only=True):
        return redirect(url_for("groups.detail", group_id=group_id))
    members = services.list_group_members(group_id)
    orders = {}
    for member in members:
        raw = request.form.get("order_%d" % member["id"], "").strip()
        if not raw:
            orders[member["id"]] = None
            continue
        try:
            orders[member["id"]] = int(raw)
        except ValueError:
            flash("Turn numbers must be whole numbers.", "error")
            return redirect(url_for("groups.detail", group_id=group_id))
    try:
        services.save_turn_orders(group_id, orders)
        flash("Turn order saved.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/start", methods=["POST"])
@login_required
def start(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not _require_manager(group, is_organiser):
        return redirect(url_for("groups.detail", group_id=group_id))
    try:
        count = services.start_group(group_id)
        flash(
            "Group started! %d rounds and %d payment records were created." % (count, count * count),
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/delete", methods=["POST"])
@login_required
def delete(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not _require_manager(group, is_organiser, draft_only=True):
        return redirect(url_for("groups.detail", group_id=group_id))
    services.delete_group(group_id)
    flash("Draft group deleted.", "success")
    return redirect(url_for("dashboard.dashboard"))


@groups_bp.route("/groups/<int:group_id>/leave", methods=["POST"])
@login_required
def leave(group_id):
    group, my_membership, is_organiser = _load_access(group_id)
    if is_organiser or not my_membership:
        abort(403)
    if group["status"] != "draft":
        flash("You cannot leave a group after it has started.", "error")
        return redirect(url_for("groups.detail", group_id=group_id))
    services.remove_member(group_id, my_membership["id"])
    flash("You left %s." % group["name"], "success")
    return redirect(url_for("dashboard.dashboard"))


def _set_payment(group_id, payment_id, paid):
    group, _, is_organiser = _load_access(group_id)
    if not is_organiser:
        abort(403)
    if group["status"] == "draft":
        flash("Payments open once the group has started.", "error")
        return redirect(url_for("groups.detail", group_id=group_id))

    exists = db.query(
        """SELECT p.id FROM payments p JOIN rounds r ON r.id = p.round_id
           WHERE p.id = %s AND r.group_id = %s""",
        (payment_id, group_id),
        one=True,
    )
    if not exists:
        abort(404)

    method = request.form.get("method", "cash")
    notes = request.form.get("notes", "")
    try:
        result = services.mark_payment(
            payment_id, paid, method=method, notes=notes, recorded_by=session["user_id"]
        )
    except ValueError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("groups.detail", group_id=group_id))

    if _wants_json():
        payment = result["payment"]
        round_row = result["round"]
        summary = result["summary"]
        counts = db.query(
            """SELECT COUNT(*) AS total, COALESCE(SUM(status = 'paid'), 0) AS paid
               FROM payments WHERE round_id = %s""",
            (round_row["id"],),
            one=True,
        )
        label, badge = _payment_display(payment)
        round_complete = round_row["status"] == "completed"
        group_status = result["group_status"]
        return jsonify(
            {
                "ok": True,
                "payment": {
                    "id": payment["id"],
                    "status": payment["status"],
                    "status_label": label,
                    "badge_class": badge,
                    "paid_date": payment["paid_date"].strftime("%d %b %Y")
                    if payment["paid_date"]
                    else "",
                    "method": payment["method"] or "",
                    "method_label": (payment["method"] or "").capitalize(),
                    "notes": payment["notes"] or "",
                },
                "round": {
                    "id": round_row["id"],
                    "status": round_row["status"],
                    "paid_count": int(counts["paid"]),
                    "total_count": int(counts["total"]),
                    "payout_ready": round_complete and not round_row["payout_date"],
                },
                "summary": {
                    "collected": float(summary["collected"]),
                    "pending": float(summary["pending"]),
                    "overdue": float(summary["overdue"]),
                    "collected_pct": summary["collected_pct"],
                    "paid_count": int(summary["paid_count"]),
                    "total_count": int(summary["total_count"]),
                    "rounds_completed": int(summary["rounds_completed"]),
                    "round_count": int(summary["round_count"]),
                    "overdue_count": int(summary["overdue_count"]),
                },
                "group_status": group_status,
            }
        )

    flash("Payment marked as paid." if paid else "Payment set back to pending.", "success")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/payments/<int:payment_id>/mark-paid", methods=["POST"])
@login_required
def mark_paid(group_id, payment_id):
    return _set_payment(group_id, payment_id, True)


@groups_bp.route("/groups/<int:group_id>/payments/<int:payment_id>/mark-pending", methods=["POST"])
@login_required
def mark_pending(group_id, payment_id):
    return _set_payment(group_id, payment_id, False)


@groups_bp.route("/groups/<int:group_id>/rounds/<int:round_id>/payout", methods=["POST"])
@login_required
def mark_payout(group_id, round_id):
    group, _, is_organiser = _load_access(group_id)
    if not is_organiser:
        abort(403)
    try:
        services.mark_payout(round_id, group_id)
        flash("Payout recorded for this round.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/report")
@login_required
def report(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not is_organiser:
        abort(403)
    return render_template(
        "groups/report.html",
        group=group,
        summary=services.summary_for_group(group_id),
        members=services.member_totals(group_id),
        schedule=services.schedule_for_group(group_id),
    )


@groups_bp.route("/groups/<int:group_id>/report.csv")
@login_required
def report_csv(group_id):
    group, _, is_organiser = _load_access(group_id)
    if not is_organiser:
        abort(403)
    summary = services.summary_for_group(group_id)
    members = services.member_totals(group_id)
    schedule = services.schedule_for_group(group_id)

    output = io.StringIO()
    writer = csv.writer(output)
    def amount(value):
        return "%.2f" % float(value)


    writer.writerow(["Digital Seettu report"])
    writer.writerow(["Group", group["name"]])
    writer.writerow(["Organiser", group["organiser_name"]])
    writer.writerow(["Contribution", amount(group["contribution_amount"])])
    writer.writerow(["Frequency", group["frequency"]])
    writer.writerow(["Start date", group["start_date"].isoformat()])
    writer.writerow(["Members", summary["member_count"]])
    writer.writerow(["Rounds", summary["round_count"]])
    writer.writerow(["Expected total", amount(summary["expected"])])
    writer.writerow(["Collected", amount(summary["collected"])])
    writer.writerow(["Pending", amount(summary["pending"])])
    writer.writerow(["Overdue", amount(summary["overdue"])])
    writer.writerow([])
    writer.writerow(["Member summary"])
    writer.writerow(["Member", "Email", "Turn", "Paid payments", "Total payments", "Paid total", "Pending total", "Overdue total"])
    for row in members:
        writer.writerow(
            [
                row["full_name"],
                row["email"],
                row["turn_order"] or "",
                int(row["paid_count"]),
                int(row["total_count"]),
                amount(row["paid_total"]),
                amount(row["pending_total"]),
                amount(row["overdue_total"]),
            ]
        )
    writer.writerow([])
    writer.writerow(["Round schedule"])
    writer.writerow(["Round", "Due date", "Beneficiary", "Payments received", "Status", "Payout date"])
    for row in schedule:
        writer.writerow(
            [
                row["round_no"],
                row["due_date"].isoformat(),
                row["beneficiary_name"],
                "%d/%d" % (row["paid_count"], row["total_count"]),
                row["status"],
                row["payout_date"].isoformat() if row["payout_date"] else "",
            ]
        )

    slug = re.sub(r"[^A-Za-z0-9]+", "-", group["name"]).strip("-").lower() or "group"
    filename = "seettu-report-%s.csv" % slug
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
    return response
