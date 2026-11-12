# -*- coding: utf-8 -*-
"""Shared helpers: auth guards, audit, date/time utilities."""
import calendar
from datetime import datetime, date
from functools import wraps
from flask import session, redirect, url_for, flash, request
from models import db, AuditLog, User, Employee


def mmin(s):
    """'09:52' -> 592 minutes. None if not parseable."""
    try:
        h, m = str(s).strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def current_user():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not session.get("uid"):
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **k)
    return wrapper


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            u = current_user()
            if not u:
                return redirect(url_for("auth.login", next=request.path))
            if u.role not in roles:
                flash("Aapke role ke liye ye page allowed nahi hai.", "danger")
                return redirect(url_for("auth.home"))
            return f(*a, **k)
        return wrapper
    return deco


def audit(action, detail=""):
    u = current_user()
    db.session.add(AuditLog(user_id=u.id if u else None,
                            username=u.username if u else "-",
                            action=action, detail=detail))


def month_days(y, m):
    return calendar.monthrange(y, m)[1]


def month_range(y, m):
    return date(y, m, 1), date(y, m, month_days(y, m))


def mmss(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def safe_date(y, m, d):
    try:
        return date(y, m, int(d))
    except Exception:
        return None


def emp_codes_for_office(office_id):
    return [e.emp_id for e in Employee.query.filter_by(office_id=office_id).all()]
