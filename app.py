# -*- coding: utf-8 -*-
"""Attendance Portal — main app factory."""
import os
from datetime import datetime
from flask import Flask, redirect, url_for, session, g, request, flash
from models import db, RegRequest, Employee, User
from helpers import current_user

# auto-logout after this many minutes without any activity
SESSION_IDLE_MINUTES = 30


def _bootstrap_super_admin(app):
    """Cloud first run: empty DB needs one super admin to log in and set up offices."""
    if User.query.first():
        return
    from werkzeug.security import generate_password_hash
    db.session.add(User(
        username=os.environ.get("ADMIN_USER", "admin"),
        role="super_admin",
        password_hash=generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin123"))))
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
    db_url = os.environ.get("DATABASE_URL",
                            "sqlite:///" + os.path.join(os.path.dirname(__file__), "portal.db"))
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB uploads
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _bootstrap_super_admin(app)

    @app.before_request
    def session_timeout():
        """Auto-logout after SESSION_IDLE_MINUTES of inactivity."""
        if request.path.startswith("/static"):
            return
        if session.get("uid"):
            now = datetime.utcnow().timestamp()
            last = session.get("last_act")
            if last and now - last > SESSION_IDLE_MINUTES * 60:
                session.clear()
                flash("Session expired after 30 minutes of inactivity — please log in again.",
                      "warning")
                return redirect(url_for("auth.login"))
            session["last_act"] = now

    @app.before_request
    def pending_badge():
        u = current_user()
        g.pend = 0
        if u and u.role in ("admin", "super_admin"):
            q = RegRequest.query.filter_by(status="pending")
            if u.office_id:
                q = q.join(Employee).filter(Employee.office_id == u.office_id)
            g.pend = q.count()
        g.u = u

    from routes_auth import bp as auth_bp
    from routes_agent import bp as agent_bp
    from routes_admin import bp as admin_bp
    from routes_super import bp as super_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(super_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.home"))

    @app.after_request
    def no_cache_html(response):
        """Never let the browser show a logged-in page after logout (back/refresh)."""
        if response.mimetype in ("text/html",):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.after_request
    def lite_gzip(response):
        """Compress text responses — portal stays usable on slow internet."""
        if (response.direct_passthrough or response.status_code != 200
                or not response.content_length or response.content_length < 600):
            return response
        if "gzip" not in request.headers.get("Accept-Encoding", ""):
            return response
        if response.mimetype not in ("text/html", "text/css", "application/json",
                                     "text/plain", "text/javascript"):
            return response
        import gzip as _gzip
        response.data = _gzip.compress(response.data, compresslevel=5)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(response.data))
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")
