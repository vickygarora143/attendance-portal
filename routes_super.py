# -*- coding: utf-8 -*-
"""Super Admin routes: offices, users, settings, audit log."""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from models import db, Office, User, Employee, AuditLog
from helpers import login_required, role_required, current_user, audit

bp = Blueprint("super", __name__)


@bp.route("/super")
@login_required
@role_required("super_admin")
def home():
    offs = Office.query.order_by(Office.code).all()
    counts = {o.id: Employee.query.filter_by(office_id=o.id).count() for o in offs}
    return render_template("offices.html", offs=offs, counts=counts)


@bp.route("/super/offices/new", methods=["GET", "POST"])
@bp.route("/super/offices/<int:oid>", methods=["GET", "POST"])
@login_required
@role_required("super_admin")
def office_form(oid=None):
    off = db.session.get(Office, oid) if oid else None
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        if not code or not name:
            flash("Code aur Name zaroori hai.", "danger")
            return redirect(request.url)
        if not off:
            if Office.query.filter_by(code=code).first():
                flash("Office code already exists.", "danger")
                return redirect(url_for(".home"))
            off = Office(code=code, name=name)
            db.session.add(off)
        else:
            off.code, off.name = code, name
        for k in ("late_after", "hd_from", "suspect_from", "waiver"):
            v = request.form.get(k)
            if v:
                setattr(off, k, int(v))
        db.session.commit()
        flash("Office saved.", "success")
        return redirect(url_for(".home"))
    return render_template("office_form.html", off=off)


@bp.route("/super/users")
@login_required
@role_required("super_admin")
def users():
    us = User.query.order_by(User.role, User.username).all()
    offs = Office.query.all()
    emps = Employee.query.all()
    return render_template("users.html", us=us, offs=offs, emps=emps)


@bp.route("/super/users/new", methods=["GET", "POST"])
@bp.route("/super/users/<int:uid>", methods=["GET", "POST"])
@login_required
@role_required("super_admin")
def user_form(uid=None):
    u = db.session.get(User, uid) if uid else None
    offs = Office.query.order_by(Office.code).all()
    emps = Employee.query.order_by(Employee.office_id, Employee.name).all()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "agent")
        office_id = request.form.get("office_id") or None
        employee_id = request.form.get("employee_id") or None
        password = request.form.get("password", "")
        if not u:
            if not username or User.query.filter_by(username=username).first():
                flash("Username khali hai ya already exists.", "danger")
                return redirect(request.url)
            if not password:
                flash("Naye user ke liye password zaroori hai.", "danger")
                return redirect(request.url)
            u = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(u)
        else:
            u.username = username or u.username
            if password:
                u.password_hash = generate_password_hash(password)
        u.role, u.office_id, u.employee_id = role, int(office_id) if office_id else None, \
            int(employee_id) if employee_id else None
        u.active = request.form.get("active") == "on"
        audit("user.saved", f"{u.username} role={u.role}")
        db.session.commit()
        flash("User saved.", "success")
        return redirect(url_for(".users"))
    return render_template("user_form.html", u=u, offs=offs, emps=emps)


@bp.route("/super/audit")
@login_required
@role_required("super_admin")
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all()
    return render_template("audit.html", logs=logs)
