# -*- coding: utf-8 -*-
"""Agent routes — view own attendance, raise regularization requests."""
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Attendance, RegRequest, DevicePunch
from helpers import login_required, current_user, month_days

bp = Blueprint("agent", __name__)

RTYPES = [
    ("missed_punch", "Missed punch (marked A, but I was present)"),
    ("late_justify", "Late justification (L → P)"),
    ("half_to_full", "Half-day to full day"),
    ("comp_off", "Comp-off claim (WO/O day)"),
    ("other", "Other (explain in reason)"),
]
DEFAULT_CODE = {"missed_punch": "P", "late_justify": "P", "half_to_full": "P",
                "comp_off": "O", "other": "P"}


def my_emp(u):
    return u.employee


def _month_ctx():
    t = date.today()
    ym = request.args.get("ym")               # month picker sends 2026-10
    if ym:
        try:
            y, m = map(int, ym.split("-"))
            assert 1 <= m <= 12
            return y, m
        except Exception:
            pass
    try:
        y = int(request.args.get("y", t.year))
        m = int(request.args.get("m", t.month))
        assert 1 <= m <= 12
        return y, m
    except Exception:
        return t.year, t.month


@bp.route("/me")
@login_required
def my_attendance():
    u = current_user()
    emp = my_emp(u)
    if not emp:
        flash("Your profile is not linked to an employee — contact your admin.", "danger")
        return render_template("my_attendance.html", emp=None, days=[], summ={}, y=0, m=0, nd=0)
    y, m = _month_ctx()
    # no explicit month asked -> if current month has no data, open the latest
    # month that has attendance (e.g. October 2026)
    if "ym" not in request.args and "y" not in request.args:
        latest = db.session.query(db.func.max(Attendance.adate)) \
            .filter_by(employee_id=emp.id).scalar()
        if latest and (latest.year, latest.month) < (y, m):
            y, m = latest.year, latest.month
    nd = month_days(y, m)
    atts = {a.adate.day: a for a in Attendance.query.filter_by(employee_id=emp.id)
            .filter(Attendance.adate >= date(y, m, 1), Attendance.adate <= date(y, m, nd))}
    punches = {p.pdate.day: p for p in DevicePunch.query.filter_by(employee_id=emp.id)
               .filter(DevicePunch.pdate >= date(y, m, 1), DevicePunch.pdate <= date(y, m, nd))}
    days = []
    WDL = ["M", "T", "W", "T", "F", "S", "S"]
    for d in range(1, nd + 1):
        a = atts.get(d)
        days.append({"d": d, "wd": WDL[date(y, m, d).weekday()],
                     "code": a.code if a else "-", "adjusted": bool(a and a.adjusted),
                     "in": (a.in_time if a else "") or (punches[d].in_time if d in punches else ""),
                     "out": (a.out_time if a else "") or (punches[d].out_time if d in punches else "")})
    codes = [x["code"] for x in days]
    waiver = emp.office.waiver if emp.office else 4
    lates = codes.count("L")
    summ = {
        "P": codes.count("P") + min(lates, waiver),
        "A": codes.count("A"),
        "H": codes.count("H") + codes.count("HD"),
        "L": lates,
        "WO": codes.count("WO"),
        "HO": codes.count("HO"),
        "O": codes.count("O"),
        "waived": min(lates, waiver),
        "deduct": max(0, lates - waiver),
    }
    return render_template("my_attendance.html", emp=emp, days=days, summ=summ,
                           y=y, m=m, nd=nd, today=date.today())


@bp.route("/me/day/<int:y>/<int:m>/<int:d>")
@login_required
def my_day(y, m, d):
    u = current_user()
    emp = my_emp(u)
    try:
        adate = date(y, m, d)
    except ValueError:
        adate = date.today()
    a = Attendance.query.filter_by(employee_id=emp.id, adate=adate).first() if emp else None
    p = DevicePunch.query.filter_by(employee_id=emp.id, pdate=adate).first() if emp else None
    pending = RegRequest.query.filter_by(employee_id=emp.id, adate=adate, status="pending").first() if emp else None
    return render_template("my_day.html", emp=emp, a=a, p=p, adate=adate, pending=pending,
                           rtypes=RTYPES)


@bp.route("/me/regularize/<int:y>/<int:m>/<int:d>", methods=["POST"])
@login_required
def regularize(y, m, d):
    u = current_user()
    emp = my_emp(u)
    if not emp:
        flash("Profile is not linked.", "danger")
        return redirect(url_for(".my_attendance"))
    try:
        adate = date(y, m, d)
    except ValueError:
        flash("Invalid date.", "danger")
        return redirect(url_for(".my_attendance"))
    if RegRequest.query.filter_by(employee_id=emp.id, adate=adate, status="pending").first():
        flash("A request is already pending for this date.", "warning")
        return redirect(url_for(".my_day", y=y, m=m, d=d))
    rtype = request.form.get("rtype", "other")
    if rtype not in dict(RTYPES):
        rtype = "other"
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Reason is required.", "danger")
        return redirect(url_for(".my_day", y=y, m=m, d=d))
    att = Attendance.query.filter_by(employee_id=emp.id, adate=adate).first()
    req = RegRequest(employee_id=emp.id, adate=adate, rtype=rtype, reason=reason,
                     requested_code=DEFAULT_CODE.get(rtype, "P"),
                     current_code=att.code if att else "-")
    db.session.add(req)
    db.session.commit()
    flash("Request submitted — pending admin approval.", "success")
    return redirect(url_for(".my_requests"))


@bp.route("/me/requests")
@login_required
def my_requests():
    u = current_user()
    emp = my_emp(u)
    reqs = RegRequest.query.filter_by(employee_id=emp.id).order_by(RegRequest.created_at.desc()).all() if emp else []
    return render_template("my_requests.html", reqs=reqs, rtypes=dict(RTYPES))
