from datetime import date

import mysql.connector
from flask import Flask, redirect, render_template, session, url_for

import db
import services
from auth import auth_bp
from config import Config
from dashboard import dashboard_bp
from groups import groups_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(groups_bp)

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("dashboard.dashboard"))
        return render_template("index.html")

    @app.template_filter("money")
    def money(value):
        try:
            return "Rs. {:,.2f}".format(float(value or 0))
        except (TypeError, ValueError):
            return "Rs. 0.00"

    @app.template_filter("datefmt")
    def datefmt(value, pattern="%d %b %Y"):
        return value.strftime(pattern) if value else "—"

    @app.template_filter("frequency")
    def frequency(value):
        return services.FREQUENCIES.get(value, str(value).capitalize())

    @app.template_filter("initials")
    def initials(value):
        parts = [p for p in (value or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @app.context_processor
    def inject_globals():
        user = None
        unread = 0
        if session.get("user_id"):
            try:
                user = services.get_user(session["user_id"])
                if user:
                    unread = services.unread_reminder_count(user["id"])
            except mysql.connector.Error:
                user = None
        return {
            "current_user": user,
            "unread_reminders": unread,
            "today": date.today(),
            "reminder_days": app.config["REMINDER_DAYS"],
        }

    @app.errorhandler(403)
    def forbidden(error):
        return (
            render_template(
                "errors/error.html",
                code=403,
                title="Access denied",
                message="You do not have permission to open this page.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template(
                "errors/error.html",
                code=404,
                title="Page not found",
                message="The page you asked for does not exist or has been moved.",
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(error):
        return (
            render_template(
                "errors/error.html",
                code=500,
                title="Something went wrong",
                message="An unexpected error occurred. Please try again.",
            ),
            500,
        )

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        return (
            render_template(
                "errors/error.html",
                code=503,
                title="Database unavailable",
                message=(
                    "The application could not reach MySQL. Start the MySQL service in XAMPP, "
                    "check the details in your .env file, then refresh this page."
                ),
            ),
            503,
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
