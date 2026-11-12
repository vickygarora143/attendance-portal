# -*- coding: utf-8 -*-
"""Import November 2026 biometric data (Monthly Status Report.xls) into the DB.

Usage:
  python import_nov.py            -> local SQLite
  python import_nov.py cloud      -> Supabase (DATABASE_URL env)
"""
import json
import sys
from datetime import date

if len(sys.argv) > 1 and sys.argv[1] == "cloud":
    import os
    # password stays in the environment, never in the repo
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://postgres.isboqwumkgdtkyeulctw:"
        + os.environ.get("DB_PASSWORD", "") +
        "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import app
from models import db, Office, Employee, User, Upload, DevicePunch, Attendance
from parser import parse_bio, derive_code

BIO = r"C:\Users\GOODWILL\Downloads\Monthly Status Report.xls"
MONTH = (2026, 11)

def main():
    with app.app_context():
        off = Office.query.order_by(Office.code).first()
        admin = User.query.filter_by(role="super_admin").first()

        # guard: don't import twice
        already = Upload.query.filter_by(month=f"{MONTH[0]}-{MONTH[1]:02d}",
                                         status="imported").first()
        if already:
            print("ABORT: November upload already imported (id", already.id, ")")
            return

        with open(BIO, "rb") as f:
            rows = parse_bio(f)
        matched = {c: v for c, v in rows.items()
                   if Employee.query.filter_by(office_id=off.id, emp_id=c).first()}
        unmatched = [c for c in rows if c not in matched]
        print(f"parsed {len(rows)} device blocks | matched {len(matched)} | "
              f"unmatched {len(unmatched)} (skipped)")

        payload = {"month": f"{MONTH[0]}-{MONTH[1]:02d}",
                   "rows": {code: {"name": v["name"],
                                   "days": {str(d): list(rec) for d, rec in v["days"].items()}}
                            for code, v in rows.items()}}
        up = Upload(office_id=off.id, admin_id=admin.id,
                    filename="Monthly Status Report.xls",
                    month=f"{MONTH[0]}-{MONTH[1]:02d}",
                    status="imported", payload=json.dumps(payload),
                    n_rows=len(rows))
        db.session.add(up)
        db.session.flush()

        nd = 0
        codes = {}
        for code, data in matched.items():
            e = Employee.query.filter_by(office_id=off.id, emp_id=code).first()
            for dstr, (st, iv, ov, tv) in data["days"].items():
                d = date(MONTH[0], MONTH[1], int(dstr))
                final = derive_code(st, iv, False, off)   # no holidays Nov 1-12
                codes[final] = codes.get(final, 0) + 1
                db.session.add(DevicePunch(upload_id=up.id, employee_id=e.id, pdate=d,
                                           status=st, in_time=iv, out_time=ov, total_hrs=tv))
                db.session.add(Attendance(employee_id=e.id, adate=d, code=final,
                                          in_time=iv, out_time=ov, total_hrs=tv,
                                          source="device"))
                nd += 1
        db.session.commit()
        print(f"IMPORTED: {len(matched)} employees, {nd} day-records")
        print("final codes:", codes)
        print("upload id:", up.id)

main()
