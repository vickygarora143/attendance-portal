# -*- coding: utf-8 -*-
"""End-to-end smoke test of the portal using Flask test client."""
import io
import sys
import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import app

c = app.test_client()
fails = []


def check(name, resp, code=200):
    ok = resp.status_code == code
    print(f"  [{'OK' if ok else 'FAIL'}] {name} -> {resp.status_code} (want {code})")
    if not ok:
        fails.append(name)
    return resp


print("== auth ==")
check("login page", c.get("/login"))
r = c.post("/login", data={"username": "mohali_admin", "password": "admin123"}, follow_redirects=True)
check("admin login -> dashboard", r)

print("== admin pages ==")
for p in ["/admin", "/admin/upload", "/admin/requests", "/admin/employees",
          "/admin/holidays", "/admin/report", "/admin/attendance/1"]:
    check(p, c.get(p))

print("== monthly report download ==")
r = c.post("/admin/report", data={"month": "2026-10"})
check("report POST", r)
try:
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    print("   sheets:", wb.sheetnames)
    s2 = wb["2_FINAL"]
    print("   B4:", s2["B4"].value, "| I4:", s2["I4"].value, "| AN4:", s2["AN4"].value)
    check("report is valid xlsx", r)
except Exception as e:
    print("   FAIL report xlsx:", e)
    fails.append("report xlsx")

print("== agent flow ==")
c.get("/logout")
c.post("/login", data={"username": "GDSM015", "password": "welcome123"}, follow_redirects=True)
check("/me", c.get("/me"))
check("/me/requests", c.get("/me/requests"))
check("/me/day 2026-10-17", c.get("/me/day/2026/10/17"))
r = c.post("/me/regularize/2026/10/17",
           data={"rtype": "missed_punch", "reason": "test: punch did not register on device"},
           follow_redirects=True)
check("agent raise request", r)
c.get("/logout")

print("== admin approve ==")
c.post("/login", data={"username": "mohali_admin", "password": "admin123"}, follow_redirects=True)
check("requests page shows pending", c.get("/admin/requests"))
import models
with app.app_context():
    rr = models.RegRequest.query.filter_by(status="pending").first()
    rid = rr.id
    emp_id, adate = rr.employee_id, rr.adate
r = c.post(f"/admin/requests/{rid}/decide",
           data={"action": "approve", "set_code": "P", "remark": "test approve"},
           follow_redirects=True)
check("admin approve", r)
with app.app_context():
    a = models.Attendance.query.filter_by(employee_id=emp_id, adate=adate).first()
    print(f"   attendance {adate}: code={a.code} source={a.source} adjusted={a.adjusted}")
    assert a.code == "P" and a.source == "adjust" and a.adjusted

print("== super admin ==")
c.get("/logout")
c.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
for p in ["/super", "/super/users", "/super/audit"]:
    check(p, c.get(p))

print()
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("ALL SMOKE TESTS PASSED âœ…")
