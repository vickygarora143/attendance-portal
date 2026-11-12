# -*- coding: utf-8 -*-
"""Report sheets 3-6 (discrepancy, daywise, late detail, exceptions)."""
import calendar
from datetime import date, datetime, timedelta
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from report_builder import (CODE_FILL, CODE_FONTC, F_HDR, F_HDRF, F_BASE, F_TITLE,
                            BORDER, _style_hdr, _title, _code_cell, DAY_COLS, WD)
from helpers import mmin


def _hdr_row(ws, row, labels):
    for i, t in enumerate(labels, start=1):
        ws.cell(row, i, t)
        _style_hdr(ws.cell(row, i))


def _drow(ws, row, vals, fonts=None):
    for i, v in enumerate(vals, start=1):
        c = ws.cell(row, i, v)
        c.font = F_BASE
        c.border = BORDER


def add_sheets3to6(wb, s3, s4, s5, s6, office, y, m, emps, atts, punch, raw_code,
                   notes_for, last):
    nd = calendar.monthrange(y, m)[1]
    first = date(y, m, 1)

    # ---------------------------------------------------- 3_DISCREPANCY
    _title(s3, 1, f"{office.name.upper()} – {calendar.month_name[m]} {y} – "
                  "DISCREPANCY (device vs final differences)", 12)
    _hdr_row(s3, 2, ["Sr", "Emp ID", "Name", "Designation", "Zone", "Category",
                     "Diff days", "Dates (raw→final)", "Gross ₹", "Day value ₹",
                     "₹ at risk", "Action"])
    s3.column_dimensions["H"].width = 40
    s3.column_dimensions["L"].width = 34
    r = 3
    for e in emps:
        diffs = []
        for d in range(1, nd + 1):
            rc, fc = raw_code(e.id, d), (atts.get(e.id, {}).get(d).code
                                         if atts.get(e.id, {}).get(d) else "-")
            if rc != fc:
                diffs.append((d, f"{d}:{rc}→{fc}"))
        cat = ("NOT ON DEVICE" if not e.device_enrolled else
               ("DIFFERS" if diffs else "OK"))
        dv = (e.gross or 0) / nd if e.gross else 0
        act = ""
        if cat == "DIFFERS":
            act = "Verify with HR: holiday/comp-off alignment or approved regularization"
        elif cat == "NOT ON DEVICE":
            act = "Enrol thumb on device"
        _drow(s3, r, [r - 2, e.emp_id, e.name, e.designation or "", e.zone or "", cat,
                      len(diffs), ", ".join(x[1] for x in diffs), e.gross or 0,
                      round(dv, 2), round(len(diffs) * dv, 2), act])
        r += 1

    # ---------------------------------------------------- 4_DAYWISE
    _title(s4, 1, f"DAY-WISE {calendar.month_name[m]} {y}: raw device / final "
                  "(green P, red A, orange late, amber half, grey WO/HO, purple O)", 34)
    s4.cell(2, 1, "Emp ID").font = Font(bold=True, size=9)
    s4.cell(2, 2, "Name").font = Font(bold=True, size=9)
    s4.column_dimensions["A"].width = 10
    s4.column_dimensions["B"].width = 24
    for i, c in enumerate(DAY_COLS, start=3):
        d = first + timedelta(days=i - 3)
        s4.cell(2, c, f"{d.day}\n{WD[d.weekday()]}")
        _style_hdr(s4.cell(2, c))
        s4.column_dimensions[get_column_letter(c)].width = 5.6
    s4.freeze_panes = "C3"
    r = 3
    for e in emps:
        s4.cell(r, 1, e.emp_id).font = F_BASE
        s4.cell(r, 2, e.name).font = F_BASE
        for i, c in enumerate(DAY_COLS, start=3):
            d = first + timedelta(days=i - 3)
            rc, fc = raw_code(e.id, d), (atts.get(e.id, {}).get(d).code
                                         if atts.get(e.id, {}).get(d) else "-")
            cell = s4.cell(r, c, f"{rc}/{fc}")
            cell.font = Font(size=8, bold=True, color=CODE_FONTC.get(fc, "222222"))
            cell.border = BORDER
            cell.alignment = Alignment(horizontal="center")
            if fc in CODE_FILL:
                cell.fill = PatternFill("solid", fgColor=CODE_FILL[fc])
            elif rc != "-" and fc == "-":
                cell.fill = PatternFill("solid", fgColor="FFC7CE")
        r += 1

    # ---------------------------------------------------- 5_LATE_DETAIL
    _title(s5, 1, f"LATE ARRIVALS {calendar.month_name[m]} {y} – first punch after "
                  f"{office.late_after//60:02d}:{office.late_after%60:02d}. "
                  f"First {office.waiver} per employee = Present (waived); "
                  f"beyond = 1/6 day deduction", 9)
    _hdr_row(s5, 2, ["Emp ID", "Name", "Date", "Day", "IN", "Minutes late",
                     "Late #", "Action", ""])
    s5.column_dimensions["B"].width = 24
    r = 3
    cnt = {}
    for e in emps:
        lad = sorted(d for d in range(1, nd + 1)
                     if atts.get(e.id, {}).get(d) and atts[e.id][d].code == "L")
        for d in lad:
            a = atts[e.id][d]
            p = punch.get(e.id, {}).get(d)
            t = mmin(a.in_time or (p.in_time if p else ""))
            cnt[e.id] = cnt.get(e.id, 0) + 1
            n = cnt[e.id]
            _drow(s5, r, [e.emp_id, e.name, datetime(y, m, d).strftime("%d-%b-%Y"),
                          WD[date(y, m, d).weekday()], a.in_time or "",
                          (t - office.late_after) if t else "", n,
                          "Waived – Present" if n <= office.waiver else "DEDUCT 1/6 day"])
            r += 1

    # ---------------------------------------------------- 6_EXCEPTIONS
    _title(s6, 1, f"EXCEPTIONS & NOTES – {calendar.month_name[m]} {y}", 8)
    r = 3

    def sec(t):
        nonlocal r
        s6.cell(r, 1, t).font = Font(bold=True, size=10, color="1F3864")
        r += 1

    def hdr(labels):
        nonlocal r
        _hdr_row(s6, r, labels)
        r += 1

    def row(vals):
        nonlocal r
        _drow(s6, r, vals)
        r += 1

    sec("B. EMPLOYEES NOT ENROLLED ON DEVICE")
    hdr(["Emp ID", "Name", "Designation", "Zone", "Note"])
    for e in emps:
        if not e.device_enrolled:
            row([e.emp_id, e.name, e.designation or "", e.zone or "",
                 "Not on device – enrol thumb (attendance manual edit se chalta hai)"])
    r += 1
    sec("D. SUSPECT FIRST PUNCH (after "
        f"{office.suspect_from//60:02d}:{office.suspect_from%60:02d})")
    hdr(["Emp ID", "Name", "Date", "IN", "Note"])
    for e in emps:
        for d in range(1, nd + 1):
            p = punch.get(e.id, {}).get(d)
            t = mmin(p.in_time) if p and p.status == "P" else None
            if t is not None and t >= office.suspect_from:
                row([e.emp_id, e.name, datetime(y, m, d).strftime("%d-%b"), p.in_time,
                     "First punch after cutoff – probably OUT recorded as IN. Shown as P."])
    r += 1
    sec("D2. STRAY PUNCH ON DEVICE-A DAY")
    hdr(["Emp ID", "Name", "Date", "Punch", "Note"])
    for e in emps:
        for d in range(1, nd + 1):
            p = punch.get(e.id, {}).get(d)
            if p and p.status == "A" and (p.in_time or (p.total_hrs and p.total_hrs != "00:00")):
                row([e.emp_id, e.name, datetime(y, m, d).strftime("%d-%b"), p.in_time,
                     "Device A with one stray punch – probably missing IN/OUT. Regularize."])
    r += 1
    sec("E. PRESENT DAYS WITHOUT OUT PUNCH")
    hdr(["Emp ID", "Name", "Days", "Dates"])
    for e in emps:
        no = [d for d in range(1, nd + 1)
              if punch.get(e.id, {}).get(d) and punch[e.id][d].status in ("P", "WOP")
              and punch[e.id][d].in_time and not punch[e.id][d].out_time]
        if no:
            row([e.emp_id, e.name, len(no), ", ".join(map(str, no))])
    r += 1
    sec("F. ROSTER NOTES")
    hdr(["Date", "Observation", "Treatment"])
    from models import Holiday
    for h in Holiday.query.filter_by(office_id=office.id):
        if h.hdate.year == y and h.hdate.month == m:
            row([h.hdate.strftime("%d-%b"), f"Holiday: {h.name}",
                 "Device A aligned to HO (paid off). Not a discrepancy."])
    wop = [(e, d) for e in emps for d in range(1, nd + 1)
           if punch.get(e.id, {}).get(d) and punch[e.id][d].status == "WOP"]
    if wop:
        names = sorted({e.name for e, _ in wop})
        row([", ".join({f"{d:02d}" for _, d in wop}), f"Worked on weekly-off: {', '.join(names)}",
             "Counted O (comp-off present). Not a discrepancy."])
    r += 1
    sec("G. NO DEVICE DATA THIS MONTH (dormant)")
    hdr(["Emp ID", "Name", "Note"])
    for e in emps:
        if e.device_enrolled and not punch.get(e.id):
            row([e.emp_id, e.name, "Zero punches this month – check resignation/leave"])
