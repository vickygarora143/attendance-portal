# -*- coding: utf-8 -*-
"""Admin routes: upload, preview/confirm, requests, employees, attendance edit, holidays, report."""
import json
from io import BytesIO
from datetime import date, datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, current_app)
from models import (db, Office, Employee, User, Holiday, Upload, DevicePunch,
                    Attendance, RegRequest)
from helpers import (login_required, role_required, current_user, audit,
                     month_days, safe_date)
from parser import parse_bio, derive_code
from report_builder import build_report

bp = Blueprint("admin", __name__)


def _my_office():
    """Office for this admin; super_admin (no office) falls back to the first office."""
    u = current_user()
    if u.office_id:
        return u.office
    return Office.query.order_by(Office.code).first()


# ------------------------------------------------------------------ dashboard
@bp.route("/admin")
@login_required
@role_required("admin", "super_admin")
def dashboard():
    off = _my_office()
    if off is None:
        flash("Create an office first / assign an office to the admin.", "warning")
        return redirect(url_for("super.home"))
    month = date.today().strftime("%Y-%m")
    emps = Employee.query.filter_by(office_id=off.id).count()
    pending = RegRequest.query.filter_by(status="pending").join(Employee) \
        .filter(Employee.office_id == off.id).count()
    last_up = Upload.query.filter_by(office_id=off.id, status="imported") \
        .order_by(Upload.created_at.desc()).first()
    return render_template("dashboard.html", off=off, emps=emps, pending=pending,
                           last_up=last_up, month=month)


# ------------------------------------------------------------------ upload
@bp.route("/admin/upload", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def upload():
    off = _my_office()
    if request.method == "POST":
        f = request.files.get("file")
        month = request.form.get("month", "")
        if not f or not f.filename or not month:
            flash("Select both the file and the month.", "danger")
            return redirect(url_for(".upload"))
        try:
            y, m = map(int, month.split("-"))
        except Exception:
            flash("Month must be in the format 2026-10.", "danger")
            return redirect(url_for(".upload"))
        try:
            rows = parse_bio(f)
        except Exception as e:
            current_app.logger.exception(e)
            flash("Could not parse the file — is it a biometric .xls export?", "danger")
            return redirect(url_for(".upload"))
        if not rows:
            flash("No employee block found in the file.", "danger")
            return redirect(url_for(".upload"))
        payload = {"month": month,
                   "rows": {code: {"name": v["name"],
                                   "days": {str(d): list(rec) for d, rec in v["days"].items()}}
                            for code, v in rows.items()}}
        up = Upload(office_id=off.id, admin_id=current_user().id, filename=f.filename,
                    month=month, payload=json.dumps(payload), n_rows=len(rows))
        db.session.add(up)
        db.session.commit()
        return redirect(url_for(".preview", uid=up.id))
    ups = Upload.query.filter_by(office_id=off.id).order_by(Upload.created_at.desc()).limit(10).all()
    return render_template("upload.html", ups=ups)


@bp.route("/admin/upload/<int:uid>")
@login_required
@role_required("admin", "super_admin")
def preview(uid):
    up = db.session.get(Upload, uid)
    off = _my_office()
    if not up or up.office_id != off.id:
        flash("Upload not found.", "danger")
        return redirect(url_for(".upload"))
    payload = json.loads(up.payload or "{}")
    y, m = map(int, up.month.split("-"))
    known, unknown = [], []
    for code, data in payload.get("rows", {}).items():
        emp = Employee.query.filter_by(office_id=up.office_id, emp_id=code).first()
        ndays = len(data.get("days", {}))
        present = sum(1 for rec in data.get("days", {}).values() if rec[0] in ("P", "WOP"))
        lates = sum(1 for rec in data.get("days", {}).values()
                    if rec[0] == "P" and _is_late(rec[1], off))
        row = {"code": code, "name": data.get("name"), "ndays": ndays,
               "present": present, "lates": lates}
        (known if emp else unknown).append(row)
    return render_template("upload_preview.html", up=up, known=known, unknown=unknown,
                           y=y, m=m, off=off)


def _is_late(in_time, off):
    from helpers import mmin
    t = mmin(in_time)
    return t is not None and off.late_after < t < off.hd_from


@bp.route("/admin/upload/<int:uid>/confirm", methods=["POST"])
@login_required
@role_required("admin", "super_admin")
def confirm(uid):
    up = db.session.get(Upload, uid)
    off = _my_office()
    if not up or up.office_id != off.id:
        flash("Upload not found.", "danger")
        return redirect(url_for(".upload"))
    payload = json.loads(up.payload)
    y, m = map(int, up.month.split("-"))
    hols = {h.hdate for h in Holiday.query.filter_by(office_id=off.id)}
    imported = unknown = written = 0
    for code, data in payload["rows"].items():
        emp = Employee.query.filter_by(office_id=off.id, emp_id=code).first()
        if not emp:
            unknown += 1
            continue
        imported += 1
        for dstr, rec in data["days"].items():
            d = safe_date(y, m, dstr)
            if d is None:
                continue
            st, iv, ov, tv = rec
            db.session.add(DevicePunch(upload_id=up.id, employee_id=emp.id, pdate=d,
                                       status=st, in_time=iv, out_time=ov, total_hrs=tv))
            att = Attendance.query.filter_by(employee_id=emp.id, adate=d).first()
            code_new = derive_code(st, iv, d in hols, off)
            if att is None:
                db.session.add(Attendance(employee_id=emp.id, adate=d, code=code_new,
                                          in_time=iv, out_time=ov, total_hrs=tv, source="device"))
            elif att.source != "adjust":
                att.code, att.in_time, att.out_time, att.total_hrs = code_new, iv, ov, tv
                att.source = "device"
            written += 1
    up.status = "imported"
    audit("upload.imported", f"upload#{up.id} {up.filename} month={up.month} "
                             f"employees={imported} unknown={unknown} days={written}")
    db.session.commit()
    flash(f"Import done: {imported} employees, {written} day-records. "
          f"{' (' + str(unknown) + ' unknown device IDs — add them on the Employees page)' if unknown else ''}",
          "success")
    return redirect(url_for(".dashboard"))


@bp.route("/admin/upload/<int:uid>/discard", methods=["POST"])
@login_required
@role_required("admin", "super_admin")
def discard(uid):
    up = db.session.get(Upload, uid)
    if up and up.office_id == _my_office().id and up.status == "preview":
        up.status = "discarded"
        audit("upload.discarded", f"upload#{up.id}")
        db.session.commit()
    return redirect(url_for(".upload"))


# ------------------------------------------------------------------ requests
@bp.route("/admin/requests")
@login_required
@role_required("admin", "super_admin")
def requests():
    off = _my_office()
    pend = RegRequest.query.filter_by(status="pending").join(Employee) \
        .filter(Employee.office_id == off.id).order_by(RegRequest.created_at).all()
    decided = RegRequest.query.filter(RegRequest.status != "pending").join(Employee) \
        .filter(Employee.office_id == off.id).order_by(RegRequest.decided_at.desc()).limit(30).all()
    ev = {}
    for r in pend + decided:
        p = DevicePunch.query.filter_by(employee_id=r.employee_id, pdate=r.adate).first()
        a = Attendance.query.filter_by(employee_id=r.employee_id, adate=r.adate).first()
        ev[r.id] = (p, a)
    return render_template("requests.html", pend=pend, decided=decided, ev=ev)


@bp.route("/admin/requests/<int:rid>/decide", methods=["POST"])
@login_required
@role_required("admin", "super_admin")
def decide(rid):
    r = db.session.get(RegRequest, rid)
    off = _my_office()
    if not r or r.employee.office_id != off.id or r.status != "pending":
        flash("Request not found / already decided.", "danger")
        return redirect(url_for(".requests"))
    action = request.form.get("action")
    remark = request.form.get("remark", "").strip()
    if action == "approve":
        new_code = request.form.get("set_code") or r.requested_code or "P"
        att = Attendance.query.filter_by(employee_id=r.employee_id, adate=r.adate).first()
        if att is None:
            att = Attendance(employee_id=r.employee_id, adate=r.adate)
            db.session.add(att)
        old = att.code
        att.code, att.source, att.adjusted = new_code, "adjust", True
        r.status, r.admin_id, r.admin_remark, r.decided_at = "approved", current_user().id, remark, datetime.utcnow()
        audit("reg.approved", f"emp={r.employee.emp_id} {r.adate} {old}->{new_code} ({r.rtype}) remark={remark}")
        flash(f"Approved: {r.employee.name} {r.adate} {old} → {new_code}", "success")
    else:
        r.status, r.admin_id, r.admin_remark, r.decided_at = "rejected", current_user().id, remark, datetime.utcnow()
        audit("reg.rejected", f"emp={r.employee.emp_id} {r.adate} remark={remark}")
        flash("Request rejected.", "warning")
    db.session.commit()
    return redirect(url_for(".requests"))


# ------------------------------------------------------------------ employees
@bp.route("/admin/employees")
@login_required
@role_required("admin", "super_admin")
def employees():
    emps = Employee.query.filter_by(office_id=_my_office().id).order_by(Employee.name).all()
    return render_template("employees.html", emps=emps)


@bp.route("/admin/employees/new", methods=["GET", "POST"])
@bp.route("/admin/employees/<int:eid>", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def employee_form(eid=None):
    off = _my_office()
    emp = db.session.get(Employee, eid) if eid else None
    if request.method == "POST":
        vals = {k: request.form.get(k, "").strip() for k in
                ("emp_id", "name", "designation", "zone", "product", "mobile", "status")}
        doj = request.form.get("doj") or None
        gross = request.form.get("gross") or None
        # salary fields (admin-only)
        sal_fields = ("payable_days", "payable_salary", "incentive", "cash_prize",
                      "tl_incentive", "arrear", "deduction", "final_payable")
        if not vals["emp_id"] or not vals["name"]:
            flash("Employee ID and Name are required.", "danger")
            return redirect(request.url)
        if not emp:
            dup = Employee.query.filter_by(office_id=off.id, emp_id=vals["emp_id"]).first()
            if dup:
                flash(f"Employee ID {vals['emp_id']} already exists.", "danger")
                return redirect(url_for(".employees"))
            emp = Employee(office_id=off.id)
            db.session.add(emp)
        for k, v in vals.items():
            if k != "emp_id" or not emp.id or v:
                setattr(emp, k, v)
        emp.doj = datetime.strptime(doj, "%Y-%m-%d").date() if doj else None
        emp.gross = float(gross) if gross else None
        for k in sal_fields:
            v = request.form.get(k, "").strip()
            try:
                setattr(emp, k, float(v) if v else 0)
            except ValueError:
                flash(f"Salary field '{k}' must be a number.", "danger")
                return redirect(request.url)
        emp.device_enrolled = request.form.get("device_enrolled") == "on"
        audit("employee.saved", f"{emp.emp_id} {emp.name}")
        db.session.commit()
        flash("Employee saved.", "success")
        return redirect(url_for(".employees"))
    return render_template("employee_form.html", emp=emp)


# ------------------------------------------------- import employees from Excel
@bp.route("/admin/employees/import", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def employees_import():
    """Create/update Employees (+ agent logins) from the monthly manual .xlsx.

    Same column layout as the October sheet: name=2, DOJ=3, EmpID=4, mobile=6,
    product=11, zone=12, designation=13, gross=14, payable_salary=15, incentive=16,
    cash_prize=17, tl_incentive=18, arrear=19, deduction=20, final_payable=21,
    payable_days=22. Existing employees (same emp_id) are updated, not duplicated.
    """
    if request.method == "GET":
        return render_template("employees_import.html", done=None)

    off = _my_office()
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose an .xlsx file first.", "danger")
        return redirect(request.url)
    try:
        import openpyxl
        ms = openpyxl.load_workbook(BytesIO(f.read()), data_only=True)["Sheet1"]
    except Exception:
        flash("Could not read the file — it must be the manual attendance .xlsx "
              "(first sheet named Sheet1).", "danger")
        return redirect(request.url)

    from werkzeug.security import generate_password_hash
    today = date.today()
    created, updated, logins, seen = 0, 0, 0, set()
    future_doj = []
    for r in range(2, ms.max_row + 1):
        name = ms.cell(r, 2).value
        if not name or not str(name).strip():
            continue
        eid = str(ms.cell(r, 4).value or "").strip() or "UNKNOWN"
        if eid in seen:                              # duplicate ID -> suffix
            eid = eid + "-2"
        seen.add(eid)
        doj_v = ms.cell(r, 3).value
        doj = doj_v.date() if isinstance(doj_v, datetime) else None
        if doj and doj > today:
            future_doj.append(f"{eid} ({doj:%d-%b-%Y})")
        emp = Employee.query.filter_by(office_id=off.id, emp_id=eid).first()
        if not emp:
            emp = Employee(office_id=off.id, emp_id=eid)
            db.session.add(emp)
            created += 1
        else:
            updated += 1
        emp.name = str(name).strip()
        emp.designation = str(ms.cell(r, 13).value or "").strip()
        emp.zone = str(ms.cell(r, 12).value or "").strip()
        emp.product = str(ms.cell(r, 11).value or "").strip()
        emp.mobile = str(ms.cell(r, 6).value or "").strip()
        emp.doj = doj
        emp.gross = ms.cell(r, 14).value
        emp.payable_salary = ms.cell(r, 15).value
        emp.payable_days = ms.cell(r, 22).value
        emp.incentive = ms.cell(r, 16).value or 0
        emp.cash_prize = ms.cell(r, 17).value or 0
        emp.tl_incentive = ms.cell(r, 18).value or 0
        emp.arrear = ms.cell(r, 19).value or 0
        emp.deduction = ms.cell(r, 20).value or 0
        emp.final_payable = ms.cell(r, 21).value
        if not User.query.filter_by(username=eid).first():
            db.session.add(User(username=eid, role="agent", office_id=off.id,
                                employee_id=emp.id,
                                password_hash=generate_password_hash("welcome123")))
            logins += 1
    db.session.flush()
    audit("employees.imported",
          f"office={off.code} created={created} updated={updated} logins={logins}")
    db.session.commit()
    msg = (f"Import done: {created} new + {updated} updated employees, "
           f"{logins} new logins created (password welcome123).")
    if future_doj:
        msg += f" WARNING — DOJ in the future, please check: {'; '.join(future_doj)}"
    return render_template("employees_import.html", done=msg)


# ------------------------------------------------------------------ salary (admin only)
@bp.route("/admin/salary")
@login_required
@role_required("admin", "super_admin")
def salary():
    off = _my_office()
    emps = Employee.query.filter_by(office_id=off.id).order_by(Employee.name).all()
    fields = ("gross", "payable_days", "payable_salary", "incentive",
              "cash_prize", "tl_incentive", "arrear", "deduction", "final_payable")
    totals = {f: round(sum(getattr(e, f) or 0 for e in emps), 2) for f in fields}
    return render_template("salary.html", emps=emps, totals=totals, off=off)


# ------------------------------------------------------------------ attendance edit
@bp.route("/admin/attendance/<int:eid>", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def attendance_edit(eid):
    emp = db.session.get(Employee, eid)
    off = _my_office()
    if not emp or emp.office_id != off.id:
        flash("Employee not found.", "danger")
        return redirect(url_for(".employees"))
    t = date.today()
    ym = request.values.get("ym")
    if ym:
        try:
            y, m = map(int, ym.split("-"))
        except Exception:
            y, m = t.year, t.month
    else:
        y = int(request.values.get("y", t.year))
        m = int(request.values.get("m", t.month))
    nd = month_days(y, m)
    if request.method == "POST":
        changed = 0
        for d in range(1, nd + 1):
            new = request.form.get(f"d{d}", "")
            if not new:
                continue
            adate = date(y, m, d)
            att = Attendance.query.filter_by(employee_id=emp.id, adate=adate).first()
            if att is None:
                att = Attendance(employee_id=emp.id, adate=adate)
                db.session.add(att)
            if att.code != new:
                audit("attendance.edit", f"{emp.emp_id} {adate} {att.code}->{new}")
                att.code, att.source, att.adjusted = new, "manual", True
                changed += 1
        db.session.commit()
        flash(f"Attendance updated ({changed} changes).", "success")
        return redirect(url_for(".attendance_edit", eid=eid, y=y, m=m))
    atts = {a.adate.day: a for a in Attendance.query.filter_by(employee_id=emp.id)
            .filter(Attendance.adate >= date(y, m, 1), Attendance.adate <= date(y, m, nd))}
    days = [{"d": d, "att": atts.get(d)} for d in range(1, nd + 1)]
    return render_template("attendance_edit.html", emp=emp, days=days, y=y, m=m, nd=nd,
                           codes=["P", "A", "L", "H", "HD", "WO", "HO", "O", "-"])


# ------------------------------------------------------------------ holidays
@bp.route("/admin/holidays", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def holidays():
    off = _my_office()
    if request.method == "POST":
        if request.form.get("delete_id"):
            h = db.session.get(Holiday, int(request.form["delete_id"]))
            if h and h.office_id == off.id:
                audit("holiday.deleted", f"{h.hdate} {h.name}")
                db.session.delete(h)
        else:
            hd = request.form.get("hdate")
            if hd:
                h = Holiday(office_id=off.id, hdate=datetime.strptime(hd, "%Y-%m-%d").date(),
                            name=request.form.get("name", "").strip())
                db.session.merge(h)
                audit("holiday.added", f"{h.hdate} {h.name}")
        db.session.commit()
        return redirect(url_for(".holidays"))
    hols = Holiday.query.filter_by(office_id=off.id).order_by(Holiday.hdate.desc()).all()
    return render_template("holidays.html", hols=hols, off=off)


# ------------------------------------------------------------------ report
@bp.route("/admin/report", methods=["GET", "POST"])
@login_required
@role_required("admin", "super_admin")
def report():
    off = _my_office()
    if request.method == "POST":
        try:
            y, m = map(int, request.form.get("month", "").split("-"))
        except Exception:
            flash("Select the month.", "danger")
            return redirect(url_for(".report"))
        buf = build_report(off, y, m)
        audit("report.generated", f"office={off.code} {y}-{m:02d}")
        db.session.commit()
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument"
                                      ".spreadsheetml.sheet", as_attachment=True,
                         download_name=f"{off.code}_{y}-{m:02d}_Attendance_Report.xlsx")
    return render_template("report.html", off=off)
