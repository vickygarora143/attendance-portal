# -*- coding: utf-8 -*-
"""Monthly 7-sheet attendance report — same layout as the September/October Excel reports."""
import io
import calendar
from datetime import date, datetime, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from models import Employee, Attendance, DevicePunch, Holiday, RegRequest
from helpers import mmin

# ---------------------------------------------------------------- styles
F_HDR = PatternFill("solid", fgColor="1F3864")
F_TITLE = PatternFill("solid", fgColor="FFD966")
CODE_FILL = {"P": "00B050", "A": "FF0000", "L": "FF9F1C", "H": "FFC000",
             "HD": "FFC000", "WO": "A6A6A6", "HO": "2E75B6", "O": "7030A0"}
CODE_FONTC = {"P": "FFFFFF", "A": "FFFFFF", "L": "FFFFFF", "H": "222222",
              "HD": "222222", "WO": "222222", "HO": "FFFFFF", "O": "FFFFFF", "-": "BBBBBB"}
THIN = Side(style="thin", color="B0B8C4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
F_HDRF = Font(bold=True, color="FFFFFF", size=9)
F_BASE = Font(size=9)
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_COLS = list(range(9, 40))                      # I..AM (31 days)


def _style_hdr(cell):
    cell.fill = F_HDR
    cell.font = F_HDRF
    cell.border = BORDER
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _code_cell(cell, code):
    cell.value = code
    cell.border = BORDER
    cell.alignment = Alignment(horizontal="center")
    cell.font = Font(size=9, bold=True, color=CODE_FONTC.get(code, "222222"))
    if code in CODE_FILL:
        cell.fill = PatternFill("solid", fgColor=CODE_FILL[code])


def _title(ws, row, text, span):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    c = ws.cell(row, 1, text)
    c.fill = F_TITLE
    c.font = Font(bold=True, size=11)
    c.alignment = Alignment(horizontal="left", vertical="center")


def build_report(office, y, m):
    nd = calendar.monthrange(y, m)[1]
    first = date(y, m, 1)
    emps = Employee.query.filter_by(office_id=office.id).order_by(Employee.name).all()
    emp_ids = [e.id for e in emps]
    hol = {h.hdate for h in Holiday.query.filter_by(office_id=office.id)
           if h.hdate.year == y and h.hdate.month == m}

    atts, punch = {}, {}
    for a in Attendance.query.filter(Attendance.employee_id.in_(emp_ids or [0]),
                                     Attendance.adate >= first, Attendance.adate <= date(y, m, nd)):
        atts.setdefault(a.employee_id, {})[a.adate.day] = a
    for p in DevicePunch.query.filter(DevicePunch.employee_id.in_(emp_ids or [0]),
                                      DevicePunch.pdate >= first, DevicePunch.pdate <= date(y, m, nd)):
        punch.setdefault(p.employee_id, {})[p.pdate.day] = p

    def raw_code(eid, d):
        p = punch.get(eid, {}).get(d)
        if p is None:
            return "-"
        st, iv = p.status, p.in_time
        if st == "P":
            t = mmin(iv)
            if t is not None and office.late_after < t < office.hd_from:
                return "L"
            if t is not None and office.hd_from <= t < office.suspect_from:
                return "H"
            return "P"
        if st == "WOP":
            return "O"
        return "A" if st == "A" else ("WO" if st == "WO" else "-")

    def notes_for(eid):
        ns, cnt = [], 0
        for d in range(1, nd + 1):
            p = punch.get(eid, {}).get(d)
            if p is None:
                continue
            t = mmin(p.in_time)
            if p.status == "P" and t is not None and t >= office.suspect_from:
                ns.append(f"SUSPECT punch d{d}({p.in_time})")
            if p.status in ("P", "WOP") and p.in_time and not p.out_time:
                cnt += 1
            if p.status == "A" and (p.in_time or (p.total_hrs and p.total_hrs != "00:00")):
                ns.append(f"stray punch on device-A d{d}({p.in_time})")
        if cnt:
            ns.insert(0, f"No OUT punch ×{cnt}")
        return " | ".join(ns), cnt

    wb = openpyxl.Workbook()
    rd = wb.active
    rd.title = "0_README"
    s1 = wb.create_sheet("1_BIOMETRIC")
    s2 = wb.create_sheet("2_FINAL")
    s3 = wb.create_sheet("3_DISCREPANCY")
    s4 = wb.create_sheet("4_DAYWISE")
    s5 = wb.create_sheet("5_LATE_DETAIL")
    s6 = wb.create_sheet("6_EXCEPTIONS")

    # ------------------------------------------------------------- README
    rd["A1"] = f"{office.name.upper()} – {calendar.month_name[m].upper()} {y} – ATTENDANCE REPORT (Portal generated)"
    rd["A1"].font = Font(bold=True, size=13)
    rd["A3"] = "PARAMETERS"
    rd["A3"].font = Font(bold=True)
    for r, (k, v, note) in enumerate([
        ("Month start", datetime(y, m, 1), "All date columns derive from this cell"),
        ("Days in month", nd, ""),
        ("Late after", f"{office.late_after//60:02d}:{office.late_after%60:02d}", "First IN after this = L"),
        ("Half-day from", f"{office.hd_from//60:02d}:{office.hd_from%60:02d}", f"First IN {office.hd_from//60:02d}:{office.hd_from%60:02d}–{office.suspect_from//60:02d}:{office.suspect_from%60:02d} = H"),
        ("Late waiver", office.waiver, f"First {office.waiver} lates per employee = Present"),
        ("Deduction per late beyond waiver", office.late_fraction, "days"),
        ("Holidays this month", ", ".join(f"{d.strftime('%d-%b')} ({h})"
                                          for d, h in [(x.hdate, x.name)
                                                       for x in Holiday.query.filter_by(office_id=office.id)
                                                       if x.hdate.year == y and x.hdate.month == m]) or "none", ""),
    ], start=5):
        rd.cell(r, 1, k).font = Font(bold=True, size=10)
        rd.cell(r, 2, v)
        rd.cell(r, 3, note).font = Font(size=9, italic=True, color="666666")
    wb.defined_names.add(DefinedName("MonthStart", attr_text="'0_README'!$B$5"))
    wb.defined_names.add(DefinedName("DaysInMonth", attr_text="'0_README'!$B$6"))
    wb.defined_names.add(DefinedName("LateWaiver", attr_text="'0_README'!$B$9"))
    wb.defined_names.add(DefinedName("LateFraction", attr_text="'0_README'!$B$10"))
    for col, w in (("A", 34), ("B", 16), ("C", 60)):
        rd.column_dimensions[col].width = w

    n_reg = RegRequest.query.filter_by(status="approved").join(Employee) \
        .filter(Employee.office_id == office.id).count()
    rd["A13"] = (f"Generated from the Attendance Portal. Adjustments approved this month via "
                 f"regularization: {n_reg}. '1_BIOMETRIC' = raw device view (late/half derived "
                 f"from punch times, WOP shown as O). '2_FINAL' = final codes after holiday "
                 f"alignment, comp-off and approved regularizations. Discrepancies and "
                 f"exceptions listed in sheets 3 & 6.")
    rd["A13"].alignment = Alignment(wrap_text=True, vertical="top")
    rd.merge_cells("A13:C18")

    # ------------------------------------------------------- sheets 1 & 2
    for ws, mode in ((s1, "raw"), (s2, "final")):
        _title(ws, 1, f"{office.name.upper()} – {calendar.month_name[m]} {y} – "
                      f"{'BIOMETRIC (raw device)' if mode == 'raw' else 'FINAL ATTENDANCE'}", 52)
        for i, c in enumerate(DAY_COLS):
            d = first + timedelta(days=i)
            h = ws.cell(2, c, WD[d.weekday()]); _style_hdr(h)
            h2 = ws.cell(3, c, d.day); _style_hdr(h2)
            ws.column_dimensions[get_column_letter(c)].width = 4.6
        heads = ["Sr", "Name", "Emp ID", "Zone", "Designation", "Mobile", "", ""]
        for i, htxt in enumerate(heads, start=1):
            if htxt:
                ws.cell(3, i, htxt); _style_hdr(ws.cell(3, i))
        sum_heads = ["Present", "Absent", "Half Day", "Late", "PAID OFF", "TOTAL ABSENT",
                     "FINAL PRESENT", "ADJUST", "FINAL", "REMARKS"]
        for i, htxt in enumerate(sum_heads, start=40):
            ws.cell(3, i, htxt); _style_hdr(ws.cell(3, i))
        ws.column_dimensions["B"].width = 24
        ws.column_dimensions["C"].width = 10
        ws.freeze_panes = "D4"
    # fix: sheet-1&2 header columns overlap days start col9; name cols A..H
    for ws in (s1, s2):
        for c in range(1, 9):
            _style_hdr(ws.cell(3, c))
        ws.cell(3, 9, 1)
        ws.cell(2, 9, WD[first.weekday()])

    r = 4
    for e in emps:
        for ws, mode in ((s1, "raw"), (s2, "final")):
            ws.cell(r, 1, r - 3).font = F_BASE
            ws.cell(r, 2, e.name).font = F_BASE
            ws.cell(r, 3, e.emp_id).font = F_BASE
            ws.cell(r, 4, e.zone or "").font = F_BASE
            ws.cell(r, 5, e.designation or "").font = F_BASE
            ws.cell(r, 6, e.mobile or "").font = F_BASE
            for i, c in enumerate(DAY_COLS):
                day = i + 1
                if mode == "raw":
                    _code_cell(ws.cell(r, c), raw_code(e.id, day))
                else:
                    a = atts.get(e.id, {}).get(day)
                    _code_cell(ws.cell(r, c), a.code if a else "-")
            ws.cell(r, 40, f'=COUNTIF(I{r}:AM{r},"P")+MIN(AQ{r},LateWaiver)')
            ws.cell(r, 41, f'=COUNTIF(I{r}:AM{r},"A")')
            ws.cell(r, 42, f'=COUNTIF(I{r}:AM{r},"H")+COUNTIF(I{r}:AM{r},"HD")')
            ws.cell(r, 43, f'=COUNTIF(I{r}:AM{r},"L")')
            ws.cell(r, 44, f'=COUNTIF(I{r}:AM{r},"O")+COUNTIF(I{r}:AM{r},"HO")')
            ws.cell(r, 45, f'=AO{r}+AP{r}/2+MAX(0,AQ{r}-LateWaiver)*LateFraction')
            ws.cell(r, 46, f'=DaysInMonth-COUNTIF(I{r}:AM{r},"-")-AS{r}')
            ws.cell(r, 47, 0)
            ws.cell(r, 48, f'=AT{r}+N(AU{r})')
            for cc in range(40, 49):
                ws.cell(r, cc).font = F_BASE
                ws.cell(r, cc).border = BORDER
        ns, _ = notes_for(e.id)
        regs = [f"{x.adate.day}-{x.current_code}→{x.requested_code}" for x in
                RegRequest.query.filter_by(employee_id=e.id, status="approved")
                if x.adate.year == y and x.adate.month == m]
        rem = ns + (" | REG: " + ",".join(regs) if regs else "")
        s2.cell(r, 49, rem).font = Font(size=8)
        r += 1
    last = r - 1

    # totals rows on both sheets
    for ws in (s1, s2):
        ws.cell(last + 1, 2, "TOTAL (all employees)").font = Font(bold=True)
        ws.cell(last + 2, 2, "Daily Absent").font = Font(bold=True)
        for c in DAY_COLS:
            L = get_column_letter(c)
            ws.cell(last + 1, c, f'=COUNTIF({L}4:{L}{last},"P")+COUNTIF({L}4:{L}{last},"L")'
                                 f'+COUNTIF({L}4:{L}{last},"H")+COUNTIF({L}4:{L}{last},"HD")'
                                 f'+COUNTIF({L}4:{L}{last},"O")+COUNTIF({L}4:{L}{last},"HO")')
            ws.cell(last + 2, c, f'=COUNTIF({L}4:{L}{last},"A")')
            for rr in (last + 1, last + 2):
                ws.cell(rr, c).font = Font(bold=True, size=9)
                ws.cell(rr, c).border = BORDER

    from report_sheets import add_sheets3to6
    add_sheets3to6(wb, s3, s4, s5, s6, office, y, m, emps, atts, punch, raw_code, notes_for, last)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
