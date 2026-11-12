# -*- coding: utf-8 -*-
"""Login / logout / change-password routes."""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import func
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User, LoginAttempt
from helpers import current_user, audit, login_required

bp = Blueprint("auth", __name__)

# brute-force protection: N failed attempts per username+IP within the window
MAX_FAILS = 5
LOCK_MINUTES = 15


def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    ip = xff.split(",")[0].strip() if xff else (request.remote_addr or "")
    return ip[:60]


def _too_many(username, ip):
    since = datetime.utcnow() - timedelta(minutes=LOCK_MINUTES)
    n = LoginAttempt.query.filter(
        LoginAttempt.created_at >= since,
        func.lower(LoginAttempt.username) == username.lower(),
        LoginAttempt.ip == ip).count()
    return n >= MAX_FAILS


def _record_fail(username, ip):
    db.session.add(LoginAttempt(username=username[:60], ip=ip))
    # keep the table small
    db.session.query(LoginAttempt).filter(
        LoginAttempt.created_at < datetime.utcnow() - timedelta(days=1)
    ).delete(synchronize_session=False)
    db.session.commit()


def _clear_fails(username, ip):
    LoginAttempt.query.filter(
        func.lower(LoginAttempt.username) == username.lower(),
        LoginAttempt.ip == ip).delete(synchronize_session=False)
    db.session.commit()


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    u = current_user()
    if not u:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        cur_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(u.password_hash, cur_pw):
            flash("Current password is wrong.", "danger")
        elif len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
        elif new_pw != confirm:
            flash("New password and confirmation do not match.", "danger")
        elif new_pw == cur_pw:
            flash("New password must be different from the current one.", "warning")
        else:
            u.password_hash = generate_password_hash(new_pw)
            u.must_change_pw = False
            audit("password.changed", f"user={u.username}")
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("auth.home"))
    return render_template("change_password.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    # already logged in? straight to the home page
    if current_user():
        return redirect(url_for("auth.home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip = _client_ip()
        if username and _too_many(username, ip):
            flash("Too many failed attempts. Please wait 15 minutes and try again.", "danger")
            return render_template("login.html"), 429
        # case-insensitive username match (agents may type gdsm015 / Gdsm015)
        u = User.query.filter(func.lower(User.username) == username.lower()).first()
        if u and u.active and check_password_hash(u.password_hash, password):
            _clear_fails(username, ip)
            session.clear()                 # fresh session on login (no fixation)
            session["uid"] = u.id
            session["last_act"] = datetime.utcnow().timestamp()
            if getattr(u, "must_change_pw", False):
                flash("Please set a new password before continuing.", "warning")
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("auth.home"))
        if username:
            _record_fail(username, ip)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/home")
def home():
    u = current_user()
    if not u:
        return redirect(url_for("auth.login"))
    if u.role == "super_admin":
        return redirect(url_for("super.home"))
    if u.role == "agent":
        return redirect(url_for("agent.my_attendance"))
    return redirect(url_for("admin.dashboard"))
