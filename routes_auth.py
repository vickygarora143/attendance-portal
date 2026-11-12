# -*- coding: utf-8 -*-
"""Login / logout / change-password routes."""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User
from helpers import current_user, audit, login_required

bp = Blueprint("auth", __name__)


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
            audit("password.changed", f"user={u.username}")
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("auth.home"))
    return render_template("change_password.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = User.query.filter_by(username=username).first()
        if u and u.active and check_password_hash(u.password_hash, password):
            session["uid"] = u.id
            return redirect(url_for("auth.home"))
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
