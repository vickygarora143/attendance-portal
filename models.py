# -*- coding: utf-8 -*-
"""Database models for the Attendance Portal."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

CODES = ["P", "A", "L", "H", "HD", "WO", "HO", "O", "-"]


class Office(db.Model):
    __tablename__ = "offices"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    late_after = db.Column(db.Integer, default=615)      # minutes: 10:15
    hd_from = db.Column(db.Integer, default=810)         # minutes: 13:30
    suspect_from = db.Column(db.Integer, default=960)    # minutes: 16:00
    waiver = db.Column(db.Integer, default=4)            # first N lates = Present
    late_fraction = db.Column(db.Float, default=1.0 / 6) # deduction per late beyond waiver


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # super_admin / admin / agent
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"))
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    active = db.Column(db.Boolean, default=True)
    office = db.relationship("Office")
    employee = db.relationship("Employee", foreign_keys=[employee_id])


class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"), nullable=False)
    emp_id = db.Column(db.String(32), nullable=False)          # device ID e.g. GDSM015
    name = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(60))
    zone = db.Column(db.String(60))
    product = db.Column(db.String(60))
    mobile = db.Column(db.String(20))
    doj = db.Column(db.Date)
    gross = db.Column(db.Float)
    device_enrolled = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default="ACTIVE")
    # salary fields (admin-only, imported from the salary sheet)
    payable_salary = db.Column(db.Float)        # Payable Salary (N/31*V)
    payable_days = db.Column(db.Float)          # Payable Days (V)
    incentive = db.Column(db.Float, default=0)
    cash_prize = db.Column(db.Float, default=0)
    tl_incentive = db.Column(db.Float, default=0)
    arrear = db.Column(db.Float, default=0)
    deduction = db.Column(db.Float, default=0)
    final_payable = db.Column(db.Float)         # Final Payable Salary (U)
    office = db.relationship("Office")
    __table_args__ = (db.UniqueConstraint("office_id", "emp_id", name="uq_office_empid"),)


class Holiday(db.Model):
    __tablename__ = "holidays"
    id = db.Column(db.Integer, primary_key=True)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"), nullable=False)
    hdate = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(100))
    __table_args__ = (db.UniqueConstraint("office_id", "hdate", name="uq_office_hdate"),)


class Upload(db.Model):
    __tablename__ = "uploads"
    id = db.Column(db.Integer, primary_key=True)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    filename = db.Column(db.String(200))
    month = db.Column(db.String(7), nullable=False)            # "2026-10"
    status = db.Column(db.String(20), default="preview")       # preview / imported / discarded
    payload = db.Column(db.Text)                               # parsed JSON
    n_rows = db.Column(db.Integer, default=0)
    n_errors = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DevicePunch(db.Model):
    __tablename__ = "device_punches"
    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.Integer, db.ForeignKey("uploads.id"))
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    pdate = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(8))    # raw device status: P / A / WO / WOP
    in_time = db.Column(db.String(8))
    out_time = db.Column(db.String(8))
    total_hrs = db.Column(db.String(8))


class Attendance(db.Model):
    """FINAL daily code — source of truth for views and the monthly report."""
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    adate = db.Column(db.Date, nullable=False)
    code = db.Column(db.String(4), nullable=False)             # P/A/L/H/HD/WO/HO/O/-
    in_time = db.Column(db.String(8))
    out_time = db.Column(db.String(8))
    total_hrs = db.Column(db.String(8))
    source = db.Column(db.String(10), default="device")        # device / manual / adjust
    adjusted = db.Column(db.Boolean, default=False)            # changed after device import
    __table_args__ = (db.UniqueConstraint("employee_id", "adate", name="uq_emp_date"),)


class RegRequest(db.Model):
    __tablename__ = "reg_requests"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    adate = db.Column(db.Date, nullable=False)
    rtype = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.Text)
    requested_code = db.Column(db.String(4))                   # suggested by agent/admin mapping
    current_code = db.Column(db.String(4))                     # code at request time
    status = db.Column(db.String(10), default="pending")       # pending / approved / rejected
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    admin_remark = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime)
    employee = db.relationship("Employee")


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(64))
    action = db.Column(db.String(60))
    detail = db.Column(db.Text)
