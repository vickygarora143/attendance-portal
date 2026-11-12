# -*- coding: utf-8 -*-
"""Seed the portal with 100% REAL data:
   - Mohali office + users (super admin, admin, agent login for EVERY device/emp ID)
   - Employees from Oct Manual Attednace.xlsx (with designation, DOJ, gross)
   - Pure biometric October data from October Biomatric Report.xls
   - Device employees not in the salary sheet are also added (real device IDs)
   - Holiday 02-Oct-2026 (Gandhi Jayanti)
Run:  python seed.py
"""
import json
import sys
from datetime import date, datetime
import openpyxl

from app import app
from models import db, Office, User, Employee, Holiday, Upload, DevicePunch, Attendance
from parser import parse_bio, derive_code
from werkzeug.security import generate_password_hash

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MAN = r"C:\Users\GOODWILL\Desktop\Oct Manual Attednace.xlsx"
BIO = r"C:\Users\GOODWILL\Desktop\October Biomatric Report.xls"


def main():
    with app.app_context():
        db.drop_all()
        db.create_all()

        off = Office(code="MOHALI", name="Mohali Office")
        db.session.add(off)
        db.session.flush()

        db.session.add(User(username="admin", role="super_admin",
                            password_hash=generate_password_hash("admin123")))
        db.session.add(User(username="mohali_admin", role="admin", office_id=off.id,
                            password_hash=generate_password_hash("admin123")))
        db.session.flush()

        # ---- 1. parse biometric first (source of truth for device IDs)
        with open(BIO, "rb") as f:
            rows = parse_bio(f)

        # ---- 2. employees from the manual (salary) sheet
        mw = openpyxl.load_workbook(MAN, data_only=True)
        ms = mw["Sheet1"]
        seen = set()
        n_emp = 0
        manual_emp_ids = set()
        for r in range(2, ms.max_row + 1):
            name = ms.cell(r, 2).value
            if not name or not str(name).strip():
                continue
            eid = str(ms.cell(r, 4).value or "").strip() or "UNKNOWN"
            if eid in seen:                     # duplicate ID (e.g. FIELD) -> suffix
                eid = eid + "-2"
            seen.add(eid)
            manual_emp_ids.add(eid)
            doj = ms.cell(r, 3).value
            db.session.add(Employee(
                office_id=off.id, emp_id=eid, name=str(name).strip(),
                designation=str(ms.cell(r, 13).value or "").strip(),
                zone=str(ms.cell(r, 12).value or "").strip(),
                product=str(ms.cell(r, 11).value or "").strip(),
                mobile=str(ms.cell(r, 6).value or "").strip(),
                doj=doj.date() if isinstance(doj, datetime) else None,
                gross=ms.cell(r, 14).value,
                payable_salary=ms.cell(r, 15).value,
                payable_days=ms.cell(r, 22).value,
                incentive=ms.cell(r, 16).value or 0,
                cash_prize=ms.cell(r, 17).value or 0,
                tl_incentive=ms.cell(r, 18).value or 0,
                arrear=ms.cell(r, 19).value or 0,
                deduction=ms.cell(r, 20).value or 0,
                final_payable=ms.cell(r, 21).value))
            n_emp += 1
        db.session.flush()

        # ---- 3. Device-only / dormant IDs are NOT employees here (not in the
        # system per user request). Their device data, if any, will simply show
        # as "unknown device ID" in the upload preview and be skipped.

        # ---- 4. agent login for the 48 salary employees (username = Emp ID)
        n_users = 0
        for e in Employee.query.filter_by(office_id=off.id).all():
            if not User.query.filter_by(username=e.emp_id).first():
                db.session.add(User(username=e.emp_id, role="agent", office_id=off.id,
                                    employee_id=e.id,
                                    password_hash=generate_password_hash("welcome123")))
                n_users += 1

        # ---- 5. holiday
        db.session.add(Holiday(office_id=off.id, hdate=date(2026, 10, 2),
                               name="Gandhi Jayanti"))

        # ---- 6. PURE biometric import (October)
        payload = {"month": "2026-10",
                   "rows": {code: {"name": v["name"],
                                   "days": {str(d): list(rec) for d, rec in v["days"].items()}}
                            for code, v in rows.items()}}
        up = Upload(office_id=off.id, admin_id=1, filename="October Biomatric Report.xls",
                    month="2026-10", status="imported", payload=json.dumps(payload),
                    n_rows=len(rows))
        db.session.add(up)
        db.session.flush()

        hol = {date(2026, 10, 2)}
        n_days = 0
        active_ids = set()
        for code, data in rows.items():
            e = Employee.query.filter_by(office_id=off.id, emp_id=code).first()
            if not e:
                continue
            active_ids.add(e.id)
            for dstr, rec in data["days"].items():
                d = date(2026, 10, int(dstr))
                st, iv, ov, tv = rec
                db.session.add(DevicePunch(upload_id=up.id, employee_id=e.id, pdate=d,
                                           status=st, in_time=iv, out_time=ov, total_hrs=tv))
                db.session.add(Attendance(
                    employee_id=e.id, adate=d,
                    code=derive_code(st, iv, d in hol, off),
                    in_time=iv, out_time=ov, total_hrs=tv, source="device"))
                n_days += 1

        # ---- 7. employees without device data -> not enrolled
        for e in Employee.query.filter_by(office_id=off.id).all():
            if e.id not in active_ids:
                e.device_enrolled = False

        db.session.commit()
        print(f"Seeded (PURE biometric, no mock): {n_emp} active employees "
              f"(all with portal logins).")
        print(f"October day-records: {n_days} (device IDs not in the system are skipped)")
        print("Logins:")
        print("  super admin : admin / admin123")
        print("  admin       : mohali_admin / admin123")
        print("  agent       : <EMP ID> / welcome123  (e.g. GDSM015 / welcome123)")


if __name__ == "__main__":
    main()
