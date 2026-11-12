# -*- coding: utf-8 -*-
"""Login / logout routes."""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from models import db, User
from helpers import current_user

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = User.query.filter_by(username=username).first()
        if u and u.active and check_password_hash(u.password_hash, password):
            session["uid"] = u.id
            return redirect(url_for("auth.home"))
        flash("Galat username ya password.", "danger")
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
