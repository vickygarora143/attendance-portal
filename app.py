# -*- coding: utf-8 -*-
"""Attendance Portal — main app factory."""
import os
import secrets
from datetime import datetime
from flask import Flask, redirect, url_for, session, g, request, flash
from models import db, RegRequest, Employee, User
from helpers import current_user

# auto-logout after this many minutes without any activity
SESSION_IDLE_MINUTES = 30

# endpoints reachable while a user is forced to change their password
PW_CHANGE_ALLOWED = {"auth.change_password", "auth.logout", "static"}


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


def _resolve_db_url():
    """DATABASE_URL, with a temporary fallback file if that URL cannot connect.

    db_fallback.json only kicks in when the configured URL is unusable (e.g. the
    Supabase password was rotated but the Render env var was not updated yet).
    Delete db_fallback.json once the env var is correct.
    """
    default = "sqlite:///" + os.path.join(os.path.dirname(__file__), "portal.db")
    url = os.environ.get("DATABASE_URL", default)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    fb_path = os.path.join(os.path.dirname(__file__), "db_fallback.json")
    if url.startswith("postgresql") and os.path.exists(fb_path):
        try:
            import psycopg2
            psycopg2.connect(url, connect_timeout=6).close()
        except Exception as exc:
            try:
                import json
                with open(fb_path, "r", encoding="utf-8") as f:
                    fb = json.load(f)["database_url"]
                print("WARNING: DATABASE_URL unusable (%s) - using db_fallback.json"
                      % str(exc).splitlines()[0][:70])
                return fb
            except Exception as e2:
                print("WARNING: fallback config unreadable: %s" % e2)
    return url


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
    db_url = _resolve_db_url()
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB uploads
    # --- session cookie hardening ---
    # Secure cookies only make sense on HTTPS; local dev runs on plain http.
    _on_cloud = bool(os.environ.get("RENDER") or os.environ.get("DATABASE_URL"))
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get(
        "SESSION_COOKIE_SECURE", "1" if _on_cloud else "0") == "1"
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

    # ---- CSRF: one token per session, checked on every POST ----
    def csrf_token():
        tok = session.get("_csrf")
        if not tok:
            tok = secrets.token_urlsafe(32)
            session["_csrf"] = tok
        return tok

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def csrf_protect():
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return
        if app.config.get("TESTING"):        # smoke tests post forms directly
            return
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        good = session.get("_csrf")
        if not good or not sent or not secrets.compare_digest(str(sent), str(good)):
            flash("Your form expired for security reasons. Please try again.", "danger")
            back = request.referrer or ""
            if not back.startswith(request.host_url):
                back = url_for("auth.home")
            return redirect(back), 303
        # extra guard: reject cross-site origins even if a token leaks
        origin = request.headers.get("Origin", "")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            flash("Request blocked: unexpected origin.", "danger")
            return redirect(url_for("auth.home")), 303

    @app.before_request
    def force_password_change():
        """Users flagged by an admin must set a new password before doing anything else."""
        u = current_user()
        if u and getattr(u, "must_change_pw", False) and request.endpoint not in PW_CHANGE_ALLOWED:
            flash("Please set a new password before continuing.", "warning")
            return redirect(url_for("auth.change_password"))

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
    def security_headers(response):
        """Baseline hardening headers (no CDN, no inline external assets)."""
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        h.setdefault("Content-Security-Policy",
                     "default-src 'self'; img-src 'self' data:; "
                     "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                     "font-src 'self' data:; connect-src 'self'; "
                     "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
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
