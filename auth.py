from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

import services

auth_bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        if not services.get_user(user_id):
            session.clear()
            flash("Your session is no longer valid. Please log in again.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def organiser_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = services.get_user(session["user_id"])
        if not user or user["role"] != "organiser":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))

    form = {"full_name": "", "email": "", "phone": "", "role": "member"}
    if request.method == "POST":
        form["full_name"] = request.form.get("full_name", "").strip()
        form["email"] = request.form.get("email", "").strip().lower()
        form["phone"] = request.form.get("phone", "").strip()
        form["role"] = request.form.get("role", "member")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if len(form["full_name"]) < 3:
            errors.append("Please enter your full name.")
        if not services.EMAIL_RE.match(form["email"]):
            errors.append("Please enter a valid email address.")
        if form["role"] not in ("organiser", "member"):
            errors.append("Please choose a valid account type.")
        if len(password) < 8:
            errors.append("The password must be at least 8 characters.")
        if password != confirm:
            errors.append("The two passwords do not match.")
        if not errors and services.user_by_email(form["email"]):
            errors.append("An account with that email already exists. Try logging in.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            user_id = services.create_user(
                form["full_name"], form["email"], form["phone"], password, form["role"]
            )
            session.clear()
            session["user_id"] = user_id
            flash("Welcome to Digital Seettu, %s." % form["full_name"].split()[0], "success")
            return redirect(url_for("dashboard.dashboard"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))

    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = services.user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back, %s." % user["full_name"].split()[0], "success")
            return redirect(url_for("dashboard.dashboard"))
        flash("Email or password is incorrect.", "error")

    return render_template("auth/login.html", email=email)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))
