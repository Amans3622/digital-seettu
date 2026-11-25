from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import services
from auth import login_required, organiser_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    user = services.get_user(session["user_id"])
    groups = services.groups_for_user(user["id"])
    is_organiser = user["role"] == "organiser"
    stats = services.organiser_stats(user["id"]) if is_organiser else services.member_stats(user["id"])
    reminders = services.reminders_for_user(user["id"])[:4]
    due = services.due_payments_ledger(user["id"])[:6] if is_organiser else []
    return render_template(
        "dashboard.html",
        user=user,
        groups=groups,
        is_organiser=is_organiser,
        stats=stats,
        reminders=reminders,
        due=due,
    )


@dashboard_bp.route("/join", methods=["POST"])
@login_required
def join():
    code = request.form.get("invite_code", "").strip().upper()
    group = services.group_by_invite_code(code)
    if not group:
        flash("That invite code does not match any group.", "error")
        return redirect(url_for("dashboard.dashboard"))
    try:
        services.join_group(group["id"], session["user_id"])
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("dashboard.dashboard"))
    flash("You joined %s. The organiser can now assign your turn." % group["name"], "success")
    return redirect(url_for("groups.detail", group_id=group["id"]))


@dashboard_bp.route("/reminders")
@login_required
def reminders():
    user = services.get_user(session["user_id"])
    inbox = services.reminders_for_user(user["id"])
    due = services.due_payments_ledger(user["id"])
    own_groups = [
        g for g in services.groups_for_user(user["id"]) if g["organiser_id"] == user["id"]
    ]
    return render_template(
        "reminders.html",
        user=user,
        inbox=inbox,
        due=due,
        own_groups=own_groups,
        reminder_days=current_app.config["REMINDER_DAYS"],
    )


@dashboard_bp.route("/reminders/run", methods=["POST"])
@login_required
@organiser_required
def run_reminders():
    group_id = request.form.get("group_id", "").strip()
    if group_id:
        group = services.get_group(int(group_id))
        if not group or group["organiser_id"] != session["user_id"]:
            flash("You do not manage that group.", "error")
            return redirect(url_for("dashboard.reminders"))
        group_ids = [group["id"]]
    else:
        group_ids = services.organiser_group_ids(session["user_id"], active_only=True)

    result = services.create_reminders(group_ids)
    if result["candidates"] == 0:
        flash("Nothing is due in the reminder window, so no reminders were needed.", "success")
    elif result["created"] == 0:
        flash("Reminders were already sent today for the %d due payments." % result["candidates"], "success")
    else:
        flash(
            "%d new reminder(s) sent for %d due payment(s)."
            % (result["created"], result["candidates"]),
            "success",
        )
    if group_id:
        return redirect(url_for("groups.detail", group_id=int(group_id)))
    return redirect(url_for("dashboard.reminders"))


@dashboard_bp.route("/reminders/read", methods=["POST"])
@login_required
def read_reminders():
    services.mark_reminders_read(session["user_id"])
    flash("All reminders marked as read.", "success")
    return redirect(url_for("dashboard.reminders"))
